from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.main import app
from app.schemas.policy import PolicyRuleExtractionRequest, PolicyRuleExtractionResponse
from app.services.ai_service import rule_extraction_system_prompt, rule_extraction_user_prompt
from app.services import policy_service


class FakeAiClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, system_prompt: str, user_prompt: str):
        self.calls.append((system_prompt, user_prompt))
        return self.payload


class FakeSupabaseResponse:
    def __init__(self, data):
        self.data = data


class FakePolicyRulesTable:
    def __init__(self):
        self.payloads = []
        self.fail_missing_thresholds_json_once = False

    def upsert(self, payloads, on_conflict=None):
        self.payloads = payloads
        self.on_conflict = on_conflict
        return self

    def execute(self):
        if self.fail_missing_thresholds_json_once and self.payloads and "thresholds_json" in self.payloads[0]:
            self.fail_missing_thresholds_json_once = False
            raise APIError(
                {
                    "message": "Could not find the 'thresholds_json' column of 'policy_rules' in the schema cache",
                    "code": "PGRST204",
                    "hint": None,
                    "details": None,
                }
            )
        return FakeSupabaseResponse(
            [
                {
                    "id": f"rule-{index}",
                    "rule_code": payload["rule_code"],
                }
                for index, payload in enumerate(self.payloads, start=1)
            ]
        )


class FakeSupabaseClient:
    def __init__(self):
        self.policy_rules = FakePolicyRulesTable()

    def table(self, table_name: str):
        assert table_name == "policy_rules"
        return self.policy_rules


def extraction_request() -> PolicyRuleExtractionRequest:
    return PolicyRuleExtractionRequest(
        policy_text="Expenses over CAD 50 require manager preapproval before reimbursement.",
        company_context="Synthetic Brim demo company.",
        available_fields=["amount_cad", "business_category", "department_name", "missing_preapproval"],
    )


def test_mocked_ai_extraction_auto_activates_safe_rules_and_refreshes_downstream(monkeypatch):
    supabase = FakeSupabaseClient()
    monkeypatch.setattr(policy_service, "get_supabase_client", lambda: supabase)
    refresh_calls = []
    monkeypatch.setattr(policy_service, "run_policy_scan_and_refresh", lambda request: refresh_calls.append(request))
    ai_client = FakeAiClient(
        {
            "draft_rules": [
                {
                    "rule_code": "preapproval_over_50",
                    "name": "Preapproval over CAD 50",
                    "description": "Manager preapproval is required over CAD 50.",
                    "severity": "high",
                        "rule_json": {
                            "condition": {
                                "all": [
                                    {"field": "amount_cad", "operator": "greater_than", "value": 50},
                                    {"field": "missing_preapproval", "operator": "equals", "value": True},
                                ]
                            },
                            "outcome": {
                                "status": "approval_evidence_needed",
                                "message": "Approval evidence is required.",
                            "required_action": "Collect manager approval evidence.",
                        },
                        "scope": {"department_ids": [], "employee_ids": []},
                        "applies_to": {"transaction_types": ["card_purchase"]},
                        "thresholds": {
                            "preapproval_threshold_cad": {
                                "value": 50,
                                "currency": "CAD",
                                "by_department": {"department_1": 75},
                            }
                        },
                        "context_requirements": [],
                        "evidence_requirements": ["manager preapproval"],
                        "requires": {"facts": ["amount_cad"]},
                    },
                    "extraction_confidence": 0.92,
                    "needs_human_review": False,
                }
            ],
            "ambiguities": [],
            "unsupported_or_missing_fields": [],
            "suggested_feature_engineering": ["approval_evidence_available"],
            "summary": "Extracted one approval evidence rule.",
        }
    )

    response = policy_service.extract_policy_rules(extraction_request(), ai_client=ai_client)

    assert len(response.draft_rules) == 1
    assert response.draft_rules[0].status == "active"
    assert response.draft_rules[0].source_type == "ai_extracted"
    assert response.draft_rules[0].needs_human_review is False
    assert supabase.policy_rules.payloads[0]["active"] is True
    assert supabase.policy_rules.payloads[0]["enabled"] is True
    assert supabase.policy_rules.payloads[0]["source_type"] == "ai_extracted"
    assert supabase.policy_rules.payloads[0]["needs_human_review"] is False
    assert supabase.policy_rules.payloads[0]["status"] == "active"
    assert supabase.policy_rules.payloads[0]["rule_json"]["thresholds"]["preapproval_threshold_cad"]["value"] == 50
    assert supabase.policy_rules.payloads[0]["rule_json"]["condition"]["all"][0]["operator"] == "greater_than"
    assert "manager preapproval" in supabase.policy_rules.payloads[0]["rule_json"]["evidence_requirements"]
    assert supabase.policy_rules.payloads[0]["conditions_json"]["all"][1]["operator"] == "eq"
    assert "Expenses over CAD 50" in supabase.policy_rules.payloads[0]["source_text"]
    assert "transaction rows" not in ai_client.calls[0][1].lower()
    assert len(refresh_calls) == 1


