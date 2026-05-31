from app.services.policy_engine import (
    PolicyThresholds,
    build_policy_context,
    calculate_severity_score,
    evaluate_policy,
    infer_policy_category,
    infer_synthetic_preapproval,
    infer_synthetic_receipt,
    max_severity,
    policy_thresholds_from_rules,
)
from app.services.policy_service import (
    compose_policy_findings,
    compose_repeat_offender_summary,
    compose_repeat_offender_summary_from_review_queue,
)
from app.services.rule_evaluator import ConfigurablePolicyRule


def transaction(**overrides):
    base = {
        "id": "txn_1",
        "raw_transactions": {"source_fingerprint": "fingerprint-1"},
        "employee_id": "employee_1",
        "department_id": "department_1",
        "transaction_date": "2026-05-10",
        "description": "Office supply purchase",
        "merchant_name": "STAPLES",
        "normalized_merchant_name": "STAPLES",
        "source_category": "Office",
        "business_category": "Office Supplies",
        "normalized_category": "Office Supplies",
        "debit_credit": "debit",
        "amount_cad": 42.0,
        "business_purpose": None,
        "guest_names": None,
    }
    row = {**base, **overrides}
    if "normalized_category" in overrides and "business_category" not in overrides:
        row["business_category"] = row["normalized_category"]
    return row


def receipt(status="submitted", synthetic=False):
    return {
        "status": status,
        "submitted_at": "2026-05-10T12:00:00+00:00",
        "receipt_date": "2026-05-10",
        "synthetic": synthetic,
    }


def preapproval(status="not_required"):
    return {
        "status": status,
        "requested_amount_cad": 42.0,
        "business_purpose": None,
    }


def rule(
    rule_code: str,
    severity: str,
    condition: dict,
    outcome: dict,
    name: str | None = None,
    applies_to: dict | None = None,
    thresholds: dict | None = None,
) -> ConfigurablePolicyRule:
    return ConfigurablePolicyRule(
        rule_code=rule_code,
        name=name or rule_code.replace("_", " ").title(),
        enabled=True,
        severity=severity,
        condition=condition,
        outcome=outcome,
        scope={"department_ids": [], "employee_ids": []},
        applies_to=applies_to or {},
        thresholds=thresholds or {},
    )


