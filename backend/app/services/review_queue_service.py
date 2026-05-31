from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

try:
    from postgrest.exceptions import APIError
except ModuleNotFoundError:
    class APIError(Exception):
        pass

from app.database.supabase_client import get_supabase_client
from app.schemas.review_queue import (
    CitedPolicyClause,
    ReviewQueueItem,
    ReviewQueueRefreshRequest,
    ReviewQueueRefreshResponse,
    ReviewQueueSummary,
    ReviewerBrief,
)
from app.schemas.risk import RiskSignal
from app.services.policy_engine import utc_now_iso
from app.services.reviewer_brief_service import compose_reviewer_brief

PAGE_SIZE = 500
QUERY_CHUNK_SIZE = 100
POLICY_CLEAR_STATUSES = {"compliant", "excluded_non_expense", None}
RISK_FLAG_LEVELS = {"medium", "high", "critical"}
LEVEL_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
POLICY_EXPLANATIONS = {
    "PREAPPROVAL_OVER_50": "the amount is above the configured policy threshold and approval evidence is missing",
    "PREAPPROVAL_PENDING_REVIEW": "approval evidence exists only as a pending request",
    "RECEIPT_REQUIRED": "the receipt status is explicitly missing",
    "RECEIPT_EVIDENCE_REQUIRED": "receipt evidence is unavailable in the source data for a receipt-sensitive expense",
    "ENTERTAINMENT_CONTEXT_REQUIRED": "meal or entertainment context is incomplete",
    "ALCOHOL_RESTRICTED": "alcohol-related spend needs customer dining context",
    "TICKETS_NOT_REIMBURSABLE": "the category is treated as non-reimbursable under policy",
    "PERSONAL_CARD_USE_PROHIBITED": "the transaction appears personal or cardholder-only rather than a business expense",
}
RISK_EXPLANATIONS = {
    "duplicate_charge": "similar employee, merchant, amount, and date pattern suggests a possible duplicate",
    "split_transaction_pattern": "near-threshold same-merchant charges combine above the approval threshold",
    "merchant_amount_outlier": "the amount is unusually large for this merchant relative to its prior imported history",
    "first_time_high_value_merchant": "a new merchant appears for the first time already at a high value",
    "near_approval_threshold": "the amount sits just below the configured preapproval threshold",
    "round_number_amount": "the amount is a large round number",
    "department_category_outlier": "the amount is high relative to department/category history",
    "policy_risk_overlap": "the compliance scan already flagged the same transaction",
    "ml_isolation_forest_outlier": "the unsupervised model ranked the transaction as unusual compared with imported debit activity",
}


def refresh_review_queue(request: ReviewQueueRefreshRequest | None = None) -> ReviewQueueRefreshResponse:
    request = request or ReviewQueueRefreshRequest()
    items = build_review_queue_items(limit=request.limit)
    return finalize_review_queue_refresh(items, persist=request.persist)


def refresh_review_queue_for_transaction_ids(
    transaction_ids: list[str],
    *,
    persist: bool = True,
) -> ReviewQueueRefreshResponse:
    items = build_review_queue_items(transaction_ids=transaction_ids)
    return finalize_review_queue_refresh(items, persist=persist)


def list_review_queue(
    limit: int = 100,
    offset: int = 0,
    queue_status: str = "open",
    review_level: str | None = None,
    policy_status: str | None = None,
) -> list[ReviewQueueItem]:
    try:
        rows = fetch_persisted_review_queue(limit, offset, queue_status, review_level, policy_status)
    except APIError:
        rows = []

    if rows:
        return [item_from_persisted_row(row) for row in rows]

    items = build_review_queue_items(limit=max(limit + offset, 500))
    if queue_status:
        items = [item for item in items if item.queue_status == queue_status]
    if review_level:
        items = [item for item in items if item.review_level == review_level]
    if policy_status:
        items = [item for item in items if item.policy_status == policy_status]
    return items[offset : offset + limit]


def finalize_review_queue_refresh(
    items: list[ReviewQueueItem],
    *,
    persist: bool,
) -> ReviewQueueRefreshResponse:
    table_available = True
    persisted = 0

    if persist:
        try:
            persisted = persist_review_items(items)
        except APIError:
            table_available = False

    return ReviewQueueRefreshResponse(
        generated=len(items),
        persisted=persisted,
        table_available=table_available,
        summary=summarize_review_queue(items),
    )