def test_invalid_ai_rule_stays_as_follow_up_draft_without_refresh(monkeypatch):
    supabase = FakeSupabaseClient()
    refresh_calls = []

    monkeypatch.setattr(policy_service, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(policy_service, "run_policy_scan_and_refresh", lambda request: refresh_calls.append(request))
    ai_client = FakeAiClient(
        {
            "draft_rules": [
                {
                    "rule_code": "receipt_due_date",
                    "name": "Receipt due date",
                    "description": "Receipts must be submitted within 30 days.",
                    "severity": "medium",
                    "rule_json": {
                        "condition": {
                            "field": "receipt_submitted_at",
                            "operator": "less_than_or_equal",
                            "value": 30,
                        }
                    },
                }
            ],
            "unsupported_or_missing_fields": [],
        }
    )

    response = policy_service.extract_policy_rules(extraction_request(), ai_client=ai_client)

    assert len(response.draft_rules) == 1
    assert response.draft_rules[0].needs_human_review is False
    assert response.draft_rules[0].status == "draft"
    assert supabase.policy_rules.payloads[0]["active"] is False
    assert supabase.policy_rules.payloads[0]["enabled"] is False
    assert supabase.policy_rules.payloads[0]["status"] == "draft"
    assert any("receipt_due_date" in item.lower() for item in response.unsupported_or_missing_fields)
    assert any("not allowed" in item for item in response.unsupported_or_missing_fields)
    assert refresh_calls == []


def test_extraction_save_retries_when_thresholds_json_is_missing_from_schema_cache(monkeypatch):
    supabase = FakeSupabaseClient()
    supabase.policy_rules.fail_missing_thresholds_json_once = True
    monkeypatch.setattr(policy_service, "get_supabase_client", lambda: supabase)
    ai_client = FakeAiClient(
        {
            "draft_rules": [
                {
                    "rule_code": "preapproval_over_50",
                    "name": "Preapproval over CAD 50",
                    "description": "Manager preapproval is required over CAD 50.",
                    "severity": "high",
                    "rule_json": {
                        "condition": {"field": "amount_cad", "operator": "greater_than", "value": 50},
                        "outcome": {
                            "status": "approval_evidence_needed",
                            "message": "Approval evidence is required.",
                            "required_action": "Collect manager approval evidence.",
                        },
                        "thresholds": {
                            "preapproval_threshold_cad": {
                                "value": 50,
                                "currency": "CAD",
                            }
                        },
                    },
                    "needs_human_review": False,
                }
            ],
            "ambiguities": [],
            "unsupported_or_missing_fields": [],
            "suggested_feature_engineering": [],
            "summary": "Extracted one approval evidence rule.",
        }
    )

    response = policy_service.extract_policy_rules(extraction_request(), ai_client=ai_client)

    assert len(response.draft_rules) == 1
    assert response.draft_rules[0].rule_code.startswith("PREAPPROVAL_OVER_50")
    assert "thresholds_json" not in supabase.policy_rules.payloads[0]


def test_unsupported_or_missing_data_is_returned_without_persistence(monkeypatch):
    monkeypatch.setattr(policy_service, "save_extracted_draft_rules", lambda draft_rules: draft_rules)
    ai_client = FakeAiClient(
        {
            "draft_rules": [],
            "ambiguities": ["Customer dinner requires guest names, but the source CSV has no guest-name field."],
            "unsupported_or_missing_fields": ["receipt_submitted_at is unavailable in the transaction dataset."],
            "suggested_feature_engineering": ["guest_names_available"],
            "summary": "No enforceable rules were extracted.",
        }
    )

    response = policy_service.extract_policy_rules(extraction_request(), ai_client=ai_client)

    assert response.draft_rules == []
    assert response.ambiguities == ["Customer dinner requires guest names, but the source CSV has no guest-name field."]
    assert response.unsupported_or_missing_fields == ["receipt_submitted_at is unavailable in the transaction dataset."]
    assert response.suggested_feature_engineering == ["guest_names_available"]


def test_policy_rules_extract_endpoint_is_mockable(monkeypatch):
    def fake_extract(_request):
        return PolicyRuleExtractionResponse(summary="mocked", draft_rules=[])

    monkeypatch.setattr("app.routers.policy.policy_rules_extract", fake_extract)

    response = TestClient(app).post(
        "/policy/rules/extract",
        json={"policy_text": "Expenses over CAD 50 require manager preapproval before reimbursement."},
    )

    assert response.status_code == 200
    assert response.json()["summary"] == "mocked"


def test_rule_extraction_prompt_requests_canonical_rule_json():
    prompt = rule_extraction_user_prompt(extraction_request())

    assert '"allowed_condition_operators"' in prompt
    assert '"rule_json"' in prompt
    assert '"condition"' in prompt
    assert '"outcome"' in prompt
    assert '"scope"' in prompt
    assert '"needs_human_review": false' in prompt.lower()
    assert "at most one draft rule for each distinct compliance intent" in prompt
    assert "cannot be the whole proof" in prompt
    assert "prefer creating a draft rule plus missing data notes" in prompt


def test_rule_extraction_system_prompt_stays_domain_neutral():
    prompt = rule_extraction_system_prompt().lower()

    assert "general-purpose rules platform" in prompt
    assert "needs_human_review=true" in prompt
    assert "policy intent as a draft rule" in prompt
    assert "do not decide compliance for specific records" in prompt
    assert "duplicate rules" in prompt
    assert "debit activity" in prompt


def test_policy_rules_extract_endpoint_surfaces_ai_payload_failures_as_bad_gateway(monkeypatch):
    def fake_extract(_request):
        raise ValueError("Claude returned invalid JSON for policy rule extraction.")

    monkeypatch.setattr("app.routers.policy.policy_rules_extract", fake_extract)

    response = TestClient(app).post(
        "/policy/rules/extract",
        json={"policy_text": "Expenses over CAD 50 require manager preapproval before reimbursement."},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Claude returned invalid JSON for policy rule extraction."
