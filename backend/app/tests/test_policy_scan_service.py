import pytest

from app.schemas.policy import PolicyScanRequest
from app.services import policy_service
from app.services.rule_evaluator import ConfigurablePolicyRule


def transaction(transaction_id: str, amount_cad: float = 25.0, **overrides):
    return {
        "id": transaction_id,
        "raw_transactions": {"source_fingerprint": f"fingerprint-{transaction_id}"},
        "employee_id": "employee_1",
        "department_id": "department_1",
        "transaction_date": "2026-05-10",
        "posting_date": "2026-05-10",
        "description": "Office supply purchase",
        "merchant_name": "STAPLES",
        "normalized_merchant_name": "STAPLES",
        "source_category": "Office",
        "business_category": "Office Supplies",
        "normalized_category": "Office Supplies",
        "debit_credit": "debit",
        "amount_cad": amount_cad,
        "business_purpose": None,
        "guest_names": None,
        **overrides,
    }


def test_policy_scan_batches_through_multiple_pages(monkeypatch):
    pages = {
        0: [transaction("txn_1"), transaction("txn_2", amount_cad=75.0)],
        2: [transaction("txn_3", debit_credit="credit", transaction_eligibility="excluded_non_expense")],
    }
    persisted_batches: list[list[str]] = []
    preapproval_rule = configurable_rule(
        rule_code="PREAPPROVAL_OVER_50",
        name="Preapproval over threshold",
        condition={
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": 50},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        outcome={
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "PREAPPROVAL_OVER_50",
                "severity": "high",
                "explanation": "Transactions over 50 need preapproval.",
                "required_action": "Collect preapproval evidence before approval.",
            },
            "missing_information": [],
        },
    )

    monkeypatch.setattr(policy_service, "fetch_transactions_page", lambda request, start, batch_size: pages.get(start, []))
    monkeypatch.setattr(policy_service, "enrich_transactions_with_people", lambda transactions: transactions)
    monkeypatch.setattr(policy_service, "load_active_configurable_rules", lambda: [preapproval_rule])
    monkeypatch.setattr(
        policy_service,
        "resolve_receipts",
        lambda transactions, reset_synthetic_evidence, dry_run, active_configurable_rules=None: {
            transaction["id"]: {"status": "submitted", "synthetic": False, "submitted_at": "2026-05-10T12:00:00+00:00"}
            for transaction in transactions
        },
    )
    monkeypatch.setattr(
        policy_service,
        "resolve_preapprovals",
        lambda transactions, reset_synthetic_evidence, dry_run, active_configurable_rules=None: {
            transaction["id"]: {"status": "missing" if transaction["amount_cad"] > 50 else "not_required"}
            for transaction in transactions
        },
    )
    monkeypatch.setattr(
        policy_service,
        "persist_policy_results",
        lambda results, transaction_ids, reset_existing=False: persisted_batches.append(transaction_ids),
    )

    summary = policy_service.scan_transactions(PolicyScanRequest(batch_size=2))

    assert summary.total_scanned == 3
    assert summary.batch_count == 2
    assert summary.approval_evidence_required == 1
    assert summary.approval_evidence_needed == 1
    assert summary.excluded_non_expense == 1
    assert summary.duration_ms >= 0
    assert persisted_batches == [["txn_1", "txn_2"], ["txn_3"]]


def test_policy_scan_dry_run_does_not_persist(monkeypatch):
    monkeypatch.setattr(policy_service, "fetch_transactions_page", lambda request, start, batch_size: [transaction("txn_1")] if start == 0 else [])
    monkeypatch.setattr(policy_service, "enrich_transactions_with_people", lambda transactions: transactions)
    monkeypatch.setattr(policy_service, "load_active_configurable_rules", lambda: [])
    monkeypatch.setattr(
        policy_service,
        "resolve_receipts",
        lambda transactions, reset_synthetic_evidence, dry_run: {
            transaction["id"]: {"status": "submitted", "synthetic": False, "submitted_at": "2026-05-10T12:00:00+00:00"}
            for transaction in transactions
        },
    )
    monkeypatch.setattr(
        policy_service,
        "resolve_preapprovals",
        lambda transactions, reset_synthetic_evidence, dry_run, active_configurable_rules=None: {transaction["id"]: {"status": "not_required"} for transaction in transactions},
    )

    def fail_persist(*args, **kwargs):
        raise AssertionError("dry_run should not persist policy results")

    monkeypatch.setattr(policy_service, "persist_policy_results", fail_persist)

    summary = policy_service.scan_transactions(PolicyScanRequest(batch_size=1, dry_run=True))

    assert summary.total_scanned == 1
    assert summary.compliant == 1