def build_review_queue_items(
    limit: int | None = None,
    transaction_ids: list[str] | None = None,
) -> list[ReviewQueueItem]:
    transactions = fetch_transactions_by_ids(transaction_ids) if transaction_ids is not None else fetch_transactions(limit=limit)
    transaction_ids = [str(transaction["id"]) for transaction in transactions if transaction.get("id")]
    if not transaction_ids:
        return []
    policy_checks = latest_by_transaction_id(fetch_rows_by_values("policy_checks", "transaction_id", transaction_ids, "*"))
    risk_scores = latest_by_transaction_id(fetch_rows_by_values("risk_scores", "transaction_id", transaction_ids, "*"))
    violations = fetch_rows_by_values("violations", "transaction_id", transaction_ids, "*")
    violations_by_transaction = group_violations(violations)
    citations_by_rule_code = fetch_policy_citations_by_rule_code(unique_ids(row.get("rule_code") for row in violations))
    employees = fetch_by_ids("employees", unique_ids(transaction.get("employee_id") for transaction in transactions))
    departments = fetch_by_ids("departments", unique_ids(transaction.get("department_id") for transaction in transactions))
    employees_by_id = {str(row["id"]): row for row in employees}
    departments_by_id = {str(row["id"]): row for row in departments}

    items = [
        compose_review_queue_item(
            transaction,
            policy_checks.get(str(transaction["id"])),
            risk_scores.get(str(transaction["id"])),
            current_policy_violations(
                policy_checks.get(str(transaction["id"])),
                violations_by_transaction.get(str(transaction["id"]), []),
            ),
            citations_by_rule_code,
            employees_by_id,
            departments_by_id,
        )
        for transaction in transactions
    ]
    return sorted(items, key=lambda item: (item.review_priority, item.amount_cad), reverse=True)


def compose_review_queue_item(
    transaction: dict[str, Any],
    policy_check: dict[str, Any] | None,
    risk_score: dict[str, Any] | None,
    violations: list[dict[str, Any]],
    citations_by_rule_code: dict[str, list[CitedPolicyClause]] | None,
    employees_by_id: dict[str, dict[str, Any]],
    departments_by_id: dict[str, dict[str, Any]],
) -> ReviewQueueItem:
    employee = employees_by_id.get(str(transaction.get("employee_id") or ""))
    department = departments_by_id.get(str(transaction.get("department_id") or ""))
    policy_status = policy_check.get("status") if policy_check else None
    policy_severity = policy_check.get("max_severity") if policy_check else None
    risk_level = risk_score.get("risk_level") if risk_score else None
    risk_signals = [RiskSignal(**signal) for signal in risk_score.get("signals", [])] if risk_score else []
    policy_flags = [
        {
            "rule_code": violation.get("rule_code"),
            "severity": violation.get("severity"),
            "explanation": violation.get("explanation"),
            "required_action": violation.get("required_action"),
        }
        for violation in violations
    ]
    review_level = merged_review_level(policy_severity, risk_level)
    review_priority = calculate_review_priority(policy_status, policy_severity, policy_flags, risk_score, risk_signals)
    next_action = compose_next_action(policy_check, risk_score, policy_flags, risk_signals)
    cited_policy_clauses = policy_citations_for_flags(policy_flags, citations_by_rule_code or {})
    reviewer_brief = compose_reviewer_brief(
        transaction=transaction,
        policy_check=policy_check,
        risk_score=risk_score,
        policy_flags=policy_flags,
        risk_signals=risk_signals,
        cited_policy_clauses=cited_policy_clauses,
        fallback_next_action=next_action,
    )

    return ReviewQueueItem(
        transaction_id=str(transaction["id"]),
        employee_id=str(transaction.get("employee_id")) if transaction.get("employee_id") else None,
        employee=transaction.get("employee_name") or (employee or {}).get("full_name"),
        department_id=str(transaction.get("department_id")) if transaction.get("department_id") else None,
        department=transaction.get("department_name") or (department or {}).get("name"),
        transaction_date=str(transaction.get("transaction_date")) if transaction.get("transaction_date") else None,
        merchant=transaction.get("normalized_merchant_name") or transaction.get("merchant_name"),
        amount_cad=float(transaction.get("amount_cad") or 0),
        category=transaction.get("business_category")
        or transaction.get("policy_category")
        or transaction.get("normalized_category")
        or "Uncategorized",
        queue_status="open" if review_priority > 0 else "resolved",
        review_priority=review_priority,
        review_level=review_level,
        policy_check_id=str(policy_check.get("id")) if policy_check and policy_check.get("id") else None,
        policy_status=policy_status,
        policy_severity=policy_severity,
        policy_flags=policy_flags,
        risk_score_id=str(risk_score.get("id")) if risk_score and risk_score.get("id") else None,
        risk_score=int(risk_score.get("risk_score") or 0) if risk_score else 0,
        risk_level=risk_level,
        risk_signals=risk_signals,
        ai_context=compose_ai_context(policy_status, risk_level, policy_flags, risk_signals),
        reviewer_brief=reviewer_brief,
        next_action=next_action,
        generated_at=utc_now_iso(),
    )


