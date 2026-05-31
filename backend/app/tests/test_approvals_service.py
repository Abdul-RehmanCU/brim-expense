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
    ApprovalContextSnapshot,
    ApprovalRecommendation,
    DepartmentBudgetStatus,
    EmployeeSpendHistory,
)
from app.services.approvals_service import approval_recommendation_from_row, compose_approval_recommendation


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