def test_policy_scan_refreshes_review_queue_without_resetting_persisted_ids(monkeypatch):
    refresh_calls = []
    risk_requests = []

    monkeypatch.setattr(
        policy_service,
        "scan_transactions",
        lambda request: policy_service.PolicyScanSummary(total_scanned=3, compliant=3),
    )
    monkeypatch.setattr(
        policy_service,
        "iter_transaction_batches",
        lambda request, batch_size: [[transaction("txn_1"), transaction("txn_2")], [transaction("txn_3")]],
    )

    def fake_refresh_review_queue_for_transaction_ids(transaction_ids, *, persist=True):
        refresh_calls.append({"transaction_ids": transaction_ids, "persist": persist})

    def fake_scan_risk_scores(request):
        risk_requests.append(request)

    monkeypatch.setattr(
        "app.services.review_queue_service.refresh_review_queue_for_transaction_ids",
        fake_refresh_review_queue_for_transaction_ids,
    )
    monkeypatch.setattr("app.services.risk_service.scan_risk_scores", fake_scan_risk_scores)

    summary = policy_service.run_policy_scan_and_refresh(PolicyScanRequest(batch_size=50, reset_existing=True))

    assert summary.total_scanned == 3
    assert len(risk_requests) == 1
    assert risk_requests[0].reset_existing is False
    assert len(refresh_calls) == 1
    assert refresh_calls[0]["persist"] is True
    assert refresh_calls[0]["transaction_ids"] == ["txn_1", "txn_2", "txn_3"]


def test_normalized_batch_size_is_bounded():
    assert policy_service.normalized_batch_size(0) == 500
    assert policy_service.normalized_batch_size(2500) == 1000


def test_dedupe_policy_checks_keeps_first_check_per_transaction():
    checks = [
        {"id": "check_3", "transaction_id": "txn_1", "checked_at": "2026-05-30T10:00:00+00:00"},
        {"id": "check_2", "transaction_id": "txn_2", "checked_at": "2026-05-30T09:59:00+00:00"},
        {"id": "check_1", "transaction_id": "txn_1", "checked_at": "2026-05-30T09:58:00+00:00"},
    ]

    deduped = policy_service.dedupe_policy_checks(checks)

    assert [check["transaction_id"] for check in deduped] == ["txn_1", "txn_2"]
    assert deduped[0]["id"] == "check_3"


def configurable_rule(**overrides):
    base = {
        "rule_code": "FUEL_REVIEW",
        "name": "Fuel review outside Operations",
        "enabled": True,
        "severity": "high",
        "condition": {
            "all": [
                {"field": "business_category", "operator": "eq", "value": "Fuel"},
                {"field": "department_name", "operator": "neq", "value": "Operations"},
            ]
        },
        "outcome": {
            "status": "review_required",
            "violation": {
                "rule_code": "FUEL_REVIEW",
                "severity": "high",
                "explanation": "Fuel spend outside Operations requires finance review.",
                "required_action": "Route this fuel charge to finance review.",
            },
            "missing_information": [],
        },
        "scope": {"department_ids": [], "employee_ids": []},
    }
    return ConfigurablePolicyRule(**{**base, **overrides})


def scan_with_rules(monkeypatch, rules, transactions=None, receipt_status="submitted", preapproval_status="not_required"):
    transactions = transactions or [
        transaction("txn_1", business_category="Fuel", normalized_category="Fuel", department_name="Sales"),
    ]
    captured = {}

    monkeypatch.setattr(policy_service, "fetch_transactions_page", lambda request, start, batch_size: transactions if start == 0 else [])
    monkeypatch.setattr(policy_service, "enrich_transactions_with_people", lambda rows: rows)
    monkeypatch.setattr(policy_service, "load_active_configurable_rules", lambda: rules)
    monkeypatch.setattr(
        policy_service,
        "resolve_receipts",
        lambda rows, reset_synthetic_evidence, dry_run: {
            row["id"]: {"status": receipt_status, "synthetic": False, "submitted_at": "2026-05-10T12:00:00+00:00"}
            for row in rows
        },
    )
    monkeypatch.setattr(
        policy_service,
        "resolve_preapprovals",
        lambda rows, reset_synthetic_evidence, dry_run, active_configurable_rules=None: {row["id"]: {"status": preapproval_status} for row in rows},
    )

    def capture_persist(results, transaction_ids, reset_existing=False):
        captured["results"] = results
        captured["transaction_ids"] = transaction_ids

    monkeypatch.setattr(policy_service, "persist_policy_results", capture_persist)

    return policy_service.scan_transactions(PolicyScanRequest(batch_size=10)), captured


