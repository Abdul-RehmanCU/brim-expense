import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

if "supabase" not in sys.modules:
    supabase_module = types.ModuleType("supabase")
    supabase_module.Client = object
    supabase_module.create_client = lambda *args, **kwargs: None
    sys.modules["supabase"] = supabase_module
if "postgrest.exceptions" not in sys.modules:
    postgrest_module = types.ModuleType("postgrest")
    exceptions_module = types.ModuleType("postgrest.exceptions")
    exceptions_module.APIError = Exception
    sys.modules["postgrest"] = postgrest_module
    sys.modules["postgrest.exceptions"] = exceptions_module

from app.schemas.approvals import (
    ApprovalExplanation,
    ApprovalListResponse,
    ApprovalRecommendation,
    ApprovalRequestDetail,
    ApprovalRequestItem,
)
from app.routers import approvals

app = FastAPI()
app.include_router(approvals.router)


def test_approvals_create_endpoint(monkeypatch):
    def fake_create(request):
        assert request.review_queue_item_id == "queue_1"
        assert request.actor == "Amelia Stone"
        return approval_detail()

    monkeypatch.setattr("app.routers.approvals.create_approval_request", fake_create)

    response = TestClient(app).post(
        "/approvals",
        json={"review_queue_item_id": "queue_1", "actor": "Amelia Stone"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "approval_1"
    assert payload["ai_recommendation"]["recommendation"] == "deny"


def test_approvals_decision_endpoint(monkeypatch):
    def fake_decide(approval_id, request):
        assert approval_id == "approval_1"
        assert request.decision == "approved"
        assert request.actor == "Maya Patel"
        return approval_detail(status="approved", decided_by="Maya Patel")

    monkeypatch.setattr("app.routers.approvals.decide_approval", fake_decide)

    response = TestClient(app).post(
        "/approvals/approval_1/decision",
        json={"decision": "approved", "actor": "Maya Patel", "note": "Conference registration approved."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["decided_by"] == "Maya Patel"


def test_approvals_list_endpoint(monkeypatch):
    def fake_list(status=None, limit=100, offset=0):
        assert status == "requested"
        assert limit == 25
        assert offset == 0
        return ApprovalListResponse(approvals=[approval_item()])

    monkeypatch.setattr("app.routers.approvals.list_approvals", fake_list)

    response = TestClient(app).get("/approvals?status=requested&limit=25")

    assert response.status_code == 200
    assert response.json()["approvals"][0]["employee_name"] == "Sarah Chen"


def test_approvals_explanation_endpoint(monkeypatch):
    def fake_explanation(approval_id):
        assert approval_id == "approval_1"
        return ApprovalExplanation(
            decision="deny",
            confidence="medium",
            summary="Deny is recommended because required context is missing.",
            blocking_reasons=[],
            supporting_evidence=["Policy status: approval_evidence_needed."],
            missing_information=["manager pre-authorization evidence"],
            cited_policy_clauses=[],
            would_change_outcome_if=["Attach or confirm manager pre-authorization evidence."],
        )

    monkeypatch.setattr("app.routers.approvals.get_approval_explanation", fake_explanation)

    response = TestClient(app).get("/approvals/approval_1/explanation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "deny"
    assert payload["missing_information"] == ["manager pre-authorization evidence"]


def approval_item(**overrides):
    values = {
        "id": "approval_1",
        "transaction_id": "txn_1",
        "employee_id": "employee_1",
        "employee_name": "Sarah Chen",
        "department_id": "department_1",
        "department_name": "Marketing",
        "approver_name": "Maya Patel",
        "status": "requested",
        "requested_amount_cad": 1200,
        "transaction_date": "2026-05-30",
        "merchant": "Conference Demo",
        "category": "Events / Conference",
        "ai_recommendation": ApprovalRecommendation(
            recommendation="deny",
            confidence="medium",
            rationale="Manager pre-authorization evidence is needed.",
            grounded_inputs=["Policy status: approval_evidence_needed."],
            missing_information=["manager pre-authorization evidence"],
        ),
    }
    values.update(overrides)
    return ApprovalRequestItem(**values)


def approval_detail(**overrides):
    return ApprovalRequestDetail(**approval_item(**overrides).model_dump())
