import sys
import types

from app.schemas.review_queue import CitedPolicyClause, ReviewQueueItem, ReviewQueueRefreshRequest

if "supabase" not in sys.modules:
    supabase_module = types.ModuleType("supabase")
    supabase_module.Client = object
    supabase_module.create_client = lambda *args, **kwargs: None
    sys.modules["supabase"] = supabase_module

from app.services.review_queue_service import (
    apply_workflow_queue_status,
    compose_review_queue_item,
    current_policy_violations,
    latest_by_transaction_id,
    persisted_payload,
    refresh_review_queue,
)


def test_compose_review_queue_item_attaches_structured_reviewer_brief() -> None:
    item = compose_review_queue_item(
        transaction={
            "id": "txn-1",
            "employee_id": "emp-1",
            "department_id": "dept-1",
            "transaction_date": "2026-05-30",
            "normalized_merchant_name": "Demo Hotel",
            "amount_cad": 125.0,
            "business_category": "Lodging",
        },
        policy_check={
            "id": "check-1",
            "status": "approval_evidence_needed",
            "max_severity": "high",
            "missing_information": ["manager pre-authorization evidence"],
        },
        risk_score={
            "id": "risk-1",
            "risk_score": 65,
            "risk_level": "high",
            "signals": [
                {
                    "type": "policy_risk_overlap",
                    "severity": "medium",
                    "message": "Open policy violations exist for this transaction.",
                    "evidence": {},
                }
            ],
        },
        violations=[
            {
                "rule_code": "PREAPPROVAL_OVER_50",
                "severity": "high",
                "explanation": "This transaction exceeds the active preapproval threshold.",
                "required_action": "Collect the required preapproval evidence.",
            }
        ],
        citations_by_rule_code={
            "PREAPPROVAL_OVER_50": [
                CitedPolicyClause(
                    rule_code="PREAPPROVAL_OVER_50",
                    clause_id="clause-1",
                    title="Preapproval",
                    text="Expenses above the threshold require manager pre-authorization.",
                    source="policy_chunks",
                )
            ]
        },
        employees_by_id={"emp-1": {"full_name": "Synthetic Employee"}},
        departments_by_id={"dept-1": {"name": "Synthetic Department"}},
    )

    assert item.reviewer_brief is not None
    assert item.reviewer_brief.recommended_next_action == "Collect the required preapproval evidence."
    assert item.reviewer_brief.cited_policy_clauses[0].rule_code == "PREAPPROVAL_OVER_50"
    assert item.reviewer_brief.missing_context == ["manager pre-authorization evidence"]

    payload = persisted_payload(item)
    assert payload["reviewer_brief"]["summary"].startswith("Advisory brief:")
    assert payload["reviewer_brief"]["generated_by"] == "deterministic_fallback"


def test_current_policy_violations_only_uses_latest_policy_check() -> None:
    policy_check = {
        "id": "check-latest",
        "status": "excluded_non_expense",
        "max_severity": "low",
    }
    violations = [
        {
            "policy_check_id": "check-old",
            "rule_code": "RECEIPT_REQUIRED_ALL_20FC6736_2",
            "severity": "high",
            "explanation": "Receipt evidence is missing or unavailable.",
            "required_action": "Request receipt from employee or reject reimbursement.",
        }
    ]

    assert current_policy_violations(policy_check, violations) == []


def test_latest_by_transaction_id_prefers_most_recent_timestamp() -> None:
    rows = [
        {
            "id": "older",
            "transaction_id": "txn-1",
            "status": "approval_evidence_needed",
            "checked_at": "2026-05-31T06:00:00+00:00",
        },
        {
            "id": "newer",
            "transaction_id": "txn-1",
            "status": "excluded_non_expense",
            "checked_at": "2026-05-31T06:30:00+00:00",
        },
    ]

    latest = latest_by_transaction_id(rows)

    assert latest["txn-1"]["id"] == "newer"
    assert latest["txn-1"]["status"] == "excluded_non_expense"


def test_apply_workflow_queue_status_respects_final_approval(monkeypatch) -> None:
    def fake_fetch_rows_by_values(table_name, _column_name, _values, _columns):
        if table_name == "approval_requests":
            return [
                {
                    "transaction_id": "txn-1",
                    "status": "denied",
                    "updated_at": "2026-05-31T06:30:00+00:00",
                }
            ]
        return []

    monkeypatch.setattr("app.services.review_queue_service.fetch_rows_by_values", fake_fetch_rows_by_values)

    rows = apply_workflow_queue_status([{"transaction_id": "txn-1", "queue_status": "open"}])

    assert rows[0]["queue_status"] == "resolved"


def test_refresh_review_queue_preserves_existing_row_identity_on_reset(monkeypatch) -> None:
    existing_row = {
        "id": "review-1",
        "transaction_id": "txn-1",
        "queue_status": "resolved",
        "review_priority": 55,
        "review_level": "high",
        "generated_at": "2026-05-31T00:00:00Z",
    }
    client = FakeReviewQueueClient({"review_queue_items": [existing_row]})

    monkeypatch.setattr("app.services.review_queue_service.get_supabase_client", lambda: client)
    monkeypatch.setattr(
        "app.services.review_queue_service.build_review_queue_items",
        lambda limit=None, transaction_ids=None: [
            ReviewQueueItem(
                transaction_id="txn-1",
                employee_id="emp-1",
                department_id="dept-1",
                merchant="Refresh Test",
                amount_cad=199.0,
                category="Travel",
                queue_status="open",
                review_priority=70,
                review_level="high",
            )
        ],
    )

    def fake_fetch_rows_by_values(table_name, _column_name, _values, _columns):
        if table_name == "review_queue_items":
            return [existing_row]
        return []

    monkeypatch.setattr("app.services.review_queue_service.fetch_rows_by_values", fake_fetch_rows_by_values)

    response = refresh_review_queue(ReviewQueueRefreshRequest(reset_existing=True, persist=True))

    assert response.generated == 1
    assert response.persisted == 1
    assert client.tables["review_queue_items"][0]["id"] == "review-1"
    assert client.tables["review_queue_items"][0]["transaction_id"] == "txn-1"
    assert client.tables["review_queue_items"][0]["review_priority"] == 70
    assert client.tables["review_queue_items"][0]["queue_status"] == "resolved"


class FakeReviewQueueClient:
    def __init__(self, tables):
        self.tables = tables

    def table(self, table_name):
        return FakeReviewQueueQuery(self, table_name)


class FakeReviewQueueQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.upsert_payload = None

    def upsert(self, payload, on_conflict=None):
        assert on_conflict == "transaction_id"
        self.upsert_payload = payload
        return self

    def execute(self):
        if self.upsert_payload is None:
            return types.SimpleNamespace(data=self.client.tables.get(self.table_name, []))

        rows = self.client.tables.setdefault(self.table_name, [])
        for payload in self.upsert_payload:
            transaction_id = str(payload.get("transaction_id") or "")
            existing = next((row for row in rows if str(row.get("transaction_id") or "") == transaction_id), None)
            if existing is not None:
                existing.update(payload)
            else:
                new_row = dict(payload)
                new_row.setdefault("id", f"review-{len(rows) + 1}")
                rows.append(new_row)
        return types.SimpleNamespace(data=rows)