def platform_rules() -> list[ConfigurablePolicyRule]:
    return [
        rule(
            "PREAPPROVAL_OVER_50",
            "high",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "amount_cad", "operator": "gt", "value": {"threshold": "preapproval_threshold_cad"}},
                    {"field": "missing_preapproval", "operator": "is_true"},
                ]
            },
            {
                "status": "approval_evidence_needed",
                "violation": {
                    "rule_code": "PREAPPROVAL_OVER_50",
                    "severity": "high",
                    "explanation": "This transaction exceeds the active preapproval threshold and is missing approval evidence.",
                    "required_action": "Collect or document the required preapproval evidence before approval.",
                },
            },
            thresholds={
                "preapproval_threshold_cad": {"value": 50, "currency": "CAD"},
                "high_value_threshold_cad": {"value": 500, "currency": "CAD"},
                "critical_value_threshold_cad": {"value": 1000, "currency": "CAD"},
            },
        ),
        rule(
            "PREAPPROVAL_PENDING_REVIEW",
            "medium",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "requires_preapproval", "operator": "is_true"},
                    {"field": "has_pending_preapproval", "operator": "is_true"},
                ]
            },
            {
                "status": "review_required",
                "violation": {
                    "rule_code": "PREAPPROVAL_PENDING_REVIEW",
                    "severity": "medium",
                    "explanation": "This transaction still has pending preapproval evidence.",
                    "required_action": "Follow up on the pending preapproval before approving reimbursement.",
                },
            },
        ),
        rule(
            "RECEIPT_REQUIRED",
            "medium",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "receipt_explicitly_missing", "operator": "is_true"},
                ]
            },
            {
                "status": "approval_evidence_needed",
                "violation": {
                    "rule_code": "RECEIPT_REQUIRED",
                    "severity": "medium",
                    "explanation": "This transaction is explicitly missing required receipt evidence.",
                    "required_action": "Collect and attach the required receipt evidence before approval.",
                },
            },
        ),
        rule(
            "RECEIPT_EVIDENCE_REQUIRED",
            "low",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "receipt_sensitive_category", "operator": "is_true"},
                    {"field": "receipt_evidence_unavailable", "operator": "is_true"},
                    {"field": "receipt_explicitly_missing", "operator": "is_false"},
                ]
            },
            {
                "status": "review_required",
                "violation": {
                    "rule_code": "RECEIPT_EVIDENCE_REQUIRED",
                    "severity": "low",
                    "explanation": "Receipt-sensitive spend is missing receipt evidence in the current dataset.",
                    "required_action": "Collect the receipt evidence during reimbursement review.",
                },
            },
        ),
        rule(
            "RECEIPT_CURRENT_MONTH",
            "low",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "has_receipt_evidence", "operator": "is_true"},
                    {"field": "receipt_submitted_current_month", "operator": "is_false"},
                ]
            },
            {
                "status": "review_required",
                "violation": {
                    "rule_code": "RECEIPT_CURRENT_MONTH",
                    "severity": "low",
                    "explanation": "Receipt evidence was submitted outside the transaction month.",
                    "required_action": "Review whether the delayed receipt submission is acceptable.",
                },
            },
        ),
        rule(
            "ENTERTAINMENT_CONTEXT_REQUIRED",
            "medium",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "is_meal_or_entertainment", "operator": "is_true"},
                    {"field": "amount_cad", "operator": "gt", "value": {"threshold": "meal_context_threshold_cad"}},
                    {
                        "any": [
                            {"field": "has_guest_names", "operator": "is_false"},
                            {"field": "has_business_purpose", "operator": "is_false"},
                        ]
                    },
                ]
            },
            {
                "status": "context_needed",
                "missing_information": ["customer context", "guest names", "business purpose"],
                "violation": {
                    "rule_code": "ENTERTAINMENT_CONTEXT_REQUIRED",
                    "severity": "medium",
                    "explanation": "Entertainment spend over the configured threshold is missing required context.",
                    "required_action": "Collect the missing entertainment context before deciding compliance.",
                },
            },
            thresholds={"meal_context_threshold_cad": {"value": 50, "currency": "CAD"}},
        ),
        rule(
            "ALCOHOL_RESTRICTED",
            "high",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "is_alcohol_category", "operator": "is_true"},
                ]
            },
            {
                "status": "context_needed",
                "missing_information": ["customer dining context", "guest names", "business purpose"],
                "violation": {
                    "rule_code": "ALCOHOL_RESTRICTED",
                    "severity": "high",
                    "explanation": "Alcohol spend requires supporting customer dining context.",
                    "required_action": "Collect the customer dining context before approving reimbursement.",
                },
            },
        ),
        rule(
            "TICKETS_NOT_REIMBURSABLE",
            "high",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "is_ticket_or_fine", "operator": "is_true"},
                ]
            },
            {
                "status": "policy_violation",
                "violation": {
                    "rule_code": "TICKETS_NOT_REIMBURSABLE",
                    "severity": "high",
                    "explanation": "This transaction matches a non-reimbursable ticket or fine rule.",
                    "required_action": "Do not reimburse this transaction.",
                },
            },
        ),
        rule(
            "PERSONAL_CARD_USE_PROHIBITED",
            "critical",
            {
                "all": [
                    {"field": "skips_normal_expense_rules", "operator": "is_false"},
                    {"field": "is_personal_expense", "operator": "is_true"},
                ]
            },
            {
                "status": "policy_violation",
                "violation": {
                    "rule_code": "PERSONAL_CARD_USE_PROHIBITED",
                    "severity": "critical",
                    "explanation": "This transaction matches a personal-spend prohibition rule.",
                    "required_action": "Review the charge and recover funds if it is personal spend.",
                },
            },
        ),
    ]


