from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.policy import PolicyStatus, Severity
from app.schemas.review_queue import CitedPolicyClause, ReviewerBrief
from app.schemas.risk import RiskLevel, RiskSignal

ApprovalStatus = Literal["draft", "requested", "approved", "denied", "cancelled"]
ApprovalDecision = Literal["approved", "denied", "cancelled"]
ApprovalRecommendationValue = Literal["approve", "deny"]
ApprovalRecommendationConfidence = Literal["low", "medium", "high"]
ApprovalRecommendationSource = Literal["deterministic_fallback", "openai_structured_output"]
ApprovalExplanationSeverity = Literal["info", "warning", "blocking"]


class ApprovalRecommendation(BaseModel):
    recommendation: ApprovalRecommendationValue
    confidence: ApprovalRecommendationConfidence = "medium"
    rationale: str
    grounded_inputs: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    source: ApprovalRecommendationSource = "deterministic_fallback"


class ApprovalExplanationReason(BaseModel):
    label: str
    severity: ApprovalExplanationSeverity = "warning"
    detail: str


class ApprovalExplanation(BaseModel):
    decision: ApprovalRecommendationValue
    confidence: ApprovalRecommendationConfidence = "medium"
    summary: str
    blocking_reasons: list[ApprovalExplanationReason] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    cited_policy_clauses: list[CitedPolicyClause] = Field(default_factory=list)
    would_change_outcome_if: list[str] = Field(default_factory=list)
    generated_by: str = "deterministic_packet_explainer"


class DepartmentBudgetStatus(BaseModel):
    department_id: str | None = None
    department_name: str | None = None
    monthly_budget_cad: float = 0
    quarterly_budget_cad: float = 0
    month_to_date_spend_cad: float = 0
    quarter_to_date_spend_cad: float = 0
    monthly_remaining_cad: float = 0
    quarterly_remaining_cad: float = 0
    budget_period_month: str | None = None
    budget_period_quarter: str | None = None
    synthetic: bool = True


class EmployeeSpendHistory(BaseModel):
    employee_id: str | None = None
    employee_name: str | None = None
    transaction_count: int = 0
    total_spend_cad: float = 0
    same_category_count: int = 0
    same_category_spend_cad: float = 0
    prior_approval_count: int = 0
    prior_approved_count: int = 0


class ApprovalContextSnapshot(BaseModel):
    transaction: dict[str, Any] = Field(default_factory=dict)
    employee: dict[str, Any] = Field(default_factory=dict)
    department: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    budget: DepartmentBudgetStatus = Field(default_factory=DepartmentBudgetStatus)
    spend_history: EmployeeSpendHistory = Field(default_factory=EmployeeSpendHistory)
    review_queue: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequestCreate(BaseModel):
    review_queue_item_id: str | None = None
    transaction_id: str | None = None
    requester_note: str | None = Field(default=None, max_length=1000)
    actor: str | None = Field(default="Finance Manager", max_length=200)


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    actor: str = Field(default="Finance Manager", max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class ApprovalRequestItem(BaseModel):
    id: str
    transaction_id: str
    employee_id: str
    employee_name: str | None = None
    department_id: str
    department_name: str | None = None
    approver_name: str | None = None
    status: ApprovalStatus
    requested_amount_cad: float
    transaction_date: str | None = None
    merchant: str | None = None
    category: str = "Uncategorized"
    policy_check_id: str | None = None
    policy_status: PolicyStatus | None = None
    policy_severity: Severity | None = None
    policy_flags: list[dict[str, Any]] = Field(default_factory=list)
    risk_score_id: str | None = None
    risk_score: int = 0
    risk_level: RiskLevel | None = None
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    ai_recommendation: ApprovalRecommendation | None = None
    reviewer_brief: ReviewerBrief | None = None
    review_group_key: str | None = None
    review_group_size: int = 1
    review_group_total_amount_cad: float = 0
    review_group_transaction_ids: list[str] = Field(default_factory=list)
    budget_status: DepartmentBudgetStatus | None = None
    spend_history: EmployeeSpendHistory | None = None
    requester_note: str | None = None
    decision_note: str | None = None
    decided_by: str | None = None
    decided_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ApprovalRequestDetail(ApprovalRequestItem):
    context_snapshot: ApprovalContextSnapshot | None = None
    approval_explanation: ApprovalExplanation | None = None
    audit_events: list[dict[str, Any]] = Field(default_factory=list)


class ApprovalListResponse(BaseModel):
    approvals: list[ApprovalRequestItem] = Field(default_factory=list)