def test_draft_and_disabled_rules_do_not_affect_policy_scan(monkeypatch):
    summary, captured = scan_with_rules(monkeypatch, [])

    assert summary.review_required == 0
    assert summary.compliant == 1
    assert captured["results"][0].violations == []


def test_active_configurable_rule_affects_policy_scan_and_persisted_result(monkeypatch):
    summary, captured = scan_with_rules(monkeypatch, [configurable_rule()])
    result = captured["results"][0]

    assert summary.review_required == 1
    assert summary.high_or_critical == 1
    assert result.status == "review_required"
    assert result.violations[0].rule_code == "FUEL_REVIEW"
    assert result.violations[0].explanation == "Fuel spend outside Operations requires finance review."
    assert result.recommended_next_action == "Route this fuel charge to finance review."


def test_active_department_scoped_rule_only_matches_department(monkeypatch):
    department_rule = configurable_rule(scope={"department_ids": ["department_2"], "employee_ids": []})
    summary, captured = scan_with_rules(
        monkeypatch,
        [department_rule],
        transactions=[
            transaction("txn_1", business_category="Fuel", normalized_category="Fuel", department_id="department_1", department_name="Sales"),
            transaction("txn_2", business_category="Fuel", normalized_category="Fuel", department_id="department_2", department_name="Sales"),
        ],
    )

    assert summary.review_required == 1
    assert captured["results"][0].violations == []
    assert captured["results"][1].violations[0].rule_code == "FUEL_REVIEW"


def test_active_employee_scoped_rule_only_matches_employee(monkeypatch):
    employee_rule = configurable_rule(scope={"department_ids": [], "employee_ids": ["employee_2"]})
    summary, captured = scan_with_rules(
        monkeypatch,
        [employee_rule],
        transactions=[
            transaction("txn_1", business_category="Fuel", normalized_category="Fuel", employee_id="employee_1", department_name="Sales"),
            transaction("txn_2", business_category="Fuel", normalized_category="Fuel", employee_id="employee_2", department_name="Sales"),
        ],
    )

    assert summary.review_required == 1
    assert captured["results"][0].violations == []
    assert captured["results"][1].violations[0].rule_code == "FUEL_REVIEW"


def test_declarative_rules_are_the_authoritative_scan_path(monkeypatch):
    preapproval_rule = configurable_rule(
        rule_code="PREAPPROVAL_OVER_50",
        condition={
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": 50},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        outcome={
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "PREAPPROVAL_OVER_50",
                "severity": "high",
                "explanation": "Declarative preapproval policy matched.",
                "required_action": "Collect preapproval before approval.",
            },
        },
    )
    summary, captured = scan_with_rules(
        monkeypatch,
        [preapproval_rule],
        transactions=[transaction("txn_1", amount_cad=75)],
        preapproval_status="missing",
    )

    result = captured["results"][0]
    assert summary.approval_evidence_needed == 1
    assert [violation.rule_code for violation in result.violations] == ["PREAPPROVAL_OVER_50"]
    assert result.status == "approval_evidence_needed"
    assert result.violations[0].explanation == "Declarative preapproval policy matched."


def test_scan_uses_active_rule_threshold_instead_of_demo_default(monkeypatch):
    preapproval_rule = configurable_rule(
        rule_code="PREAPPROVAL_OVER_100",
        condition={
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": {"threshold": "preapproval_threshold_cad"}},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        outcome={
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "PREAPPROVAL_OVER_100",
                "severity": "high",
                "explanation": "Rule-configured threshold matched.",
                "required_action": "Collect preapproval before approval.",
            },
        },
        thresholds={"preapproval_threshold_cad": {"value": 100, "currency": "CAD"}},
    )
    summary, captured = scan_with_rules(
        monkeypatch,
        [preapproval_rule],
        transactions=[transaction("txn_75", amount_cad=75), transaction("txn_125", amount_cad=125)],
        preapproval_status="missing",
    )

    assert summary.approval_evidence_needed == 1
    assert captured["results"][0].violations == []
    assert captured["results"][1].violations[0].rule_code == "PREAPPROVAL_OVER_100"