def evaluate(source_transaction, source_receipt=None, source_preapproval=None, rules=None):
    return evaluate_policy(
        source_transaction,
        source_receipt or receipt(),
        source_preapproval or preapproval(),
        rules=rules if rules is not None else platform_rules(),
    )


def test_under_50_with_receipt_is_compliant():
    result = evaluate(transaction())

    assert result.status == "compliant"
    assert result.violations == []


def test_policy_context_features_are_derived_from_transaction_evidence():
    context = build_policy_context(
        transaction(normalized_category="Fuel", amount_cad=1200.0),
        receipt("missing"),
        preapproval("requested"),
        thresholds=PolicyThresholds(
            preapproval_threshold_cad=50,
            high_value_threshold_cad=500,
            critical_value_threshold_cad=1000,
        ),
    )

    assert context.requires_preapproval is True
    assert context.has_pending_preapproval is True
    assert context.receipt_explicitly_missing is True
    assert context.receipt_evidence_unavailable is False
    assert context.receipt_sensitive_category is True
    assert context.is_high_value is True
    assert context.is_critical_value is True


def test_policy_context_groups_transaction_evidence_and_derived_facts():
    context = build_policy_context(
        transaction(normalized_category="Meals / Entertainment", amount_cad=75.0),
        receipt("submitted"),
        preapproval("approved"),
    )

    assert context.facts["transaction"]["category"] == "Meals / Entertainment"
    assert context.facts["evidence"]["receipt_status"] == "submitted"
    assert context.facts["derived"]["is_meal_or_entertainment"] is True


def test_declarative_rules_can_match_individual_findings():
    context_transaction = transaction(normalized_category="Fuel", amount_cad=75.0)

    preapproval_result = evaluate(context_transaction, receipt("submitted"), preapproval("missing"), rules=platform_rules()[:1])
    assert preapproval_result.violations[0].rule_code == "PREAPPROVAL_OVER_50"

    receipt_result = evaluate(context_transaction, receipt("missing"), preapproval("approved"), rules=[platform_rules()[2]])
    assert receipt_result.violations[0].rule_code == "RECEIPT_REQUIRED"

    evidence_result = evaluate(
        transaction(normalized_category="Fuel", amount_cad=40.0),
        receipt("unavailable", synthetic=True),
        preapproval("approved"),
        rules=[platform_rules()[3]],
    )
    assert evidence_result.violations[0].rule_code == "RECEIPT_EVIDENCE_REQUIRED"


def test_over_50_without_preapproval_needs_preapproval():
    result = evaluate(transaction(amount_cad=75.0), receipt(), preapproval("missing"))

    assert result.status == "approval_evidence_needed"
    assert "PREAPPROVAL_OVER_50" in {violation.rule_code for violation in result.violations}


def test_explicitly_missing_receipt_needs_approval_evidence():
    result = evaluate(transaction(), receipt("missing"), preapproval())

    assert result.status == "approval_evidence_needed"
    assert "RECEIPT_REQUIRED" in {violation.rule_code for violation in result.violations}


def test_receipt_evidence_rule_does_not_duplicate_missing_receipt_rule():
    result = evaluate(
        transaction(normalized_category="Fuel", amount_cad=40.0),
        receipt("missing"),
        preapproval(),
    )

    receipt_violations = [violation for violation in result.violations if "RECEIPT" in violation.rule_code]
    assert len(receipt_violations) == 1
    assert receipt_violations[0].rule_code == "RECEIPT_REQUIRED"


def test_alcohol_without_customer_context_needs_context():
    result = evaluate(
        transaction(normalized_category="Alcohol / Restricted", amount_cad=80.0),
        receipt(),
        preapproval("approved"),
    )

    assert result.status == "context_needed"
    assert "customer dining context" in result.missing_information
    assert "ALCOHOL_RESTRICTED" in {violation.rule_code for violation in result.violations}


