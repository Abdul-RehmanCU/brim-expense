from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from app.database.supabase_client import get_supabase_client
from app.schemas.common import PlaceholderResponse
from app.schemas.approvals import ApprovalRequestCreate
from app.schemas.policy import PolicyScanRequest
from app.schemas.reports import (
    ExpenseReportDetail,
    ExpenseReportLineItem,
    ExpenseReportListResponse,
    ExpenseReportSummary,
    ReportGenerateResponse,
    ReportCsvResponse,
    ReportGenerateRequest,
    ReportMetric,
    ReportNarrative,
    ReportPlanTarget,
    ReportScopeDepartmentOption,
    ReportScopeEmployeeOption,
    ReportScopeOptionsResponse,
    ReportSpec,
    ReportVisualResult,
    ReportVisualRow,
    ReportVisualSeries,
    ReportVisualSpec,
)
from app.schemas.review_queue import CitedPolicyClause
from app.schemas.risk import RiskScanRequest
from app.services.approvals_service import approval_recommendation_from_row, create_approval_request
from app.services.ai_service import AnthropicJsonClient, default_report_narrative_client
from app.services.rag_service import retrieve_policy_chunks
from app.services.policy_service import scan_transactions as scan_policy_transactions
from app.services.review_grouping import annotate_review_clusters, review_group_key_from_transaction, review_group_key_from_values
from app.services.review_queue_service import (
    fetch_policy_citations_by_rule_code,
    policy_citations_for_flags,
    refresh_review_queue_for_transaction_ids,
)
from app.services.risk_service import scan_risk_scores

RISK_FLAG_LEVELS = {"medium", "high", "critical"}
POLICY_CLEAR_STATUSES = {"compliant", "excluded_non_expense"}
MISSING_RECEIPT_STATUSES = {"missing", "unavailable", "rejected"}
MISSING_PREAPPROVAL_STATUSES = {"missing", "denied"}
OPEN_APPROVAL_STATUSES = {"draft", "requested"}
TRAVEL_EVENT_CATEGORY_KEYWORDS = (
    "travel",
    "lodging",
    "hotel",
    "air",
    "flight",
    "conference",
    "meal",
    "entertainment",
    "transport",
    "parking",
    "taxi",
    "uber",
)
EVENT_CLUSTER_WINDOW_DAYS = 10
RECENT_ACTIVITY_WINDOW_DAYS = 30
EVENT_LOOKBACK_DAYS = 180


@dataclass(frozen=True)
class PlannedReportScope:
    scope_type: str
    requested_label: str
    employee_id: str | None = None
    employee_name: str | None = None
    department_id: str | None = None
    department_name: str | None = None


@dataclass(frozen=True)
class PlannedReportRequest:
    planner_source: str
    sql_preview: str | None
    warnings: list[str]
    targets: list[PlannedReportScope]
    report_spec: ReportSpec | None = None


@dataclass(frozen=True)
class ReportSelection:
    period_start: str
    period_end: str
    transactions: list[dict[str, Any]]
    grouping_reason: str


@dataclass(frozen=True)
class ReportWorkflowMetrics:
    missing_receipt_count: int = 0
    missing_preapproval_count: int = 0
    approval_request_count: int = 0
    open_approval_count: int = 0
    policy_flag_count: int = 0
    risk_flag_count: int = 0
    policy_unscanned_count: int = 0
    risk_unscanned_count: int = 0
    approval_ready: bool = False
    workflow_status: str = "action_required"
    blocker_count: int = 0
    approval_recommendation_counts: dict[str, int] = field(default_factory=dict)
    cfo_next_actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReportWorkflowRefreshResult:
    policy_scanned: bool = False
    risk_scanned: bool = False
    review_queue_refreshed: bool = False
    approval_requests_created: int = 0
    warnings: list[str] = field(default_factory=list)


def get_reports_status() -> PlaceholderResponse:
    return PlaceholderResponse(
        status="implemented",
        service="reports",
        implemented=True,
        message="Expense report generation, detail, listing, and CSV export are available.",
    )


def list_report_scope_options() -> ReportScopeOptionsResponse:
    client = get_supabase_client()
    employee_rows = client.table("employees").select("id, full_name, department_id").order("full_name").execute().data or []
    department_rows = client.table("departments").select("id, name").order("name").execute().data or []
    latest_transaction_rows = (
        client.table("transactions").select("transaction_date").not_.is_("transaction_date", "null").order("transaction_date", desc=True).limit(1).execute().data
        or []
    )
    department_name_by_id = {
        str(department.get("id") or ""): str(department.get("name") or "")
        for department in department_rows
        if department.get("id")
    }

    return ReportScopeOptionsResponse(
        employees=[
            ReportScopeEmployeeOption(
                id=str(employee.get("id") or ""),
                full_name=str(employee.get("full_name") or "Unknown employee"),
                department_id=str(employee.get("department_id") or "") or None,
                department_name=department_name_by_id.get(str(employee.get("department_id") or "")) or None,
            )
            for employee in employee_rows
            if employee.get("id")
        ],
        departments=[
            ReportScopeDepartmentOption(
                id=str(department.get("id") or ""),
                name=str(department.get("name") or "Unknown department"),
            )
            for department in department_rows
            if department.get("id")
        ],
        latest_transaction_date=str(latest_transaction_rows[0].get("transaction_date") or "") or None,
    )


def generate_reports(request: ReportGenerateRequest | None = None) -> ReportGenerateResponse:
    request = request or ReportGenerateRequest()
    client = get_supabase_client()
    planned = plan_report_request(client, request)
    report_scopes, targets = expand_planned_scopes(client, planned.targets)

    if not report_scopes:
        raise HTTPException(status_code=404, detail="No report scopes matched the requested prompt.")

    shared_period_hint = derive_shared_period_hint(client, report_scopes, request)
    reports = [
        generate_report_for_scope(
            client,
            scope,
            request,
            planned.report_spec,
            period_hint=shared_period_hint if should_align_scope_to_shared_period(scope, report_scopes, request) else None,
        )
        for scope in report_scopes
    ]
    return ReportGenerateResponse(
        request=request.request,
        planner_source=planned.planner_source,  # type: ignore[arg-type]
        sql_preview=planned.sql_preview,
        generated_count=len(reports),
        targets=targets,
        warnings=planned.warnings,
        reports=reports,
    )


def generate_report(request: ReportGenerateRequest | None = None) -> ExpenseReportDetail:
    request = request or ReportGenerateRequest()
    client = get_supabase_client()
    employee = resolve_employee(client, request)
    return generate_report_for_scope(
        client,
        PlannedReportScope(
            scope_type="employee",
            requested_label=str(employee.get("full_name") or "Employee"),
            employee_id=str(employee["id"]),
            employee_name=str(employee.get("full_name") or "Employee"),
            department_id=str(employee.get("department_id") or ""),
        ),
        request,
        None,
    )


def refresh_report_workflow_for_selection(
    *,
    scope: PlannedReportScope,
    owner_employee: dict[str, Any],
    department: dict[str, Any],
    request: ReportGenerateRequest,
    period_start: str,
    period_end: str,
    transaction_ids: list[str],
) -> ReportWorkflowRefreshResult:
    if not request.refresh_workflow:
        return ReportWorkflowRefreshResult()

    warnings: list[str] = []
    policy_scanned = False
    risk_scanned = False
    review_queue_refreshed = False
    approval_requests_created = 0
    scan_filters = {
        "employee_id": str(owner_employee.get("id") or "") if scope.scope_type == "employee" else None,
        "department_id": str(department.get("id") or "") if scope.scope_type == "department" else None,
        "date_start": period_start,
        "date_end": period_end,
    }

    try:
        scan_policy_transactions(
            PolicyScanRequest(
                employee_id=scan_filters["employee_id"],
                department_id=scan_filters["department_id"],
                date_start=period_start,
                date_end=period_end,
                reset_existing=False,
                reset_synthetic_evidence=False,
            )
        )
        policy_scanned = True
    except Exception as error:
        warnings.append(f"Policy refresh failed before report packaging: {error}")

    try:
        scan_risk_scores(
            RiskScanRequest(
                employee_id=scan_filters["employee_id"],
                department_id=scan_filters["department_id"],
                date_start=period_start,
                date_end=period_end,
                reset_existing=False,
            )
        )
        risk_scanned = True
    except Exception as error:
        warnings.append(f"Risk refresh failed before report packaging: {error}")

    try:
        refresh_review_queue_for_transaction_ids(transaction_ids, persist=True)
        review_queue_refreshed = True
    except Exception as error:
        warnings.append(f"Review queue refresh failed before report packaging: {error}")

    if review_queue_refreshed:
        try:
            selected_queue_items = fetch_rows_by_values(
                get_supabase_client(),
                "review_queue_items",
                "transaction_id",
                transaction_ids,
                "*",
            )
            for item in selected_queue_items:
                if str(item.get("queue_status") or "") not in {"open", "in_approval"}:
                    continue
                if int(item.get("review_priority") or 0) <= 0:
                    continue
                approval = create_approval_request(
                    ApprovalRequestCreate(
                        review_queue_item_id=str(item["id"]),
                        actor="Report Workflow",
                    )
                )
                if approval and approval.id:
                    approval_requests_created += 1
        except Exception as error:
            warnings.append(f"Approval packet creation failed before report packaging: {error}")

    return ReportWorkflowRefreshResult(
        policy_scanned=policy_scanned,
        risk_scanned=risk_scanned,
        review_queue_refreshed=review_queue_refreshed,
        approval_requests_created=approval_requests_created,
        warnings=warnings,
    )


