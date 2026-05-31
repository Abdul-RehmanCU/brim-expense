from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from fastapi import HTTPException
from pydantic import ValidationError

try:
    from postgrest.exceptions import APIError
except ModuleNotFoundError:
    class APIError(Exception):
        pass

from app.database.supabase_client import get_supabase_client
from app.schemas.approvals import (
    ApprovalExplanation,
    ApprovalExplanationReason,
    ApprovalContextSnapshot,
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalRecommendation,
    ApprovalRequestCreate,
    ApprovalRequestDetail,
    ApprovalRequestItem,
    DepartmentBudgetStatus,
    EmployeeSpendHistory,
)
from app.schemas.common import PlaceholderResponse
from app.schemas.review_queue import CitedPolicyClause, ReviewerBrief
from app.schemas.risk import RiskSignal
from app.services.policy_engine import utc_now_iso
from app.services.review_grouping import annotate_review_clusters, review_group_key_from_transaction, review_group_key_from_values

POLICY_CLEAR_STATUSES = {"compliant", "excluded_non_expense", None}
RISK_FLAG_LEVELS = {"medium", "high", "critical"}
OPEN_APPROVAL_STATUSES = {"draft", "requested"}
DECISION_TO_PREAPPROVAL_STATUS = {
    "approved": "approved",
    "denied": "denied",
    "cancelled": "missing",
}


class ApprovalRecommendationClient(Protocol):
    def compose_approval_recommendation(self, facts: dict[str, Any]) -> ApprovalRecommendation:
        ...


def get_approvals_status() -> PlaceholderResponse:
    return PlaceholderResponse(
        status="ok",
        service="approvals",
        implemented=True,
        message="Approval workflows promote review queue items into durable approval requests.",
    )