def test_ticket_category_is_violation():
    result = evaluate(
        transaction(normalized_category="Non-Reimbursable Fine", amount_cad=90.0),
        receipt(),
        preapproval("approved"),
    )

    assert result.status == "policy_violation"
    assert "TICKETS_NOT_REIMBURSABLE" in {violation.rule_code for violation in result.violations}


def test_missing_receipt_and_preapproval_returns_one_result_with_two_violations():
    result = evaluate(
        transaction(normalized_category="Fuel", amount_cad=75.0),
        receipt("missing"),
        preapproval("missing"),
    )

    assert result.status == "approval_evidence_needed"
    assert {violation.rule_code for violation in result.violations} == {"PREAPPROVAL_OVER_50", "RECEIPT_REQUIRED"}
    assert len(result.violations) == 2


def test_receipt_unavailable_stays_review_required_and_low_severity():
    source = transaction(
        normalized_category="Fuel",
        business_category="Fuel",
        amount_cad=40.0,
        raw_transactions={"source_fingerprint": "fp-15"},
    )
    result = evaluate(source, infer_synthetic_receipt(source), preapproval())

    assert result.status == "review_required"
    assert result.max_severity == "low"
    assert {violation.rule_code for violation in result.violations} == {"RECEIPT_EVIDENCE_REQUIRED"}
    assert "missing receipt evidence in the current dataset" in result.violations[0].explanation


def test_unscoped_synthetic_receipt_gap_does_not_create_global_findings():
    unscoped_receipt_rule = rule(
        "GLOBAL_RECEIPT_UNAVAILABLE",
        "high",
        {
            "all": [
                {"field": "skips_normal_expense_rules", "operator": "is_false"},
                {"field": "receipt_evidence_unavailable", "operator": "is_true"},
            ]
        },
        {
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "GLOBAL_RECEIPT_UNAVAILABLE",
                "severity": "high",
                "explanation": "Receipt evidence is unavailable.",
                "required_action": "Attach a receipt.",
            },
        },
    )
    source = transaction(normalized_category="Office Supplies", amount_cad=42.0)

    result = evaluate(source, infer_synthetic_receipt(source), preapproval(), rules=[unscoped_receipt_rule])

    assert result.status == "compliant"
    assert result.violations == []


def test_excluded_payment_row_does_not_trigger_generic_receipt_rule():
    generic_receipt_rule = rule(
        "GENERIC_RECEIPT_REQUIRED",
        "medium",
        {"field": "receipt_explicitly_missing", "operator": "is_true"},
        {
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "GENERIC_RECEIPT_REQUIRED",
                "severity": "medium",
                "explanation": "Receipt evidence is required for this expense.",
                "required_action": "Attach a receipt.",
            },
        },
    )
    cwb_payment = transaction(
        description="CWB EFT PAYMENT",
        merchant_name="CWB EFT PAYMENT",
        normalized_merchant_name="CWB EFT PAYMENT",
        source_category="Payment",
        business_category="Account Payment / Transfer",
        normalized_category="Account Payment / Transfer",
        policy_category="Excluded Non-Expense",
        transaction_eligibility="excluded_non_expense",
        transaction_type="account_payment",
        amount_cad=2500.0,
    )

    result = evaluate(cwb_payment, receipt("missing"), preapproval(), rules=[generic_receipt_rule])

    assert result.status == "excluded_non_expense"
    assert result.violations == []