def merged_review_level(policy_severity: str | None, risk_level: str | None) -> str:
    levels = [level for level in [policy_severity, risk_level] if level in LEVEL_RANK]
    if not levels:
        return "low"
    return max(levels, key=lambda level: LEVEL_RANK[level])


def calculate_review_priority(
    policy_status: str | None,
    policy_severity: str | None,
    policy_flags: list[dict[str, Any]],
    risk_score: dict[str, Any] | None,
    risk_signals: list[RiskSignal],
) -> int:
    score = 0
    if policy_status == "policy_violation":
        score += 65
    elif policy_status == "approval_evidence_needed":
        score += 45
    elif policy_status in {"context_needed", "review_required"}:
        score += 30
    if policy_status not in POLICY_CLEAR_STATUSES and policy_severity in LEVEL_RANK:
        score += LEVEL_RANK[policy_severity] * 7
    if policy_flags:
        score += min(20, len(policy_flags) * 5)
    if risk_score:
        score += int(risk_score.get("risk_score") or 0) // 3
    if any(signal.type in {"duplicate_charge", "split_transaction_pattern"} for signal in risk_signals):
        score += 18
    if any(signal.type == "ml_isolation_forest_outlier" for signal in risk_signals):
        score += 12
    return min(score, 100)


def compose_next_action(
    policy_check: dict[str, Any] | None,
    risk_score: dict[str, Any] | None,
    policy_flags: list[dict[str, Any]],
    risk_signals: list[RiskSignal],
) -> str:
    if policy_flags:
        return str(policy_flags[0].get("required_action") or "Review the policy finding before approval.")
    if any(signal.type == "split_transaction_pattern" for signal in risk_signals):
        return "Review nearby same-merchant transactions before approving reimbursement."
    if any(signal.type == "duplicate_charge" for signal in risk_signals):
        return "Check whether this duplicates another card transaction before approving."
    if risk_score and risk_score.get("risk_level") in {"high", "critical"}:
        return "Review the risk signals and supporting transaction context before approval."
    if policy_check and policy_check.get("recommended_next_action"):
        return str(policy_check["recommended_next_action"])
    return "No action required."


def compose_ai_context(
    policy_status: str | None,
    risk_level: str | None,
    policy_flags: list[dict[str, Any]],
    risk_signals: list[RiskSignal],
) -> str:
    policy_reasons = explain_policy_flags(policy_flags)
    risk_reasons = explain_risk_signals(risk_signals)

    if policy_reasons and risk_reasons:
        return (
            f"Policy flagged this because {policy_reasons}. "
            f"Risk detection also raised {risk_level or 'low'} concern because {risk_reasons}. "
            "Review both the policy evidence and anomaly drivers before approval."
        )
    if policy_reasons:
        return f"Policy flagged this because {policy_reasons}. Confirm the required evidence before approval."
    if risk_reasons:
        return (
            f"No blocking policy issue is currently recorded, but risk detection raised {risk_level or 'low'} concern "
            f"because {risk_reasons}. Review the pattern before approving."
        )
    return "No blocking policy issue or material risk signal is currently recorded."


