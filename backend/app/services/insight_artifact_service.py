from __future__ import annotations

from fastapi import HTTPException

from app.database.supabase_client import get_supabase_client
from app.schemas.insights import InsightArtifactType, InsightCitation, InsightQueryResponse, InsightResultRow
from app.schemas.insights import InsightPlan, InsightValidationResult


def build_insight_artifact(result: InsightQueryResponse, artifact_type: InsightArtifactType) -> tuple[str, str, str]:
    if artifact_type == "csv":
        return build_insight_csv(result), build_insight_artifact_filename(result, artifact_type), "text/csv; charset=utf-8"
    if artifact_type == "diagram":
        return build_insight_mermaid(result), build_insight_artifact_filename(result, artifact_type), "text/plain; charset=utf-8"
    return build_insight_brief_markdown(result), build_insight_artifact_filename(result, artifact_type), "text/markdown; charset=utf-8"


def build_session_artifact(
    session_id: str,
    artifact_type: InsightArtifactType,
    message_id: str | None = None,
) -> tuple[str, str, str]:
    return build_insight_artifact(load_stored_insight_result(session_id, message_id=message_id), artifact_type)


def load_stored_insight_result(session_id: str, message_id: str | None = None) -> InsightQueryResponse:
    rows = (
        get_supabase_client()
        .table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    if message_id:
        rows = [row for row in rows if str(row.get("id")) == message_id]

    for row in reversed(rows):
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if metadata.get("kind") != "insight_response":
            continue
        return _response_from_message_row(row)

    detail = "Insight result message was not found for this session." if message_id else "No stored insight result was found for this session."
    raise HTTPException(status_code=404, detail=detail)


def build_insight_csv(result: InsightQueryResponse) -> str:
    columns = result.columns or infer_columns(result.rows)
    lines = [",".join(escape_csv_cell(column) for column in columns)]
    for row in result.rows:
        values = []
        for column in columns:
            cell = row.label if column == "label" else row.values.get(column)
            values.append(escape_csv_cell(format_csv_value(cell)))
        lines.append(",".join(values))
    return "\n".join(lines)


def build_insight_mermaid(result: InsightQueryResponse) -> str:
    filter_summary = format_filters(result.plan.filters)
    top_rows = result.rows[:5]
    metric = pick_primary_metric(result)
    lines = [
        "flowchart TD",
        f'question["Question<br/>{escape_mermaid(result.question)}"]',
        f'validation["Validation<br/>{"Passed" if result.validation.valid else "Blocked"}"]',
        f'tool["Tool<br/>{escape_mermaid(result.plan.tool)}"]',
        f'intent["Intent<br/>{escape_mermaid(result.plan.intent)}"]',
        f'summary["Answer<br/>{escape_mermaid(result.summary)}"]',
        "question --> validation",
        "validation --> tool",
        "tool --> intent",
        "intent --> summary",
    ]

    if filter_summary:
        lines.append(f'filters["Filters<br/>{escape_mermaid(filter_summary)}"]')
        lines.append("tool --> filters")
        lines.append("filters --> summary")

    for index, row in enumerate(top_rows):
        metric_value = row.values.get(metric)
        lines.append(f'row{index}["{escape_mermaid(row.label)}<br/>{escape_mermaid(format_metric(metric, metric_value))}"]')
        lines.append(f"summary --> row{index}")

    if result.citations:
        lines.append(f'citations["Policy citations<br/>{escape_mermaid(format_citation_count(result.citations))}"]')
        lines.append("summary --> citations")

    return "\n".join(lines)


def build_insight_brief_markdown(result: InsightQueryResponse) -> str:
    lines = [
        f"# {result.plan.intent}",
        "",
        f"**Question**: {result.question}",
        "",
        f"**Summary**: {result.summary}",
        "",
        "## Execution",
        "",
        f"- Planner: {result.planner_source}",
        f"- Tool: {result.plan.tool}",
        f"- View: {result.visualization or 'table'}",
        f"- Rows returned: {result.metadata.get('returned_count', len(result.rows))}",
    ]

    filter_summary = format_filters(result.plan.filters)
    if filter_summary:
        lines.append(f"- Filters: {filter_summary}")

    if result.rows:
        columns = result.columns or infer_columns(result.rows)
        lines.extend(["", "## Result Preview", "", f"| {' | '.join(columns)} |", f"| {' | '.join('---' for _ in columns)} |"])
        for row in result.rows[:12]:
            values = []
            for column in columns:
                cell = row.label if column == "label" else row.values.get(column)
                values.append(escape_markdown_cell(format_csv_value(cell)))
            lines.append(f"| {' | '.join(values)} |")

    if result.citations:
        lines.extend(["", "## Citations", ""])
        for citation in result.citations:
            title = citation.title or citation.rule_code or "Policy citation"
            suffix = f" ({citation.source})" if citation.source else ""
            lines.append(f"- {title}: {citation.text}{suffix}")

    return "\n".join(lines)


def build_insight_artifact_filename(result: InsightQueryResponse, artifact_type: InsightArtifactType) -> str:
    base_name = slugify(result.plan.intent or result.plan.tool or result.question or "insight")
    if artifact_type == "csv":
        return f"{base_name}.csv"
    if artifact_type == "diagram":
        return f"{base_name}.mmd"
    return f"{base_name}.md"


def infer_columns(rows: list[InsightResultRow]) -> list[str]:
    columns = ["label"]
    for row in rows:
        for key in row.values:
            if key not in columns:
                columns.append(key)
    return columns


def pick_primary_metric(result: InsightQueryResponse) -> str:
    preferred = {"sum_amount_cad", "policy_flag_count", "risk_score", "transaction_count", "avg_amount_cad"}
    for column in result.columns:
        if column in preferred:
            return column
    first_row = result.rows[0] if result.rows else None
    return next(iter(first_row.values.keys()), "value") if first_row else "value"


def format_filters(filters: dict[str, object]) -> str:
    parts: list[str] = []
    for key, value in filters.items():
        if value in (None, ""):
            continue
        if isinstance(value, list):
            text = ", ".join(str(entry) for entry in value)
        else:
            text = str(value)
        parts.append(f"{key}: {text}")
    return " | ".join(parts)


def format_citation_count(citations: list[InsightCitation]) -> str:
    return "1 citation" if len(citations) == 1 else f"{len(citations)} citations"


def format_metric(metric: str, value: object) -> str:
    if isinstance(value, (int, float)):
        if "amount" in metric:
            return f"CAD {value:,.2f}"
        return f"{value:,.2f}" if isinstance(value, float) and not float(value).is_integer() else f"{int(value):,}"
    return str(value or "-")


def format_csv_value(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}" if not value.is_integer() else str(int(value))
    if value is None:
        return ""
    return str(value)


def escape_csv_cell(value: str) -> str:
    if any(char in value for char in ('"', ",", "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def escape_mermaid(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "'").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")


def slugify(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    normalized = normalized.strip("-")
    return normalized or "insight"


def _response_from_message_row(row: dict[str, object]) -> InsightQueryResponse:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    plan_payload = metadata.get("plan") if isinstance(metadata.get("plan"), dict) else {}
    validation_payload = metadata.get("validation") if isinstance(metadata.get("validation"), dict) else {}
    citations_payload = metadata.get("citations") if isinstance(metadata.get("citations"), list) else []
    rows_payload = metadata.get("artifact_rows") if isinstance(metadata.get("artifact_rows"), list) else metadata.get("rows")
    response_rows = rows_payload if isinstance(rows_payload, list) else []
    result_metadata = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    summary = str(metadata.get("summary") or row.get("content") or "")
    return InsightQueryResponse(
        question=str(metadata.get("question") or ""),
        session_id=str(metadata.get("session_id")) if metadata.get("session_id") else str(row.get("session_id") or ""),
        plan=InsightPlan(**plan_payload),
        validation=InsightValidationResult(**validation_payload),
        planner_source=str(metadata.get("planner_source") or "deterministic"),
        summary=summary,
        columns=[str(column) for column in metadata.get("columns") or []],
        rows=[InsightResultRow(**item) for item in response_rows if isinstance(item, dict)],
        citations=[InsightCitation(**item) for item in citations_payload if isinstance(item, dict)],
        visualization=str(metadata.get("visualization")) if metadata.get("visualization") else None,
        metadata=result_metadata,
    )