def test_finance_review_row_does_not_trigger_generic_approval_rule():
    generic_approval_rule = rule(
        "GENERIC_PREAPPROVAL_REQUIRED",
        "high",
        {
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": 50},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        {
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "GENERIC_PREAPPROVAL_REQUIRED",
                "severity": "high",
                "explanation": "Approval evidence is required for this expense.",
                "required_action": "Attach approval evidence.",
            },
        },
    )
    card_fee = transaction(
        description="Monthly card fee",
        merchant_name="BRIM FINANCE",
        business_category="Card Fees / Interest",
        normalized_category="Card Fees / Interest",
        policy_category="Finance Review",
        transaction_eligibility="finance_review",
        transaction_type="card_fee",
        amount_cad=125.0,
    )

    result = evaluate(card_fee, receipt(), preapproval("missing"), rules=[generic_approval_rule])

    assert result.status == "review_required"
    assert result.violations == []


def test_applies_to_allows_scoped_broad_conditions_without_flagging_unrelated_rows():
    scoped_vehicle_rule = rule(
        "VEHICLE_DEBIT_REVIEW",
        "medium",
        {"field": "debit_credit", "operator": "eq", "value": "debit"},
        {
            "status": "review_required",
            "violation": {
                "rule_code": "VEHICLE_DEBIT_REVIEW",
                "severity": "medium",
                "explanation": "Vehicle debit spend needs review.",
                "required_action": "Review vehicle expense support.",
            },
        },
        applies_to={"business_categories": ["vehicle"]},
    )

    unrelated = evaluate(transaction(normalized_category="Office Supplies"), rules=[scoped_vehicle_rule])
    fuel = evaluate(transaction(normalized_category="Fuel"), rules=[scoped_vehicle_rule])

    assert unrelated.status == "compliant"
    assert unrelated.violations == []
    assert fuel.status == "review_required"
    assert {violation.rule_code for violation in fuel.violations} == {"VEHICLE_DEBIT_REVIEW"}


def test_thresholds_only_apply_when_rule_scope_matches_transaction():
    scoped_fuel_rule = rule(
        "FUEL_PREAPPROVAL_OVER_50",
        "high",
        {
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": {"threshold": "preapproval_threshold_cad"}},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        {
            "status": "approval_evidence_needed",
            "violation": {
                "rule_code": "FUEL_PREAPPROVAL_OVER_50",
                "severity": "high",
                "explanation": "Fuel spend needs approval evidence.",
                "required_action": "Attach approval evidence.",
            },
        },
        applies_to={"business_categories": ["Fuel"]},
        thresholds={"preapproval_threshold_cad": {"value": 50, "currency": "CAD"}},
    )

    office_thresholds = policy_thresholds_from_rules([scoped_fuel_rule], transaction(normalized_category="Office Supplies"))
    fuel_thresholds = policy_thresholds_from_rules([scoped_fuel_rule], transaction(normalized_category="Fuel"))

    assert office_thresholds.preapproval_threshold_cad == float("inf")
    assert fuel_thresholds.preapproval_threshold_cad == 50


def test_pending_preapproval_review_action_is_specific():
    result = evaluate(
        transaction(amount_cad=75.0),
        receipt(),
        preapproval("requested"),
    )

    assert result.status == "review_required"
    assert "pending preapproval" in result.recommended_next_action


def test_max_severity_picks_highest_severity():
    assert max_severity(["low", "critical", "medium"]) == "critical"


def test_severity_score_adds_amount_and_multiple_violation_weight():
    source_transaction = transaction(normalized_category="Fuel", amount_cad=1200.0)
    result = evaluate(
        source_transaction,
        receipt("missing"),
        preapproval("missing"),
    )

    assert result.severity_score >= 80
    assert result.scan_version == "python-policy-engine-v5-platform-facts"
    assert (
        calculate_severity_score(
            result.violations,
            build_policy_context(
                source_transaction,
                receipt("missing"),
                preapproval("missing"),
                thresholds=PolicyThresholds(
                    preapproval_threshold_cad=50,
                    high_value_threshold_cad=500,
                    critical_value_threshold_cad=1000,
                ),
            ),
        )
        >= 80
    )