def list_approvals(status: str | None = None, limit: int = 100, offset: int = 0) -> ApprovalListResponse:
    query = (
        get_supabase_client()
        .table("approval_requests")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        query = query.eq("status", status)
    rows = query.execute().data or []
    return ApprovalListResponse(approvals=approval_items_from_rows(rows))


def get_approval(approval_id: str) -> ApprovalRequestDetail:
    row = fetch_one_by_id("approval_requests", approval_id, "*")
    if not row:
        raise HTTPException(status_code=404, detail="Approval request was not found.")

    detail = approval_detail_from_row(row)
    detail.audit_events = fetch_approval_audit_events(approval_id)
    return detail


def get_approval_explanation(approval_id: str) -> ApprovalExplanation:
    detail = get_approval(approval_id)
    if detail.approval_explanation:
        return detail.approval_explanation
    raise HTTPException(status_code=404, detail="Approval explanation was not found.")


def create_approval_request(request: ApprovalRequestCreate) -> ApprovalRequestDetail:
    if not request.review_queue_item_id and not request.transaction_id:
        raise HTTPException(status_code=422, detail="review_queue_item_id or transaction_id is required.")

    review_item = fetch_review_queue_item(request)
    transaction_id = str(review_item.get("transaction_id") or request.transaction_id or "")
    if not transaction_id:
        raise HTTPException(status_code=422, detail="Review queue item does not include a transaction id.")

    cluster_review_items = fetch_review_cluster_review_items(review_item)
    created_or_existing: list[dict[str, Any]] = []

    for cluster_review_item in cluster_review_items:
        cluster_transaction_id = str(cluster_review_item.get("transaction_id") or "")
        if not cluster_transaction_id:
            continue
        existing = fetch_existing_open_approval(cluster_transaction_id)
        if existing:
            created_or_existing.append(existing)
            update_review_queue_status(cluster_transaction_id, "in_approval")
            continue

        snapshot = build_approval_context_snapshot(cluster_review_item)
        recommendation = compose_approval_recommendation(snapshot, client=default_approval_recommendation_client())
        transaction = snapshot.transaction
        employee_id = str(transaction.get("employee_id") or cluster_review_item.get("employee_id") or "")
        department_id = str(transaction.get("department_id") or cluster_review_item.get("department_id") or "")
        if not employee_id or not department_id:
            raise HTTPException(status_code=422, detail="Approval request requires employee and department context.")

        payload = {
            "transaction_id": cluster_transaction_id,
            "employee_id": employee_id,
            "department_id": department_id,
            "status": "requested",
            "requested_amount_cad": float(transaction.get("amount_cad") or cluster_review_item.get("amount_cad") or 0),
            "policy_check_id": cluster_review_item.get("policy_check_id") or snapshot.policy.get("id"),
            "risk_score_id": cluster_review_item.get("risk_score_id") or snapshot.risk.get("id"),
            "ai_recommendation": recommendation.model_dump(mode="json"),
            "requester_note": request.requester_note,
            "review_queue_item_id": cluster_review_item.get("id"),
            "context_snapshot": snapshot.model_dump(mode="json"),
            "recommendation_source": recommendation.source,
            "recommendation_generated_at": utc_now_iso(),
        }
        inserted = get_supabase_client().table("approval_requests").insert(payload).execute().data or []
        if not inserted:
            raise HTTPException(status_code=500, detail="Approval request could not be created.")
        approval = inserted[0]
        created_or_existing.append(approval)
        update_review_queue_status(cluster_transaction_id, "in_approval")
        insert_audit_event(
            action="approval.requested",
            entity_id=str(approval["id"]),
            actor=request.actor,
            details={
                "transaction_id": cluster_transaction_id,
                "review_queue_item_id": cluster_review_item.get("id"),
                "review_group_transaction_ids": [str(item.get("transaction_id")) for item in cluster_review_items if item.get("transaction_id")],
                "recommendation": recommendation.model_dump(mode="json"),
            },
        )

    selected = next(
        (row for row in created_or_existing if str(row.get("transaction_id") or "") == transaction_id),
        created_or_existing[0] if created_or_existing else None,
    )
    if not selected:
        raise HTTPException(status_code=500, detail="Approval request could not be created.")
    return get_approval(str(selected["id"]))


def decide_approval(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRequestDetail:
    existing = fetch_one_by_id("approval_requests", approval_id, "*")
    if not existing:
        raise HTTPException(status_code=404, detail="Approval request was not found.")
    if existing.get("status") in {"approved", "denied", "cancelled"}:
        raise HTTPException(status_code=409, detail="Approval request already has a final decision.")

    decided_at = utc_now_iso()
    update_payload = {
        "status": request.decision,
        "decision_note": request.note,
        "decided_by": request.actor,
        "decided_at": decided_at,
    }
    cluster_transactions = fetch_review_cluster_transactions_for_transaction_id(str(existing.get("transaction_id") or ""))
    cluster_transaction_ids = [str(transaction["id"]) for transaction in cluster_transactions if transaction.get("id")]
    cluster_approvals = fetch_rows_by_values("approval_requests", "transaction_id", cluster_transaction_ids, "*")
    approvals_by_transaction_id = {
        str(row.get("transaction_id") or ""): row
        for row in cluster_approvals
        if row.get("transaction_id")
    }

    for approval in cluster_approvals:
        if approval.get("status") in {"approved", "denied", "cancelled"} and str(approval.get("id")) != approval_id:
            continue
        get_supabase_client().table("approval_requests").update(update_payload).eq("id", approval["id"]).execute()
        insert_audit_event(
            action=f"approval.{request.decision}",
            entity_id=str(approval["id"]),
            actor=request.actor,
            details={
                "transaction_id": approval.get("transaction_id"),
                "decision": request.decision,
                "note": request.note,
                "review_group_transaction_ids": cluster_transaction_ids,
            },
        )

    for transaction in cluster_transactions:
        transaction_id = str(transaction.get("id") or "")
        update_preapproval_from_decision(
            approvals_by_transaction_id.get(transaction_id) or approval_row_from_transaction(existing, transaction),
            request,
            decided_at,
        )
        update_review_queue_status(transaction_id, "resolved")
    return get_approval(approval_id)


def fetch_review_queue_item(request: ApprovalRequestCreate) -> dict[str, Any]:
    client = get_supabase_client()
    query = client.table("review_queue_items").select("*")
    if request.review_queue_item_id:
        rows = query.eq("id", request.review_queue_item_id).limit(1).execute().data or []
    else:
        rows = query.eq("transaction_id", request.transaction_id).limit(1).execute().data or []
    if rows:
        return rows[0]
    if request.transaction_id:
        return {"transaction_id": request.transaction_id}
    raise HTTPException(status_code=404, detail="Review queue item was not found.")


def fetch_review_cluster_review_items(seed_review_item: dict[str, Any]) -> list[dict[str, Any]]:
    transaction_id = str(seed_review_item.get("transaction_id") or "")
    cluster_transactions = fetch_review_cluster_transactions_for_transaction_id(transaction_id)
    cluster_transaction_ids = [str(transaction["id"]) for transaction in cluster_transactions if transaction.get("id")]
    if not cluster_transaction_ids:
        return [seed_review_item]

    rows = fetch_rows_by_values("review_queue_items", "transaction_id", cluster_transaction_ids, "*")
    rows_by_transaction_id = {
        str(row.get("transaction_id") or ""): row
        for row in rows
        if row.get("transaction_id")
        and (
            str(row.get("queue_status") or "") in {"open", "in_approval"}
            or int(row.get("review_priority") or 0) > 0
        )
    }
    rows_by_transaction_id.setdefault(transaction_id, seed_review_item)
    return [
        rows_by_transaction_id[cluster_transaction_id]
        for cluster_transaction_id in cluster_transaction_ids
        if cluster_transaction_id in rows_by_transaction_id
    ]


def fetch_review_cluster_transactions_for_transaction_id(transaction_id: str) -> list[dict[str, Any]]:
    transaction = fetch_one_by_id("transactions", transaction_id, "*")
    if not transaction:
        return []
    return fetch_review_cluster_transactions(transaction)


def fetch_review_cluster_transactions(seed_transaction: dict[str, Any]) -> list[dict[str, Any]]:
    seed_key = review_group_key_from_transaction(seed_transaction)
    if seed_key.startswith("transaction:"):
        return [seed_transaction]

    employee_id = str(seed_transaction.get("employee_id") or "")
    if not employee_id:
        return [seed_transaction]

    candidates = fetch_rows_by_values("transactions", "employee_id", [employee_id], "*")
    cluster = [
        transaction
        for transaction in candidates
        if transaction.get("id") and review_group_key_from_transaction(transaction) == seed_key
    ]
    return cluster or [seed_transaction]


def approval_row_from_transaction(existing: dict[str, Any], transaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "employee_id": transaction.get("employee_id") or existing.get("employee_id"),
        "transaction_id": transaction.get("id") or existing.get("transaction_id"),
        "department_id": transaction.get("department_id") or existing.get("department_id"),
        "requested_amount_cad": transaction.get("amount_cad") or existing.get("requested_amount_cad") or 0,
        "created_at": existing.get("created_at"),
    }


def build_approval_context_snapshot(review_item: dict[str, Any]) -> ApprovalContextSnapshot:
    transaction_id = str(review_item.get("transaction_id") or "")
    transaction = fetch_one_by_id("transactions", transaction_id, "*")
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction was not found.")

    employee = fetch_one_by_id("employees", str(transaction.get("employee_id") or review_item.get("employee_id") or ""), "*")
    department = fetch_one_by_id("departments", str(transaction.get("department_id") or review_item.get("department_id") or ""), "*")
    policy = fetch_one_by_id("policy_checks", str(review_item.get("policy_check_id") or ""), "*")
    risk = fetch_one_by_id("risk_scores", str(review_item.get("risk_score_id") or ""), "*")
    if not policy:
        policy = latest_row_by_transaction("policy_checks", transaction_id)
    if not risk:
        risk = latest_row_by_transaction("risk_scores", transaction_id)
    policy_flags = review_item.get("policy_flags")
    if not isinstance(policy_flags, list):
        policy_flags = fetch_policy_flags(transaction_id)
    risk_signals = review_item.get("risk_signals")
    if not isinstance(risk_signals, list):
        risk_signals = list((risk or {}).get("signals") or [])
    budget = compose_department_budget_status(department, transaction)
    spend_history = compose_employee_spend_history(employee, transaction)

    return ApprovalContextSnapshot(
        transaction=transaction_summary(transaction),
        employee=person_summary(employee),
        department=department_summary(department),
        policy={
            "id": (policy or {}).get("id"),
            "status": (policy or {}).get("status") or review_item.get("policy_status"),
            "severity": (policy or {}).get("max_severity") or review_item.get("policy_severity"),
            "missing_information": list((policy or {}).get("missing_information") or []),
            "recommended_next_action": (policy or {}).get("recommended_next_action") or review_item.get("next_action"),
            "flags": policy_flags,
        },
        risk={
            "id": (risk or {}).get("id"),
            "score": int((risk or {}).get("risk_score") or review_item.get("risk_score") or 0),
            "level": (risk or {}).get("risk_level") or review_item.get("risk_level"),
            "signals": risk_signals,
        },
        budget=budget,
        spend_history=spend_history,
        review_queue={
            "id": review_item.get("id"),
            "queue_status": review_item.get("queue_status"),
            "review_priority": review_item.get("review_priority"),
            "review_level": review_item.get("review_level"),
            "next_action": review_item.get("next_action"),
            "reviewer_brief": review_item.get("reviewer_brief"),
        },
    )


def default_approval_recommendation_client() -> ApprovalRecommendationClient | None:
    try:
        from app.services.ai_service import default_approval_recommendation_client as default_client

        return default_client()
    except Exception:
        return None


def compose_approval_recommendation(
    snapshot: ApprovalContextSnapshot,
    client: ApprovalRecommendationClient | None = None,
) -> ApprovalRecommendation:
    fallback = deterministic_approval_recommendation(snapshot)
    if client:
        try:
            facts = approval_recommendation_facts(snapshot, fallback)
            return sanitize_ai_approval_recommendation(client.compose_approval_recommendation(facts), fallback)
        except Exception:
            return fallback
    return fallback


def deterministic_approval_recommendation(snapshot: ApprovalContextSnapshot) -> ApprovalRecommendation:
    policy_status = snapshot.policy.get("status")
    policy_flags = list(snapshot.policy.get("flags") or [])
    risk_level = snapshot.risk.get("level")
    risk_signals = list(snapshot.risk.get("signals") or [])
    missing_information = normalized_strings([*list(snapshot.policy.get("missing_information") or []), *budget_missing_context(snapshot)])
    grounded_inputs = approval_grounding_inputs(snapshot)

    blocking_rule_codes = {str(flag.get("rule_code") or "") for flag in policy_flags}
    if blocking_rule_codes & {"TICKETS_NOT_REIMBURSABLE", "PERSONAL_CARD_USE_PROHIBITED", "FALSIFICATION_PROHIBITED"}:
        return ApprovalRecommendation(
            recommendation="deny",
            confidence="high",
            rationale="Deterministic policy findings include a non-reimbursable or prohibited expense rule.",
            grounded_inputs=grounded_inputs,
            missing_information=missing_information,
        )

    if policy_status in {"approval_evidence_needed", "context_needed", "review_required"} or missing_information:
        return ApprovalRecommendation(
            recommendation="deny",
            confidence="medium",
            rationale="The packet shows missing approval evidence, business context, or policy support, so the approver should not approve it as-is.",
            grounded_inputs=grounded_inputs,
            missing_information=missing_information,
        )

    if risk_level in {"high", "critical"} or any(signal.get("severity") in {"high", "critical"} for signal in risk_signals):
        return ApprovalRecommendation(
            recommendation="deny",
            confidence="medium",
            rationale="Risk scoring attached high-priority anomaly signals, so the packet should be denied unless the approver has enough outside evidence.",
            grounded_inputs=grounded_inputs,
            missing_information=missing_information,
        )

    if policy_status == "policy_violation" and policy_flags:
        return ApprovalRecommendation(
            recommendation="deny",
            confidence="medium",
            rationale="The transaction has an open deterministic policy violation.",
            grounded_inputs=grounded_inputs,
            missing_information=missing_information,
        )

    if snapshot.budget.quarterly_remaining_cad < 0:
        return ApprovalRecommendation(
            recommendation="deny",
            confidence="medium",
            rationale="The department is over its synthetic quarterly budget after current posted spend.",
            grounded_inputs=grounded_inputs,
            missing_information=missing_information,
        )

    return ApprovalRecommendation(
        recommendation="approve",
        confidence="high" if snapshot.budget.quarterly_remaining_cad >= 0 else "medium",
        rationale="The request has no blocking policy finding, no high-risk signal, and remains within synthetic budget context.",
        grounded_inputs=grounded_inputs,
        missing_information=missing_information,
    )


def approval_recommendation_facts(
    snapshot: ApprovalContextSnapshot,
    fallback: ApprovalRecommendation,
) -> dict[str, Any]:
    return {
        "transaction": snapshot.transaction,
        "employee": snapshot.employee,
        "department": snapshot.department,
        "policy": snapshot.policy,
        "risk": snapshot.risk,
        "budget": snapshot.budget.model_dump(mode="json"),
        "spend_history": snapshot.spend_history.model_dump(mode="json"),
        "review_queue": snapshot.review_queue,
        "deterministic_fallback": fallback.model_dump(mode="json"),
        "instructions": [
            "Use only supplied facts.",
            "Treat this recommendation as advisory; a human approver makes the final decision.",
            "Do not recommend approve if deterministic_fallback is deny.",
        ],
    }


def sanitize_ai_approval_recommendation(
    recommendation: ApprovalRecommendation,
    fallback: ApprovalRecommendation,
) -> ApprovalRecommendation:
    allowed_grounding = set(fallback.grounded_inputs)
    grounded_inputs = [
        item
        for item in recommendation.grounded_inputs
        if item in allowed_grounding
    ] or fallback.grounded_inputs
    missing_information = normalized_strings([*fallback.missing_information, *recommendation.missing_information])
    selected = recommendation.recommendation
    rationale = recommendation.rationale or fallback.rationale

    if fallback.recommendation == "deny" and selected == "approve":
        selected = fallback.recommendation
        rationale = f"{fallback.rationale} AI approval wording was constrained by deterministic policy, risk, or missing-context facts."

    return ApprovalRecommendation(
        recommendation=selected,
        confidence=recommendation.confidence if recommendation.confidence in {"low", "medium", "high"} else fallback.confidence,
        rationale=rationale,
        grounded_inputs=grounded_inputs,
        missing_information=missing_information,
        source="openai_structured_output",
    )


def approval_grounding_inputs(snapshot: ApprovalContextSnapshot) -> list[str]:
    transaction = snapshot.transaction
    policy_status = snapshot.policy.get("status") or "not scanned"
    risk_level = snapshot.risk.get("level") or "low"
    return normalized_strings(
        [
            f"Transaction {transaction.get('merchant') or 'Unknown merchant'} for CAD {float(transaction.get('amount_cad') or 0):,.2f}.",
            f"Policy status: {policy_status}.",
            f"Risk level: {risk_level}; score {snapshot.risk.get('score') or 0}.",
            f"Department quarterly remaining: CAD {snapshot.budget.quarterly_remaining_cad:,.2f}.",
            f"Employee history: {snapshot.spend_history.transaction_count} transactions totaling CAD {snapshot.spend_history.total_spend_cad:,.2f}.",
        ]
    )


def compose_department_budget_status(department: dict[str, Any] | None, transaction: dict[str, Any]) -> DepartmentBudgetStatus:
    transaction_date = parse_date(transaction.get("transaction_date")) or date.today()
    department_id = str((department or {}).get("id") or transaction.get("department_id") or "")
    monthly_budget = float((department or {}).get("monthly_budget_cad") or 0)
    quarterly_budget = float((department or {}).get("quarterly_budget_cad") or 0)
    rows = fetch_department_transactions(department_id)
    month_start = transaction_date.replace(day=1)
    quarter_month = ((transaction_date.month - 1) // 3) * 3 + 1
    quarter_start = transaction_date.replace(month=quarter_month, day=1)
    month_spend = sum_amount_in_period(rows, month_start, transaction_date)
    quarter_spend = sum_amount_in_period(rows, quarter_start, transaction_date)

    return DepartmentBudgetStatus(
        department_id=department_id or None,
        department_name=(department or {}).get("name"),
        monthly_budget_cad=monthly_budget,
        quarterly_budget_cad=quarterly_budget,
        month_to_date_spend_cad=round(month_spend, 2),
        quarter_to_date_spend_cad=round(quarter_spend, 2),
        monthly_remaining_cad=round(monthly_budget - month_spend, 2),
        quarterly_remaining_cad=round(quarterly_budget - quarter_spend, 2),
        budget_period_month=transaction_date.strftime("%Y-%m"),
        budget_period_quarter=f"{transaction_date.year}-Q{((transaction_date.month - 1) // 3) + 1}",
        synthetic=bool((department or {}).get("synthetic", True)),
    )


def compose_employee_spend_history(employee: dict[str, Any] | None, transaction: dict[str, Any]) -> EmployeeSpendHistory:
    employee_id = str((employee or {}).get("id") or transaction.get("employee_id") or "")
    rows = fetch_rows_by_values("transactions", "employee_id", [employee_id], "*") if employee_id else []
    category = transaction.get("business_category") or transaction.get("policy_category") or transaction.get("normalized_category")
    same_category_rows = [
        row
        for row in rows
        if (row.get("business_category") or row.get("policy_category") or row.get("normalized_category")) == category
    ]
    approvals = fetch_rows_by_values("approval_requests", "employee_id", [employee_id], "*") if employee_id else []
    return EmployeeSpendHistory(
        employee_id=employee_id or None,
        employee_name=(employee or {}).get("full_name"),
        transaction_count=len(rows),
        total_spend_cad=round(sum(expense_amount(row) for row in rows), 2),
        same_category_count=len(same_category_rows),
        same_category_spend_cad=round(sum(expense_amount(row) for row in same_category_rows), 2),
        prior_approval_count=len(approvals),
        prior_approved_count=sum(1 for approval in approvals if approval.get("status") == "approved"),
    )


def approval_items_from_rows(rows: list[dict[str, Any]]) -> list[ApprovalRequestItem]:
    if not rows:
        return []
    transaction_ids = unique_ids(row.get("transaction_id") for row in rows)
    transactions = {str(row["id"]): row for row in fetch_rows_by_values("transactions", "id", transaction_ids, "*") if row.get("id")}
    employees = {str(row["id"]): row for row in fetch_rows_by_values("employees", "id", unique_ids(row.get("employee_id") for row in rows), "*") if row.get("id")}
    departments = {str(row["id"]): row for row in fetch_rows_by_values("departments", "id", unique_ids(row.get("department_id") for row in rows), "*") if row.get("id")}
    queue_items = {
        str(row["transaction_id"]): row
        for row in fetch_rows_by_values("review_queue_items", "transaction_id", transaction_ids, "*")
        if row.get("transaction_id")
    }
    return annotate_review_clusters(
        approval_item_from_row(
            row,
            transaction=transactions.get(str(row.get("transaction_id") or "")),
            employee=employees.get(str(row.get("employee_id") or "")),
            department=departments.get(str(row.get("department_id") or "")),
            review_item=queue_items.get(str(row.get("transaction_id") or "")),
        )
        for row in rows
    )


def approval_detail_from_row(row: dict[str, Any]) -> ApprovalRequestDetail:
    transaction = fetch_one_by_id("transactions", str(row.get("transaction_id") or ""), "*")
    employee = fetch_one_by_id("employees", str(row.get("employee_id") or ""), "*")
    department = fetch_one_by_id("departments", str(row.get("department_id") or ""), "*")
    review_item = latest_review_queue_item(str(row.get("transaction_id") or ""))
    item = approval_item_from_row(row, transaction=transaction, employee=employee, department=department, review_item=review_item)
    context_snapshot = row.get("context_snapshot") if isinstance(row.get("context_snapshot"), dict) else None
    parsed_snapshot = ApprovalContextSnapshot(**context_snapshot) if context_snapshot else None
    return ApprovalRequestDetail(
        **item.model_dump(),
        context_snapshot=parsed_snapshot,
        approval_explanation=build_approval_explanation(
            item=item,
            snapshot=parsed_snapshot,
            reviewer_brief=item.reviewer_brief,
        ),
    )


def approval_item_from_row(
    row: dict[str, Any],
    *,
    transaction: dict[str, Any] | None,
    employee: dict[str, Any] | None,
    department: dict[str, Any] | None,
    review_item: dict[str, Any] | None,
) -> ApprovalRequestItem:
    ai_recommendation = approval_recommendation_from_row(row.get("ai_recommendation"))
    reviewer_brief = (review_item or {}).get("reviewer_brief")
    budget = None
    spend_history = None
    snapshot = row.get("context_snapshot") if isinstance(row.get("context_snapshot"), dict) else None
    if snapshot:
        budget = snapshot.get("budget") if isinstance(snapshot.get("budget"), dict) else None
        spend_history = snapshot.get("spend_history") if isinstance(snapshot.get("spend_history"), dict) else None
    return ApprovalRequestItem(
        id=str(row["id"]),
        transaction_id=str(row["transaction_id"]),
        employee_id=str(row["employee_id"]),
        employee_name=(employee or {}).get("full_name"),
        department_id=str(row["department_id"]),
        department_name=(department or {}).get("name"),
        approver_name=(department or {}).get("manager_name"),
        status=row.get("status") or "requested",
        requested_amount_cad=float(row.get("requested_amount_cad") or 0),
        transaction_date=str((transaction or {}).get("transaction_date")) if (transaction or {}).get("transaction_date") else None,
        merchant=(transaction or {}).get("normalized_merchant_name") or (transaction or {}).get("merchant_name"),
        category=(transaction or {}).get("business_category")
        or (transaction or {}).get("policy_category")
        or (transaction or {}).get("normalized_category")
        or "Uncategorized",
        policy_check_id=str(row.get("policy_check_id")) if row.get("policy_check_id") else None,
        policy_status=(review_item or {}).get("policy_status"),
        policy_severity=(review_item or {}).get("policy_severity"),
        policy_flags=(review_item or {}).get("policy_flags") or [],
        risk_score_id=str(row.get("risk_score_id")) if row.get("risk_score_id") else None,
        risk_score=int((review_item or {}).get("risk_score") or 0),
        risk_level=(review_item or {}).get("risk_level"),
        risk_signals=[RiskSignal(**signal) for signal in (review_item or {}).get("risk_signals") or []],
        ai_recommendation=ai_recommendation,
        reviewer_brief=ReviewerBrief(**reviewer_brief) if isinstance(reviewer_brief, dict) else None,
        review_group_key=(
            review_item.get("review_group_key")
            or (
                review_group_key_from_transaction(transaction)
                if transaction
                else review_group_key_from_values(
                transaction_id=str(row.get("transaction_id") or ""),
                employee_id=str(row.get("employee_id")) if row.get("employee_id") else None,
                department_id=str(row.get("department_id")) if row.get("department_id") else None,
                merchant=None,
                transaction_date=None,
                category=None,
            )
            )
        ),
        review_group_size=1,
        review_group_total_amount_cad=float(row.get("requested_amount_cad") or (transaction or {}).get("amount_cad") or 0),
        review_group_transaction_ids=[str(row["transaction_id"])],
        budget_status=DepartmentBudgetStatus(**budget) if budget else None,
        spend_history=EmployeeSpendHistory(**spend_history) if spend_history else None,
        requester_note=row.get("requester_note"),
        decision_note=row.get("decision_note"),
        decided_by=row.get("decided_by"),
        decided_at=str(row.get("decided_at")) if row.get("decided_at") else None,
        created_at=str(row.get("created_at")) if row.get("created_at") else None,
        updated_at=str(row.get("updated_at")) if row.get("updated_at") else None,
    )


def approval_recommendation_from_row(value: Any) -> ApprovalRecommendation | None:
    if not isinstance(value, dict):
        return None

    payload = dict(value)
    if payload.get("recommendation") == "request_information":
        payload["recommendation"] = "deny"
        payload["rationale"] = (
            "The packet shows missing approval evidence, business context, or policy support, so the approver should not approve it as-is."
        )

    try:
        return ApprovalRecommendation(**payload)
    except ValidationError:
        return None


def build_approval_explanation(
    *,
    item: ApprovalRequestItem,
    snapshot: ApprovalContextSnapshot | None,
    reviewer_brief: ReviewerBrief | None,
) -> ApprovalExplanation | None:
    recommendation = item.ai_recommendation
    if not recommendation and snapshot:
        recommendation = compose_approval_recommendation(snapshot, client=None)
    if not recommendation:
        return None

    policy = snapshot.policy if snapshot else {}
    risk = snapshot.risk if snapshot else {}
    budget = snapshot.budget if snapshot else item.budget_status or DepartmentBudgetStatus()
    spend_history = snapshot.spend_history if snapshot else item.spend_history or EmployeeSpendHistory()
    policy_flags = list(policy.get("flags") or item.policy_flags or [])
    risk_signals = list(risk.get("signals") or [signal.model_dump(mode="json") for signal in item.risk_signals])
    missing_information = normalized_strings(
        [*recommendation.missing_information, *list(policy.get("missing_information") or [])]
    )
    cited_policy_clauses = list(reviewer_brief.cited_policy_clauses if reviewer_brief else [])
    blocking_reasons = approval_blocking_reasons(
        item=item,
        policy_flags=policy_flags,
        risk_signals=risk_signals,
        missing_information=missing_information,
        budget=budget,
    )
    supporting_evidence = approval_supporting_evidence(
        item=item,
        recommendation=recommendation,
        budget=budget,
        spend_history=spend_history,
    )
    would_change_outcome_if = approval_outcome_change_conditions(
        recommendation=recommendation,
        missing_information=missing_information,
        policy_flags=policy_flags,
        risk_signals=risk_signals,
        budget=budget,
        cited_policy_clauses=cited_policy_clauses,
    )

    return ApprovalExplanation(
        decision=recommendation.recommendation,
        confidence=recommendation.confidence,
        summary=approval_explanation_summary(
            recommendation=recommendation,
            blocking_reasons=blocking_reasons,
            missing_information=missing_information,
            cited_policy_clauses=cited_policy_clauses,
        ),
        blocking_reasons=blocking_reasons,
        supporting_evidence=supporting_evidence,
        missing_information=missing_information,
        cited_policy_clauses=cited_policy_clauses,
        would_change_outcome_if=would_change_outcome_if,
    )


def approval_blocking_reasons(
    *,
    item: ApprovalRequestItem,
    policy_flags: list[dict[str, Any]],
    risk_signals: list[dict[str, Any]],
    missing_information: list[str],
    budget: DepartmentBudgetStatus,
) -> list[ApprovalExplanationReason]:
    reasons: list[ApprovalExplanationReason] = []
    seen: set[str] = set()

    if missing_information:
        detail = "The packet is missing evidence or business context required before approval."
        reasons.append(ApprovalExplanationReason(label="Missing required context", severity="blocking", detail=detail))
        seen.add(detail)

    for flag in policy_flags[:3]:
        rule_code = str(flag.get("rule_code") or "Policy finding")
        explanation = str(flag.get("explanation") or "A deterministic policy rule matched this transaction.")
        required_action = str(flag.get("required_action") or "").strip()
        detail = explanation if not required_action else f"{explanation} Next step: {required_action}"
        if detail in seen:
            continue
        reasons.append(
            ApprovalExplanationReason(
                label=format_reason_label(rule_code),
                severity="blocking" if str(item.policy_status or "").lower() in {"policy_violation", "approval_evidence_needed", "context_needed", "review_required"} else "warning",
                detail=detail,
            )
        )
        seen.add(detail)

    for signal in risk_signals[:3]:
        message = str(signal.get("message") or "Risk scoring attached a material anomaly signal.")
        if message in seen:
            continue
        severity = str(signal.get("severity") or "medium").lower()
        reasons.append(
            ApprovalExplanationReason(
                label=f"{format_reason_label(str(signal.get('type') or 'risk signal'))} risk",
                severity="blocking" if severity in {"high", "critical"} else "warning",
                detail=message,
            )
        )
        seen.add(message)

    if budget.quarterly_remaining_cad < 0:
        detail = (
            f"Department quarterly remaining budget is CAD {budget.quarterly_remaining_cad:,.2f}, so the request lands beyond the synthetic budget envelope."
        )
        if detail not in seen:
            reasons.append(ApprovalExplanationReason(label="Budget overrun", severity="blocking", detail=detail))

    return reasons


def approval_supporting_evidence(
    *,
    item: ApprovalRequestItem,
    recommendation: ApprovalRecommendation,
    budget: DepartmentBudgetStatus,
    spend_history: EmployeeSpendHistory,
) -> list[str]:
    evidence = [
        f"AI recommendation: {format_reason_label(recommendation.recommendation)} with {recommendation.confidence} confidence.",
        f"Transaction amount: CAD {item.requested_amount_cad:,.2f} at {item.merchant or 'Unknown merchant'}.",
        f"Policy status: {format_reason_label(item.policy_status or 'compliant')}.",
        f"Risk level: {format_reason_label(item.risk_level or 'low')} with score {item.risk_score}.",
        f"Department quarterly remaining: CAD {budget.quarterly_remaining_cad:,.2f}.",
        f"Employee history: {spend_history.transaction_count} transactions totaling CAD {spend_history.total_spend_cad:,.2f}; prior approvals {spend_history.prior_approved_count}/{spend_history.prior_approval_count}.",
    ]
    return normalized_strings([*recommendation.grounded_inputs, *evidence])


def approval_outcome_change_conditions(
    *,
    recommendation: ApprovalRecommendation,
    missing_information: list[str],
    policy_flags: list[dict[str, Any]],
    risk_signals: list[dict[str, Any]],
    budget: DepartmentBudgetStatus,
    cited_policy_clauses: list[CitedPolicyClause],
) -> list[str]:
    if recommendation.recommendation == "approve":
        return ["No blocking policy, risk, or budget condition is currently attached to this packet."]

    next_steps: list[str] = []
    for item in missing_information:
        next_steps.append(f"Attach or confirm {item}.")
    for flag in policy_flags:
        required_action = str(flag.get("required_action") or "").strip()
        if required_action:
            next_steps.append(required_action)
    if any(str(signal.get("severity") or "").lower() in {"high", "critical"} for signal in risk_signals):
        next_steps.append("Add supporting evidence that resolves the anomaly signals or confirms the business purpose.")
    if budget.quarterly_remaining_cad < 0:
        next_steps.append("Document a budget exception or move the spend into an approved funding path.")
    if cited_policy_clauses:
        next_steps.append("Show why the packet satisfies the cited policy clauses, or clarify why the rule should not apply.")
    if not next_steps:
        next_steps.append("Provide stronger business justification or correct the underlying transaction classification.")
    return normalized_strings(next_steps)


def approval_explanation_summary(
    *,
    recommendation: ApprovalRecommendation,
    blocking_reasons: list[ApprovalExplanationReason],
    missing_information: list[str],
    cited_policy_clauses: list[CitedPolicyClause],
) -> str:
    if recommendation.recommendation == "approve":
        return (
            "Approve is recommended because the packet has no blocking policy finding, no unresolved high-risk signal, "
            "and the current budget context remains within range."
        )

    if blocking_reasons:
        top_labels = ", ".join(reason.label for reason in blocking_reasons[:3])
        clause_note = " Matching policy citations are attached." if cited_policy_clauses else ""
        return f"Deny is recommended because the packet currently shows {top_labels}.{clause_note}"

    if missing_information:
        return "Deny is recommended until the packet includes the missing approval evidence or business context."

    return recommendation.rationale


def format_reason_label(value: str) -> str:
    return value.replace("_", " ").strip().title()


def update_preapproval_from_decision(existing: dict[str, Any], request: ApprovalDecisionRequest, decided_at: str) -> None:
    transaction_id = str(existing.get("transaction_id") or "")
    status = DECISION_TO_PREAPPROVAL_STATUS[request.decision]
    payload = {
        "employee_id": existing.get("employee_id"),
        "transaction_id": transaction_id,
        "department_id": existing.get("department_id"),
        "requested_amount_cad": existing.get("requested_amount_cad") or 0,
        "status": status,
        "approver_name": request.actor,
        "approved_at": decided_at if request.decision == "approved" else None,
        "synthetic": True,
    }
    current = latest_row_by_transaction("preapprovals", transaction_id)
    if current and current.get("id"):
        get_supabase_client().table("preapprovals").update(payload).eq("id", current["id"]).execute()
    else:
        payload["requested_at"] = existing.get("created_at") or decided_at
        get_supabase_client().table("preapprovals").insert(payload).execute()


def update_review_queue_status(transaction_id: str, queue_status: str) -> None:
    try:
        get_supabase_client().table("review_queue_items").update({"queue_status": queue_status}).eq(
            "transaction_id", transaction_id
        ).execute()
    except APIError:
        return


def insert_audit_event(action: str, entity_id: str, actor: str | None, details: dict[str, Any]) -> None:
    payload = {
        "action": action,
        "entity_type": "approval_request",
        "entity_id": entity_id,
        "details": {"actor": actor or "Finance Manager", **details},
    }
    try:
        get_supabase_client().table("audit_log").insert(payload).execute()
    except APIError:
        return


def fetch_approval_audit_events(approval_id: str) -> list[dict[str, Any]]:
    try:
        return (
            get_supabase_client()
            .table("audit_log")
            .select("*")
            .eq("entity_type", "approval_request")
            .eq("entity_id", approval_id)
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
    except APIError:
        return []


def fetch_existing_open_approval(transaction_id: str) -> dict[str, Any] | None:
    rows = (
        get_supabase_client()
        .table("approval_requests")
        .select("*")
        .eq("transaction_id", transaction_id)
        .in_("status", list(OPEN_APPROVAL_STATUSES))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def fetch_one_by_id(table_name: str, row_id: str, columns: str) -> dict[str, Any] | None:
    if not row_id:
        return None
    rows = get_supabase_client().table(table_name).select(columns).eq("id", row_id).limit(1).execute().data or []
    return rows[0] if rows else None


def latest_row_by_transaction(table_name: str, transaction_id: str) -> dict[str, Any] | None:
    if not transaction_id:
        return None
    rows = (
        get_supabase_client()
        .table(table_name)
        .select("*")
        .eq("transaction_id", transaction_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def latest_review_queue_item(transaction_id: str) -> dict[str, Any] | None:
    rows = (
        get_supabase_client()
        .table("review_queue_items")
        .select("*")
        .eq("transaction_id", transaction_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def fetch_policy_flags(transaction_id: str) -> list[dict[str, Any]]:
    rows = fetch_rows_by_values("violations", "transaction_id", [transaction_id], "*")
    return [
        {
            "rule_code": row.get("rule_code"),
            "severity": row.get("severity"),
            "explanation": row.get("explanation"),
            "required_action": row.get("required_action"),
        }
        for row in rows
    ]


def fetch_department_transactions(department_id: str) -> list[dict[str, Any]]:
    if not department_id:
        return []
    return fetch_rows_by_values("transactions", "department_id", [department_id], "id,transaction_date,amount_cad,debit_credit")


def fetch_rows_by_values(table_name: str, column_name: str, values: list[str], columns: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunked(unique_ids(values), 100):
        if not chunk:
            continue
        rows.extend(get_supabase_client().table(table_name).select(columns).in_(column_name, chunk).execute().data or [])
    return rows


def transaction_summary(transaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(transaction.get("id") or ""),
        "employee_id": transaction.get("employee_id"),
        "department_id": transaction.get("department_id"),
        "transaction_date": str(transaction.get("transaction_date")) if transaction.get("transaction_date") else None,
        "merchant": transaction.get("normalized_merchant_name") or transaction.get("merchant_name"),
        "amount_cad": float(transaction.get("amount_cad") or 0),
        "category": transaction.get("business_category")
        or transaction.get("policy_category")
        or transaction.get("normalized_category")
        or "Uncategorized",
        "business_purpose": transaction.get("business_purpose"),
        "guest_names": transaction.get("guest_names") or [],
        "synthetic_assignment": bool(transaction.get("synthetic_assignment", True)),
    }


def person_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": str(row.get("id") or ""),
        "full_name": row.get("full_name"),
        "email": row.get("email"),
        "role": row.get("role"),
        "manager_employee_id": row.get("manager_employee_id"),
        "synthetic": bool(row.get("synthetic", True)),
    }


def department_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": str(row.get("id") or ""),
        "name": row.get("name"),
        "manager_name": row.get("manager_name"),
        "monthly_budget_cad": float(row.get("monthly_budget_cad") or 0),
        "quarterly_budget_cad": float(row.get("quarterly_budget_cad") or 0),
        "synthetic": bool(row.get("synthetic", True)),
    }


def sum_amount_in_period(rows: list[dict[str, Any]], start: date, end: date) -> float:
    total = 0.0
    for row in rows:
        value_date = parse_date(row.get("transaction_date"))
        if value_date and start <= value_date <= end:
            total += expense_amount(row)
    return total


def expense_amount(row: dict[str, Any]) -> float:
    if row.get("debit_credit") == "credit":
        return 0.0
    return max(0.0, float(row.get("amount_cad") or 0))


def parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None
    return None


def normalized_strings(values: list[Any]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen.setdefault(text, None)
    return list(seen.keys())


def unique_ids(values) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def budget_missing_context(snapshot: ApprovalContextSnapshot) -> list[str]:
    missing = []
    if not snapshot.budget.department_id:
        missing.append("department budget unavailable")
    if snapshot.budget.quarterly_budget_cad == 0:
        missing.append("quarterly budget amount unavailable")
    return missing
