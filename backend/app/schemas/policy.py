from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
PolicyRuleStatus = Literal["active", "draft", "disabled"]
PolicyDocumentSourceType = Literal["seed", "pasted_text", "uploaded_pdf"]
PolicyDocumentExtractionStatus = Literal["pending", "extracted", "failed"]
PolicyExtractionRunStatus = Literal["pending", "completed", "failed"]
PolicyStatus = Literal[
    "compliant",
    "excluded_non_expense",
    "review_required",
    "context_needed",
    "approval_evidence_needed",
    "policy_violation",
]


class PolicyViolation(BaseModel):
    rule_code: str
    severity: Severity
    explanation: str
    required_action: str


class PolicyCheckResult(BaseModel):
    transaction_id: str
    status: PolicyStatus
    max_severity: Severity
    severity_score: int = 0
    scan_version: str | None = None
    violations: list[PolicyViolation] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_next_action: str


class PolicyScanRequest(BaseModel):
    department_id: str | None = None
    employee_id: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    batch_size: int = 500
    limit: int | None = None
    dry_run: bool = False
    reset_existing: bool = False
    reset_synthetic_evidence: bool = False


class PolicyScanSummary(BaseModel):
    total_scanned: int = 0
    compliant: int = 0
    excluded_non_expense: int = 0
    evidence_required: int = 0
    approval_evidence_required: int = 0
    approval_evidence_needed: int = 0
    context_needed: int = 0
    policy_violations: int = 0
    policy_violation: int = 0
    review_required: int = 0
    high_or_critical: int = 0
    individual_flags: int = 0
    violations_created: int = 0
    duration_ms: int = 0
    batch_count: int = 0


class PolicyResetResponse(BaseModel):
    rows_deleted: dict[str, int] = Field(default_factory=dict)
    storage_paths_removed: int = 0
    warnings: list[str] = Field(default_factory=list)


class RepeatOffenderItem(BaseModel):
    id: str | None = None
    name: str
    open_violations: int


class RepeatOffenderSummary(BaseModel):
    employees: list[RepeatOffenderItem] = Field(default_factory=list)
    departments: list[RepeatOffenderItem] = Field(default_factory=list)


class PolicyFindingItem(BaseModel):
    transaction_id: str
    employee: str | None = None
    department: str | None = None
    date: str | None = None
    merchant: str | None = None
    amount_cad: float
    category: str
    overall_status: PolicyStatus
    max_severity: Severity
    severity_score: int = 0
    scan_version: str | None = None
    violations: list[PolicyViolation] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_next_action: str


class ViolationListItem(BaseModel):
    id: str
    transaction_id: str
    policy_check_id: str
    rule_code: str
    status: PolicyStatus
    severity: Severity
    explanation: str
    required_action: str
    transaction_date: str | None = None
    merchant: str | None = None
    amount_cad: float
    category: str
    employee: str | None = None
    department: str | None = None


class PolicyRuleItem(BaseModel):
    id: str
    rule_code: str
    name: str
    description: str
    severity: Severity
    enabled: bool
    status: PolicyRuleStatus
    deterministic: bool = True
    source_type: str = "seeded"
    source_text: str | None = None
    rule_json: dict[str, Any] = Field(default_factory=dict)
    policy_document_id: str | None = None
    policy_extraction_run_id: str | None = None
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    needs_human_review: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class PolicyRuleWriteRequest(BaseModel):
    rule_code: str
    name: str
    description: str
    severity: Severity = "medium"
    enabled: bool = False
    status: PolicyRuleStatus = "draft"
    source_type: str = "manual"
    source_text: str | None = None
    rule_json: dict[str, Any] = Field(default_factory=dict)


class PolicyRulePatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    severity: Severity | None = None
    enabled: bool | None = None
    status: PolicyRuleStatus | None = None
    source_text: str | None = None
    rule_json: dict[str, Any] | None = None


class PolicyRuleTestRequest(BaseModel):
    rule_json: dict[str, Any] = Field(default_factory=dict)
    sample_limit: int = 5


class PolicyRuleTestResponse(BaseModel):
    valid: bool
    matched_count: int = 0
    sample_matches: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    estimated_impact: dict[str, dict[str, int]] = Field(
        default_factory=lambda: {"by_department": {}, "by_employee": {}, "by_category": {}}
    )


class PolicyRuleExtractionRequest(BaseModel):
    policy_text: str = Field(min_length=20, max_length=60000)
    company_context: str | None = Field(default=None, max_length=4000)
    available_fields: list[str] | None = None


class PolicyDocumentTextRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    policy_text: str = Field(min_length=20, max_length=120000)


class PolicyDocumentExtractRequest(BaseModel):
    company_context: str | None = Field(default=None, max_length=4000)
    available_fields: list[str] | None = None


class PolicyDocumentItem(BaseModel):
    id: str
    title: str
    version: str
    source_type: PolicyDocumentSourceType
    file_name: str | None = None
    storage_path: str | None = None
    raw_text: str | None = None
    extracted_text: str | None = None
    extraction_status: PolicyDocumentExtractionStatus = "pending"
    extraction_error: str | None = None
    active: bool = True
    synthetic: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class PolicyDocumentCreateResponse(BaseModel):
    policy_document_id: str
    document: PolicyDocumentItem
    text_preview: str = ""
    char_count: int = 0
    embedding_status: str | None = None
    embedding_error: str | None = None
    chunk_count: int = 0
    embedded_chunk_count: int = 0


class PolicyExtractionRunItem(BaseModel):
    id: str
    policy_document_id: str
    model_used: str | None = None
    status: PolicyExtractionRunStatus = "pending"
    summary: str | None = None
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_or_missing_fields: list[str] = Field(default_factory=list)
    suggested_feature_engineering: list[str] = Field(default_factory=list)
    draft_rule_count: int = 0
    error: str | None = None
    created_at: str | None = None


class ExtractedDraftRule(BaseModel):
    id: str | None = None
    rule_code: str
    name: str
    description: str
    severity: Severity
    enabled: bool = False
    status: PolicyRuleStatus = "draft"
    source_type: str = "ai_extracted"
    source_text: str | None = None
    rule_json: dict[str, Any] = Field(default_factory=dict)
    policy_document_id: str | None = None
    policy_extraction_run_id: str | None = None
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    needs_human_review: bool = False
    validation_errors: list[str] = Field(default_factory=list)


class PolicyRuleExtractionResponse(BaseModel):
    policy_document_id: str | None = None
    extraction_run: PolicyExtractionRunItem | None = None
    draft_rules: list[ExtractedDraftRule] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    unsupported_or_missing_fields: list[str] = Field(default_factory=list)
    suggested_feature_engineering: list[str] = Field(default_factory=list)
    summary: str = ""