def test_policy_category_prioritizes_permit_patterns_over_broad_transportation():
    category = infer_policy_category(
        transaction(
            normalized_category="Fuel",
            merchant_name="PZG MT DEPT TRANSPORT",
            normalized_merchant_name="PZG MT DEPT TRANSPORT",
            description="OSOW PERMIT",
        )
    )

    assert category == "Permits / Government Fees"


def test_policy_category_prefers_business_category_over_legacy_normalized_category():
    category = infer_policy_category(
        transaction(
            business_category="Permits / Government Fees",
            normalized_category="Fuel",
            merchant_name="GENERIC MERCHANT",
            normalized_merchant_name="GENERIC MERCHANT",
            description="Permit filing",
        )
    )

    assert category == "Permits / Government Fees"


def test_enriched_eligibility_excludes_account_activity_before_expense_rules():
    result = evaluate(
        transaction(
            amount_cad=1000,
            debit_credit="credit",
            transaction_type="account_payment",
            transaction_eligibility="excluded_non_expense",
            business_category="Account Payment / Transfer",
            normalized_category="Fuel",
        ),
        receipt("missing"),
        preapproval("missing"),
    )

    assert result.status == "excluded_non_expense"
    assert result.violations == []


def test_policy_category_uses_enriched_policy_category_first():
    category = infer_policy_category(
        transaction(
            policy_category="Ground Transportation",
            business_category="Uncategorized",
            normalized_category="Fuel",
            merchant_name="GENERIC MERCHANT",
            normalized_merchant_name="GENERIC MERCHANT",
            description="Generic purchase",
        )
    )

    assert category == "Ground Transportation"


def test_synthetic_evidence_generation_is_deterministic():
    source = transaction(id="txn_2", amount_cad=125.0)

    assert infer_synthetic_receipt(source) == infer_synthetic_receipt(source)
    assert infer_synthetic_preapproval(source) == infer_synthetic_preapproval(source)
    assert infer_synthetic_receipt(source)["status"] == "approved"


def test_overall_status_priority_prefers_approval_evidence_over_context():
    result = evaluate(
        transaction(normalized_category="Alcohol / Restricted", amount_cad=125.0),
        receipt("missing"),
        preapproval("missing"),
    )

    assert result.status == "approval_evidence_needed"


def test_policy_findings_group_violations_by_transaction():
    findings = compose_policy_findings(
        checks=[
            {
                "id": "check_1",
                "transaction_id": "txn_1",
                "status": "approval_evidence_needed",
                "max_severity": "high",
                "missing_information": [],
                "recommended_next_action": "Request manager preauthorization before approval.",
            }
        ],
        violations=[
            {
                "policy_check_id": "check_1",
                "transaction_id": "txn_1",
                "rule_code": "PREAPPROVAL_OVER_50",
                "severity": "high",
                "explanation": "Needs preapproval.",
                "required_action": "Get approval.",
            },
            {
                "policy_check_id": "check_1",
                "transaction_id": "txn_1",
                "rule_code": "RECEIPT_REQUIRED",
                "severity": "medium",
                "explanation": "Receipt missing.",
                "required_action": "Attach receipt.",
            },
        ],
        transactions=[
            {
                "id": "txn_1",
                "employee_id": "employee_1",
                "department_id": "department_1",
                "transaction_date": "2026-05-10",
                "normalized_merchant_name": "STAPLES",
                "merchant_name": "STAPLES",
                "amount_cad": 75,
                "normalized_category": "Office Supplies",
            }
        ],
        employees=[{"id": "employee_1", "full_name": "Synthetic Employee"}],
        departments=[{"id": "department_1", "name": "Synthetic Department"}],
    )

    assert len(findings) == 1
    assert findings[0].transaction_id == "txn_1"
    assert findings[0].overall_status == "approval_evidence_needed"
    assert findings[0].max_severity == "high"
    assert len(findings[0].violations) == 2


