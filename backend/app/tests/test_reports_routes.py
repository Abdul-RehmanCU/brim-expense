from fastapi.testclient import TestClient

from app.main import app
from app.schemas.reports import (
    ExpenseReportDetail,
    ExpenseReportLineItem,
    ExpenseReportListResponse,
    ExpenseReportSummary,
    ReportGenerateResponse,
    ReportPlanTarget,
)


def test_reports_generate_endpoint(monkeypatch):
    def fake_generate_reports(request):
        assert request.request == "Generate Sarah Chen report"
        return ReportGenerateResponse(
            request=request.request,
            planner_source="deterministic",
            sql_preview="select * from transactions;",
            generated_count=1,
            targets=[
                ReportPlanTarget(
                    scope_type="employee",
                    requested_label="Sarah Chen",
                    resolved_label="Sarah Chen",
                    report_count=1,
                )
            ],
            reports=[report_detail()],
        )

    monkeypatch.setattr("app.routers.reports.generate_reports", fake_generate_reports)

    response = TestClient(app).post("/reports/generate", json={"request": "Generate Sarah Chen report"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_count"] == 1
    assert payload["reports"][0]["id"] == "report_1"
    assert payload["reports"][0]["line_items"][0]["transaction_id"] == "txn_1"


def test_reports_list_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.routers.reports.list_reports",
        lambda limit=25, offset=0: ExpenseReportListResponse(reports=[report_summary()]),
    )

    response = TestClient(app).get("/reports")

    assert response.status_code == 200
    assert response.json()["reports"][0]["employee_name"] == "Sarah Chen"


def test_reports_csv_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.routers.reports.export_report_csv",
        lambda report_id: type("Csv", (), {"csv": "Total CAD,10.00\n", "content_type": "text/csv", "file_name": "report.csv"})(),
    )

    response = TestClient(app).get("/reports/report_1/csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="report.csv"'
    assert "Total CAD,10.00" in response.text


def report_summary():
    return ExpenseReportSummary(
        id="report_1",
        employee_id="employee_1",
        employee_name="Sarah Chen",
        department_id="department_1",
        department_name="Marketing",
        period_start="2026-05-01",
        period_end="2026-05-31",
        status="generated",
        total_amount_cad=10,
        item_count=1,
    )


def report_detail():
    return ExpenseReportDetail(
        **report_summary().model_dump(),
        line_items=[
            ExpenseReportLineItem(
                id="item_1",
                transaction_id="txn_1",
                transaction_date="2026-05-01",
                merchant="AIR CANADA",
                amount_cad=10,
                category="Travel",
                policy_status="compliant",
                risk_level="low",
            )
        ],
    )
