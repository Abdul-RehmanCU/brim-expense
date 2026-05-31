from typing import Literal

from pydantic import BaseModel, Field
from app.schemas.review_queue import CitedPolicyClause

ReportStatus = Literal["draft", "generated", "exported", "archived"]
ReportScopeType = Literal["employee", "department"]
ReportPlannerSource = Literal["deterministic", "claude_fallback", "claude_critic"]
ReportChartType = Literal["bar", "line", "pie", "table"]
ReportDimension = Literal["employee", "department", "business_category", "month", "merchant"]
ReportMetric = Literal["sum_amount_cad", "transaction_count", "policy_flag_count", "risk_flag_count"]
ReportSortDirection = Literal["asc", "desc"]
WorkflowScanStatus = Literal["scanned", "unscanned"]
ReportWorkflowStatus = Literal["scan_incomplete", "action_required", "pending_cfo_review", "ready_for_cfo"]
ReportApprovalRecommendationValue = Literal["approve", "deny"]
ReportApprovalRecommendationConfidence = Literal["low", "medium", "high"]


class ReportGenerateRequest(BaseModel):
    request: str | None = Field(default=None, max_length=1000)
    employee_id: str | None = None
    employee_name: str | None = Field(default=None, max_length=200)
    department_id: str | None = None
    department_name: str | None = Field(default=None, max_length=200)
    date_start: str | None = None
    date_end: str | None = None
    refresh_workflow: bool = False


class ExpenseReportLineItem(BaseModel):
    id: str
    transaction_id: str
    transaction_date: str | None = None
    merchant: str | None = None
    amount_cad: float
    category: str
    receipt_status: str | None = None
    preapproval_status: str | None = None
    approval_status: str | None = None
    policy_status: str | None = None
    risk_level: str | None = None
    policy_scan_status: WorkflowScanStatus = "scanned"
    risk_scan_status: WorkflowScanStatus = "scanned"
    review_queue_item_id: str | None = None
    review_priority: int = 0
    review_level: str | None = None
    reviewer_next_action: str | None = None
    approval_request_id: str | None = None
    approval_recommendation: ReportApprovalRecommendationValue | None = None
    approval_recommendation_confidence: ReportApprovalRecommendationConfidence | None = None
    approval_recommendation_rationale: str | None = None
    review_group_key: str | None = None
    review_group_size: int = 1
    review_group_total_amount_cad: float = 0
    review_group_transaction_ids: list[str] = Field(default_factory=list)
    business_purpose: str | None = None
    guest_names: list[str] = Field(default_factory=list)


class ReportVisualSpec(BaseModel):
    id: str | None = None
    title: str
    subtitle: str | None = None
    chart_type: ReportChartType = "bar"
    dimension: ReportDimension
    metric: ReportMetric
    limit: int = Field(default=10, ge=1, le=20)
    sort_direction: ReportSortDirection = "desc"


class ReportSpec(BaseModel):
    title: str
    summary: str | None = None
    visuals: list[ReportVisualSpec] = Field(default_factory=list)


class ReportNarrative(BaseModel):
    title: str | None = None
    summary: str


class ReportVisualSeries(BaseModel):
    key: str
    label: str


class ReportVisualRow(BaseModel):
    label: str
    values: dict[str, float] = Field(default_factory=dict)


class ReportVisualResult(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    chart_type: ReportChartType
    dimension: ReportDimension
    metric: ReportMetric
    series: list[ReportVisualSeries] = Field(default_factory=list)
    rows: list[ReportVisualRow] = Field(default_factory=list)


class ExpenseReportSummary(BaseModel):
    id: str
    employee_id: str
    employee_name: str | None = None
    report_name: str | None = None
    department_id: str
    department_name: str | None = None
    period_start: str
    period_end: str
    status: ReportStatus
    total_amount_cad: float
    missing_receipt_count: int = 0
    missing_preapproval_count: int = 0
    approval_request_count: int = 0
    open_approval_count: int = 0
    policy_flag_count: int = 0
    risk_flag_count: int = 0
    policy_unscanned_count: int = 0
    risk_unscanned_count: int = 0
    approval_ready: bool = False
    workflow_status: ReportWorkflowStatus = "action_required"
    blocker_count: int = 0
    approval_recommendation_counts: dict[str, int] = Field(default_factory=dict)
    cfo_next_actions: list[str] = Field(default_factory=list)
    report_scope_type: ReportScopeType = "employee"
    grouping_reason: str | None = None
    ai_summary: str | None = None
    item_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class ExpenseReportDetail(ExpenseReportSummary):
    line_items: list[ExpenseReportLineItem] = Field(default_factory=list)
    report_spec: ReportSpec | None = None
    visuals: list[ReportVisualResult] = Field(default_factory=list)
    policy_clauses: list[CitedPolicyClause] = Field(default_factory=list)


class ReportPlanTarget(BaseModel):
    scope_type: ReportScopeType
    requested_label: str
    resolved_label: str
    report_count: int = 1


class ReportScopeEmployeeOption(BaseModel):
    id: str
    full_name: str
    department_id: str | None = None
    department_name: str | None = None


class ReportScopeDepartmentOption(BaseModel):
    id: str
    name: str


class ReportScopeOptionsResponse(BaseModel):
    employees: list[ReportScopeEmployeeOption] = Field(default_factory=list)
    departments: list[ReportScopeDepartmentOption] = Field(default_factory=list)
    latest_transaction_date: str | None = None


class ReportGenerateResponse(BaseModel):
    request: str | None = None
    planner_source: ReportPlannerSource = "deterministic"
    sql_preview: str | None = None
    generated_count: int = 0
    targets: list[ReportPlanTarget] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reports: list[ExpenseReportDetail] = Field(default_factory=list)


class ExpenseReportListResponse(BaseModel):
    reports: list[ExpenseReportSummary] = Field(default_factory=list)


class ReportCsvResponse(BaseModel):
    file_name: str
    content_type: str = "text/csv"
    csv: str
