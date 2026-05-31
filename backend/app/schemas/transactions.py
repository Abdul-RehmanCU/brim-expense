from typing import Any

from pydantic import BaseModel, Field

from app.schemas.data_quality import DataQualityValidationResponse


class TransactionsSummaryResponse(BaseModel):
    raw_transaction_count: int
    normalized_transaction_count: int
    employee_count: int
    department_count: int


class TransactionEnrichmentRequest(BaseModel):
    batch_size: int = 500
    limit: int | None = None
    dry_run: bool = False


class TransactionEnrichmentResponse(BaseModel):
    total_seen: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: int = 0
    batch_count: int = 0
    error_messages: list[str] = []


class TransactionResetResponse(BaseModel):
    deleted_transactions: int = 0
    deleted_raw_transactions: int = 0
    deleted_receipts: int = 0
    deleted_preapprovals: int = 0
    deleted_policy_checks: int = 0
    deleted_violations: int = 0
    deleted_risk_scores: int = 0
    deleted_approval_requests: int = 0
    deleted_expense_report_items: int = 0
    deleted_expense_reports: int = 0


class TransactionImportRow(BaseModel):
    source_row_number: int
    source_fingerprint: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    transaction: dict[str, Any] = Field(default_factory=dict)


class TransactionImportRequest(BaseModel):
    source_file_name: str | None = None
    rows: list[TransactionImportRow] = Field(default_factory=list)
    run_data_quality: bool = True
    run_great_expectations: bool = False
    dry_run: bool = False


class TransactionImportResponse(BaseModel):
    inserted_count: int = 0
    skipped_duplicate_count: int = 0
    import_batch_id: str
    validation: DataQualityValidationResponse
    persisted: bool = True
    authoritative_enrichment_applied: int = 0
    warnings: list[str] = Field(default_factory=list)
