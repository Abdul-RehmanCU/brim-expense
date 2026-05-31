from app.schemas.common import PlaceholderResponse
from app.schemas.risk import RiskLevel, RiskScanRequest, RiskScanSummary, RiskScoreItem
from app.services.risk_service import get_risk_status, list_risk_scores, scan_risk


def risk_status() -> PlaceholderResponse:
    return get_risk_status()


def risk_scan_transactions(request: RiskScanRequest | None = None) -> RiskScanSummary:
    return scan_risk(request)


def risk_list_scores(
    min_level: RiskLevel = "medium",
    limit: int = 100,
    signal_type: str | None = None,
    department_id: str | None = None,
    employee_id: str | None = None,
) -> list[RiskScoreItem]:
    return list_risk_scores(
        min_level=min_level,
        limit=limit,
        signal_type=signal_type,
        department_id=department_id,
        employee_id=employee_id,
    )

