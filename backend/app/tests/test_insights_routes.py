from fastapi.testclient import TestClient

from app.main import app
from app.schemas.insights import (
    InsightArtifactRequest,
    InsightPlan,
    InsightPlanResponse,
    InsightQueryResponse,
    InsightSession,
    InsightSessionDetail,
    InsightValidationResult,
)


def test_insights_create_session_endpoint(monkeypatch):
    def fake_create_session(request):
        assert request.page_context is not None
        assert request.page_context.page == "reports"
        return InsightSession(
            id="session_1",
            title="Talk to Data",
            created_at="2026-05-31T00:00:00Z",
            updated_at="2026-05-31T00:00:00Z",
        )

    def fake_get_session(session_id):
        return InsightSessionDetail(
            session=InsightSession(
                id=session_id,
                title="Talk to Data",
                created_at="2026-05-31T00:00:00Z",
                updated_at="2026-05-31T00:00:00Z",
            ),
            messages=[],
        )

    monkeypatch.setattr("app.routers.insights.create_insight_session", fake_create_session)
    monkeypatch.setattr("app.routers.insights.get_insight_session", fake_get_session)

    response = TestClient(app).post(
        "/insights/sessions",
        json={"page_context": {"page": "reports", "route": "/reports/report_1", "payload": {"department": "Marketing"}}},
    )

    assert response.status_code == 200
    assert response.json()["session"]["id"] == "session_1"


def test_insights_list_sessions_endpoint(monkeypatch):
    monkeypatch.setattr(
        "app.routers.insights.list_insight_sessions",
        lambda limit=40: [
            InsightSession(id="session_2", title="Review queue follow-up"),
            InsightSession(id="session_1", title="Marketing spend"),
        ][:limit],
    )

    response = TestClient(app).get("/insights/sessions?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["id"] == "session_2"


def test_insights_plan_endpoint(monkeypatch):
    def fake_create_insight_plan(request):
        return InsightPlanResponse(
            question=request.question,
            plan=InsightPlan(intent="top_merchants", tool="spend.topMerchants"),
            validation=InsightValidationResult(valid=True),
            critic=InsightValidationResult(valid=True),
        )

    monkeypatch.setattr("app.routers.insights.create_insight_plan", fake_create_insight_plan)

    response = TestClient(app).post("/insights/plan", json={"question": "Show top merchants"})

    assert response.status_code == 200
    assert response.json()["plan"]["tool"] == "spend.topMerchants"


def test_insights_query_endpoint(monkeypatch):
    def fake_query_insights(request):
        assert request.page_context is not None
        assert request.page_context.payload["department_name"] == "Marketing"
        return InsightQueryResponse(
            question=request.question,
            session_id=request.session_id,
            plan=InsightPlan(intent="spend_summary"),
            validation=InsightValidationResult(valid=True),
            planner_source="deterministic",
            summary="All matching spend: CAD 100.00 across 2 transaction(s).",
            columns=["label", "sum_amount_cad"],
            rows=[{"label": "All matching spend", "values": {"sum_amount_cad": 100}}],
            visualization="metric",
        )

    monkeypatch.setattr("app.routers.insights.query_insights", fake_query_insights)

    response = TestClient(app).post(
        "/insights/query",
        json={
            "question": "Summarize spend",
            "session_id": "session_1",
            "page_context": {"page": "dashboard", "payload": {"department_name": "Marketing"}},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "session_1"
    assert payload["summary"].startswith("All matching spend")
    assert payload["rows"][0]["values"]["sum_amount_cad"] == 100


def test_insights_artifact_endpoint(monkeypatch):
    def fake_build_insight_artifact(result, artifact_type):
        assert artifact_type == "brief"
        assert result.question == "Summarize spend"
        return ("# spend_summary", "spend-summary.md", "text/markdown; charset=utf-8")

    monkeypatch.setattr("app.routers.insights.build_insight_artifact", fake_build_insight_artifact)

    response = TestClient(app).post(
        "/insights/artifacts/brief",
        json={
            "result": {
                "question": "Summarize spend",
                "session_id": "session_1",
                "plan": {
                    "intent": "spend_summary",
                    "mode": "answer",
                    "tool": "spend.summary",
                    "filters": {},
                    "group_by": [],
                    "metrics": ["sum_amount_cad"],
                    "sort": [],
                    "limit": 100,
                    "visualization": "metric",
                    "comparison_options": {},
                    "report_options": {},
                },
                "validation": {"valid": True, "errors": [], "warnings": []},
                "planner_source": "deterministic",
                "summary": "All matching spend: CAD 100.00 across 2 transaction(s).",
                "columns": ["label", "sum_amount_cad"],
                "rows": [{"label": "All matching spend", "values": {"sum_amount_cad": 100}}],
                "citations": [],
                "visualization": "metric",
                "metadata": {},
            }
        },
    )

    assert response.status_code == 200
    assert response.text == "# spend_summary"
    assert response.headers["content-disposition"] == 'attachment; filename="spend-summary.md"'
    assert response.headers["content-type"].startswith("text/markdown")


def test_insights_session_artifact_download_endpoint(monkeypatch):
    def fake_build_session_artifact(session_id, artifact_type, message_id=None):
        assert session_id == "session_1"
        assert artifact_type == "csv"
        assert message_id is None
        return ("label,sum_amount_cad\nMarketing,100\n", "spend-summary.csv", "text/csv; charset=utf-8")

    monkeypatch.setattr("app.routers.insights.build_session_artifact", fake_build_session_artifact)

    response = TestClient(app).get("/insights/sessions/session_1/artifacts/csv")

    assert response.status_code == 200
    assert response.text.startswith("label,sum_amount_cad")
    assert response.headers["content-disposition"] == 'attachment; filename="spend-summary.csv"'
    assert response.headers["content-type"].startswith("text/csv")


def test_insights_message_artifact_download_endpoint(monkeypatch):
    def fake_build_session_artifact(session_id, artifact_type, message_id=None):
        assert session_id == "session_1"
        assert artifact_type == "diagram"
        assert message_id == "msg_2"
        return ("flowchart TD", "spend-summary.mmd", "text/plain; charset=utf-8")

    monkeypatch.setattr("app.routers.insights.build_session_artifact", fake_build_session_artifact)

    response = TestClient(app).get("/insights/sessions/session_1/messages/msg_2/artifacts/diagram")

    assert response.status_code == 200
    assert response.text == "flowchart TD"
    assert response.headers["content-disposition"] == 'attachment; filename="spend-summary.mmd"'
    assert response.headers["content-type"].startswith("text/plain")