def explain_policy_flags(policy_flags: list[dict[str, Any]]) -> str:
    reasons = []
    for flag in policy_flags[:3]:
        rule_code = str(flag.get("rule_code") or "")
        reasons.append(POLICY_EXPLANATIONS.get(rule_code) or str(flag.get("explanation") or rule_code or "a policy rule matched"))
    return "; ".join(reason for reason in reasons if reason)


def explain_risk_signals(risk_signals: list[RiskSignal]) -> str:
    reasons = []
    for signal in risk_signals[:3]:
        if signal.type == "ml_isolation_forest_outlier":
            feature_labels = [
                str(feature.get("label") or feature.get("feature"))
                for feature in signal.evidence.get("top_features", [])
                if isinstance(feature, dict)
            ]
            if feature_labels:
                reasons.append(f"Isolation Forest saw {', '.join(feature_labels[:3]).lower()}")
                continue
        reasons.append(RISK_EXPLANATIONS.get(signal.type) or signal.message)
    return "; ".join(reason for reason in reasons if reason)


def summarize_review_queue(items: list[ReviewQueueItem]) -> ReviewQueueSummary:
    status_counts = Counter(item.queue_status for item in items)
    return ReviewQueueSummary(
        total=len(items),
        open=status_counts["open"],
        in_approval=status_counts["in_approval"],
        resolved=status_counts["resolved"],
        ignored=status_counts["ignored"],
        high_or_critical=sum(1 for item in items if item.review_level in {"high", "critical"}),
        policy_flagged=sum(1 for item in items if item.policy_status not in POLICY_CLEAR_STATUSES),
        risk_flagged=sum(1 for item in items if item.risk_level in RISK_FLAG_LEVELS),
    )


def persist_review_items(items: list[ReviewQueueItem]) -> int:
    rows = [persisted_payload(item) for item in items]
    rows = apply_workflow_queue_status(rows)
    persisted = 0
    for chunk in chunked(rows, PAGE_SIZE):
        get_supabase_client().table("review_queue_items").upsert(chunk, on_conflict="transaction_id").execute()
        persisted += len(chunk)
    return persisted