def generate_report_for_scope(
    client: Any,
    scope: PlannedReportScope,
    request: ReportGenerateRequest,
    planned_report_spec: ReportSpec | None,
    period_hint: tuple[str, str] | None = None,
) -> ExpenseReportDetail:
    owner_employee, department, employee_ids, owner_label = resolve_scope_context(client, scope)
    scope_transactions = fetch_scope_transactions(client, employee_ids)
    selection = select_report_transactions(client, scope, scope_transactions, request, period_hint=period_hint)
    period_start, period_end, transactions = selection.period_start, selection.period_end, selection.transactions

    if not transactions:
        raise HTTPException(
            status_code=404,
            detail=f"No transactions found for {owner_label} from {period_start} to {period_end}.",
        )

    transaction_ids = [str(transaction["id"]) for transaction in transactions]
    workflow_refresh = refresh_report_workflow_for_selection(
        scope=scope,
        owner_employee=owner_employee,
        department=department,
        request=request,
        period_start=period_start,
        period_end=period_end,
        transaction_ids=transaction_ids,
    )
    policy_by_transaction_id = latest_by_transaction_id(
        fetch_rows_by_values(client, "policy_checks", "transaction_id", transaction_ids, "*")
    )
    risk_by_transaction_id = latest_by_transaction_id(
        fetch_rows_by_values(client, "risk_scores", "transaction_id", transaction_ids, "*")
    )
    violations = fetch_rows_by_values(client, "violations", "transaction_id", transaction_ids, "*")
    receipts_by_transaction_id = latest_by_transaction_id(
        fetch_rows_by_values(client, "receipts", "transaction_id", transaction_ids, "*")
    )
    preapprovals_by_transaction_id = latest_by_transaction_id(
        fetch_rows_by_values(client, "preapprovals", "transaction_id", transaction_ids, "*")
    )
    approvals_by_transaction_id = latest_by_transaction_id(
        fetch_rows_by_values(client, "approval_requests", "transaction_id", transaction_ids, "*")
    )
    review_queue_by_transaction_id = latest_by_transaction_id(
        fetch_rows_by_values(client, "review_queue_items", "transaction_id", transaction_ids, "*")
    )

    line_items = compose_line_items(
        transactions,
        policy_by_transaction_id,
        risk_by_transaction_id,
        receipts_by_transaction_id,
        preapprovals_by_transaction_id,
        approvals_by_transaction_id,
        review_queue_by_transaction_id,
    )
    line_items = annotate_review_clusters(line_items)
    total_amount_cad = round(sum(item.amount_cad for item in line_items), 2)
    workflow_metrics = summarize_report_workflow_metrics(
        transactions,
        policy_by_transaction_id,
        risk_by_transaction_id,
        receipts_by_transaction_id,
        preapprovals_by_transaction_id,
        approvals_by_transaction_id,
        review_queue_by_transaction_id,
    )
    report_spec = finalize_report_spec(scope, owner_label, planned_report_spec)
    policy_clauses = build_report_policy_clauses(
        transactions=transactions,
        violations=violations,
        review_queue_items=list(review_queue_by_transaction_id.values()),
        workflow_metrics=workflow_metrics,
        report_label=report_spec.title,
        department=department,
    )
    narrative = compose_report_narrative(
        report_label=report_spec.title,
        period_start=period_start,
        period_end=period_end,
        item_count=len(line_items),
        total_amount_cad=total_amount_cad,
        workflow_metrics=workflow_metrics,
        grouping_reason=selection.grouping_reason,
        transactions=transactions,
        policy_clauses=policy_clauses,
    )
    report_name = narrative.title or report_spec.title
    report_spec = report_spec.model_copy(update={"title": report_name})
    summary = narrative.summary
    visuals = compile_report_visuals(
        client,
        report_spec,
        transactions,
        policy_by_transaction_id,
        risk_by_transaction_id,
    )

    report_row = {
        "employee_id": owner_employee["id"],
        "department_id": department["id"],
        "report_name": report_name,
        "report_spec": report_spec.model_dump(mode="json"),
        "period_start": period_start,
        "period_end": period_end,
        "status": "generated",
        "total_amount_cad": total_amount_cad,
        "missing_receipt_count": workflow_metrics.missing_receipt_count,
        "policy_flag_count": workflow_metrics.policy_flag_count,
        "risk_flag_count": workflow_metrics.risk_flag_count,
        "ai_summary": summary,
        "workflow_status": workflow_metrics.workflow_status,
        "workflow_snapshot": compose_report_workflow_snapshot(workflow_metrics, workflow_refresh),
        "synthetic": True,
    }
    inserted_reports = client.table("expense_reports").insert(report_row).execute().data or []
    if not inserted_reports:
        raise HTTPException(status_code=500, detail="Could not create expense report.")

    report = inserted_reports[0]
    report_id = str(report["id"])
    item_rows = [
        {
            "report_id": report_id,
            "transaction_id": item.transaction_id,
            "amount_cad": item.amount_cad,
            "category": item.category,
            "policy_status": item.policy_status,
            "risk_level": item.risk_level,
            "review_queue_item_id": item.review_queue_item_id,
            "approval_request_id": item.approval_request_id,
            "approval_recommendation": line_item_approval_recommendation_snapshot(item),
            "reviewer_next_action": item.reviewer_next_action,
        }
        for item in line_items
    ]
    inserted_items = client.table("expense_report_items").insert(item_rows).execute().data or []
    items_by_transaction_id = {str(item["transaction_id"]): item for item in inserted_items if item.get("transaction_id")}
    persisted_line_items = [
        item.model_copy(update={"id": str(items_by_transaction_id.get(item.transaction_id, {}).get("id") or item.id)})
        for item in line_items
    ]

    return compose_report_detail(
        report,
        owner_employee,
        department,
        persisted_line_items,
        report_name_override=report_name,
        report_spec=report_spec,
        visuals=visuals,
        workflow_metrics=workflow_metrics,
        report_scope_type=scope.scope_type,
        grouping_reason=selection.grouping_reason,
        policy_clauses=policy_clauses,
    )


def list_reports(limit: int = 25, offset: int = 0) -> ExpenseReportListResponse:
    client = get_supabase_client()
    rows = client.table("expense_reports").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute().data or []
    report_ids = [str(row["id"]) for row in rows if row.get("id")]
    employees_by_id, departments_by_id = fetch_people_for_reports(client, rows)
    report_item_rows = fetch_rows_by_values(client, "expense_report_items", "report_id", report_ids, "report_id,transaction_id")
    item_counts = count_items_by_report_id(report_item_rows)
    transactions_by_id = fetch_transactions_for_report_items(client, report_item_rows)
    evidence = fetch_report_evidence(client, list(transactions_by_id))
    report_name_overrides = infer_report_name_overrides(report_item_rows, transactions_by_id, departments_by_id)
    workflow_metrics_by_report_id = summarize_workflow_metrics_by_report_id(
        report_item_rows,
        transactions_by_id,
        evidence,
    )
    scope_type_by_report_id = infer_report_scope_type_by_report_id(report_item_rows, transactions_by_id)

    return ExpenseReportListResponse(
        reports=[
            compose_report_summary(
                row,
                employees_by_id.get(str(row.get("employee_id") or "")),
                departments_by_id.get(str(row.get("department_id") or "")),
                item_counts.get(str(row.get("id") or ""), 0),
                report_name_override=report_name_overrides.get(str(row.get("id") or "")),
                workflow_metrics=workflow_metrics_by_report_id.get(str(row.get("id") or "")),
                report_scope_type=scope_type_by_report_id.get(str(row.get("id") or ""), "employee"),
            )
            for row in rows
        ]
    )


