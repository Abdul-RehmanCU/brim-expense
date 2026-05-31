from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic
from pydantic import BaseModel, Field

from app.config import get_settings
from app.schemas.insights import InsightPageContext, InsightResultRow
from app.services.ai_service import parse_strict_json

MAX_SQL_ROWS = 200
CANONICAL_SQL_ALIASES = {
    "label": ("label", "name", "title"),
    "sum_amount_cad": ("sum_amount_cad", "total_spend", "total_amount", "spend_total", "amount_total", "total_cad"),
    "amount_cad": ("amount_cad", "spend_amount", "amount", "value"),
    "avg_amount_cad": ("avg_amount_cad", "average_spend", "avg_spend", "average_amount", "avg_amount"),
    "transaction_count": ("transaction_count", "count", "txn_count", "transactions", "total_transactions"),
    "month": ("month", "period", "month_label"),
    "department": ("department", "department_name", "team", "team_name"),
    "merchant": ("merchant", "merchant_name"),
    "employee": ("employee", "employee_name", "full_name"),
    "business_category": ("business_category", "category", "normalized_category"),
}
FORBIDDEN_SQL_PATTERNS = (
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\balter\b",
    r"\bdrop\b",
    r"\btruncate\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bcreate\b",
    r"\bcomment\b",
    r"\bcopy\b",
    r"\bcall\b",
    r"\bdo\b",
    r"\brefresh\b",
    r"\bmerge\b",
    r"\bexecute\b",
    r"\bprepare\b",
    r"\bdeallocate\b",
    r"\bset\s+role\b",
    r"\bset\s+session\b",
    r"\breset\b",
    r"\bbegin\b",
    r"\bcommit\b",
    r"\brollback\b",
    r"\block\b",
    r"\bvacuum\b",
    r"\banalyze\b",
    r"\bpg_sleep\b",
    r"--",
    r"/\*",
)


class SqlGuardDecision(BaseModel):
    approved: bool
    reason: str
    normalized_sql: str | None = None
    chart_hint: str | None = None
    warnings: list[str] = Field(default_factory=list)


def validate_and_prepare_sql(
    *,
    question: str,
    sql_statement: str,
    page_context: InsightPageContext | None,
    ask_context: dict[str, Any] | None,
    limit: int,
) -> tuple[str, dict[str, Any]]:
    decision = review_sql_with_anthropic(
        question=question,
        sql_statement=sql_statement,
        page_context=page_context,
        ask_context=ask_context,
        limit=limit,
    )

    candidate_sql = (decision.normalized_sql or sql_statement).strip()
    errors = deterministic_sql_guard_errors(candidate_sql)
    if not decision.approved:
        raise ValueError(f"SQL guard rejected the generated query: {decision.reason}")
    if errors:
        raise ValueError("SQL guard rejected the generated query: " + "; ".join(errors))

    prepared_sql = apply_sql_limit(candidate_sql, limit)
    return prepared_sql, {
        "sql_validation": decision.model_dump(mode="json"),
        "generated_sql": candidate_sql,
        "executed_sql": prepared_sql,
    }


def execute_read_only_sql(sql_statement: str, limit: int) -> tuple[list[InsightResultRow], dict[str, Any]]:
    settings = get_settings()
    if not settings.supabase_db_url:
        raise RuntimeError("SUPABASE_DB_URL is required for validated SQL execution.")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as error:
        raise RuntimeError("psycopg is required for validated SQL execution.") from error

    effective_limit = max(1, min(limit, MAX_SQL_ROWS))
    with psycopg.connect(settings.supabase_db_url) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("BEGIN READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '8000ms'")
            cursor.execute("SET LOCAL idle_in_transaction_session_timeout = '8000ms'")
            cursor.execute(sql_statement)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description or []]
            connection.rollback()

    result_rows = [row_to_insight_result(row, columns, index) for index, row in enumerate(rows)]
    normalized_columns = [normalize_sql_result_key(column) for column in columns]
    return result_rows, {
        "record_count": len(result_rows),
        "returned_count": len(result_rows),
        "sql_columns": normalized_columns,
        "sql_limit": effective_limit,
    }


