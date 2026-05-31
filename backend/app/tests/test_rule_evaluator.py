import pytest
from pydantic import ValidationError

from app.schemas.policy_rules import ConfigurablePolicyRulePayload
from app.services.policy_engine import PolicyThresholds, build_policy_context
from app.services.rule_evaluator import (
    ConfigurablePolicyRule,
    RuleValidationError,
    condition_matches,
    evaluate_configurable_rule,
    validate_configurable_rule,
)


def transaction(**overrides):
    base = {
        "id": "txn_1",
        "employee_id": "employee_1",
        "department_id": "department_1",
        "transaction_date": "2026-05-10",
        "description": "Lunch with customer",
        "merchant_name": "CAFE",
        "normalized_merchant_name": "CAFE",
        "source_category": "Food",
        "business_category": "Meals / Entertainment",
        "normalized_category": "Meals / Entertainment",
        "debit_credit": "debit",
        "amount_cad": 75.0,
        "business_purpose": None,
        "guest_names": None,
    }
    return {**base, **overrides}


def receipt(status="submitted"):
    return {
        "status": status,
        "submitted_at": "2026-05-10T12:00:00+00:00",
        "receipt_date": "2026-05-10",
        "synthetic": False,
    }


def preapproval(status="missing"):
    return {"status": status}


def context(**overrides):
    return build_policy_context(
        transaction(**overrides),
        receipt(),
        preapproval("missing"),
        thresholds=PolicyThresholds(
            preapproval_threshold_cad=50,
            meal_context_threshold_cad=50,
        ),
    )


