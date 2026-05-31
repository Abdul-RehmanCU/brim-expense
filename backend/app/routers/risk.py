from fastapi import APIRouter, Query

from app.schemas.common import PlaceholderResponse
from app.schemas.risk import RiskLevel, RiskScanRequest, RiskScanSummary, RiskScoreItem
from app.tools.risk_tools import risk_list_scores, risk_scan_transactions, risk_status

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/status", response_model=PlaceholderResponse)
def risk_status_route() -> PlaceholderResponse:
    return risk_status()


@router.post("/scan", response_model=RiskScanSummary)
def scan_risk(request: RiskScanRequest | None = None) -> RiskScanSummary:
    return risk_scan_transactions(request or RiskScanRequest())


@router.get("/scores", response_model=list[RiskScoreItem])
def risk_scores(
    min_level: RiskLevel = Query(default="medium"),
    limit: int = Query(default=100, ge=1, le=500),
    signal_type: str | None = Query(default=None),
    department_id: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
) -> list[RiskScoreItem]:
    return risk_list_scores(
        min_level=min_level,
        limit=limit,
        signal_type=signal_type,
        department_id=department_id,
        employee_id=employee_id,
    )

