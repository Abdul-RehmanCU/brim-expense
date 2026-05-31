from app.schemas.review_queue import CitedPolicyClause, ReviewerBrief
from app.schemas.risk import RiskSignal
from app.services.reviewer_brief_service import compose_reviewer_brief


def test_compose_reviewer_brief_uses_deterministic_facts() -> None:
    brief = compose_reviewer_brief(
        transaction={
            "id": "txn-1",
            "employee_id": "emp-1",
            "department_id": "dept-1",
            "transaction_date": "2026-05-30",
            "normalized_merchant_name": "Hotel Demo",
            "amount_cad": 183.42,
            "business_category": "Lodging",
        },
        policy_check={
            "status": "approval_evidence_needed",
            "max_severity": "high",
            "missing_information": ["manager pre-authorization evidence"],
        },
        risk_score={"risk_score": 72, "risk_level": "high"},
        policy_flags=[
            {
                "rule_code": "PREAPPROVAL_OVER_50",
                "severity": "high",
                "explanation": "This transaction exceeds the active preapproval threshold.",
                "required_action": "Collect the required preapproval evidence.",
            }
        ],
        risk_signals=[
            RiskSignal(
                type="near_approval_threshold",
                severity="medium",
                message="Amount is near the policy threshold.",
                evidence={},
            )
        ],
        cited_policy_clauses=[
            CitedPolicyClause(
                rule_code="PREAPPROVAL_OVER_50",
                clause_id="clause-1",
                title="Preapproval",
                text="Expenses above the threshold require manager pre-authorization.",
                source="policy_chunks",
            )
        ],
        fallback_next_action="Collect the required preapproval evidence.",
    )

    assert brief.generated_by == "deterministic_fallback"
    assert brief.confidence == "low"
    assert brief.recommended_next_action == "Collect the required preapproval evidence."
    assert "deterministic policy status Approval Evidence Needed" in brief.summary
    assert brief.missing_context == ["manager pre-authorization evidence"]
    assert brief.cited_policy_clauses[0].rule_code == "PREAPPROVAL_OVER_50"
    assert "source of truth" in brief.advisory_notice


def test_compose_reviewer_brief_includes_data_quality_findings_as_missing_context() -> None:
    brief = compose_reviewer_brief(
        transaction={"id": "txn-1", "amount_cad": 15},
        policy_check=None,
        risk_score=None,
        policy_flags=[],
        risk_signals=[],
        fallback_next_action="No action required.",
    )

    assert "employee assignment unavailable" in brief.missing_context
    assert "department assignment unavailable" in brief.missing_context
    assert any("Data-quality findings" in warning for warning in brief.grounding_warnings)


def test_ai_brief_is_sanitized_to_deterministic_reasons_and_action() -> None:
    class MockBriefClient:
        def compose_reviewer_brief(self, facts):
            return ReviewerBrief(
                summary="AI wording is allowed, but unsupported reasons are filtered.",
                key_reasons=["Unsupported invented reason"],
                cited_policy_clauses=[
                    CitedPolicyClause(
                        rule_code="MADE_UP_RULE",
                        clause_id="fake",
                        title="Fake",
                        text="Made-up citation.",
                    )
                ],
                missing_context=["receipt evidence"],
                recommended_next_action="Approve immediately.",
                confidence="high",
                grounding_warnings=[],
                generated_by="openai_structured_output",
            )

    brief = compose_reviewer_brief(
        transaction={"id": "txn-1", "merchant_name": "Demo Merchant", "amount_cad": 62},
        policy_check={"status": "context_needed", "max_severity": "medium", "missing_information": []},
        risk_score=None,
        policy_flags=[
            {
                "rule_code": "ENTERTAINMENT_CONTEXT_REQUIRED",
                "severity": "medium",
                "explanation": "Business purpose is incomplete.",
                "required_action": "Request business purpose.",
            }
        ],
        risk_signals=[],
        cited_policy_clauses=[],
        fallback_next_action="Request business purpose.",
        client=MockBriefClient(),
    )

    assert brief.generated_by == "openai_structured_output"
    assert brief.recommended_next_action == "Request business purpose."
    assert brief.key_reasons == [
        "ENTERTAINMENT_CONTEXT_REQUIRED (medium): Business purpose is incomplete."
    ]
    assert brief.cited_policy_clauses == []
    assert any("AI-generated reasons were constrained" in warning for warning in brief.grounding_warnings)


def test_failed_ai_client_falls_back_to_deterministic_brief() -> None:
    class FailingBriefClient:
        def compose_reviewer_brief(self, facts):
            raise RuntimeError("provider unavailable")

    brief = compose_reviewer_brief(
        transaction={"id": "txn-1", "merchant_name": "Demo Merchant", "amount_cad": 12},
        policy_check=None,
        risk_score=None,
        policy_flags=[],
        risk_signals=[],
        fallback_next_action="No action required.",
        client=FailingBriefClient(),
    )

    assert brief.generated_by == "deterministic_fallback"
    assert brief.confidence == "low"
    assert brief.recommended_next_action == "No action required."