def configurable_rule(**overrides):
    base = {
        "rule_code": "PREAPPROVAL_OVER_50",
        "name": "Preapproval over threshold",
        "enabled": True,
        "severity": "high",
        "condition": {
            "all": [
                {"field": "skips_normal_expense_rules", "operator": "is_false"},
                {"field": "amount_cad", "operator": "gt", "value": {"threshold": "preapproval_threshold_cad"}},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        "outcome": {
            "violation": {
                "rule_code": "PREAPPROVAL_OVER_50",
                "severity": "high",
                "explanation": "Transaction exceeds the configurable preauthorization threshold.",
                "required_action": "Collect or document approval evidence.",
            }
        },
        "scope": {"department_ids": [], "employee_ids": []},
        "thresholds": {
            "preapproval_threshold_cad": {"value": 50, "currency": "CAD"},
            "meal_context_threshold_cad": {"value": 50, "currency": "CAD"},
        },
    }
    return ConfigurablePolicyRule(**{**base, **overrides})


def test_schema_accepts_configurable_policy_rule_payload():
    payload = ConfigurablePolicyRulePayload.model_validate(
        {
            "rule_code": "PREAPPROVAL_OVER_50",
            "name": "Preapproval over threshold",
            "severity": "high",
            "condition": {"field": "amount_cad", "operator": "gt", "value": 50},
            "outcome": {
                "violation": {
                    "explanation": "Transaction exceeds threshold.",
                    "required_action": "Collect approval.",
                }
            },
        }
    )

    assert payload.scope.department_ids == []
    assert payload.outcome.violation is not None


def test_schema_rejects_invalid_severity():
    with pytest.raises(ValidationError):
        ConfigurablePolicyRulePayload.model_validate(
            {
                "rule_code": "BAD",
                "name": "Bad",
                "severity": "severe",
                "condition": {"field": "amount_cad", "operator": "gt", "value": 50},
                "outcome": {"violation": {"explanation": "Bad.", "required_action": "Fix."}},
            }
        )


def test_field_and_operator_validation():
    with pytest.raises(RuleValidationError, match="Unsupported context field"):
        validate_configurable_rule(configurable_rule(condition={"field": "raw_sql", "operator": "eq", "value": "x"}))

    with pytest.raises(RuleValidationError, match="Unsupported operator"):
        validate_configurable_rule(configurable_rule(condition={"field": "amount_cad", "operator": "between", "value": [1, 2]}))


def test_all_any_and_not_conditions():
    ctx = context(amount_cad=75)

    assert condition_matches(
        {
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": 50},
                {
                    "any": [
                        {"field": "category", "operator": "eq", "value": "Fuel"},
                        {"field": "category", "operator": "eq", "value": "Meals / Entertainment"},
                    ]
                },
                {"not": {"field": "debit_credit", "operator": "eq", "value": "credit"}},
            ]
        },
        ctx,
    )


def test_department_and_employee_scope():
    ctx = context(employee_id="employee_1", department_id="department_1")
    matching = configurable_rule(scope={"department_ids": ["department_1"], "employee_ids": ["employee_1"]})
    blocked = configurable_rule(scope={"department_ids": ["department_2"], "employee_ids": []})

    assert evaluate_configurable_rule(matching, ctx).violations
    assert evaluate_configurable_rule(blocked, ctx).violations == []


def test_applies_to_business_category_gates_broad_debit_rule():
    broad_debit_rule = configurable_rule(
        rule_code="MEALS_DEBIT_REVIEW",
        name="Meals debit review",
        severity="medium",
        condition={"field": "debit_credit", "operator": "eq", "value": "debit"},
        outcome={
            "violation": {
                "rule_code": "MEALS_DEBIT_REVIEW",
                "severity": "medium",
                "explanation": "Meals debit needs review.",
                "required_action": "Review the meal context.",
            }
        },
        applies_to={"business_categories": ["Meals / Entertainment"]},
    )

    unrelated = context(
        description="Office paper",
        merchant_name="STAPLES",
        normalized_merchant_name="STAPLES",
        business_category="Office Supplies",
        normalized_category="Office Supplies",
        source_category="Office",
    )
    meals = context()

    assert evaluate_configurable_rule(broad_debit_rule, unrelated).violations == []
    assert evaluate_configurable_rule(broad_debit_rule, meals).violations[0].rule_code == "MEALS_DEBIT_REVIEW"


def test_applies_to_merchant_family_and_workflow_tags_gate_rules():
    merchant_rule = configurable_rule(
        rule_code="FUEL_NETWORK_REVIEW",
        condition={"field": "debit_credit", "operator": "eq", "value": "debit"},
        outcome={
            "violation": {
                "rule_code": "FUEL_NETWORK_REVIEW",
                "severity": "medium",
                "explanation": "Fuel network spend needs review.",
                "required_action": "Review fuel network support.",
            }
        },
        applies_to={"merchant_families": ["pilot"]},
    )
    workflow_rule = configurable_rule(
        rule_code="NORMAL_EXPENSE_REVIEW",
        condition={"field": "debit_credit", "operator": "eq", "value": "debit"},
        outcome={
            "violation": {
                "rule_code": "NORMAL_EXPENSE_REVIEW",
                "severity": "medium",
                "explanation": "Normal spend needs review.",
                "required_action": "Review normal expense support.",
            }
        },
        applies_to={"workflow_tags": ["normal_expense"]},
    )

    pilot = context(
        merchant_name="PILOT #123",
        normalized_merchant_name="PILOT",
        normalized_merchant_family="Pilot",
        business_category="Fuel",
        normalized_category="Fuel",
    )
    unrelated = context(normalized_merchant_family="Staples")
    account_payment = context(
        debit_credit="credit",
        transaction_eligibility="excluded_non_expense",
        transaction_type="account_payment",
    )

    assert evaluate_configurable_rule(merchant_rule, pilot).violations
    assert evaluate_configurable_rule(merchant_rule, unrelated).violations == []
    assert evaluate_configurable_rule(workflow_rule, pilot).violations
    assert evaluate_configurable_rule(workflow_rule, account_payment).violations == []


def test_reimbursable_eligibility_alias_matches_normal_expense_context():
    rule = configurable_rule(
        rule_code="REIMBURSABLE_PREAUTH_REVIEW",
        condition={
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": 50},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        outcome={
            "violation": {
                "rule_code": "REIMBURSABLE_PREAUTH_REVIEW",
                "severity": "high",
                "explanation": "Reimbursable expense needs preapproval review.",
                "required_action": "Collect preapproval evidence.",
            }
        },
        applies_to={"eligibility_tags": ["reimbursable"]},
    )

    assert evaluate_configurable_rule(rule, context(amount_cad=75)).violations[0].rule_code == "REIMBURSABLE_PREAUTH_REVIEW"


def test_employee_role_applies_to_matches_role_families():
    role_rule = configurable_rule(
        rule_code="MANAGER_ROLE_REVIEW",
        condition={"field": "amount_cad", "operator": "gt", "value": 50},
        outcome={
            "violation": {
                "rule_code": "MANAGER_ROLE_REVIEW",
                "severity": "medium",
                "explanation": "Manager role expense needs review.",
                "required_action": "Review manager approval path.",
            }
        },
        applies_to={"employee_roles": ["Manager"]},
    )
    manager_context = context(amount_cad=75, employee_role="Marketing Manager")

    assert evaluate_configurable_rule(role_rule, manager_context).violations[0].rule_code == "MANAGER_ROLE_REVIEW"


def test_policy_category_aliases_match_permit_rule_when_policy_category_is_inferred():
    permit_rule = configurable_rule(
        rule_code="PERMIT_APPROVAL_REVIEW",
        condition={
            "all": [
                {"field": "policy_category", "operator": "eq", "value": "permit"},
                {"field": "amount_cad", "operator": "gt", "value": 500},
            ]
        },
        outcome={
            "violation": {
                "rule_code": "PERMIT_APPROVAL_REVIEW",
                "severity": "high",
                "explanation": "Permit charge needs approval review.",
                "required_action": "Verify permit approval evidence.",
            }
        },
        applies_to={"workflow_tags": ["approval_required"], "business_categories": ["permit"]},
    )
    permit_context = context(
        amount_cad=650,
        description="Oversize permit fee",
        merchant_name="WSDOT COMMERCIAL VEHIC",
        normalized_merchant_name="WSDOT COMMERCIAL VEHIC",
        business_category="Permits / Government Fees",
        normalized_category="Permits / Government Fees",
        source_category="Permit",
    )

    assert evaluate_configurable_rule(permit_rule, permit_context).violations[0].rule_code == "PERMIT_APPROVAL_REVIEW"


def test_specific_lodging_category_rule_does_not_match_fuel_via_travel_family_tokens():
    lodging_rule = configurable_rule(
        rule_code="LODGING_RECEIPT_REVIEW",
        condition={"field": "category", "operator": "eq", "value": "lodging"},
        outcome={
            "violation": {
                "rule_code": "LODGING_RECEIPT_REVIEW",
                "severity": "high",
                "explanation": "Lodging needs a receipt.",
                "required_action": "Request a lodging receipt.",
            }
        },
    )
    fuel_context = context(
        description="Fuel stop",
        merchant_name="PILOT",
        normalized_merchant_name="PILOT",
        business_category="Fuel",
        normalized_category="Fuel",
        policy_category="Fuel",
        source_category="Fuel",
    )

    assert evaluate_configurable_rule(lodging_rule, fuel_context).violations == []


def test_eligibility_and_workflow_scopes_do_not_match_each_other():
    eligibility_rule = configurable_rule(
        rule_code="ACCOUNT_PAYMENT_ELIGIBILITY_REVIEW",
        condition={"field": "debit_credit", "operator": "eq", "value": "credit"},
        outcome={
            "violation": {
                "rule_code": "ACCOUNT_PAYMENT_ELIGIBILITY_REVIEW",
                "severity": "medium",
                "explanation": "Account-payment eligibility needs review.",
                "required_action": "Review account-payment eligibility.",
            }
        },
        applies_to={"eligibility_tags": ["account_payment"]},
    )
    workflow_rule = configurable_rule(
        rule_code="ACCOUNT_PAYMENT_WORKFLOW_REVIEW",
        condition={"field": "debit_credit", "operator": "eq", "value": "credit"},
        outcome={
            "violation": {
                "rule_code": "ACCOUNT_PAYMENT_WORKFLOW_REVIEW",
                "severity": "medium",
                "explanation": "Account-payment workflow needs review.",
                "required_action": "Review account-payment workflow.",
            }
        },
        applies_to={"workflow_tags": ["account_payment"]},
    )
    account_payment = context(
        debit_credit="credit",
        transaction_eligibility="excluded_non_expense",
        transaction_type="account_payment",
    )

    assert evaluate_configurable_rule(eligibility_rule, account_payment).violations == []
    assert evaluate_configurable_rule(workflow_rule, account_payment).violations[0].rule_code == "ACCOUNT_PAYMENT_WORKFLOW_REVIEW"


def test_account_activity_is_excluded_by_condition():
    ctx = context(
        amount_cad=1000,
        debit_credit="credit",
        transaction_eligibility="excluded_non_expense",
        transaction_type="account_payment",
        business_category="Account Payment / Transfer",
    )

    result = evaluate_configurable_rule(configurable_rule(), ctx)

    assert result.violations == []


def test_preauth_threshold_rule_emits_violation():
    result = evaluate_configurable_rule(configurable_rule(), context(amount_cad=75))

    assert result.violations[0].rule_code == "PREAPPROVAL_OVER_50"
    assert result.violations[0].severity == "high"


def test_custom_policy_threshold_reference_is_valid_and_resolves():
    rule = configurable_rule(
        rule_code="MANAGER_APPROVAL_POLICY_NAME",
        condition={
            "all": [
                {"field": "amount_cad", "operator": "gt", "value": {"threshold": "manager_preapproval_limit"}},
                {"field": "missing_preapproval", "operator": "is_true"},
            ]
        },
        outcome={
            "violation": {
                "rule_code": "MANAGER_APPROVAL_POLICY_NAME",
                "severity": "high",
                "explanation": "Transaction exceeds the manager-specific policy threshold.",
                "required_action": "Collect or document approval evidence.",
            }
        },
        thresholds={"manager_preapproval_limit": {"value": 60, "currency": "CAD"}},
    )

    validate_configurable_rule(rule)
    result = evaluate_configurable_rule(rule, context(amount_cad=75))

    assert result.violations[0].rule_code == "MANAGER_APPROVAL_POLICY_NAME"


def test_synthetic_submitted_receipt_counts_as_evidence():
    ctx = build_policy_context(
        transaction(amount_cad=75),
        {**receipt("submitted"), "synthetic": True},
        preapproval("approved"),
    )

    assert ctx.has_receipt_evidence is True
    assert ctx.receipt_evidence_unavailable is False


def test_synthetic_missing_preapproval_can_enforce_threshold_rule():
    ctx = build_policy_context(
        transaction(amount_cad=75),
        receipt(),
        {"status": "missing", "synthetic": True},
        thresholds=PolicyThresholds(preapproval_threshold_cad=50),
    )

    result = evaluate_configurable_rule(configurable_rule(), ctx)

    assert result.violations[0].rule_code == "PREAPPROVAL_OVER_50"


def test_meals_context_rule_emits_missing_information():
    rule = configurable_rule(
        rule_code="ENTERTAINMENT_CONTEXT_REQUIRED",
        name="Meals context",
        severity="medium",
        condition={
            "all": [
                {"field": "skips_normal_expense_rules", "operator": "is_false"},
                {"field": "category", "operator": "in", "value": ["Meals / Entertainment", "Meals"]},
                {"field": "amount_cad", "operator": "gt", "value": {"threshold": "meal_context_threshold_cad"}},
                {
                    "any": [
                        {"field": "has_guest_names", "operator": "is_false"},
                        {"field": "has_business_purpose", "operator": "is_false"},
                    ]
                },
            ]
        },
        outcome={
            "violation": {
                "rule_code": "ENTERTAINMENT_CONTEXT_REQUIRED",
                "severity": "medium",
                "explanation": "Meals over the context threshold require guest names and business purpose.",
                "required_action": "Collect missing entertainment context.",
            },
            "missing_information": ["guest names", "business purpose"],
        },
    )

    result = evaluate_configurable_rule(rule, context(amount_cad=75))

    assert result.violations[0].rule_code == "ENTERTAINMENT_CONTEXT_REQUIRED"
    assert result.missing_information == {"guest names", "business purpose"}
