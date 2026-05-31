from typing import Any, Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical"]
RiskDetectorProfile = Literal["focused", "full"]


class RiskSignal(BaseModel):
    type: str
    severity: RiskLevel
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RiskScanRequest(BaseModel):
    department_id: str | None = None
    employee_id: str | None = None
    date_start: str | None = None
    date_end: str | None = None
    limit: int | None = None
    dry_run: bool = False
    reset_existing: bool = True
    split_window_days: int = 0
    anomaly_model: Literal["auto", "pyod", "sklearn"] = "auto"
    detector_profile: RiskDetectorProfile = "focused"


class RiskScanSummary(BaseModel):
    total_scanned: int = 0
    scored: int = 0
    persisted: int = 0
    high_or_critical: int = 0
    signal_counts: dict[str, int] = Field(default_factory=dict)
    duration_ms: int = 0
    engine_version: str
    dry_run: bool = False


class RiskScoreItem(BaseModel):
    id: str | None = None
    transaction_id: str
    risk_score: int
    risk_level: RiskLevel
    signals: list[RiskSignal] = Field(default_factory=list)
    scored_at: str | None = None
    engine_version: str | None = None
    employee: str | None = None
    department: str | None = None
    transaction_date: str | None = None
    merchant: str | None = None
    amount_cad: float = 0
    category: str = "Uncategorized"