def get_report(report_id: str) -> ExpenseReportDetail:
    client = get_supabase_client()
    report = fetch_one_by_id(client, "expense_reports", report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Expense report not found.")

    item_rows = (
        client.table("expense_report_items")
        .select("*")
        .eq("report_id", report_id)
        .order("created_at")
        .execute()
        .data
        or []
    )
    transaction_ids = [str(item["transaction_id"]) for item in item_rows if item.get("transaction_id")]
    transactions_by_id = {
        str(row["id"]): row for row in fetch_rows_by_values(client, "transactions", "id", transaction_ids, "*") if row.get("id")
    }
    evidence = fetch_report_evidence(client, transaction_ids)
    violations = fetch_rows_by_values(client, "violations", "transaction_id", transaction_ids, "*")
    employee = fetch_one_by_id(client, "employees", str(report.get("employee_id") or ""))
    department = fetch_one_by_id(client, "departments", str(report.get("department_id") or ""))

    line_items = annotate_review_clusters([
        compose_line_item_from_report_item(
            item,
            transactions_by_id.get(str(item.get("transaction_id") or "")),
            evidence["policy"].get(str(item.get("transaction_id") or "")),
            evidence["risk"].get(str(item.get("transaction_id") or "")),
            evidence["receipts"].get(str(item.get("transaction_id") or "")),
            evidence["preapprovals"].get(str(item.get("transaction_id") or "")),
            evidence["approvals"].get(str(item.get("transaction_id") or "")),
            evidence["review_queue"].get(str(item.get("transaction_id") or "")),
        )
        for item in item_rows
    ])
    workflow_metrics = summarize_report_workflow_metrics(
        [transactions_by_id[transaction_id] for transaction_id in transaction_ids if transaction_id in transactions_by_id],
        evidence["policy"],
        evidence["risk"],
        evidence["receipts"],
        evidence["preapprovals"],
        evidence["approvals"],
        evidence["review_queue"],
    )

    report_name_override = infer_report_name_override_for_report(
        report_id,
        item_rows,
        transactions_by_id,
        department,
    )
    policy_clauses = build_report_policy_clauses(
        transactions=[transactions_by_id[transaction_id] for transaction_id in transaction_ids if transaction_id in transactions_by_id],
        violations=violations,
        review_queue_items=list(evidence["review_queue"].values()),
        workflow_metrics=workflow_metrics,
        report_label=report_name_override or string_or_none(report.get("report_name")) or "Expense Report",
        department=department,
    )
    report_spec = hydrate_report_spec(report.get("report_spec"), report_name_override or string_or_none(report.get("report_name")) or "")
    visuals = compile_report_visuals_from_items(client, report_spec, item_rows, line_items, transactions_by_id)
    report_scope_type = infer_report_scope_type(item_rows, transactions_by_id)
    return compose_report_detail(
        report,
        employee,
        department,
        line_items,
        report_name_override=report_name_override,
        report_spec=report_spec,
        visuals=visuals,
        workflow_metrics=workflow_metrics,
        report_scope_type=report_scope_type,
        grouping_reason=infer_grouping_reason_from_report(report_scope_type, transactions_by_id, item_rows),
        policy_clauses=policy_clauses,
    )


def export_report_csv(report_id: str) -> ReportCsvResponse:
    report = get_report(report_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["Report ID", report.id])
    writer.writerow(["Report Name", report.report_name or ""])
    writer.writerow(["Employee", report.employee_name or ""])
    writer.writerow(["Department", report.department_name or ""])
    writer.writerow(["Period", f"{report.period_start} to {report.period_end}"])
    writer.writerow(["Total CAD", f"{report.total_amount_cad:.2f}"])
    writer.writerow(["Missing receipt count", report.missing_receipt_count])
    writer.writerow(["Missing preapproval count", report.missing_preapproval_count])
    writer.writerow(["Approval request count", report.approval_request_count])
    writer.writerow(["Open approval count", report.open_approval_count])
    writer.writerow(["Policy flag count", report.policy_flag_count])
    writer.writerow(["Risk flag count", report.risk_flag_count])
    writer.writerow(["Policy unscanned count", report.policy_unscanned_count])
    writer.writerow(["Risk unscanned count", report.risk_unscanned_count])
    writer.writerow(["Approval ready", "yes" if report.approval_ready else "no"])
    writer.writerow(["Workflow status", report.workflow_status])
    writer.writerow(["Blocker count", report.blocker_count])
    writer.writerow(["Approval recommendations", json.dumps(report.approval_recommendation_counts, ensure_ascii=True)])
    writer.writerow(["CFO next actions", "; ".join(report.cfo_next_actions)])
    writer.writerow(["Grouping reason", report.grouping_reason or ""])
    writer.writerow(["Summary", report.ai_summary or ""])
    if report.policy_clauses:
        writer.writerow([])
        writer.writerow(["Policy Clauses"])
        writer.writerow(["Rule Code", "Title", "Text", "Match Score"])
        for clause in report.policy_clauses:
            writer.writerow([clause.rule_code or "", clause.title or "", clause.text, clause.match_score or ""])
    writer.writerow([])
    writer.writerow(
        [
            "Date",
            "Merchant",
            "Category",
            "Amount CAD",
            "Receipt Status",
            "Preapproval Status",
            "Approval Status",
            "Policy Status",
            "Risk Level",
            "Approval Request ID",
            "Approval Recommendation",
            "Approval Rationale",
            "Reviewer Next Action",
            "Business Purpose",
            "Guest Names",
            "Transaction ID",
        ]
    )
    for item in report.line_items:
        writer.writerow(
            [
                item.transaction_date or "",
                item.merchant or "",
                item.category,
                f"{item.amount_cad:.2f}",
                item.receipt_status or "",
                item.preapproval_status or "",
                item.approval_status or "",
                item.policy_status or "",
                item.risk_level or "",
                item.approval_request_id or "",
                item.approval_recommendation or "",
                item.approval_recommendation_rationale or "",
                item.reviewer_next_action or "",
                item.business_purpose or "",
                "; ".join(item.guest_names),
                item.transaction_id,
            ]
        )

    safe_employee = slugify(report.report_name or report.employee_name or "expense-report")
    return ReportCsvResponse(file_name=f"{safe_employee}-{report.period_start}-{report.period_end}.csv", csv=buffer.getvalue())


def plan_report_request(client: Any, request: ReportGenerateRequest) -> PlannedReportRequest:
    if request.request and request.request.strip():
        planned = plan_report_request_with_ai(client, request)
        if planned:
            return planned

    return deterministic_report_plan(client, request, warnings=[])


def plan_report_request_with_ai(client: Any, request: ReportGenerateRequest) -> PlannedReportRequest | None:
    if not request.request or not request.request.strip():
        return None

    warnings: list[str] = []
    employees = client.table("employees").select("id, full_name, department_id").execute().data or []
    departments = client.table("departments").select("id, name").execute().data or []
    payload = {
        "request": request.request,
        "explicit_filters": {
            "employee_id": request.employee_id,
            "employee_name": request.employee_name,
            "department_id": request.department_id,
            "department_name": request.department_name,
            "date_start": request.date_start,
            "date_end": request.date_end,
        },
        "available_employees": [
            {"id": str(employee.get("id") or ""), "full_name": str(employee.get("full_name") or "")}
            for employee in employees
        ],
        "available_departments": [
            {"id": str(department.get("id") or ""), "name": str(department.get("name") or "")}
            for department in departments
        ],
        "allowed_visual_dimensions": ["employee", "department", "business_category", "month", "merchant"],
        "allowed_visual_metrics": ["sum_amount_cad", "transaction_count", "policy_flag_count", "risk_flag_count"],
        "allowed_chart_types": ["bar", "line", "pie", "table"],
        "instructions": [
            "Return strict JSON only.",
            "Extract every requested report target from the prompt.",
            "Use scope_type employee or department.",
            "If the prompt asks for a team, department, or group, emit one department target instead of inventing employee targets.",
            "Do not invent names that are not in the provided employee or department lists.",
            "Prefer exact matches from provided names and ids.",
            "Produce one concise report_spec that can be safely compiled against the allowed dimensions, metrics, and chart types.",
            "When a team or department report asks for spending per person, use dimension employee and metric sum_amount_cad.",
            "Provide a compact sql_preview that would filter transactions for the requested targets.",
        ],
        "output_shape": {
            "targets": [{"scope_type": "employee|department", "employee_name": None, "department_name": None}],
            "report_spec": {
                "title": "Human-friendly report title",
                "summary": "Short explanation of the generated report",
                "visuals": [
                    {
                        "title": "Chart title",
                        "subtitle": "Optional chart subtitle",
                        "chart_type": "bar|line|pie|table",
                        "dimension": "employee|department|business_category|month|merchant",
                        "metric": "sum_amount_cad|transaction_count|policy_flag_count|risk_flag_count",
                        "limit": 10,
                        "sort_direction": "asc|desc",
                    }
                ],
            },
            "sql_preview": "select ... where ...",
            "warnings": ["optional warning strings"],
        },
    }

    try:
        completion = AnthropicJsonClient()
        planner_response = completion.complete_json(
            system_prompt=(
                "You are a report request planner for an expense platform. "
                "Translate user report requests into strict JSON targets, a safe report_spec, and a SQL preview only. "
                "Do not return Markdown. Do not add prose outside JSON."
            ),
            user_prompt=json.dumps(payload, ensure_ascii=True),
        )
    except Exception:
        return None

    reviewed_response = review_report_plan_with_ai(completion, payload, planner_response)
    response = reviewed_response or planner_response

    targets = parse_ai_targets(response)
    if not targets:
        warnings.append("AI planner returned no usable targets; used deterministic fallback.")
        return deterministic_report_plan(client, request, warnings=warnings)

    sql_preview = string_or_none(response.get("sql_preview")) or build_sql_preview(targets, request)
    report_spec = parse_report_spec(response.get("report_spec"))
    if reviewed_response:
        warnings.append("AI critic reviewed and refined the requested report shape.")
    merged_warnings = warnings + [str(item) for item in response.get("warnings") or [] if str(item).strip()]
    return PlannedReportRequest(
        planner_source="claude_critic" if reviewed_response else "claude_fallback",
        sql_preview=sql_preview,
        warnings=merged_warnings,
        targets=targets,
        report_spec=report_spec,
    )


def parse_ai_targets(payload: dict[str, Any]) -> list[PlannedReportScope]:
    parsed: list[PlannedReportScope] = []
    for raw_target in payload.get("targets") or []:
        if not isinstance(raw_target, dict):
            continue
        scope_type = str(raw_target.get("scope_type") or "").lower().strip()
        if scope_type not in {"employee", "department"}:
            continue
        employee_name = string_or_none(raw_target.get("employee_name"))
        department_name = string_or_none(raw_target.get("department_name"))
        requested_label = employee_name or department_name or scope_type.title()
        parsed.append(
            PlannedReportScope(
                scope_type=scope_type,
                requested_label=requested_label,
                employee_name=employee_name,
                department_name=department_name,
            )
        )
    return dedupe_planned_targets(parsed)


def parse_report_spec(payload: Any) -> ReportSpec | None:
    if not isinstance(payload, dict):
        return None

    title = string_or_none(payload.get("title"))
    if not title:
        return None

    visuals: list[ReportVisualSpec] = []
    for index, raw_visual in enumerate(payload.get("visuals") or []):
        if not isinstance(raw_visual, dict):
            continue
        visual_title = string_or_none(raw_visual.get("title"))
        chart_type = string_or_none(raw_visual.get("chart_type"))
        dimension = string_or_none(raw_visual.get("dimension"))
        metric = string_or_none(raw_visual.get("metric"))
        if not visual_title or not chart_type or not dimension or not metric:
            continue
        try:
            visuals.append(
                ReportVisualSpec(
                    id=string_or_none(raw_visual.get("id")) or f"visual_{index + 1}",
                    title=visual_title,
                    subtitle=string_or_none(raw_visual.get("subtitle")),
                    chart_type=chart_type,  # type: ignore[arg-type]
                    dimension=dimension,  # type: ignore[arg-type]
                    metric=metric,  # type: ignore[arg-type]
                    limit=int(raw_visual.get("limit") or 10),
                    sort_direction=(string_or_none(raw_visual.get("sort_direction")) or "desc"),  # type: ignore[arg-type]
                )
            )
        except Exception:
            continue

    return ReportSpec(
        title=title,
        summary=string_or_none(payload.get("summary")),
        visuals=visuals,
    )


def review_report_plan_with_ai(
    completion: AnthropicJsonClient,
    planner_payload: dict[str, Any],
    planner_response: dict[str, Any],
) -> dict[str, Any] | None:
    critic_payload = {
        "original_request": planner_payload.get("request"),
        "available_employees": planner_payload.get("available_employees"),
        "available_departments": planner_payload.get("available_departments"),
        "allowed_visual_dimensions": planner_payload.get("allowed_visual_dimensions"),
        "allowed_visual_metrics": planner_payload.get("allowed_visual_metrics"),
        "allowed_chart_types": planner_payload.get("allowed_chart_types"),
        "candidate_plan": planner_response,
        "instructions": [
            "Return strict JSON only.",
            "Repair the plan if it invents names, uses unsupported dimensions, metrics, or chart types, or mismatches the prompt.",
            "Keep department/team requests grouped as one department target.",
            "Preserve the user's requested analytical shape when possible.",
            "If the plan is already valid, return it unchanged.",
        ],
    }

    try:
        return completion.complete_json(
            system_prompt=(
                "You are a strict report-plan critic. "
                "Validate and repair a candidate JSON report plan against the supplied schema and reporting rules. "
                "Do not return Markdown or prose outside JSON."
            ),
            user_prompt=json.dumps(critic_payload, ensure_ascii=True),
        )
    except Exception:
        return None


def deterministic_report_plan(client: Any, request: ReportGenerateRequest, warnings: list[str]) -> PlannedReportRequest:
    targets: list[PlannedReportScope] = []
    employees = client.table("employees").select("id, full_name, department_id").execute().data or []
    departments = client.table("departments").select("id, name").execute().data or []
    normalized_request = normalize_text(request.request or "")

    if request.employee_id or request.employee_name:
        targets.append(
            PlannedReportScope(
                scope_type="employee",
                requested_label=request.employee_name or request.employee_id or "Employee",
                employee_id=request.employee_id,
                employee_name=request.employee_name,
            )
        )

    if request.department_id or request.department_name:
        targets.append(
            PlannedReportScope(
                scope_type="department",
                requested_label=request.department_name or request.department_id or "Department",
                department_id=request.department_id,
                department_name=request.department_name,
            )
        )

    for employee in employees:
        full_name = string_or_none(employee.get("full_name"))
        if full_name and normalize_text(full_name) in normalized_request:
            targets.append(
                PlannedReportScope(
                    scope_type="employee",
                    requested_label=full_name,
                    employee_id=str(employee.get("id") or ""),
                    employee_name=full_name,
                )
            )

    for department in departments:
        department_name = string_or_none(department.get("name"))
        if not department_name:
            continue
        department_tokens = {normalize_text(department_name), normalize_text(f"{department_name} team"), normalize_text(f"{department_name} team's")}
        if normalized_request and any(token in normalized_request for token in department_tokens):
            targets.append(
                PlannedReportScope(
                    scope_type="department",
                    requested_label=department_name,
                    department_id=str(department.get("id") or ""),
                    department_name=department_name,
                )
            )

    if not targets:
        requested_name = request.employee_name or extract_employee_name(request.request or "") or "Sarah Chen"
        targets.append(
            PlannedReportScope(
                scope_type="employee",
                requested_label=requested_name,
                employee_name=requested_name,
            )
        )

    targets = dedupe_planned_targets(targets)
    primary_target = targets[0] if targets else None
    return PlannedReportRequest(
        planner_source="deterministic",
        sql_preview=build_sql_preview(targets, request),
        warnings=warnings,
        targets=targets,
        report_spec=default_report_spec(primary_target) if len(targets) == 1 else None,
    )


def dedupe_planned_targets(targets: list[PlannedReportScope]) -> list[PlannedReportScope]:
    seen: set[tuple[str, str]] = set()
    deduped: list[PlannedReportScope] = []
    for target in targets:
        key = (target.scope_type, normalize_text(target.employee_name or target.department_name or target.requested_label))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped


def build_sql_preview(targets: list[PlannedReportScope], request: ReportGenerateRequest) -> str:
    clauses: list[str] = []
    employee_names = [target.employee_name for target in targets if target.scope_type == "employee" and target.employee_name]
    department_names = [target.department_name for target in targets if target.scope_type == "department" and target.department_name]
    if employee_names:
        names = ", ".join(f"'{normalize_text(name)}'" for name in employee_names)
        clauses.append(f"lower(e.full_name) in ({names})")
    if department_names:
        names = ", ".join(f"'{normalize_text(name)}'" for name in department_names)
        clauses.append(f"lower(d.name) in ({names})")

    date_start = request.date_start or extract_date(request.request or "", "start")
    date_end = request.date_end or extract_date(request.request or "", "end")
    date_clause = ""
    if date_start and date_end:
        date_clause = f" and t.transaction_date between '{date_start}' and '{date_end}'"

    where_clause = " or ".join(clauses) if clauses else "1 = 1"
    return (
        "select e.full_name, d.name as department_name, t.transaction_date, t.normalized_merchant_name, t.amount_cad "
        "from transactions t "
        "join employees e on e.id = t.employee_id "
        "join departments d on d.id = t.department_id "
        f"where ({where_clause}){date_clause} "
        "order by e.full_name, t.transaction_date;"
    )


def expand_planned_scopes(client: Any, targets: list[PlannedReportScope]) -> tuple[list[PlannedReportScope], list[ReportPlanTarget]]:
    report_scopes: list[PlannedReportScope] = []
    summarized_targets: list[ReportPlanTarget] = []

    for target in targets:
        if target.scope_type == "employee":
            employee = resolve_employee_scope(client, target)
            report_scopes.append(
                PlannedReportScope(
                    scope_type="employee",
                    requested_label=target.requested_label,
                    employee_id=str(employee["id"]),
                    employee_name=str(employee.get("full_name") or "Employee"),
                    department_id=str(employee.get("department_id") or ""),
                )
            )
            summarized_targets.append(
                ReportPlanTarget(
                    scope_type="employee",
                    requested_label=target.requested_label,
                    resolved_label=str(employee.get("full_name") or target.requested_label),
                    report_count=1,
                )
            )
            continue

        department = resolve_department_scope(client, target)
        employees = (
            client.table("employees")
            .select("*")
            .eq("department_id", str(department["id"]))
            .order("full_name")
            .execute()
            .data
            or []
        )
        if not employees:
            raise HTTPException(status_code=404, detail=f"No employees found for department '{department.get('name')}'.")

        report_scopes.append(
            PlannedReportScope(
                scope_type="department",
                requested_label=target.requested_label,
                department_id=str(department["id"]),
                department_name=str(department.get("name") or ""),
            )
        )
        summarized_targets.append(
            ReportPlanTarget(
                scope_type="department",
                requested_label=target.requested_label,
                resolved_label=str(department.get("name") or target.requested_label),
                report_count=1,
            )
        )

    deduped_scopes: list[PlannedReportScope] = []
    seen_scope_keys: set[tuple[str, str]] = set()
    for scope in report_scopes:
        scope_key = (
            scope.scope_type,
            scope.employee_id or scope.department_id or normalize_text(scope.requested_label),
        )
        if scope_key in seen_scope_keys:
            continue
        seen_scope_keys.add(scope_key)
        deduped_scopes.append(scope)
    return deduped_scopes, summarized_targets


def resolve_employee(client: Any, request: ReportGenerateRequest) -> dict[str, Any]:
    if request.employee_id:
        employee = fetch_one_by_id(client, "employees", request.employee_id)
        if employee:
            return employee
        raise HTTPException(status_code=404, detail="Employee not found.")

    requested_name = request.employee_name or extract_employee_name(request.request or "") or "Sarah Chen"
    employees = client.table("employees").select("*").execute().data or []
    normalized_requested_name = normalize_text(requested_name)
    for employee in employees:
        if normalize_text(str(employee.get("full_name") or "")) == normalized_requested_name:
            return employee

    for employee in employees:
        if normalized_requested_name in normalize_text(str(employee.get("full_name") or "")):
            return employee

    if requested_name == "Sarah Chen":
        raise HTTPException(status_code=404, detail="Default Sarah Chen scenario requires a Sarah Chen employee row.")
    raise HTTPException(status_code=404, detail=f"Employee '{requested_name}' was not found.")


def resolve_employee_scope(client: Any, scope: PlannedReportScope) -> dict[str, Any]:
    if scope.employee_id:
        employee = fetch_one_by_id(client, "employees", scope.employee_id)
        if employee:
            return employee

    if scope.employee_name:
        employees = client.table("employees").select("*").execute().data or []
        normalized_name = normalize_text(scope.employee_name)
        for employee in employees:
            if normalize_text(str(employee.get("full_name") or "")) == normalized_name:
                return employee
        for employee in employees:
            if normalized_name in normalize_text(str(employee.get("full_name") or "")):
                return employee
        raise HTTPException(status_code=404, detail=f"Employee '{scope.employee_name}' was not found.")

    raise HTTPException(status_code=422, detail="Employee scope is missing an employee identifier.")


def resolve_department_scope(client: Any, scope: PlannedReportScope) -> dict[str, Any]:
    if scope.department_id:
        department = fetch_one_by_id(client, "departments", scope.department_id)
        if department:
            return department

    departments = client.table("departments").select("*").execute().data or []
    if scope.department_name:
        normalized_name = normalize_text(scope.department_name)
        for department in departments:
            if normalize_text(str(department.get("name") or "")) == normalized_name:
                return department
        for department in departments:
            if normalized_name in normalize_text(str(department.get("name") or "")):
                return department
        raise HTTPException(status_code=404, detail=f"Department '{scope.department_name}' was not found.")

    raise HTTPException(status_code=422, detail="Department scope is missing a department identifier.")


def should_align_scope_to_shared_period(
    scope: PlannedReportScope,
    report_scopes: list[PlannedReportScope],
    request: ReportGenerateRequest,
) -> bool:
    requested_start, requested_end = resolve_requested_period(request)
    return (
        scope.scope_type == "department"
        and requested_start is None
        and requested_end is None
        and any(candidate.scope_type == "employee" for candidate in report_scopes)
    )


def derive_shared_period_hint(
    client: Any,
    report_scopes: list[PlannedReportScope],
    request: ReportGenerateRequest,
) -> tuple[str, str] | None:
    requested_start, requested_end = resolve_requested_period(request)
    if requested_start or requested_end:
        return None

    employee_scopes = [scope for scope in report_scopes if scope.scope_type == "employee"]
    department_scopes = [scope for scope in report_scopes if scope.scope_type == "department"]
    if not employee_scopes or not department_scopes:
        return None

    for scope in employee_scopes:
        _, _, employee_ids, _ = resolve_scope_context(client, scope)
        selection = select_report_transactions(client, scope, fetch_scope_transactions(client, employee_ids), request)
        if selection.transactions:
            return selection.period_start, selection.period_end
    return None


def resolve_requested_period(request: ReportGenerateRequest) -> tuple[str | None, str | None]:
    requested_start = request.date_start or extract_date(request.request or "", "start")
    requested_end = request.date_end or extract_date(request.request or "", "end")
    if requested_start and requested_end and requested_end < requested_start:
        raise HTTPException(status_code=422, detail="date_end must be on or after date_start.")
    return requested_start, requested_end


def fetch_scope_transactions(client: Any, employee_ids: list[str]) -> list[dict[str, Any]]:
    rows = fetch_rows_by_values(client, "transactions", "employee_id", employee_ids, "*")
    return sorted(
        [row for row in rows if row.get("transaction_date")],
        key=lambda row: (str(row.get("transaction_date") or ""), str(row.get("id") or "")),
    )


def select_report_transactions(
    client: Any,
    scope: PlannedReportScope,
    transactions: list[dict[str, Any]],
    request: ReportGenerateRequest,
    period_hint: tuple[str, str] | None = None,
) -> ReportSelection:
    requested_start, requested_end = resolve_requested_period(request)
    if requested_start and requested_end:
        filtered = filter_transactions_by_period(transactions, requested_start, requested_end)
        return ReportSelection(
            period_start=requested_start,
            period_end=requested_end,
            transactions=filtered,
            grouping_reason="Used the explicitly requested report period.",
        )

    if period_hint:
        period_start, period_end = expand_period_hint_for_scope(scope, period_hint)
        filtered = filter_transactions_by_period(transactions, period_start, period_end)
        if filtered:
            return ReportSelection(
                period_start=period_start,
                period_end=period_end,
                transactions=filtered,
                grouping_reason="Aligned this report to the related employee expense window.",
            )

    if not transactions:
        today = date.today().isoformat()
        return ReportSelection(today, today, [], "No dated transactions were available for grouping.")

    workflow_selection = select_current_workflow_transactions(client, scope, transactions)
    if workflow_selection:
        return workflow_selection

    clustered = select_best_recent_cluster(scope, transactions)
    if clustered:
        return clustered

    latest_transaction_date = max(parse_transaction_date(row) for row in transactions if parse_transaction_date(row) is not None)
    assert latest_transaction_date is not None
    recent_start = max(
        parse_transaction_date(transactions[0]) or latest_transaction_date,
        latest_transaction_date - timedelta(days=RECENT_ACTIVITY_WINDOW_DAYS - 1),
    )
    filtered = [
        row
        for row in transactions
        if parse_transaction_date(row) is not None and recent_start <= parse_transaction_date(row) <= latest_transaction_date
    ]
    if not filtered:
        filtered = transactions[-min(10, len(transactions)) :]
    return ReportSelection(
        period_start=str(filtered[0].get("transaction_date") or latest_transaction_date.isoformat()),
        period_end=str(filtered[-1].get("transaction_date") or latest_transaction_date.isoformat()),
        transactions=filtered,
        grouping_reason="No strong event cluster was found, so the report used the most recent expense activity window.",
    )


def select_current_workflow_transactions(
    client: Any,
    scope: PlannedReportScope,
    transactions: list[dict[str, Any]],
) -> ReportSelection | None:
    transaction_ids = [str(row["id"]) for row in transactions if row.get("id")]
    if not transaction_ids:
        return None

    review_items = fetch_rows_by_values(client, "review_queue_items", "transaction_id", transaction_ids, "*")
    approval_items = fetch_rows_by_values(client, "approval_requests", "transaction_id", transaction_ids, "*")
    workflow_by_transaction_id: dict[str, dict[str, Any]] = {}

    for item in review_items:
        transaction_id = str(item.get("transaction_id") or "")
        if not transaction_id:
            continue
        if str(item.get("queue_status") or "") in {"open", "in_approval", "resolved"} or int(item.get("review_priority") or 0) > 0:
            workflow_by_transaction_id.setdefault(transaction_id, {})["review"] = item

    for approval in approval_items:
        transaction_id = str(approval.get("transaction_id") or "")
        if not transaction_id:
            continue
        workflow_by_transaction_id.setdefault(transaction_id, {})["approval"] = approval

    if not workflow_by_transaction_id:
        return None

    transaction_by_id = {str(row["id"]): row for row in transactions if row.get("id")}
    anchors = [
        transaction_by_id[transaction_id]
        for transaction_id in workflow_by_transaction_id
        if transaction_id in transaction_by_id and parse_transaction_date(transaction_by_id[transaction_id]) is not None
    ]
    if not anchors:
        return None

    anchor = max(
        anchors,
        key=lambda row: (
            workflow_transaction_score(row, workflow_by_transaction_id.get(str(row.get("id") or ""), {})),
            parse_transaction_date(row) or date.min,
            abs(float(row.get("amount_cad") or 0)),
        ),
    )
    anchor_date = str(anchor.get("transaction_date") or "")
    anchor_merchant = normalize_text(transaction_merchant(anchor))
    anchor_category = normalize_text(transaction_category(anchor))
    anchor_employee_id = str(anchor.get("employee_id") or "")

    clustered = [
        row
        for row in transactions
        if str(row.get("transaction_date") or "") == anchor_date
        and normalize_text(transaction_merchant(row)) == anchor_merchant
        and normalize_text(transaction_category(row)) == anchor_category
        and (scope.scope_type == "department" or str(row.get("employee_id") or "") == anchor_employee_id)
    ]
    selected = clustered or [anchor]
    anchor_workflow = workflow_by_transaction_id.get(str(anchor.get("id") or ""), {})
    anchor_approval = anchor_workflow.get("approval") if isinstance(anchor_workflow.get("approval"), dict) else {}
    has_final_approval = str(anchor_approval.get("status") or "").lower() in {"approved", "denied", "cancelled"}
    if len(selected) < 2 and not has_final_approval:
        return None

    selected = sorted(selected, key=lambda row: (str(row.get("transaction_date") or ""), str(row.get("id") or "")))
    period_start = str(selected[0].get("transaction_date") or anchor_date)
    period_end = str(selected[-1].get("transaction_date") or anchor_date)
    label = transaction_merchant(anchor) or "current workflow item"
    return ReportSelection(
        period_start=period_start,
        period_end=period_end,
        transactions=selected,
        grouping_reason=(
            f"Prioritized the current approval/review workflow cluster for {label} "
            f"so report status matches Review and Approvals."
        ),
    )


def workflow_transaction_score(transaction: dict[str, Any], workflow: dict[str, Any]) -> float:
    review = workflow.get("review") if isinstance(workflow.get("review"), dict) else {}
    approval = workflow.get("approval") if isinstance(workflow.get("approval"), dict) else {}
    approval_status = str(approval.get("status") or "").lower()
    review_status = str(review.get("queue_status") or "").lower()
    risk_level = str(review.get("risk_level") or "").lower()
    review_level = str(review.get("review_level") or "").lower()
    severity_score = {
        "critical": 40,
        "high": 30,
        "medium": 20,
        "low": 5,
    }
    status_score = 0
    if approval_status in {"denied", "approved", "cancelled"}:
        status_score += 90
    elif approval_status in OPEN_APPROVAL_STATUSES:
        status_score += 70
    if review_status in {"open", "in_approval"}:
        status_score += 50
    elif review_status == "resolved":
        status_score += 35

    transaction_date = parse_transaction_date(transaction) or date.min
    date_score = transaction_date.toordinal() / 100000
    return (
        status_score
        + int(review.get("review_priority") or 0)
        + severity_score.get(risk_level, 0)
        + severity_score.get(review_level, 0)
        + date_score
    )


def select_best_recent_cluster(scope: PlannedReportScope, transactions: list[dict[str, Any]]) -> ReportSelection | None:
    dated_transactions = [row for row in transactions if parse_transaction_date(row) is not None]
    if len(dated_transactions) < 2:
        return None

    latest_transaction_date = max(parse_transaction_date(row) for row in dated_transactions if parse_transaction_date(row) is not None)
    assert latest_transaction_date is not None
    lookback_start = latest_transaction_date - timedelta(days=EVENT_LOOKBACK_DAYS)
    candidates = [row for row in dated_transactions if parse_transaction_date(row) is not None and parse_transaction_date(row) >= lookback_start]
    best_selection: ReportSelection | None = None
    best_score = float("-inf")

    for index, transaction in enumerate(candidates):
        anchor_date = parse_transaction_date(transaction)
        if anchor_date is None:
            continue
        window_end = anchor_date + timedelta(days=EVENT_CLUSTER_WINDOW_DAYS)
        cluster = [
            row
            for row in candidates[index:]
            if parse_transaction_date(row) is not None and anchor_date <= parse_transaction_date(row) <= window_end
        ]
        if len(cluster) < 2:
            continue
        score = score_transaction_cluster(scope, cluster, latest_transaction_date)
        if score > best_score:
            best_score = score
            best_selection = ReportSelection(
                period_start=str(cluster[0].get("transaction_date") or anchor_date.isoformat()),
                period_end=str(cluster[-1].get("transaction_date") or window_end.isoformat()),
                transactions=cluster,
                grouping_reason=describe_transaction_cluster(scope, cluster),
            )

    return best_selection if best_score >= 18 else None


def score_transaction_cluster(scope: PlannedReportScope, cluster: list[dict[str, Any]], latest_transaction_date: date) -> float:
    cluster_end = parse_transaction_date(cluster[-1]) or latest_transaction_date
    size = len(cluster)
    unique_categories = len({normalize_text(transaction_category(row)) for row in cluster if transaction_category(row)})
    unique_days = len({str(row.get("transaction_date") or "") for row in cluster})
    travel_hits = sum(1 for row in cluster if transaction_looks_like_event_expense(row))
    purpose_hits = sum(1 for row in cluster if string_or_none(row.get("business_purpose")) or row.get("guest_names"))
    employee_count = len({str(row.get("employee_id") or "") for row in cluster if row.get("employee_id")})
    size_score = max(0, 20 - abs(size - 8) * 2)
    recency_score = max(0, 16 - (latest_transaction_date - cluster_end).days)
    multi_day_score = min(unique_days, 5) * 2
    diversity_score = min(unique_categories, 5) * 2
    travel_score = travel_hits * 4
    purpose_score = purpose_hits * 3
    cross_employee_score = 8 if scope.scope_type == "department" and employee_count > 1 else 0
    amount_score = min(sum(abs(float(row.get("amount_cad") or 0)) for row in cluster) / 500, 10)
    oversize_penalty = max(0, size - 18) * 1.5
    return size_score + recency_score + multi_day_score + diversity_score + travel_score + purpose_score + cross_employee_score + amount_score - oversize_penalty


def describe_transaction_cluster(scope: PlannedReportScope, cluster: list[dict[str, Any]]) -> str:
    event_like_count = sum(1 for row in cluster if transaction_looks_like_event_expense(row))
    team_segment = " for the team" if scope.scope_type == "department" else ""
    if event_like_count:
        return (
            f"Grouped a recent {len(cluster)}-transaction expense cluster{team_segment} with travel or event-style activity "
            f"across {str(cluster[0].get('transaction_date') or '')} to {str(cluster[-1].get('transaction_date') or '')}."
        )
    return (
        f"Grouped a recent {len(cluster)}-transaction expense window{team_segment} across "
        f"{str(cluster[0].get('transaction_date') or '')} to {str(cluster[-1].get('transaction_date') or '')}."
    )


def filter_transactions_by_period(transactions: list[dict[str, Any]], period_start: str, period_end: str) -> list[dict[str, Any]]:
    return [
        row
        for row in transactions
        if period_start <= str(row.get("transaction_date") or "") <= period_end
    ]


def expand_period_hint_for_scope(scope: PlannedReportScope, period_hint: tuple[str, str]) -> tuple[str, str]:
    if scope.scope_type != "department":
        return period_hint

    start_date = date.fromisoformat(period_hint[0])
    end_date = date.fromisoformat(period_hint[1])
    return (
        (start_date - timedelta(days=2)).isoformat(),
        (end_date + timedelta(days=max(2, EVENT_CLUSTER_WINDOW_DAYS // 2))).isoformat(),
    )


def default_report_spec(scope: PlannedReportScope | None, owner_label: str | None = None) -> ReportSpec:
    if scope and scope.scope_type == "department":
        team_label = owner_label or f"{scope.department_name or scope.requested_label or 'Team'} Team"
        return ReportSpec(
            title=f"{team_label} Report",
            summary="Department-level expense report with spending grouped by employee.",
            visuals=[
                ReportVisualSpec(
                    id="spend_per_employee",
                    title="Spend per employee",
                    subtitle="How total spend is distributed across the team.",
                    chart_type="bar",
                    dimension="employee",
                    metric="sum_amount_cad",
                    limit=12,
                    sort_direction="desc",
                )
            ],
        )

    employee_label = owner_label or (scope.employee_name if scope else None) or "Employee"
    return ReportSpec(
        title=f"{employee_label} Expense Report",
        summary="Employee expense report grouped by business category.",
        visuals=[
            ReportVisualSpec(
                id="spend_by_category",
                title="Spend by category",
                subtitle="Where this report is spending by business category.",
                chart_type="bar",
                dimension="business_category",
                metric="sum_amount_cad",
                limit=8,
                sort_direction="desc",
            )
        ],
    )


def finalize_report_spec(scope: PlannedReportScope, owner_label: str, planned_report_spec: ReportSpec | None) -> ReportSpec:
    fallback = default_report_spec(scope, owner_label)
    source = planned_report_spec or fallback
    visuals = [sanitize_visual_spec(visual) for visual in source.visuals if is_supported_visual(visual)]
    if not visuals:
        return fallback

    title = string_or_none(source.title) or fallback.title
    summary = string_or_none(source.summary) or fallback.summary
    return ReportSpec(title=title, summary=summary, visuals=visuals)


def hydrate_report_spec(payload: Any, fallback_title: str) -> ReportSpec | None:
    parsed = parse_report_spec(payload) if payload else None
    if not parsed:
        return None

    visuals = [sanitize_visual_spec(visual) for visual in parsed.visuals if is_supported_visual(visual)]
    if not visuals:
        return None

    return ReportSpec(
        title=string_or_none(parsed.title) or fallback_title,
        summary=string_or_none(parsed.summary),
        visuals=visuals,
    )


def sanitize_visual_spec(visual: ReportVisualSpec) -> ReportVisualSpec:
    return ReportVisualSpec(
        id=visual.id or slugify(visual.title),
        title=visual.title.strip(),
        subtitle=string_or_none(visual.subtitle),
        chart_type=visual.chart_type,
        dimension=visual.dimension,
        metric=visual.metric,
        limit=max(1, min(int(visual.limit or 10), 20)),
        sort_direction=visual.sort_direction,
    )


def is_supported_visual(visual: ReportVisualSpec) -> bool:
    return (
        visual.chart_type in {"bar", "line", "pie", "table"}
        and visual.dimension in {"employee", "department", "business_category", "month", "merchant"}
        and visual.metric in {"sum_amount_cad", "transaction_count", "policy_flag_count", "risk_flag_count"}
    )


def compile_report_visuals(
    client: Any,
    report_spec: ReportSpec,
    transactions: list[dict[str, Any]],
    policy_by_transaction_id: dict[str, dict[str, Any]],
    risk_by_transaction_id: dict[str, dict[str, Any]],
) -> list[ReportVisualResult]:
    records = build_report_records_from_transactions(client, transactions, policy_by_transaction_id, risk_by_transaction_id)
    return compile_visual_results(report_spec, records)


def compile_report_visuals_from_items(
    client: Any,
    report_spec: ReportSpec | None,
    _item_rows: list[dict[str, Any]],
    line_items: list[ExpenseReportLineItem],
    transactions_by_id: dict[str, dict[str, Any]],
) -> list[ReportVisualResult]:
    if not report_spec:
        return []

    records = build_report_records_from_line_items(client, line_items, transactions_by_id)
    return compile_visual_results(report_spec, records)


def build_report_records_from_transactions(
    client: Any,
    transactions: list[dict[str, Any]],
    policy_by_transaction_id: dict[str, dict[str, Any]],
    risk_by_transaction_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    employee_ids = [str(transaction.get("employee_id") or "") for transaction in transactions if transaction.get("employee_id")]
    department_ids = [str(transaction.get("department_id") or "") for transaction in transactions if transaction.get("department_id")]
    employees_by_id = {
        str(row["id"]): row
        for row in fetch_rows_by_values(client, "employees", "id", employee_ids, "id,full_name")
        if row.get("id")
    }
    departments_by_id = {
        str(row["id"]): row
        for row in fetch_rows_by_values(client, "departments", "id", department_ids, "id,name")
        if row.get("id")
    }

    records: list[dict[str, Any]] = []
    for transaction in transactions:
        transaction_id = str(transaction.get("id") or "")
        employee_id = str(transaction.get("employee_id") or "")
        department_id = str(transaction.get("department_id") or "")
        records.append(
            {
                "employee_id": employee_id,
                "employee_name": string_or_none((employees_by_id.get(employee_id) or {}).get("full_name")) or "Unknown employee",
                "department_id": department_id,
                "department_name": string_or_none((departments_by_id.get(department_id) or {}).get("name")) or "Unknown department",
                "transaction_date": str(transaction.get("transaction_date") or ""),
                "merchant": string_or_none(transaction.get("normalized_merchant_name"))
                or string_or_none(transaction.get("merchant_name"))
                or "Unknown merchant",
                "business_category": string_or_none(transaction.get("business_category"))
                or string_or_none(transaction.get("normalized_category"))
                or "Uncategorized",
                "amount_cad": float(transaction.get("amount_cad") or 0),
                "policy_status": string_or_none((policy_by_transaction_id.get(transaction_id) or {}).get("status")) or "unscanned",
                "risk_level": string_or_none((risk_by_transaction_id.get(transaction_id) or {}).get("risk_level")) or "unscanned",
            }
        )
    return records


def build_report_records_from_line_items(
    client: Any,
    line_items: list[ExpenseReportLineItem],
    transactions_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    employee_ids = [
        str(transactions_by_id.get(item.transaction_id, {}).get("employee_id") or "")
        for item in line_items
        if transactions_by_id.get(item.transaction_id, {}).get("employee_id")
    ]
    department_ids = [
        str(transactions_by_id.get(item.transaction_id, {}).get("department_id") or "")
        for item in line_items
        if transactions_by_id.get(item.transaction_id, {}).get("department_id")
    ]
    employees_by_id = {
        str(row["id"]): row
        for row in fetch_rows_by_values(client, "employees", "id", employee_ids, "id,full_name")
        if row.get("id")
    }
    departments_by_id = {
        str(row["id"]): row
        for row in fetch_rows_by_values(client, "departments", "id", department_ids, "id,name")
        if row.get("id")
    }

    records: list[dict[str, Any]] = []
    for item in line_items:
        transaction = transactions_by_id.get(item.transaction_id, {})
        employee_id = str(transaction.get("employee_id") or "")
        department_id = str(transaction.get("department_id") or "")
        records.append(
            {
                "employee_id": employee_id,
                "employee_name": string_or_none((employees_by_id.get(employee_id) or {}).get("full_name")) or "Unknown employee",
                "department_id": department_id,
                "department_name": string_or_none((departments_by_id.get(department_id) or {}).get("name")) or "Unknown department",
                "transaction_date": item.transaction_date or "",
                "merchant": item.merchant or "Unknown merchant",
                "business_category": item.category,
                "amount_cad": item.amount_cad,
                "policy_status": item.policy_status or "unscanned",
                "risk_level": item.risk_level or "unscanned",
            }
        )
    return records


def compile_visual_results(report_spec: ReportSpec, records: list[dict[str, Any]]) -> list[ReportVisualResult]:
    visuals: list[ReportVisualResult] = []
    for index, visual in enumerate(report_spec.visuals):
        compiled = compile_single_visual(visual, records, index)
        if compiled:
            visuals.append(compiled)
    return visuals


def compile_single_visual(visual: ReportVisualSpec, records: list[dict[str, Any]], index: int) -> ReportVisualResult | None:
    grouped: dict[str, float] = {}
    for record in records:
        label = group_label_for_visual(record, visual.dimension)
        grouped[label] = grouped.get(label, 0) + metric_value_for_record(record, visual.metric)

    rows = [
        ReportVisualRow(label=label, values={visual.metric: round(total, 2)})
        for label, total in grouped.items()
    ]
    reverse = visual.sort_direction != "asc"
    rows.sort(key=lambda row: row.values.get(visual.metric, 0), reverse=reverse)
    rows = rows[: visual.limit]

    if not rows:
        return None

    return ReportVisualResult(
        id=visual.id or f"visual_{index + 1}",
        title=visual.title,
        subtitle=visual.subtitle,
        chart_type=visual.chart_type,
        dimension=visual.dimension,
        metric=visual.metric,
        series=[ReportVisualSeries(key=visual.metric, label=metric_label(visual.metric))],
        rows=rows,
    )


def group_label_for_visual(record: dict[str, Any], dimension: str) -> str:
    if dimension == "employee":
        return str(record.get("employee_name") or "Unknown employee")
    if dimension == "department":
        return str(record.get("department_name") or "Unknown department")
    if dimension == "month":
        return str(record.get("transaction_date") or "")[:7] or "Unknown month"
    if dimension == "merchant":
        return str(record.get("merchant") or "Unknown merchant")
    return str(record.get("business_category") or "Uncategorized")


def metric_value_for_record(record: dict[str, Any], metric: ReportMetric) -> float:
    if metric == "sum_amount_cad":
        return float(record.get("amount_cad") or 0)
    if metric == "transaction_count":
        return 1
    if metric == "policy_flag_count":
        status = str(record.get("policy_status") or "unscanned")
        return 0 if status in POLICY_CLEAR_STATUSES or status == "unscanned" else 1
    if metric == "risk_flag_count":
        level = str(record.get("risk_level") or "unscanned")
        return 1 if level in RISK_FLAG_LEVELS else 0
    return 0


def metric_label(metric: ReportMetric) -> str:
    labels = {
        "sum_amount_cad": "Total spend",
        "transaction_count": "Transactions",
        "policy_flag_count": "Policy flags",
        "risk_flag_count": "Risk flags",
    }
    return labels.get(metric, metric.replace("_", " "))


def compose_line_items(
    transactions: list[dict[str, Any]],
    policy_by_transaction_id: dict[str, dict[str, Any]],
    risk_by_transaction_id: dict[str, dict[str, Any]],
    receipts_by_transaction_id: dict[str, dict[str, Any]],
    preapprovals_by_transaction_id: dict[str, dict[str, Any]],
    approvals_by_transaction_id: dict[str, dict[str, Any]],
    review_queue_by_transaction_id: dict[str, dict[str, Any]] | None = None,
) -> list[ExpenseReportLineItem]:
    line_items: list[ExpenseReportLineItem] = []
    review_queue_by_transaction_id = review_queue_by_transaction_id or {}
    for transaction in transactions:
        transaction_id = str(transaction["id"])
        review_item = review_queue_by_transaction_id.get(transaction_id, {})
        policy = policy_by_transaction_id.get(transaction_id, {})
        risk = risk_by_transaction_id.get(transaction_id, {})
        receipt = receipts_by_transaction_id.get(transaction_id, {})
        preapproval = preapprovals_by_transaction_id.get(transaction_id, {})
        approval = approvals_by_transaction_id.get(transaction_id, {})
        recommendation = approval_recommendation_from_row(approval.get("ai_recommendation"))
        line_items.append(
            ExpenseReportLineItem(
                id=f"pending-{transaction_id}",
                transaction_id=transaction_id,
                transaction_date=string_or_none(transaction.get("transaction_date")),
                merchant=string_or_none(transaction.get("normalized_merchant_name") or transaction.get("merchant_name")),
                amount_cad=float(transaction.get("amount_cad") or 0),
                category=str(transaction.get("business_category") or transaction.get("normalized_category") or "Uncategorized"),
                receipt_status=string_or_none(receipt.get("status")),
                preapproval_status=string_or_none(preapproval.get("status")),
                approval_status=string_or_none(approval.get("status")),
                policy_status=string_or_none(review_item.get("policy_status") or policy.get("status") or "unscanned"),
                risk_level=string_or_none(review_item.get("risk_level") or risk.get("risk_level") or "unscanned"),
                policy_scan_status="scanned" if policy else "unscanned",
                risk_scan_status="scanned" if risk else "unscanned",
                review_queue_item_id=string_or_none(review_item.get("id")),
                review_priority=int(review_item.get("review_priority") or 0),
                review_level=string_or_none(review_item.get("review_level")),
                reviewer_next_action=string_or_none(review_item.get("next_action")),
                approval_request_id=string_or_none(approval.get("id")),
                approval_recommendation=recommendation.recommendation if recommendation else None,
                approval_recommendation_confidence=recommendation.confidence if recommendation else None,
                approval_recommendation_rationale=recommendation.rationale if recommendation else None,
                review_group_key=review_group_key_from_transaction(transaction),
                review_group_size=1,
                review_group_total_amount_cad=float(transaction.get("amount_cad") or 0),
                review_group_transaction_ids=[transaction_id],
                business_purpose=string_or_none(transaction.get("business_purpose")),
                guest_names=[str(value) for value in transaction.get("guest_names") or [] if str(value).strip()],
            )
        )
    return line_items


def compose_line_item_from_report_item(
    item: dict[str, Any],
    transaction: dict[str, Any] | None,
    policy: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    preapproval: dict[str, Any] | None,
    approval: dict[str, Any] | None,
    review_item: dict[str, Any] | None = None,
) -> ExpenseReportLineItem:
    transaction = transaction or {}
    policy = policy or {}
    risk = risk or {}
    receipt = receipt or {}
    preapproval = preapproval or {}
    approval = approval or {}
    review_item = review_item or {}
    recommendation = approval_recommendation_from_row(
        item.get("approval_recommendation") if isinstance(item.get("approval_recommendation"), dict) else approval.get("ai_recommendation")
    )
    return ExpenseReportLineItem(
        id=str(item["id"]),
        transaction_id=str(item["transaction_id"]),
        transaction_date=string_or_none(transaction.get("transaction_date")),
        merchant=string_or_none(transaction.get("normalized_merchant_name") or transaction.get("merchant_name")),
        amount_cad=float(item.get("amount_cad") or 0),
        category=str(item.get("category") or transaction.get("business_category") or transaction.get("normalized_category") or "Uncategorized"),
        receipt_status=string_or_none(receipt.get("status")),
        preapproval_status=string_or_none(preapproval.get("status")),
        approval_status=string_or_none(approval.get("status")),
        policy_status=string_or_none(item.get("policy_status") or review_item.get("policy_status") or policy.get("status") or "unscanned"),
        risk_level=string_or_none(item.get("risk_level") or review_item.get("risk_level") or risk.get("risk_level") or "unscanned"),
        policy_scan_status="scanned" if policy else "unscanned",
        risk_scan_status="scanned" if risk else "unscanned",
        review_queue_item_id=string_or_none(item.get("review_queue_item_id") or review_item.get("id")),
        review_priority=int(review_item.get("review_priority") or 0),
        review_level=string_or_none(review_item.get("review_level")),
        reviewer_next_action=string_or_none(item.get("reviewer_next_action") or review_item.get("next_action")),
        approval_request_id=string_or_none(item.get("approval_request_id") or approval.get("id")),
        approval_recommendation=recommendation.recommendation if recommendation else None,
        approval_recommendation_confidence=recommendation.confidence if recommendation else None,
        approval_recommendation_rationale=recommendation.rationale if recommendation else None,
        review_group_key=(
            review_group_key_from_transaction(transaction)
            if transaction.get("id")
            else review_group_key_from_values(
                transaction_id=str(item.get("transaction_id") or ""),
                employee_id=string_or_none(transaction.get("employee_id")),
                department_id=string_or_none(transaction.get("department_id")),
                merchant=string_or_none(transaction.get("normalized_merchant_name") or transaction.get("merchant_name")),
                transaction_date=string_or_none(transaction.get("transaction_date")),
                category=string_or_none(item.get("category") or transaction.get("business_category") or transaction.get("normalized_category")),
            )
        ),
        review_group_size=1,
        review_group_total_amount_cad=float(item.get("amount_cad") or transaction.get("amount_cad") or 0),
        review_group_transaction_ids=[str(item["transaction_id"])],
        business_purpose=string_or_none(transaction.get("business_purpose")),
        guest_names=[str(value) for value in transaction.get("guest_names") or [] if str(value).strip()],
    )


def count_missing_receipts(
    transactions: list[dict[str, Any]],
    receipts_by_transaction_id: dict[str, dict[str, Any]],
    policy_by_transaction_id: dict[str, dict[str, Any]],
) -> int:
    missing_count = 0
    for transaction in transactions:
        transaction_id = str(transaction["id"])
        receipt = receipts_by_transaction_id.get(transaction_id)
        policy = policy_by_transaction_id.get(transaction_id, {})
        missing_information = [str(value).lower() for value in policy.get("missing_information") or []]
        if receipt and str(receipt.get("status") or "").lower() in MISSING_RECEIPT_STATUSES:
            missing_count += 1
        elif any("receipt" in value for value in missing_information):
            missing_count += 1
    return missing_count


def compose_summary(
    *,
    report_label: str,
    period_start: str,
    period_end: str,
    item_count: int,
    total_amount_cad: float,
    workflow_metrics: ReportWorkflowMetrics,
    grouping_reason: str,
) -> str:
    segments = [
        f"{report_label} covers {item_count} transactions from {period_start} to {period_end} totaling CAD {total_amount_cad:,.2f}.",
        grouping_reason,
        (
            f"It includes {workflow_metrics.missing_receipt_count} missing receipt items, "
            f"{workflow_metrics.missing_preapproval_count} missing preapproval items, "
            f"{workflow_metrics.open_approval_count} open approvals, "
            f"{workflow_metrics.policy_flag_count} policy flags, and {workflow_metrics.risk_flag_count} risk flags."
        ),
    ]
    if workflow_metrics.policy_unscanned_count or workflow_metrics.risk_unscanned_count:
        segments.append(
            f"Scan coverage is partial: {workflow_metrics.policy_unscanned_count} policy items and "
            f"{workflow_metrics.risk_unscanned_count} risk items are unscanned."
        )
    elif workflow_metrics.workflow_status == "pending_cfo_review":
        segments.append(
            f"The report has {workflow_metrics.open_approval_count} approval packet(s) ready for CFO review."
        )
    elif workflow_metrics.approval_ready:
        segments.append("Workflow evidence is complete enough for manager or CFO review.")
    return " ".join(segment for segment in segments if segment)


def compose_report_workflow_snapshot(
    workflow_metrics: ReportWorkflowMetrics,
    refresh_result: ReportWorkflowRefreshResult,
) -> dict[str, Any]:
    return {
        "workflow_status": workflow_metrics.workflow_status,
        "blocker_count": workflow_metrics.blocker_count,
        "approval_recommendation_counts": workflow_metrics.approval_recommendation_counts,
        "cfo_next_actions": workflow_metrics.cfo_next_actions,
        "refresh": {
            "policy_scanned": refresh_result.policy_scanned,
            "risk_scanned": refresh_result.risk_scanned,
            "review_queue_refreshed": refresh_result.review_queue_refreshed,
            "approval_requests_created": refresh_result.approval_requests_created,
            "warnings": refresh_result.warnings,
        },
    }


def line_item_approval_recommendation_snapshot(item: ExpenseReportLineItem) -> dict[str, Any] | None:
    if not item.approval_recommendation:
        return None
    return {
        "recommendation": item.approval_recommendation,
        "confidence": item.approval_recommendation_confidence or "medium",
        "rationale": item.approval_recommendation_rationale or "",
    }


def compose_report_narrative(
    *,
    report_label: str,
    period_start: str,
    period_end: str,
    item_count: int,
    total_amount_cad: float,
    workflow_metrics: ReportWorkflowMetrics,
    grouping_reason: str,
    transactions: list[dict[str, Any]],
    policy_clauses: list[CitedPolicyClause],
) -> ReportNarrative:
    fallback = ReportNarrative(
        title=report_label,
        summary=compose_summary(
            report_label=report_label,
            period_start=period_start,
            period_end=period_end,
            item_count=item_count,
            total_amount_cad=total_amount_cad,
            workflow_metrics=workflow_metrics,
            grouping_reason=grouping_reason,
        ),
    )
    client = default_report_narrative_client()
    if not client:
        return fallback

    facts = {
        "report": {
            "title": report_label,
            "period_start": period_start,
            "period_end": period_end,
            "item_count": item_count,
            "total_amount_cad": round(total_amount_cad, 2),
            "grouping_reason": grouping_reason,
            "workflow_metrics": workflow_metrics.__dict__,
            "top_categories": top_labels_by_amount(transactions, "business_category"),
            "top_merchants": top_labels_by_amount(transactions, "merchant"),
        },
        "policy_clauses": [clause.model_dump() for clause in policy_clauses],
        "deterministic_summary": fallback.summary,
    }
    try:
        return sanitize_report_narrative(client.compose_report_narrative(facts), facts, fallback)
    except Exception:
        return fallback


def sanitize_report_narrative(
    narrative: ReportNarrative,
    facts: dict[str, Any],
    fallback: ReportNarrative,
) -> ReportNarrative:
    title = string_or_none(narrative.title) or fallback.title
    summary = string_or_none(narrative.summary) or fallback.summary
    if not title or len(title) > 120:
        title = fallback.title
    if not summary or len(summary) > 500 or not summary_has_grounded_numbers(summary, facts):
        summary = fallback.summary
    return ReportNarrative(title=title, summary=summary)


def summary_has_grounded_numbers(summary: str, facts: dict[str, Any]) -> bool:
    allowed_tokens = {
        normalize_numeric_token(token)
        for token in re.findall(r"\b[\d][\d,.\-]*\b", json.dumps(facts, ensure_ascii=True))
        if normalize_numeric_token(token)
    }
    observed_tokens = {
        normalize_numeric_token(token)
        for token in re.findall(r"\b[\d][\d,.\-]*\b", summary)
        if normalize_numeric_token(token)
    }
    return observed_tokens.issubset(allowed_tokens)


def normalize_numeric_token(token: str) -> str:
    return token.replace(",", "").strip()


def top_labels_by_amount(transactions: list[dict[str, Any]], dimension: str, limit: int = 3) -> list[dict[str, Any]]:
    totals: dict[str, float] = {}
    for transaction in transactions:
        if dimension == "merchant":
            label = string_or_none(transaction.get("normalized_merchant_name") or transaction.get("merchant_name")) or "Unknown merchant"
        else:
            label = transaction_category(transaction)
        totals[label] = totals.get(label, 0.0) + abs(float(transaction.get("amount_cad") or 0))
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [{"label": label, "amount_cad": round(amount, 2)} for label, amount in ranked]


def build_report_policy_clauses(
    *,
    transactions: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    review_queue_items: list[dict[str, Any]] | None = None,
    workflow_metrics: ReportWorkflowMetrics,
    report_label: str,
    department: dict[str, Any] | None,
) -> list[CitedPolicyClause]:
    policy_flags = aggregate_report_policy_flags(violations, review_queue_items or [])
    citations_by_rule_code = fetch_policy_citations_by_rule_code(
        [str(flag.get("rule_code") or "") for flag in policy_flags if flag.get("rule_code")]
    )
    clauses = policy_citations_for_flags(policy_flags, citations_by_rule_code)

    if len(clauses) < 4:
        retrieval = retrieve_policy_chunks(
            query=build_report_policy_query(report_label, workflow_metrics, department),
            transaction_context={
                "department_name": (department or {}).get("name"),
                "categories": [entry["label"] for entry in top_labels_by_amount(transactions, "business_category")],
                "merchants": [entry["label"] for entry in top_labels_by_amount(transactions, "merchant")],
                "item_count": len(transactions),
            },
            top_k=max(2, 4 - len(clauses)),
        )
        if retrieval.status == "ok":
            clauses.extend(
                CitedPolicyClause(
                    rule_code=match.rule_code,
                    clause_id=match.id,
                    title=str(match.citation.get("title") or match.metadata.get("section_label") or "Policy clause"),
                    text=match.content,
                    source=str(match.citation.get("document_id") or ""),
                    match_score=round(match.similarity, 4),
                )
                for match in retrieval.chunks
            )

    deduped: list[CitedPolicyClause] = []
    seen: set[tuple[str | None, str | None, str]] = set()
    for clause in clauses:
        key = (clause.rule_code, clause.clause_id, clause.text)
        if key in seen or not clause.text.strip():
            continue
        seen.add(key)
        deduped.append(clause)
    return deduped[:4]


def aggregate_report_policy_flags(violations: list[dict[str, Any]], review_queue_items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    for item in review_queue_items or []:
        for flag in item.get("policy_flags") or []:
            if not isinstance(flag, dict):
                continue
            rule_code = str(flag.get("rule_code") or "")
            if not rule_code:
                continue
            current = aggregated.get(rule_code)
            candidate = {
                "rule_code": rule_code,
                "severity": flag.get("severity"),
                "explanation": flag.get("explanation"),
                "required_action": flag.get("required_action") or item.get("next_action"),
            }
            if current is None or severity_rank(candidate.get("severity")) > severity_rank(current.get("severity")):
                aggregated[rule_code] = candidate
    for violation in violations:
        rule_code = str(violation.get("rule_code") or "")
        if not rule_code:
            continue
        current = aggregated.get(rule_code)
        candidate = {
            "rule_code": rule_code,
            "severity": violation.get("severity"),
            "explanation": violation.get("explanation"),
            "required_action": violation.get("required_action"),
        }
        if current is None or severity_rank(candidate.get("severity")) > severity_rank(current.get("severity")):
            aggregated[rule_code] = candidate
    return list(aggregated.values())


def severity_rank(value: Any) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(str(value or "").lower(), 0)


def build_report_policy_query(
    report_label: str,
    workflow_metrics: ReportWorkflowMetrics,
    department: dict[str, Any] | None,
) -> str:
    return (
        f"Expense report policy review for {report_label}. "
        f"Department: {string_or_none((department or {}).get('name')) or 'unknown'}. "
        f"Missing receipts: {workflow_metrics.missing_receipt_count}. "
        f"Missing preapprovals: {workflow_metrics.missing_preapproval_count}. "
        f"Open approvals: {workflow_metrics.open_approval_count}. "
        f"Policy flags: {workflow_metrics.policy_flag_count}. "
        f"Risk flags: {workflow_metrics.risk_flag_count}."
    )


def compose_report_detail(
    report: dict[str, Any],
    employee: dict[str, Any] | None,
    department: dict[str, Any] | None,
    line_items: list[ExpenseReportLineItem],
    report_name_override: str | None = None,
    report_spec: ReportSpec | None = None,
    visuals: list[ReportVisualResult] | None = None,
    workflow_metrics: ReportWorkflowMetrics | None = None,
    report_scope_type: str = "employee",
    grouping_reason: str | None = None,
    policy_clauses: list[CitedPolicyClause] | None = None,
) -> ExpenseReportDetail:
    summary = compose_report_summary(
        report,
        employee,
        department,
        len(line_items),
        report_name_override=report_name_override,
        workflow_metrics=workflow_metrics,
        report_scope_type=report_scope_type,
        grouping_reason=grouping_reason,
    )
    return ExpenseReportDetail(
        **summary.model_dump(),
        line_items=line_items,
        report_spec=report_spec,
        visuals=visuals or [],
        policy_clauses=policy_clauses or [],
    )


def compose_report_summary(
    report: dict[str, Any],
    employee: dict[str, Any] | None,
    department: dict[str, Any] | None,
    item_count: int,
    report_name_override: str | None = None,
    workflow_metrics: ReportWorkflowMetrics | None = None,
    report_scope_type: str = "employee",
    grouping_reason: str | None = None,
) -> ExpenseReportSummary:
    workflow_metrics = workflow_metrics or ReportWorkflowMetrics(
        missing_receipt_count=int(report.get("missing_receipt_count") or 0),
        policy_flag_count=int(report.get("policy_flag_count") or 0),
        risk_flag_count=int(report.get("risk_flag_count") or 0),
        workflow_status=str(report.get("workflow_status") or "action_required"),
    )
    workflow_snapshot = report.get("workflow_snapshot") if isinstance(report.get("workflow_snapshot"), dict) else {}
    return ExpenseReportSummary(
        id=str(report["id"]),
        employee_id=str(report["employee_id"]),
        employee_name=string_or_none((employee or {}).get("full_name")),
        report_name=string_or_none(report.get("report_name"))
        or report_name_override
        or string_or_none((employee or {}).get("full_name")),
        department_id=str(report["department_id"]),
        department_name=string_or_none((department or {}).get("name")),
        period_start=str(report["period_start"]),
        period_end=str(report["period_end"]),
        status=report.get("status") or "generated",
        total_amount_cad=float(report.get("total_amount_cad") or 0),
        missing_receipt_count=workflow_metrics.missing_receipt_count,
        missing_preapproval_count=workflow_metrics.missing_preapproval_count,
        approval_request_count=workflow_metrics.approval_request_count,
        open_approval_count=workflow_metrics.open_approval_count,
        policy_flag_count=workflow_metrics.policy_flag_count,
        risk_flag_count=workflow_metrics.risk_flag_count,
        policy_unscanned_count=workflow_metrics.policy_unscanned_count,
        risk_unscanned_count=workflow_metrics.risk_unscanned_count,
        approval_ready=workflow_metrics.approval_ready,
        workflow_status=workflow_metrics.workflow_status,  # type: ignore[arg-type]
        blocker_count=workflow_metrics.blocker_count,
        approval_recommendation_counts=workflow_metrics.approval_recommendation_counts
        or dict(workflow_snapshot.get("approval_recommendation_counts") or {}),
        cfo_next_actions=workflow_metrics.cfo_next_actions or [str(value) for value in workflow_snapshot.get("cfo_next_actions") or []],
        report_scope_type=report_scope_type,  # type: ignore[arg-type]
        grouping_reason=grouping_reason,
        ai_summary=string_or_none(report.get("ai_summary")),
        item_count=item_count,
        created_at=string_or_none(report.get("created_at")),
        updated_at=string_or_none(report.get("updated_at")),
    )


def fetch_people_for_reports(client: Any, reports: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    employee_ids = [str(report["employee_id"]) for report in reports if report.get("employee_id")]
    department_ids = [str(report["department_id"]) for report in reports if report.get("department_id")]
    employees = fetch_rows_by_values(client, "employees", "id", employee_ids, "*")
    departments = fetch_rows_by_values(client, "departments", "id", department_ids, "*")
    return (
        {str(employee["id"]): employee for employee in employees if employee.get("id")},
        {str(department["id"]): department for department in departments if department.get("id")},
    )


def count_items_by_report_id(report_items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report_items:
        report_id = str(item.get("report_id") or "")
        if report_id:
            counts[report_id] = counts.get(report_id, 0) + 1
    return counts


def fetch_report_evidence(client: Any, transaction_ids: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "policy": latest_by_transaction_id(fetch_rows_by_values(client, "policy_checks", "transaction_id", transaction_ids, "*")),
        "risk": latest_by_transaction_id(fetch_rows_by_values(client, "risk_scores", "transaction_id", transaction_ids, "*")),
        "receipts": latest_by_transaction_id(fetch_rows_by_values(client, "receipts", "transaction_id", transaction_ids, "*")),
        "preapprovals": latest_by_transaction_id(fetch_rows_by_values(client, "preapprovals", "transaction_id", transaction_ids, "*")),
        "approvals": latest_by_transaction_id(fetch_rows_by_values(client, "approval_requests", "transaction_id", transaction_ids, "*")),
        "review_queue": latest_by_transaction_id(fetch_rows_by_values(client, "review_queue_items", "transaction_id", transaction_ids, "*")),
    }


def summarize_workflow_metrics_by_report_id(
    report_items: list[dict[str, Any]],
    transactions_by_id: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, ReportWorkflowMetrics]:
    transactions_by_report_id: dict[str, list[dict[str, Any]]] = {}
    for item in report_items:
        report_id = str(item.get("report_id") or "")
        transaction_id = str(item.get("transaction_id") or "")
        transaction = transactions_by_id.get(transaction_id)
        if report_id and transaction:
            transactions_by_report_id.setdefault(report_id, []).append(transaction)

    return {
        report_id: summarize_report_workflow_metrics(
            transactions,
            evidence["policy"],
            evidence["risk"],
            evidence["receipts"],
            evidence["preapprovals"],
            evidence["approvals"],
            evidence["review_queue"],
        )
        for report_id, transactions in transactions_by_report_id.items()
    }


def summarize_report_workflow_metrics(
    transactions: list[dict[str, Any]],
    policy_by_transaction_id: dict[str, dict[str, Any]],
    risk_by_transaction_id: dict[str, dict[str, Any]],
    receipts_by_transaction_id: dict[str, dict[str, Any]],
    preapprovals_by_transaction_id: dict[str, dict[str, Any]],
    approvals_by_transaction_id: dict[str, dict[str, Any]],
    review_queue_by_transaction_id: dict[str, dict[str, Any]] | None = None,
) -> ReportWorkflowMetrics:
    review_queue_by_transaction_id = review_queue_by_transaction_id or {}
    missing_receipt_count = count_missing_receipts(transactions, receipts_by_transaction_id, policy_by_transaction_id)
    missing_preapproval_count = count_missing_preapprovals(transactions, preapprovals_by_transaction_id, policy_by_transaction_id)
    approval_request_count = 0
    open_approval_count = 0
    policy_flag_count = 0
    risk_flag_count = 0
    policy_unscanned_count = 0
    risk_unscanned_count = 0
    approval_recommendation_counts: dict[str, int] = {"approve": 0, "deny": 0, "unknown": 0}
    cfo_next_actions: list[str] = []

    for transaction in transactions:
        transaction_id = str(transaction["id"])
        policy = policy_by_transaction_id.get(transaction_id)
        risk = risk_by_transaction_id.get(transaction_id)
        approval = approvals_by_transaction_id.get(transaction_id)
        review_item = review_queue_by_transaction_id.get(transaction_id, {})

        if approval:
            approval_request_count += 1
            if str(approval.get("status") or "").lower() in OPEN_APPROVAL_STATUSES:
                open_approval_count += 1
            recommendation = approval_recommendation_from_row(approval.get("ai_recommendation"))
            if recommendation:
                approval_recommendation_counts[recommendation.recommendation] = approval_recommendation_counts.get(
                    recommendation.recommendation,
                    0,
                ) + 1
            else:
                approval_recommendation_counts["unknown"] += 1
        elif review_item and int(review_item.get("review_priority") or 0) > 0:
            approval_recommendation_counts["unknown"] += 1

        next_action = string_or_none(review_item.get("next_action"))
        if next_action and next_action != "No action required.":
            cfo_next_actions.append(next_action)

        if policy:
            policy_status = str(review_item.get("policy_status") or policy.get("status") or "compliant")
            policy_flags = review_item.get("policy_flags") if isinstance(review_item.get("policy_flags"), list) else []
            if policy_flags or policy_status not in POLICY_CLEAR_STATUSES:
                policy_flag_count += 1
        else:
            policy_unscanned_count += 1
        if risk:
            if str(review_item.get("risk_level") or risk.get("risk_level") or "low") in RISK_FLAG_LEVELS:
                risk_flag_count += 1
        else:
            risk_unscanned_count += 1

    blocker_count = (
        missing_receipt_count
        + missing_preapproval_count
        + open_approval_count
        + policy_flag_count
        + risk_flag_count
        + policy_unscanned_count
        + risk_unscanned_count
    )
    workflow_status = determine_report_workflow_status(
        missing_receipt_count=missing_receipt_count,
        missing_preapproval_count=missing_preapproval_count,
        open_approval_count=open_approval_count,
        policy_unscanned_count=policy_unscanned_count,
        risk_unscanned_count=risk_unscanned_count,
        policy_flag_count=policy_flag_count,
        risk_flag_count=risk_flag_count,
    )
    approval_ready = (
        missing_receipt_count == 0
        and missing_preapproval_count == 0
        and open_approval_count == 0
        and policy_flag_count == 0
        and risk_flag_count == 0
        and policy_unscanned_count == 0
        and risk_unscanned_count == 0
    )
    return ReportWorkflowMetrics(
        missing_receipt_count=missing_receipt_count,
        missing_preapproval_count=missing_preapproval_count,
        approval_request_count=approval_request_count,
        open_approval_count=open_approval_count,
        policy_flag_count=policy_flag_count,
        risk_flag_count=risk_flag_count,
        policy_unscanned_count=policy_unscanned_count,
        risk_unscanned_count=risk_unscanned_count,
        approval_ready=approval_ready,
        workflow_status=workflow_status,
        blocker_count=blocker_count,
        approval_recommendation_counts={key: value for key, value in approval_recommendation_counts.items() if value},
        cfo_next_actions=dedupe_strings(cfo_next_actions)[:5],
    )


def determine_report_workflow_status(
    *,
    missing_receipt_count: int,
    missing_preapproval_count: int,
    open_approval_count: int,
    policy_unscanned_count: int,
    risk_unscanned_count: int,
    policy_flag_count: int,
    risk_flag_count: int,
) -> str:
    if policy_unscanned_count or risk_unscanned_count:
        return "scan_incomplete"
    if open_approval_count:
        return "pending_cfo_review"
    if missing_receipt_count or missing_preapproval_count or policy_flag_count or risk_flag_count:
        return "action_required"
    return "ready_for_cfo"


def count_missing_preapprovals(
    transactions: list[dict[str, Any]],
    preapprovals_by_transaction_id: dict[str, dict[str, Any]],
    policy_by_transaction_id: dict[str, dict[str, Any]],
) -> int:
    missing_count = 0
    for transaction in transactions:
        transaction_id = str(transaction["id"])
        preapproval = preapprovals_by_transaction_id.get(transaction_id)
        policy = policy_by_transaction_id.get(transaction_id, {})
        missing_information = [str(value).lower() for value in policy.get("missing_information") or []]
        preapproval_status = str((preapproval or {}).get("status") or "").lower()
        requires_approval_evidence = str(policy.get("status") or "").lower() == "approval_evidence_needed" or any(
            "approval" in value or "preapproval" in value for value in missing_information
        )
        if requires_approval_evidence and (not preapproval or preapproval_status in MISSING_PREAPPROVAL_STATUSES):
            missing_count += 1
    return missing_count


def infer_report_scope_type_by_report_id(
    report_items: list[dict[str, Any]],
    transactions_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    scope_types: dict[str, str] = {}
    transactions_by_report_id: dict[str, set[str]] = {}
    for item in report_items:
        report_id = str(item.get("report_id") or "")
        transaction_id = str(item.get("transaction_id") or "")
        employee_id = str(transactions_by_id.get(transaction_id, {}).get("employee_id") or "")
        if report_id and employee_id:
            transactions_by_report_id.setdefault(report_id, set()).add(employee_id)

    for report_id, employee_ids in transactions_by_report_id.items():
        scope_types[report_id] = "department" if len(employee_ids) > 1 else "employee"
    return scope_types


def infer_report_scope_type(report_items: list[dict[str, Any]], transactions_by_id: dict[str, dict[str, Any]]) -> str:
    return infer_report_scope_type_by_report_id(report_items, transactions_by_id).get(
        str(report_items[0].get("report_id") or "") if report_items else "",
        "employee",
    )


def infer_grouping_reason_from_report(
    report_scope_type: str,
    transactions_by_id: dict[str, dict[str, Any]],
    report_items: list[dict[str, Any]],
) -> str | None:
    transactions = [
        transactions_by_id[str(item.get("transaction_id") or "")]
        for item in report_items
        if str(item.get("transaction_id") or "") in transactions_by_id
    ]
    if len(transactions) < 2:
        return None
    return describe_transaction_cluster(
        PlannedReportScope(scope_type=report_scope_type, requested_label=report_scope_type.title()),
        sorted(transactions, key=lambda row: str(row.get("transaction_date") or "")),
    )


def resolve_scope_context(
    client: Any,
    scope: PlannedReportScope,
) -> tuple[dict[str, Any], dict[str, Any], list[str], str]:
    if scope.scope_type == "employee":
        employee = resolve_employee_scope(client, scope)
        department = fetch_one_by_id(client, "departments", str(employee.get("department_id") or ""))
        if not department:
            raise HTTPException(status_code=404, detail="Employee department was not found.")
        return employee, department, [str(employee["id"])], str(employee.get("full_name") or "Employee")

    department = resolve_department_scope(client, scope)
    employees = (
        client.table("employees")
        .select("*")
        .eq("department_id", str(department["id"]))
        .order("full_name")
        .execute()
        .data
        or []
    )
    if not employees:
        raise HTTPException(status_code=404, detail=f"No employees found for department '{department.get('name')}'.")

    owner_employee = employees[0]
    owner_label = f"{str(department.get('name') or scope.requested_label)} Team"
    employee_ids = [str(employee["id"]) for employee in employees if employee.get("id")]
    return owner_employee, department, employee_ids, owner_label


def fetch_transactions_for_report_items(client: Any, report_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    transaction_ids = [
        str(item["transaction_id"])
        for item in report_items
        if item.get("transaction_id")
    ]
    return {
        str(row["id"]): row
        for row in fetch_rows_by_values(client, "transactions", "id", transaction_ids, "*")
        if row.get("id")
    }


def infer_report_name_overrides(
    report_items: list[dict[str, Any]],
    transactions_by_id: dict[str, dict[str, Any]],
    departments_by_id: dict[str, dict[str, Any]],
) -> dict[str, str]:
    transaction_rows_by_report_id: dict[str, list[dict[str, Any]]] = {}
    for item in report_items:
        report_id = str(item.get("report_id") or "")
        transaction = transactions_by_id.get(str(item.get("transaction_id") or ""))
        if report_id and transaction:
            transaction_rows_by_report_id.setdefault(report_id, []).append(transaction)

    overrides: dict[str, str] = {}
    for report_id, transactions in transaction_rows_by_report_id.items():
        department_id = next(
            (str(transaction.get("department_id") or "") for transaction in transactions if transaction.get("department_id")),
            "",
        )
        department = departments_by_id.get(department_id)
        report_name = infer_department_report_name(department, transactions)
        if report_name:
            overrides[report_id] = report_name
    return overrides


def infer_report_name_override_for_report(
    report_id: str,
    item_rows: list[dict[str, Any]],
    transactions_by_id: dict[str, dict[str, Any]],
    department: dict[str, Any] | None,
) -> str | None:
    transactions = [
        transactions_by_id[str(item["transaction_id"])]
        for item in item_rows
        if item.get("transaction_id") and str(item["transaction_id"]) in transactions_by_id
    ]
    return infer_department_report_name(department, transactions)


def infer_department_report_name(
    department: dict[str, Any] | None,
    transactions: list[dict[str, Any]],
) -> str | None:
    if not department or len({str(transaction.get("employee_id") or "") for transaction in transactions if transaction.get("employee_id")}) <= 1:
        return None
    return f"{str(department.get('name') or 'Department')} Team Report"


def fetch_one_by_id(client: Any, table_name: str, row_id: str) -> dict[str, Any] | None:
    if not row_id:
        return None
    rows = client.table(table_name).select("*").eq("id", row_id).limit(1).execute().data or []
    return rows[0] if rows else None


def fetch_rows_by_values(client: Any, table_name: str, column_name: str, values: Iterable[str], columns: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unique_values = list(dict.fromkeys(value for value in values if value))
    for index in range(0, len(unique_values), 500):
        chunk = unique_values[index : index + 500]
        if chunk:
            rows.extend(client.table(table_name).select(columns).in_(column_name, chunk).execute().data or [])
    return rows


def latest_by_transaction_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ranked: dict[str, dict[str, Any]] = {}
    for row in rows:
        transaction_id = str(row.get("transaction_id") or "")
        if not transaction_id:
            continue
        existing = ranked.get(transaction_id)
        if not existing or row_timestamp(row) > row_timestamp(existing):
            ranked[transaction_id] = row
    return ranked


def row_timestamp(row: dict[str, Any]) -> str:
    return str(row.get("checked_at") or row.get("scored_at") or row.get("updated_at") or row.get("created_at") or "")


def parse_transaction_date(transaction: dict[str, Any]) -> date | None:
    value = string_or_none(transaction.get("transaction_date"))
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def transaction_category(transaction: dict[str, Any]) -> str:
    return str(transaction.get("business_category") or transaction.get("normalized_category") or "Uncategorized")


def transaction_merchant(transaction: dict[str, Any]) -> str:
    return string_or_none(transaction.get("normalized_merchant_name") or transaction.get("merchant_name")) or "Unknown merchant"


def transaction_looks_like_event_expense(transaction: dict[str, Any]) -> bool:
    category = normalize_text(transaction_category(transaction))
    merchant = normalize_text(transaction_merchant(transaction))
    return any(keyword in category or keyword in merchant for keyword in TRAVEL_EVENT_CATEGORY_KEYWORDS)


def extract_employee_name(text: str) -> str | None:
    if re.search(r"\bsarah\s+chen\b", text, re.IGNORECASE):
        return "Sarah Chen"
    match = re.search(r"\bfor\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", text)
    return match.group(1).strip() if match else None


def extract_date(text: str, position: str) -> str | None:
    dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    if not dates:
        return None
    return dates[0] if position == "start" else dates[-1]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "expense-report"


def dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