def review_sql_with_anthropic(
    *,
    question: str,
    sql_statement: str,
    page_context: InsightPageContext | None,
    ask_context: dict[str, Any] | None,
    limit: int,
) -> SqlGuardDecision:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for SQL validation.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_sql_guard_model,
        max_tokens=800,
        temperature=0,
        system=(
            "You are a strict SQL safety validator for an expense analytics app. "
            "You review candidate PostgreSQL queries and decide whether they are safe to run read-only. "
            "Return strict JSON only. Do not use markdown. Approve only a single read-only SELECT or WITH query. "
            "Reject anything that mutates data, changes session state, uses multiple statements, comments, privileged commands, "
            "or attempts to escape the allowed schema."
        ),
        messages=[
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "candidate_sql": sql_statement,
                        "page_context": page_context.model_dump(mode="json") if page_context else None,
                        "ask_context": ask_context,
                        "row_limit": max(1, min(limit, MAX_SQL_ROWS)),
                        "allowed_tables": allowed_sql_schema_context(),
                        "required_output": {
                            "approved": True,
                            "reason": "Short explanation",
                            "normalized_sql": "single read-only SQL statement",
                            "chart_hint": "bar|line|table|metric|null",
                            "warnings": [],
                        },
                    },
                    ensure_ascii=True,
                ),
            }
        ],
    )
    text = "".join(
        block.text if hasattr(block, "text") else str(getattr(block, "content", ""))
        for block in response.content
    )
    return SqlGuardDecision(**parse_strict_json(text))


def deterministic_sql_guard_errors(sql_statement: str) -> list[str]:
    sql = normalize_sql(sql_statement)
    errors: list[str] = []
    if not sql:
        return ["SQL statement is empty."]
    if ";" in sql:
        errors.append("SQL must be a single statement.")
    if not re.match(r"^(select|with)\b", sql, flags=re.IGNORECASE):
        errors.append("SQL must begin with SELECT or WITH.")
    for pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, sql, flags=re.IGNORECASE):
            errors.append(f"SQL contains a forbidden pattern: {pattern}.")
    return errors


def apply_sql_limit(sql_statement: str, limit: int) -> str:
    sql = normalize_sql(sql_statement)
    effective_limit = max(1, min(limit, MAX_SQL_ROWS))
    if re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE):
        return sql
    return f"select * from ({sql}) as insight_query limit {effective_limit}"


def normalize_sql(sql_statement: str) -> str:
    return sql_statement.strip().rstrip(";").strip()


def row_to_insight_result(row: dict[str, Any], columns: list[str], index: int) -> InsightResultRow:
    normalized_row = normalize_sql_result_row(row)
    normalized_columns = [normalize_sql_result_key(column) for column in columns]
    label_key = next((key for key in ("label", "merchant", "employee", "department", "business_category", "month", "transaction_date", "id") if key in normalized_row), None)
    if label_key is None:
        label_key = normalized_columns[0] if normalized_columns else None
    label = str(normalized_row.get(label_key) if label_key else f"Row {index + 1}")
    values = {
        key: value
        for key, value in normalized_row.items()
        if key != label_key
    }
    if not values and label_key:
        values[label_key] = normalized_row.get(label_key)
    return InsightResultRow(label=label, values=values)


def normalize_sql_result_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        normalized_key = normalize_sql_result_key(key)
        if normalized_key not in normalized:
            normalized[normalized_key] = value
    return normalized


def normalize_sql_result_key(key: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
    for canonical, aliases in CANONICAL_SQL_ALIASES.items():
        if compact == canonical or compact in aliases:
            return canonical
    return compact


def allowed_sql_schema_context() -> dict[str, list[str]]:
    return {
        "transactions": [
            "id",
            "employee_id",
            "department_id",
            "transaction_date",
            "posting_date",
            "merchant_name",
            "normalized_merchant_name",
            "amount_cad",
            "amount_original",
            "debit_credit",
            "business_category",
            "normalized_category",
            "merchant_category_code",
            "merchant_country",
            "description",
        ],
        "employees": ["id", "full_name", "department_id"],
        "departments": ["id", "name"],
        "policy_checks": ["transaction_id", "status", "max_severity", "severity_score", "created_at"],
        "risk_scores": ["transaction_id", "risk_level", "risk_score", "created_at"],
        "review_queue_items": [
            "transaction_id",
            "employee",
            "department",
            "merchant",
            "amount_cad",
            "category",
            "queue_status",
            "review_priority",
            "review_level",
            "policy_status",
            "risk_level",
            "risk_score",
            "transaction_date",
        ],
    }
