from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.policy import PolicyStatus, Severity
from app.schemas.risk import RiskLevel, RiskSignal

ReviewQueueStatus = Literal["open", "in_approval", "resolved", "ignored"]
ReviewerBriefConfidence = Literal["low", "medium", "high"]
ReviewerBriefSource = Literal["deterministic_fallback", "openai_structured_output"]


class CitedPolicyClause(BaseModel):
    rule_code: str | None = None
    clause_id: str | None = None
    title: str | None = None
    text: str
    source: str | None = None
    match_score: float | None = None


class ReviewerBrief(BaseModel):
    summary: str
    key_reasons: list[str] = Field(default_factory=list)
    cited_policy_clauses: list[CitedPolicyClause] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    recommended_next_action: str
    confidence: ReviewerBriefConfidence = "medium"
    grounding_warnings: list[str] = Field(default_factory=list)
    advisory_notice: str = (
        "Advisory reviewer brief only. Deterministic policy status, risk score, and reviewer decisions remain the "
        "source of truth."
    )
    generated_by: ReviewerBriefSource = "deterministic_fallback"


class ReviewQueueItem(BaseModel):
    id: str | None = None
    transaction_id: str
    employee: str | None = None
    employee_id: str | None = None
    department: str | None = None
    department_id: str | None = None
    transaction_date: str | None = None
    merchant: str | None = None
    amount_cad: float = 0
    category: str = "Uncategorized"
    queue_status: ReviewQueueStatus = "open"
    review_priority: int = 0
    review_level: Severity = "low"
    policy_check_id: str | None = None
    policy_status: PolicyStatus | None = None
    policy_severity: Severity | None = None
    policy_flags: list[dict[str, Any]] = Field(default_factory=list)
    risk_score_id: str | None = None
    risk_score: int = 0
    risk_level: RiskLevel | None = None
    risk_signals: list[RiskSignal] = Field(default_factory=list)
    ai_context: str | None = None
    reviewer_brief: ReviewerBrief | None = None
    next_action: str = "No action required."
    generated_at: str | None = None


class ReviewQueueSummary(BaseModel):
    total: int = 0
    open: int = 0
    in_approval: int = 0
    resolved: int = 0
    ignored: int = 0
    high_or_critical: int = 0
    policy_flagged: int = 0
    risk_flagged: int = 0


class ReviewQueueRefreshRequest(BaseModel):
    limit: int | None = None
    reset_existing: bool = True
    persist: bool = True


class ReviewQueueRefreshResponse(BaseModel):
    generated: int = 0
    persisted: int = 0
    table_available: bool = True
    summary: ReviewQueueSummary = Field(default_factory=ReviewQueueSummary)