def test_policy_findings_only_include_violations_for_selected_check():
    findings = compose_policy_findings(
        checks=[
            {
                "id": "check_latest",
                "transaction_id": "txn_1",
                "status": "review_required",
                "max_severity": "medium",
                "missing_information": [],
                "recommended_next_action": "Review the latest scan finding.",
            }
        ],
        violations=[
            {
                "policy_check_id": "check_old",
                "transaction_id": "txn_1",
                "rule_code": "STALE_RULE",
                "severity": "critical",
                "explanation": "Old scan result.",
                "required_action": "Do not show this for the latest check.",
            },
            {
                "policy_check_id": "check_latest",
                "transaction_id": "txn_1",
                "rule_code": "LATEST_RULE",
                "severity": "medium",
                "explanation": "Latest scan result.",
                "required_action": "Show this result.",
            },
        ],
        transactions=[
            {
                "id": "txn_1",
                "employee_id": "employee_1",
                "department_id": "department_1",
                "transaction_date": "2026-05-10",
                "normalized_merchant_name": "STAPLES",
                "merchant_name": "STAPLES",
                "amount_cad": 75,
                "normalized_category": "Office Supplies",
            }
        ],
        employees=[{"id": "employee_1", "full_name": "Synthetic Employee"}],
        departments=[{"id": "department_1", "name": "Synthetic Department"}],
    )

    assert [violation.rule_code for violation in findings[0].violations] == ["LATEST_RULE"]


def test_repeat_offender_summary_counts_open_violations_by_employee_and_department():
    summary = compose_repeat_offender_summary(
        violations=[
            {"transaction_id": "txn_1", "status": "open"},
            {"transaction_id": "txn_1", "status": "open"},
            {"transaction_id": "txn_2", "status": "open"},
            {"transaction_id": "txn_3", "status": "resolved"},
        ],
        transactions=[
            {"id": "txn_1", "employee_id": "employee_1", "department_id": "department_1"},
            {"id": "txn_2", "employee_id": "employee_2", "department_id": "department_1"},
            {"id": "txn_3", "employee_id": "employee_1", "department_id": "department_1"},
        ],
        employees=[
            {"id": "employee_1", "full_name": "Synthetic Employee One"},
            {"id": "employee_2", "full_name": "Synthetic Employee Two"},
        ],
        departments=[{"id": "department_1", "name": "Synthetic Department"}],
    )

    assert summary.employees[0].name == "Synthetic Employee One"
    assert summary.employees[0].open_violations == 2
    assert summary.departments[0].open_violations == 3


def test_repeat_offender_summary_counts_open_review_queue_policy_flags():
    summary = compose_repeat_offender_summary_from_review_queue(
        rows=[
            {
                "employee_id": "employee_1",
                "department_id": "department_1",
                "queue_status": "open",
                "policy_status": "approval_evidence_needed",
                "policy_flags": [],
            },
            {
                "employee_id": "employee_1",
                "department_id": "department_1",
                "queue_status": "in_approval",
                "policy_status": "review_required",
                "policy_flags": [],
            },
            {
                "employee_id": "employee_2",
                "department_id": "department_1",
                "queue_status": "open",
                "policy_status": "compliant",
                "policy_flags": [{"rule_code": "RECEIPT_REQUIRED"}],
            },
            {
                "employee_id": "employee_3",
                "department_id": "department_2",
                "queue_status": "resolved",
                "policy_status": "policy_violation",
                "policy_flags": [{"rule_code": "ALCOHOL_RESTRICTED"}],
            },
            {
                "employee_id": "employee_4",
                "department_id": "department_2",
                "queue_status": "open",
                "policy_status": "compliant",
                "policy_flags": [],
            },
        ],
        employees=[
            {"id": "employee_1", "full_name": "Synthetic Employee One"},
            {"id": "employee_2", "full_name": "Synthetic Employee Two"},
        ],
        departments=[
            {"id": "department_1", "name": "Synthetic Department One"},
            {"id": "department_2", "name": "Synthetic Department Two"},
        ],
    )

    assert summary.employees[0].name == "Synthetic Employee One"
    assert summary.employees[0].open_violations == 2
    assert summary.employees[1].name == "Synthetic Employee Two"
    assert summary.departments[0].name == "Synthetic Department One"
    assert summary.departments[0].open_violations == 3
    assert len(summary.departments) == 1


