from app.schemas.common import PlaceholderResponse
from app.schemas.reports import ExpenseReportDetail, ExpenseReportListResponse, ReportCsvResponse, ReportGenerateRequest, ReportGenerateResponse
from app.services.reports_service import export_report_csv, generate_reports, get_report, get_reports_status, list_reports


def report_status() -> PlaceholderResponse:
    return get_reports_status()


def report_generate(request: ReportGenerateRequest | None = None) -> ReportGenerateResponse:
    return generate_reports(request or ReportGenerateRequest())


def report_list() -> ExpenseReportListResponse:
    return list_reports()


def report_detail(report_id: str) -> ExpenseReportDetail:
    return get_report(report_id)


def report_export_csv(report_id: str) -> ReportCsvResponse:
    return export_report_csv(report_id)
