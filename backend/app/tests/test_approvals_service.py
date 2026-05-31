import sys
import types

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
    ApprovalContextSnapshot,
    ApprovalDecisionRequest,
    ApprovalRecommendation,
    DepartmentBudgetStatus,
    EmployeeSpendHistory,
)
from app.services import approvals_service
from app.services.approvals_service import (
    approval_recommendation_from_row,
    build_approval_explanation,
    compose_approval_recommendation,
)


def test_approval_recommendation_requests_information_for_missing_preapproval() -> None:
    recommendation = compose_approval_recommendation(
        approval_snapshot(
            policy={
                "status": "approval_evidence_needed",
                "missing_information": ["manager pre-authorization evidence"],
                "flags": [
                    {
                        "rule_code": "PREAPPROVAL_OVER_50",
                        "severity": "high",
                        "explanation": "Amount exceeds threshold.",
                        "required_action": "Collect preapproval.",
                    }
                ],
            }
        )
    )

    assert recommendation.recommendation == "deny"
    assert "manager pre-authorization evidence" in recommendation.missing_information
    assert recommendation.grounded_inputs


def test_approval_recommendation_denies_non_reimbursable_policy() -> None:
    recommendation = compose_approval_recommendation(
        approval_snapshot(
            policy={
                "status": "policy_violation",
                "missing_information": [],
                "flags": [
                    {
                        "rule_code": "TICKETS_NOT_REIMBURSABLE",
                        "severity": "high",
                        "explanation": "Traffic tickets are not reimbursable.",
                        "required_action": "Do not reimburse.",
                    }
                ],
            }
        )
    )

    assert recommendation.recommendation == "deny"
    assert recommendation.confidence == "high"


def test_approval_recommendation_approves_clean_budgeted_request() -> None:
    recommendation = compose_approval_recommendation(approval_snapshot())

    assert recommendation.recommendation == "approve"
    assert recommendation.confidence == "high"


def test_ai_approval_recommendation_is_constrained_by_missing_information() -> None:
    class ApprovingClient:
        def compose_approval_recommendation(self, facts):
            return ApprovalRecommendation(
                recommendation="approve",
                confidence="high",
                rationale="Approve despite missing context.",
                grounded_inputs=facts["deterministic_fallback"]["grounded_inputs"],
                missing_information=[],
                source="openai_structured_output",
            )

    recommendation = compose_approval_recommendation(
        approval_snapshot(
            policy={
                "status": "approval_evidence_needed",
                "missing_information": ["manager pre-authorization evidence"],
                "flags": [],
            }
        ),
        client=ApprovingClient(),
    )

    assert recommendation.recommendation == "deny"
    assert recommendation.source == "openai_structured_output"
    assert "manager pre-authorization evidence" in recommendation.missing_information


def test_legacy_request_information_recommendation_reads_as_deny() -> None:
    recommendation = approval_recommendation_from_row(
        {
            "recommendation": "request_information",
            "confidence": "medium",
            "rationale": "Ask for more information.",
            "grounded_inputs": ["Transaction requires approval evidence."],
            "missing_information": ["manager approval"],
            "source": "openai_structured_output",
        }
    )

    assert recommendation
    assert recommendation.recommendation == "deny"
    assert recommendation.missing_information == ["manager approval"]


def test_approval_explanation_highlights_missing_context_and_reversal_path() -> None:
    snapshot = approval_snapshot(
        policy={
            "status": "approval_evidence_needed",
            "missing_information": ["manager pre-authorization evidence"],
            "flags": [
                {
                    "rule_code": "PREAPPROVAL_OVER_50",
                    "severity": "high",
                    "explanation": "Amount exceeds threshold.",
                    "required_action": "Collect preapproval.",
                }
            ],
        }
    )
    explanation = build_approval_explanation(
        item=approval_item(ai_recommendation=compose_approval_recommendation(snapshot), policy_status="approval_evidence_needed"),
        snapshot=snapshot,
        reviewer_brief=None,
    )

    assert explanation
    assert explanation.decision == "deny"
    assert explanation.blocking_reasons
    assert explanation.blocking_reasons[0].label == "Missing required context"
    assert "manager pre-authorization evidence" in explanation.missing_information
    assert "Collect preapproval." in explanation.would_change_outcome_if


def test_approval_explanation_for_clean_packet_reads_as_approve() -> None:
    snapshot = approval_snapshot()
    explanation = build_approval_explanation(
        item=approval_item(ai_recommendation=compose_approval_recommendation(snapshot), policy_status="compliant", risk_level="low"),
        snapshot=snapshot,
        reviewer_brief=None,
    )

    assert explanation
    assert explanation.decision == "approve"
    assert explanation.blocking_reasons == []
    assert explanation.would_change_outcome_if == ["No blocking policy, risk, or budget condition is currently attached to this packet."]
    assert explanation.supporting_evidence


