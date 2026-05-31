from fastapi.testclient import TestClient

from app.main import app
from app.schemas.policy import (
    PolicyFindingItem,
    PolicyResetResponse,
    PolicyRuleItem,
    PolicyRuleTestResponse,
    PolicyViolation,
    RepeatOffenderItem,
    RepeatOffenderSummary,
)


def test_policy_findings_endpoint_returns_grouped_transaction_findings(monkeypatch):
    def fake_policy_list_findings(severity=None, status=None, department_id=None):
        return [
            PolicyFindingItem(
                transaction_id="txn_1",
                employee="Synthetic Employee",
                department="Synthetic Department",
                date="2026-05-10",
                merchant="STAPLES",
                amount_cad=75,
                category="Office Supplies",
                overall_status="approval_evidence_needed",
                max_severity="high",
                violations=[
                    PolicyViolation(
                        rule_code="PREAPPROVAL_OVER_50",
                        severity="high",
                        explanation="Needs preapproval.",
                        required_action="Get approval.",
                    ),
                    PolicyViolation(
                        rule_code="RECEIPT_REQUIRED",
                        severity="medium",
                        explanation="Receipt missing.",
                        required_action="Attach receipt.",
                    ),
                ],
                missing_information=[],
                recommended_next_action="Request manager preauthorization before approval.",
            )
        ]

    monkeypatch.setattr("app.routers.policy.policy_list_findings", fake_policy_list_findings)

    response = TestClient(app).get("/policy/findings")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["transaction_id"] == "txn_1"
    assert payload[0]["overall_status"] == "approval_evidence_needed"
    assert len(payload[0]["violations"]) == 2


def test_repeat_offenders_endpoint_returns_employee_and_department_counts(monkeypatch):
    def fake_repeat_offenders():
        return RepeatOffenderSummary(
            employees=[RepeatOffenderItem(id="employee_1", name="Synthetic Employee", open_violations=3)],
            departments=[RepeatOffenderItem(id="department_1", name="Synthetic Department", open_violations=5)],
        )

    monkeypatch.setattr("app.routers.policy.policy_repeat_offenders", fake_repeat_offenders)

    response = TestClient(app).get("/policy/repeat-offenders")

    assert response.status_code == 200
    payload = response.json()
    assert payload["employees"][0]["open_violations"] == 3
    assert payload["departments"][0]["name"] == "Synthetic Department"


def test_policy_scan_endpoint_accepts_batch_options(monkeypatch):
    def fake_run_policy_scan_and_refresh(request):
        assert request.batch_size == 250
        assert request.dry_run is True
        return {
            "total_scanned": 2,
            "compliant": 1,
            "excluded_non_expense": 1,
            "evidence_required": 0,
            "approval_evidence_required": 0,
            "approval_evidence_needed": 0,
            "context_needed": 0,
            "policy_violations": 0,
            "policy_violation": 0,
            "review_required": 0,
            "high_or_critical": 0,
            "individual_flags": 0,
            "violations_created": 0,
            "duration_ms": 12,
            "batch_count": 1,
        }

    monkeypatch.setattr("app.routers.policy.run_policy_scan_and_refresh", fake_run_policy_scan_and_refresh)

    response = TestClient(app).post("/policy/scan", json={"batch_size": 250, "dry_run": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_scanned"] == 2
    assert payload["batch_count"] == 1
    assert payload["individual_flags"] == 0


def test_policy_rules_endpoint_returns_seeded_rules(monkeypatch):
    def fake_policy_rules_list(limit=50, offset=0, status=None):
        assert limit == 50
        assert offset == 0
        assert status is None
        return [
            PolicyRuleItem(
                id="rule_1",
                rule_code="PREAPPROVAL_OVER_50",
                name="Preapproval over threshold",
                description="Expenses over CAD 50 require approval evidence.",
                severity="high",
                enabled=True,
                status="active",
            )
        ]

    monkeypatch.setattr("app.routers.policy.policy_rules_list", fake_policy_rules_list)

    response = TestClient(app).get("/policy/rules")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["rule_code"] == "PREAPPROVAL_OVER_50"
    assert payload[0]["status"] == "active"


def test_policy_reset_endpoint_returns_cleanup_summary(monkeypatch):
    def fake_policy_reset_data():
        return PolicyResetResponse(
            rows_deleted={
                "violations": 3,
                "policy_checks": 2,
                "policy_rules": 4,
                "policy_chunks": 1,
                "policy_extraction_runs": 1,
                "policy_documents": 1,
                "receipts": 5,
                "preapprovals": 2,
            },
            storage_paths_removed=1,
            warnings=[],
        )

    monkeypatch.setattr("app.routers.policy.policy_reset_data", fake_policy_reset_data)

    response = TestClient(app).delete("/policy/reset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows_deleted"]["policy_rules"] == 4
    assert payload["rows_deleted"]["policy_documents"] == 1
    assert payload["storage_paths_removed"] == 1


def test_policy_rules_test_draft_endpoint_returns_validation_result(monkeypatch):
    def fake_policy_rules_test_draft(request):
        assert request.rule_json["conditions"]["all"][0]["field"] == "amount_cad"
        return PolicyRuleTestResponse(valid=True, warnings=[])

    monkeypatch.setattr("app.routers.policy.policy_rules_test_draft", fake_policy_rules_test_draft)

    response = TestClient(app).post(
        "/policy/rules/test-draft",
        json={
            "rule_json": {
                "conditions": {
                    "all": [{"field": "amount_cad", "operator": "greater_than", "value": 50}],
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["matched_count"] == 0