def apply_workflow_queue_status(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transaction_ids = [str(row.get("transaction_id") or "") for row in rows if row.get("transaction_id")]
    if not transaction_ids:
        return rows

    try:
        existing_review_items = fetch_rows_by_values("review_queue_items", "transaction_id", transaction_ids, "transaction_id,queue_status,updated_at,generated_at")
    except APIError:
        existing_review_items = []
    try:
        approvals = fetch_rows_by_values("approval_requests", "transaction_id", transaction_ids, "transaction_id,status,updated_at,created_at")
    except APIError:
        approvals = []

    existing_status_by_transaction_id = {
        str(row.get("transaction_id") or ""): str(row.get("queue_status") or "")
        for row in existing_review_items
        if row.get("transaction_id") and row.get("queue_status")
    }
    approval_status_by_transaction_id = latest_approval_status_by_transaction_id(approvals)

    for row in rows:
        transaction_id = str(row.get("transaction_id") or "")
        approval_status = approval_status_by_transaction_id.get(transaction_id)
        if approval_status in {"draft", "requested"}:
            row["queue_status"] = "in_approval"
        elif approval_status in {"approved", "denied", "cancelled"}:
            row["queue_status"] = "resolved"
        elif existing_status_by_transaction_id.get(transaction_id) in {"in_approval", "resolved", "ignored"}:
            row["queue_status"] = existing_status_by_transaction_id[transaction_id]
    return rows


def latest_approval_status_by_transaction_id(rows: list[dict[str, Any]]) -> dict[str, str]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        transaction_id = str(row.get("transaction_id") or "")
        if not transaction_id:
            continue
        current = latest.get(transaction_id)
        if current is None or approval_row_timestamp(row) > approval_row_timestamp(current):
            latest[transaction_id] = row
    return {
        transaction_id: str(row.get("status") or "").lower()
        for transaction_id, row in latest.items()
        if row.get("status")
    }


def approval_row_timestamp(row: dict[str, Any]) -> str:
    return str(row.get("updated_at") or row.get("created_at") or "")


def persisted_payload(item: ReviewQueueItem) -> dict[str, Any]:
    return {
        "transaction_id": item.transaction_id,
        "employee_id": item.employee_id,
        "department_id": item.department_id,
        "transaction_date": item.transaction_date,
        "merchant": item.merchant,
        "amount_cad": item.amount_cad,
        "category": item.category,
        "queue_status": item.queue_status,
        "review_priority": item.review_priority,
        "review_level": item.review_level,
        "policy_check_id": item.policy_check_id,
        "policy_status": item.policy_status,
        "policy_severity": item.policy_severity,
        "policy_flags": item.policy_flags,
        "risk_score_id": item.risk_score_id,
        "risk_score": item.risk_score,
        "risk_level": item.risk_level,
        "risk_signals": [signal.model_dump() for signal in item.risk_signals],
        "ai_context": item.ai_context,
        "reviewer_brief": item.reviewer_brief.model_dump(mode="json") if item.reviewer_brief else None,
        "next_action": item.next_action,
        "generated_at": utc_now_iso(),
    }


def fetch_persisted_review_queue(
    limit: int,
    offset: int,
    queue_status: str,
    review_level: str | None,
    policy_status: str | None,
) -> list[dict[str, Any]]:
    query = (
        get_supabase_client()
        .table("review_queue_items")
        .select("*, employees(full_name), departments(name)")
        .order("review_priority", desc=True)
        .order("amount_cad", desc=True)
        .order("generated_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if queue_status:
        query = query.eq("queue_status", queue_status)
    if review_level:
        query = query.eq("review_level", review_level)
    if policy_status:
        query = query.eq("policy_status", policy_status)
    return query.execute().data or []


def item_from_persisted_row(row: dict[str, Any]) -> ReviewQueueItem:
    employee = row.get("employees") if isinstance(row.get("employees"), dict) else None
    department = row.get("departments") if isinstance(row.get("departments"), dict) else None
    return ReviewQueueItem(
        id=str(row.get("id")) if row.get("id") else None,
        transaction_id=str(row["transaction_id"]),
        employee_id=str(row.get("employee_id")) if row.get("employee_id") else None,
        employee=(employee or {}).get("full_name"),
        department_id=str(row.get("department_id")) if row.get("department_id") else None,
        department=(department or {}).get("name"),
        transaction_date=str(row.get("transaction_date")) if row.get("transaction_date") else None,
        merchant=row.get("merchant"),
        amount_cad=float(row.get("amount_cad") or 0),
        category=row.get("category") or "Uncategorized",
        queue_status=row.get("queue_status") or "open",
        review_priority=int(row.get("review_priority") or 0),
        review_level=row.get("review_level") or "low",
        policy_check_id=str(row.get("policy_check_id")) if row.get("policy_check_id") else None,
        policy_status=row.get("policy_status"),
        policy_severity=row.get("policy_severity"),
        policy_flags=row.get("policy_flags") or [],
        risk_score_id=str(row.get("risk_score_id")) if row.get("risk_score_id") else None,
        risk_score=int(row.get("risk_score") or 0),
        risk_level=row.get("risk_level"),
        risk_signals=[RiskSignal(**signal) for signal in row.get("risk_signals") or []],
        ai_context=row.get("ai_context"),
        reviewer_brief=ReviewerBrief(**row["reviewer_brief"]) if isinstance(row.get("reviewer_brief"), dict) else None,
        next_action=row.get("next_action") or "No action required.",
        generated_at=str(row.get("generated_at")) if row.get("generated_at") else None,
    )
def fetch_transactions(limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    max_rows = limit or 10000
    while len(rows) < max_rows:
        end = min(start + PAGE_SIZE - 1, max_rows - 1)
        batch = (
            get_supabase_client()
            .table("transactions")
            .select("*")
            .order("created_at")
            .range(start, end)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows[:max_rows]


def fetch_transactions_by_ids(transaction_ids: list[str]) -> list[dict[str, Any]]:
    ordered_transaction_ids = unique_ids(transaction_ids)
    if not ordered_transaction_ids:
        return []
    transactions_by_id = {
        str(row["id"]): row
        for row in fetch_rows_by_values("transactions", "id", ordered_transaction_ids, "*")
        if row.get("id")
    }
    return [transactions_by_id[transaction_id] for transaction_id in ordered_transaction_ids if transaction_id in transactions_by_id]


def fetch_rows_by_values(table_name: str, column_name: str, values: list[str], columns: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunked(unique_ids(values), QUERY_CHUNK_SIZE):
        rows.extend(get_supabase_client().table(table_name).select(columns).in_(column_name, chunk).execute().data or [])
    return rows


def fetch_by_ids(table_name: str, ids: list[str]) -> list[dict[str, Any]]:
    return fetch_rows_by_values(table_name, "id", ids, "*")


def fetch_policy_citations_by_rule_code(rule_codes: list[str]) -> dict[str, list[CitedPolicyClause]]:
    if not rule_codes:
        return {}

    citations_by_rule_code: dict[str, list[CitedPolicyClause]] = {}
    try:
        rows = fetch_rows_by_values("policy_chunks", "rule_code", rule_codes, "id,document_id,rule_code,content,metadata")
    except APIError:
        rows = []
    for row in rows:
        rule_code = str(row.get("rule_code") or "")
        if not rule_code:
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        citations_by_rule_code.setdefault(rule_code, []).append(
            CitedPolicyClause(
                rule_code=rule_code,
                clause_id=str(row.get("id")) if row.get("id") else None,
                title=str(metadata.get("title") or metadata.get("heading") or rule_code),
                text=str(row.get("content") or ""),
                source=str(row.get("document_id")) if row.get("document_id") else None,
                match_score=None,
            )
        )

    missing_rule_codes = [rule_code for rule_code in rule_codes if rule_code not in citations_by_rule_code]
    if not missing_rule_codes:
        return citations_by_rule_code
    try:
        rows = fetch_rows_by_values("policy_rules", "rule_code", missing_rule_codes, "id,rule_code,name,source_text")
    except APIError:
        return {}
    for row in rows:
        rule_code = str(row.get("rule_code") or "")
        source_text = str(row.get("source_text") or "").strip()
        if not rule_code or not source_text:
            continue
        citations_by_rule_code.setdefault(rule_code, []).append(
            CitedPolicyClause(
                rule_code=rule_code,
                clause_id=str(row.get("id")) if row.get("id") else None,
                title=str(row.get("name") or rule_code),
                text=source_text,
                source="policy_rules.source_text",
                match_score=None,
            )
        )
    return citations_by_rule_code


def policy_citations_for_flags(
    policy_flags: list[dict[str, Any]],
    citations_by_rule_code: dict[str, list[CitedPolicyClause]],
) -> list[CitedPolicyClause]:
    citations: list[CitedPolicyClause] = []
    seen_clause_ids: set[str] = set()
    for flag in policy_flags:
        rule_code = str(flag.get("rule_code") or "")
        for clause in citations_by_rule_code.get(rule_code, [])[:2]:
            dedupe_key = clause.clause_id or f"{clause.rule_code}:{clause.text[:80]}"
            if dedupe_key in seen_clause_ids:
                continue
            seen_clause_ids.add(dedupe_key)
            citations.append(clause)
    return citations


def group_violations(violations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for violation in violations:
        grouped.setdefault(str(violation.get("transaction_id")), []).append(violation)
    return grouped


def latest_by_transaction_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        transaction_id = row.get("transaction_id")
        if not transaction_id:
            continue
        key = str(transaction_id)
        current = latest.get(key)
        if current is None or row_recency_key(row) > row_recency_key(current):
            latest[key] = row
    return latest


def current_policy_violations(
    policy_check: dict[str, Any] | None,
    violations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not policy_check:
        return []
    policy_check_id = str(policy_check.get("id") or "")
    if not policy_check_id:
        return []
    current = [
        violation
        for violation in violations
        if str(violation.get("policy_check_id") or "") == policy_check_id
    ]
    if current:
        return current
    if policy_check.get("status") in POLICY_CLEAR_STATUSES:
        return []
    return violations


def row_recency_key(row: dict[str, Any]) -> tuple[datetime, str]:
    for field in ("checked_at", "scored_at", "generated_at", "updated_at", "created_at"):
        parsed = parse_datetime(row.get(field))
        if parsed is not None:
            return (parsed, str(row.get("id") or ""))
    return (datetime.min, str(row.get("id") or ""))


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def unique_ids(values) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