def test_decide_approval_cascades_decision_to_review_cluster(monkeypatch) -> None:
    existing = {
        "id": "approval_1",
        "transaction_id": "txn_1",
        "employee_id": "employee_1",
        "department_id": "department_1",
        "status": "requested",
        "requested_amount_cad": 120,
        "created_at": "2026-05-01T00:00:00Z",
    }
    cluster_transactions = [
        {
            "id": "txn_1",
            "employee_id": "employee_1",
            "department_id": "department_1",
            "transaction_date": "2026-05-01",
            "normalized_merchant_name": "DUPLICATE MERCHANT",
            "amount_cad": 120,
            "business_category": "Software",
        },
        {
            "id": "txn_2",
            "employee_id": "employee_1",
            "department_id": "department_1",
            "transaction_date": "2026-05-01",
            "normalized_merchant_name": "DUPLICATE MERCHANT",
            "amount_cad": 120,
            "business_category": "Software",
        },
    ]
    cluster_approvals = [
        existing,
        {**existing, "id": "approval_2", "transaction_id": "txn_2"},
    ]
    client = FakeApprovalDecisionClient()
    preapproval_updates = []
    queue_updates = []
    audit_events = []

    monkeypatch.setattr(approvals_service, "get_supabase_client", lambda: client)
    monkeypatch.setattr(approvals_service, "fetch_one_by_id", lambda table_name, row_id, columns: existing if table_name == "approval_requests" else None)
    monkeypatch.setattr(approvals_service, "fetch_review_cluster_transactions_for_transaction_id", lambda transaction_id: cluster_transactions)
    monkeypatch.setattr(
        approvals_service,
        "fetch_rows_by_values",
        lambda table_name, column_name, values, columns: cluster_approvals if table_name == "approval_requests" else [],
    )
    monkeypatch.setattr(
        approvals_service,
        "update_preapproval_from_decision",
        lambda approval, request, decided_at: preapproval_updates.append((approval["transaction_id"], request.decision)),
    )
    monkeypatch.setattr(approvals_service, "update_review_queue_status", lambda transaction_id, status: queue_updates.append((transaction_id, status)))
    monkeypatch.setattr(approvals_service, "insert_audit_event", lambda **kwargs: audit_events.append(kwargs))
    monkeypatch.setattr(approvals_service, "get_approval", lambda approval_id: approval_id)

    result = approvals_service.decide_approval(
        "approval_1",
        ApprovalDecisionRequest(decision="denied", actor="Maya Patel", note="Duplicate cluster."),
    )

    assert result == "approval_1"
    assert client.updated_ids == ["approval_1", "approval_2"]
    assert preapproval_updates == [("txn_1", "denied"), ("txn_2", "denied")]
    assert queue_updates == [("txn_1", "resolved"), ("txn_2", "resolved")]
    assert [event["entity_id"] for event in audit_events] == ["approval_1", "approval_2"]


def approval_snapshot(**overrides):
    values = {
        "transaction": {"id": "txn_1", "merchant": "Conference Demo", "amount_cad": 1200},
        "employee": {"id": "employee_1", "full_name": "Sarah Chen", "synthetic": True},
        "department": {"id": "department_1", "name": "Marketing", "manager_name": "Maya Patel", "synthetic": True},
        "policy": {"status": "compliant", "missing_information": [], "flags": []},
        "risk": {"score": 12, "level": "low", "signals": []},
        "budget": DepartmentBudgetStatus(
            department_id="department_1",
            department_name="Marketing",
            monthly_budget_cad=35000,
            quarterly_budget_cad=105000,
            month_to_date_spend_cad=12000,
            quarter_to_date_spend_cad=26000,
            monthly_remaining_cad=23000,
            quarterly_remaining_cad=79000,
        ),
        "spend_history": EmployeeSpendHistory(
            employee_id="employee_1",
            employee_name="Sarah Chen",
            transaction_count=10,
            total_spend_cad=4200,
            same_category_count=2,
            same_category_spend_cad=1800,
            prior_approval_count=1,
            prior_approved_count=1,
        ),
        "review_queue": {},
    }
    values.update(overrides)
    return ApprovalContextSnapshot(**values)


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
        "policy_check_id": "policy_1",
        "policy_status": "compliant",
        "policy_severity": "low",
        "policy_flags": [],
        "risk_score_id": "risk_1",
        "risk_score": 12,
        "risk_level": "low",
        "risk_signals": [],
        "ai_recommendation": None,
        "reviewer_brief": None,
        "budget_status": None,
        "spend_history": None,
        "requester_note": None,
        "decision_note": None,
        "decided_by": None,
        "decided_at": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    from app.schemas.approvals import ApprovalRequestItem

    return ApprovalRequestItem(**values)


class FakeApprovalDecisionClient:
    def __init__(self):
        self.updated_ids = []

    def table(self, table_name):
        assert table_name == "approval_requests"
        return FakeApprovalDecisionQuery(self)


class FakeApprovalDecisionQuery:
    def __init__(self, client):
        self.client = client
        self.update_payload = None

    def update(self, payload):
        self.update_payload = payload
        return self

    def eq(self, column, value):
        assert column == "id"
        assert self.update_payload["status"] == "denied"
        self.client.updated_ids.append(value)
        return self

    def execute(self):
        return types.SimpleNamespace(data=[])