def test_policy_findings_merge_legacy_duplicate_receipt_violations():
    findings = compose_policy_findings(
        checks=[
            {
                "id": "check_1",
                "transaction_id": "txn_1",
                "status": "review_required",
                "max_severity": "medium",
                "missing_information": [],
                "recommended_next_action": "Flag this transaction for evidence readiness and collect receipt evidence during report assembly if reimbursement proceeds.",
            }
        ],
        violations=[
            {
                "policy_check_id": "check_1",
                "transaction_id": "txn_1",
                "rule_code": "CAR_RENTAL_RECEIPTS_REQUIRED",
                "severity": "medium",
                "explanation": "Fuel expenses require receipts.",
                "required_action": "Attach the required receipt.",
            },
            {
                "policy_check_id": "check_1",
                "transaction_id": "txn_1",
                "rule_code": "RECEIPT_REQUIRED",
                "severity": "medium",
                "explanation": "A receipt is required before reimbursement.",
                "required_action": "Collect and attach a valid receipt.",
            },
        ],
        transactions=[
            {
                "id": "txn_1",
                "employee_id": "employee_1",
                "department_id": "department_1",
                "transaction_date": "2026-05-10",
                "normalized_merchant_name": "PILOT",
                "merchant_name": "PILOT",
                "amount_cad": 40,
                "business_category": "Fuel",
                "normalized_category": "Fuel",
            }
        ],
        employees=[{"id": "employee_1", "full_name": "Synthetic Employee"}],
        departments=[{"id": "department_1", "name": "Synthetic Department"}],
    )

    assert len(findings) == 1
    assert len(findings[0].violations) == 2
    explanations_by_code = {violation.rule_code: violation.explanation for violation in findings[0].violations}
    assert explanations_by_code["RECEIPT_REQUIRED"] == "A receipt is required before reimbursement."
    assert explanations_by_code["CAR_RENTAL_RECEIPTS_REQUIRED"] == "Fuel expenses require receipts."


def test_policy_findings_keep_receipt_evidence_requirement_as_detail_only():
    findings = compose_policy_findings(
        checks=[
            {
                "id": "check_1",
                "transaction_id": "txn_1",
                "status": "review_required",
                "max_severity": "low",
                "missing_information": [],
                "severity_score": 10,
                "recommended_next_action": "Flag this transaction for evidence readiness and collect receipt evidence during report assembly if reimbursement proceeds.",
            }
        ],
        violations=[
            {
                "policy_check_id": "check_1",
                "transaction_id": "txn_1",
                "rule_code": "RECEIPT_EVIDENCE_REQUIRED",
                "severity": "low",
                "explanation": "Receipt evidence unavailable in transaction dataset. Fuel expenses require receipt evidence under the travel policy, but the provided CSV does not include attachments.",
                "required_action": "Treat this as evidence-readiness metadata and collect the document during report assembly if reimbursement proceeds.",
            }
        ],
        transactions=[
            {
                "id": "txn_1",
                "employee_id": "employee_1",
                "department_id": "department_1",
                "transaction_date": "2026-05-10",
                "normalized_merchant_name": "PILOT",
                "merchant_name": "PILOT",
                "amount_cad": 40,
                "business_category": "Fuel",
                "normalized_category": "Fuel",
            }
        ],
        employees=[{"id": "employee_1", "full_name": "Synthetic Employee"}],
        departments=[{"id": "department_1", "name": "Synthetic Department"}],
    )

    assert len(findings) == 1
    assert findings[0].overall_status == "review_required"
    assert findings[0].max_severity == "low"
    assert findings[0].violations[0].rule_code == "RECEIPT_EVIDENCE_REQUIRED"
