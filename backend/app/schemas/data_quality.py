from typing import Any, Literal

from pydantic import BaseModel, Field


DataQualitySeverity = Literal["low", "medium", "high", "critical"]


class DataQualityFinding(BaseModel):
    rule_id: str
    severity: DataQualitySeverity
    field: str | None = None
    transaction_id: str | None = None
    source_row: int | None = None
    source_fingerprint: str | None = None
    row_index: int | None = None
    observed_value: Any = None
    explanation: str
    remediation: str


class DataQualitySummary(BaseModel):
    row_count: int = 0
    finding_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    rows_with_findings: int = 0


class GreatExpectationsAudit(BaseModel):
    available: bool = False
    suite_name: str = "brim_transaction_data_quality"
    evaluated_expectations: int = 0
    failed_expectations: int = 0
    error: str | None = None


class DataQualityValidationRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    run_great_expectations: bool = True


class DataQualityValidationResponse(BaseModel):
    row_count: int
    findings: list[DataQualityFinding]
    summary: DataQualitySummary
    great_expectations: GreatExpectationsAudit