def test_scan_excludes_cwb_payment_from_generic_receipt_rule(monkeypatch):
    receipt_rule = configurable_rule(
        rule_code="GENERIC_RECEIPT_REQUIRED",
        condition={"field": "receipt_explicitly_missing", "operator": "is_true"},
        outcome={
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "GENERIC_RECEIPT_REQUIRED",
                "severity": "medium",
                "explanation": "Receipt evidence is required for this expense.",
                "required_action": "Attach a receipt.",
            },
        },
    )

    summary, captured = scan_with_rules(
        monkeypatch,
        [receipt_rule],
        transactions=[
            transaction(
                "txn_cwb_payment",
                amount_cad=2500,
                description="CWB EFT PAYMENT",
                merchant_name="CWB EFT PAYMENT",
                normalized_merchant_name="CWB EFT PAYMENT",
                source_category="Payment",
                business_category="Account Payment / Transfer",
                normalized_category="Account Payment / Transfer",
                policy_category="Excluded Non-Expense",
                transaction_eligibility="excluded_non_expense",
                transaction_type="account_payment",
            ),
            transaction("txn_office", amount_cad=25),
        ],
        receipt_status="missing",
    )

    assert summary.total_scanned == 2
    assert summary.excluded_non_expense == 1
    assert summary.approval_evidence_needed == 1
    assert captured["results"][0].status == "excluded_non_expense"
    assert captured["results"][0].violations == []
    assert captured["results"][1].violations[0].rule_code == "GENERIC_RECEIPT_REQUIRED"


def test_compliance_summary_counts_configurable_rule_findings(monkeypatch):
    summary, _captured = scan_with_rules(monkeypatch, [configurable_rule()])

    assert summary.total_scanned == 1
    assert summary.review_required == 1
    assert summary.individual_flags == 1
    assert summary.violations_created == 1


def test_policy_scan_does_not_call_ai_extraction(monkeypatch):
    monkeypatch.setattr(
        policy_service,
        "extract_policy_rules_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scan must not call AI extraction")),
    )

    summary, _captured = scan_with_rules(monkeypatch, [configurable_rule()])

    assert summary.total_scanned == 1


def test_broad_ai_receipt_rule_is_blocked_from_activation():
    canonical, validation_errors = policy_service.canonicalize_rule_json(
        {
            "condition": {"field": "debit_or_credit", "operator": "eq", "value": "debit"},
            "outcome": {
                "status": "approval_evidence_needed",
                "violation": {
                    "rule_code": "RECEIPT_REQUIRED_AI",
                    "severity": "high",
                    "explanation": "Receipt evidence is required for this expense.",
                    "required_action": "Attach a receipt.",
                },
            },
        },
        "RECEIPT_REQUIRED_AI",
        "Receipt required for all reimbursable expenses",
        "high",
    )

    assert validation_errors == []
    assert any("global receipt" in error for error in policy_service.activation_guardrail_errors(canonical))


def test_amount_only_preauthorization_rule_is_blocked_from_activation():
    canonical, validation_errors = policy_service.canonicalize_rule_json(
        {
            "condition": {"field": "amount_cad", "operator": "gt", "value": 50},
            "outcome": {
                "status": "approval_evidence_needed",
                "violation": {
                    "rule_code": "PRE_AUTH_AI",
                    "severity": "high",
                    "explanation": "Manager pre-authorization evidence is required for expenses over $50.",
                    "required_action": "Verify manager pre-authorization.",
                },
            },
        },
        "PRE_AUTH_AI",
        "Pre-authorization required for expenses over $50",
        "high",
    )

    assert validation_errors == []
    assert any("must check approval evidence" in error for error in policy_service.activation_guardrail_errors(canonical))


def test_existing_broad_active_rule_is_not_loaded_for_scan():
    row = {
        "rule_code": "POLICY_001_FALSIFICATION_PROHIBITED",
        "title": "Falsification of expense reports is prohibited",
        "severity": "critical",
        "rule_kind": "json_config",
        "condition": {"field": "debit_or_credit", "operator": "eq", "value": "debit"},
        "outcome": {
            "status": "review_required",
            "violation": {
                "rule_code": "POLICY_001_FALSIFICATION_PROHIBITED",
                "severity": "critical",
                "explanation": "Verify all claimed expenses were actually incurred.",
                "required_action": "Cross-reference transaction with receipt and supporting documentation.",
            },
        },
        "scope": {"department_ids": [], "employee_ids": []},
    }

    assert policy_service.configurable_rule_from_row(row) is None
