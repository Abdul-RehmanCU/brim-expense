from fastapi import APIRouter, Query, Response

from app.schemas.common import PlaceholderResponse
from app.schemas.reports import (
    ExpenseReportDetail,
    ExpenseReportListResponse,
    ReportGenerateRequest,
    ReportGenerateResponse,
    ReportScopeOptionsResponse,
)
from app.services.reports_service import (
    export_report_csv,
    generate_reports,
    get_report,
    get_reports_status,
    list_report_scope_options,
    list_reports,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/status", response_model=PlaceholderResponse)
def reports_status() -> PlaceholderResponse:
    return get_reports_status()


@router.get("/scope-options", response_model=ReportScopeOptionsResponse)
def reports_scope_options() -> ReportScopeOptionsResponse:
    return list_report_scope_options()


@router.post("/generate", response_model=ReportGenerateResponse)
def reports_generate(request: ReportGenerateRequest | None = None) -> ReportGenerateResponse:
    return generate_reports(request or ReportGenerateRequest())


@router.get("", response_model=ExpenseReportListResponse)
def reports_list(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ExpenseReportListResponse:
    return list_reports(limit=limit, offset=offset)


@router.get("/{report_id}", response_model=ExpenseReportDetail)
def reports_detail(report_id: str) -> ExpenseReportDetail:
    return get_report(report_id)


@router.get("/{report_id}/csv")
def reports_csv(report_id: str) -> Response:
    csv_response = export_report_csv(report_id)
    return Response(
        content=csv_response.csv,
        media_type=csv_response.content_type,
        headers={"Content-Disposition": f'attachment; filename="{csv_response.file_name}"'},
    )
