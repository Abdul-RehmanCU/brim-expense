from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.policy import PolicyStatus, PolicyViolation, Severity
from app.services.policy_engine import PolicyContext

ALLOWED_OPERATORS = {
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "contains",
    "not_contains",
    "exists",
    "is_true",
    "is_false",
}

ALLOWED_CONTEXT_FIELDS = {
    "amount_cad",
    "merchant_raw",
    "merchant_normalized",
    "normalized_merchant_family",
    "transaction_code",
    "category",
    "debit_credit",
    "debit_or_credit",
    "department_id",
    "department_name",
    "employee_id",
    "employee_name",
    "employee_role",
    "transaction_date",
    "posting_date",
    "posting_delay_days",
    "merchant_country",
    "merchant_state_province",
    "merchant_postal_code",
    "mcc",
    "mcc_description",
    "network_category_code",
    "business_category",
    "normalized_category",
    "policy_category",
    "category_confidence",
    "category_source",
    "has_business_purpose",
    "has_guest_names",
    "has_pending_preapproval",
    "has_receipt_evidence",
    "is_account_activity",
    "is_alcohol_category",
    "is_critical_value",
    "is_credit_or_refund",
    "is_excluded_non_expense",
    "is_foreign_transaction",
    "is_high_value",
    "is_low_confidence_category",
    "is_meal_or_entertainment",
    "is_personal_expense",
    "is_ticket_or_fine",
    "is_uncategorized",
    "is_weekend",
    "missing_preapproval",
    "preapproval_status",
    "preapproval_synthetic",
    "receipt_synthetic",
    "receipt_evidence_unavailable",
    "receipt_explicitly_missing",
    "receipt_sensitive_category",
    "receipt_status",
    "receipt_submitted_current_month",
    "requires_finance_review",
    "requires_preapproval",
    "search_text",
    "skips_normal_expense_rules",
    "transaction_eligibility",
    "transaction_type",
}

ALLOWED_THRESHOLDS = {
    "preapproval_threshold_cad",
    "high_value_threshold_cad",
    "critical_value_threshold_cad",
    "repeat_violation_threshold",
    "meal_context_threshold_cad",
}

SEVERITIES: set[Severity] = {"low", "medium", "high", "critical"}
ORDINARY_EXPENSE_EVIDENCE_FIELDS = {
    "has_pending_preapproval",
    "has_receipt_evidence",
    "missing_preapproval",
    "preapproval_status",
    "receipt_evidence_unavailable",
    "receipt_explicitly_missing",
    "receipt_status",
    "receipt_submitted_current_month",
    "requires_preapproval",
}
EXPENSE_EVIDENCE_TERMS = {
    "approval",
    "attach",
    "attachment",
    "preapproval",
    "pre-approval",
    "preauthorization",
    "pre-authorization",
    "receipt",
    "supporting document",
}


class RuleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ConfigurablePolicyRule:
    rule_code: str
    name: str
    enabled: bool
    severity: Severity
    condition: dict[str, Any]
    outcome: dict[str, Any]
    scope: dict[str, Any] = field(default_factory=dict)
    applies_to: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    context_requirements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfigurableRuleOutcome:
    violations: list[PolicyViolation] = field(default_factory=list)
    missing_information: set[str] = field(default_factory=set)
    status: PolicyStatus | None = None


def evaluate_configurable_rule(rule: ConfigurablePolicyRule, context: PolicyContext) -> ConfigurableRuleOutcome:
    validate_configurable_rule(rule)
    if not rule.enabled or not scope_matches(rule.scope, context) or not applies_to_matches(rule.applies_to, context):
        return ConfigurableRuleOutcome()
    if ordinary_expense_evidence_rule_is_skipped(rule, context):
        return ConfigurableRuleOutcome()

    if not condition_matches(rule.condition, context, rule.thresholds):
        return ConfigurableRuleOutcome()
    if synthetic_evidence_gap_is_unscoped(rule, context):
        return ConfigurableRuleOutcome()

    missing_information = set(rule.outcome.get("missing_information") or [])
    status = normalize_outcome_status(rule.outcome.get("status"))
    violation_template = rule.outcome.get("violation")
    if not violation_template:
        return ConfigurableRuleOutcome(missing_information=missing_information, status=status)

    return ConfigurableRuleOutcome(
        violations=[
            PolicyViolation(
                rule_code=str(violation_template.get("rule_code") or rule.rule_code),
                severity=violation_template.get("severity") or rule.severity,
                explanation=render_template(str(violation_template["explanation"]), context),
                required_action=render_template(str(violation_template["required_action"]), context),
            )
        ],
        missing_information=missing_information,
        status=status,
    )


def validate_configurable_rule(rule: ConfigurablePolicyRule) -> None:
    if rule.severity not in SEVERITIES:
        raise RuleValidationError(f"Unsupported severity: {rule.severity}")
    validate_scope(rule.scope)
    validate_applies_to(rule.applies_to)
    validate_condition(rule.condition, rule.thresholds)
    validate_outcome(rule.outcome)


def validate_scope(scope: dict[str, Any]) -> None:
    for key in scope:
        if key not in {"department_ids", "employee_ids"}:
            raise RuleValidationError(f"Unsupported scope key: {key}")
    for key in ["department_ids", "employee_ids"]:
        values = scope.get(key) or []
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise RuleValidationError(f"{key} must be a list of string ids")


def validate_applies_to(applies_to: dict[str, Any]) -> None:
    if not isinstance(applies_to, dict):
        raise RuleValidationError("applies_to must be an object")
    for key, values in applies_to.items():
        if values in (None, "", []):
            continue
        if isinstance(values, str):
            continue
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise RuleValidationError(f"applies_to.{key} must be a string or list of strings")


def validate_condition(condition: dict[str, Any], thresholds: dict[str, Any] | None = None) -> None:
    if not isinstance(condition, dict) or not condition:
        raise RuleValidationError("Condition must be a non-empty object")

    combinators = [key for key in ("all", "any", "not") if key in condition]
    if combinators:
        if len(combinators) != 1 or len(condition) != 1:
            raise RuleValidationError("Condition combinators cannot be mixed with leaf fields")
        key = combinators[0]
        if key == "not":
            validate_condition(condition[key], thresholds)
            return
        children = condition[key]
        if not isinstance(children, list) or not children:
            raise RuleValidationError(f"{key} requires a non-empty list of conditions")
        for child in children:
            validate_condition(child, thresholds)
        return

    field_name = condition.get("field")
    operator = condition.get("operator")
    if field_name not in ALLOWED_CONTEXT_FIELDS:
        raise RuleValidationError(f"Unsupported context field: {field_name}")
    if operator not in ALLOWED_OPERATORS:
        raise RuleValidationError(f"Unsupported operator: {operator}")
    if operator not in {"exists", "is_true", "is_false"} and "value" not in condition:
        raise RuleValidationError(f"{operator} requires a value")
    if isinstance(condition.get("value"), dict):
        threshold = condition["value"].get("threshold")
        if threshold not in ALLOWED_THRESHOLDS and threshold not in (thresholds or {}):
            raise RuleValidationError(f"Unsupported threshold reference: {threshold}")


def validate_outcome(outcome: dict[str, Any]) -> None:
    if not isinstance(outcome, dict):
        raise RuleValidationError("Outcome must be an object")
    violation = outcome.get("violation")
    if violation is not None:
        if not isinstance(violation, dict):
            raise RuleValidationError("Outcome violation must be an object")
        if "explanation" not in violation or "required_action" not in violation:
            raise RuleValidationError("Outcome violation requires explanation and required_action")
        severity = violation.get("severity")
        if severity is not None and severity not in SEVERITIES:
            raise RuleValidationError(f"Unsupported outcome severity: {severity}")
    missing_information = outcome.get("missing_information") or []
    if not isinstance(missing_information, list) or any(not isinstance(item, str) for item in missing_information):
        raise RuleValidationError("missing_information must be a list of strings")
    status = outcome.get("status")
    if status is not None and normalize_outcome_status(status) is None:
        raise RuleValidationError(f"Unsupported outcome status: {status}")


def scope_matches(scope: dict[str, Any], context: PolicyContext) -> bool:
    department_ids = set(scope.get("department_ids") or [])
    employee_ids = set(scope.get("employee_ids") or [])
    if department_ids and context.department_id not in department_ids:
        return False
    if employee_ids and context.employee_id not in employee_ids:
        return False
    return True


def applies_to_matches(applies_to: dict[str, Any], context: PolicyContext) -> bool:
    criteria = {key: normalize_list(values) for key, values in applies_to.items() if normalize_list(values)}
    if not criteria:
        return True

    for key, expected_values in criteria.items():
        if key in {"business_categories", "business_category", "categories", "category", "policy_categories"}:
            if not values_overlap(expected_values, context_category_values(context)):
                return False
            continue
        if key in {"normalized_categories", "normalized_category"}:
            if not values_overlap(expected_values, context_normalized_category_values(context)):
                return False
            continue
        if key in {"merchant_families", "merchant_family", "normalized_merchant_families"}:
            if not values_overlap(expected_values, context_merchant_family_values(context)):
                return False
            continue
        if key in {"eligibility_tags", "eligibility", "transaction_eligibilities"}:
            if not values_overlap(expected_values, context_eligibility_values(context)):
                return False
            continue
        if key in {"workflow_tags", "workflow", "transaction_types", "transaction_type"}:
            if not values_overlap(expected_values, context_workflow_values(context)):
                return False
            continue

        # Unknown non-empty scope metadata should not be treated as a global match.
        return False

    return True


def condition_matches(condition: dict[str, Any], context: PolicyContext, thresholds: dict[str, Any] | None = None) -> bool:
    if "all" in condition:
        return all(condition_matches(child, context, thresholds) for child in condition["all"])
    if "any" in condition:
        return any(condition_matches(child, context, thresholds) for child in condition["any"])
    if "not" in condition:
        return not condition_matches(condition["not"], context, thresholds)

    actual = context_value(context, str(condition["field"]))
    operator = condition["operator"]
    expected = resolve_value(condition.get("value"), context, thresholds)

    if operator == "eq":
        return actual == expected
    if operator == "neq":
        return actual != expected
    if operator == "gt":
        return float(actual or 0) > float(expected)
    if operator == "gte":
        return float(actual or 0) >= float(expected)
    if operator == "lt":
        return float(actual or 0) < float(expected)
    if operator == "lte":
        return float(actual or 0) <= float(expected)
    if operator == "in":
        return actual in expected
    if operator == "not_in":
        return actual not in expected
    if operator == "contains":
        return str(expected).upper() in str(actual or "").upper()
    if operator == "not_contains":
        return str(expected).upper() not in str(actual or "").upper()
    if operator == "exists":
        return actual is not None and actual != ""
    if operator == "is_true":
        return bool(actual) is True
    if operator == "is_false":
        return bool(actual) is False

    raise RuleValidationError(f"Unsupported operator: {operator}")


def synthetic_evidence_gap_is_unscoped(rule: ConfigurablePolicyRule, context: PolicyContext) -> bool:
    fields = collect_condition_fields(rule.condition)
    if "receipt_evidence_unavailable" in fields and context.receipt_synthetic and not context.receipt_explicitly_missing:
        if not rule_has_specific_scope(rule, fields):
            return True
    if "missing_preapproval" in fields and context.preapproval_synthetic:
        has_threshold_gate = bool({"amount_cad", "requires_preapproval"} & fields)
        if not has_threshold_gate and not rule_has_specific_scope(rule, fields):
            return True
    return False


def rule_has_specific_scope(rule: ConfigurablePolicyRule, condition_fields: set[str]) -> bool:
    if any(normalize_list(values) for values in rule.applies_to.values()):
        return True
    return bool(
        condition_fields
        & {
            "business_category",
            "category",
            "normalized_category",
            "policy_category",
            "normalized_merchant_family",
            "merchant_normalized",
            "merchant_raw",
            "mcc",
            "mcc_description",
            "network_category_code",
            "receipt_sensitive_category",
            "is_meal_or_entertainment",
            "is_alcohol_category",
            "is_ticket_or_fine",
            "is_personal_expense",
        }
    )


def collect_condition_fields(condition: dict[str, Any]) -> set[str]:
    if "all" in condition:
        return set().union(*(collect_condition_fields(child) for child in condition["all"]))
    if "any" in condition:
        return set().union(*(collect_condition_fields(child) for child in condition["any"]))
    if "not" in condition:
        return collect_condition_fields(condition["not"])
    field_name = condition.get("field")
    return {str(field_name)} if field_name else set()


def resolve_value(value: Any, context: PolicyContext, thresholds: dict[str, Any] | None = None) -> Any:
    if isinstance(value, dict) and "threshold" in value:
        threshold_name = str(value["threshold"])
        if thresholds and threshold_name in thresholds:
            from app.services.policy_engine import resolve_threshold_config

            return resolve_threshold_config(
                thresholds[threshold_name],
                {
                    "employee_id": context.employee_id,
                    "department_id": context.department_id,
                    "employee_role": context_value(context, "employee_role"),
                    "transaction_date": context.transaction_date,
                },
            )
        return getattr(context.thresholds, threshold_name)
    return value


def normalize_list(values: Any) -> list[str]:
    if values in (None, "", []):
        return []
    if isinstance(values, str):
        return [values]
    return [str(value) for value in values if str(value).strip()]


def normalize_token(value: Any) -> str:
    return " ".join(str(value or "").replace("/", " ").replace("-", " ").replace("_", " ").lower().split())


def normalized_value_set(values: list[Any]) -> set[str]:
    result = {normalize_token(value) for value in values if normalize_token(value)}
    for value in list(result):
        result.update(category_family_tokens(value))
    return result


def values_overlap(expected_values: list[str], actual_values: list[Any]) -> bool:
    expected = normalized_value_set(expected_values)
    actual = normalized_value_set(actual_values)
    return bool(expected & actual)


def context_category_values(context: PolicyContext) -> list[Any]:
    return [
        context.category,
        context_value(context, "business_category"),
        context_value(context, "normalized_category"),
        context_value(context, "policy_category"),
    ]


def context_normalized_category_values(context: PolicyContext) -> list[Any]:
    return [
        context_value(context, "normalized_category"),
        context_value(context, "policy_category"),
        context.category,
    ]


def context_merchant_family_values(context: PolicyContext) -> list[Any]:
    return [
        context_value(context, "normalized_merchant_family"),
        context_value(context, "merchant_normalized"),
        context_value(context, "merchant_raw"),
    ]


def context_eligibility_values(context: PolicyContext) -> list[Any]:
    return [
        context.transaction_eligibility,
        *context_eligibility_tags(context),
    ]


def context_workflow_values(context: PolicyContext) -> list[Any]:
    return [
        context.transaction_type,
        *context_eligibility_tags(context),
        *context_workflow_tags(context),
    ]


def context_fact_tags(context: PolicyContext) -> list[str]:
    return [
        *context_eligibility_tags(context),
        *context_workflow_tags(context),
        *context_risk_and_evidence_tags(context),
    ]


def context_eligibility_tags(context: PolicyContext) -> list[str]:
    tags = []
    if context.is_excluded_non_expense:
        tags.extend(["excluded_non_expense", "non_expense"])
    if context.requires_finance_review:
        tags.append("finance_review")
    if not context.skips_normal_expense_rules:
        tags.append("normal_expense")
    return tags


def context_workflow_tags(context: PolicyContext) -> list[str]:
    tags = []
    debit_credit = normalize_token(context.debit_credit)
    if debit_credit:
        tags.append(debit_credit)
    if context.transaction_type:
        tags.append(str(context.transaction_type))
    return tags


def context_risk_and_evidence_tags(context: PolicyContext) -> list[str]:
    tags = []
    if context.is_high_value:
        tags.append("high_value")
    if context.is_critical_value:
        tags.append("critical_value")
    if context.receipt_sensitive_category:
        tags.append("receipt_sensitive")
    if context.receipt_explicitly_missing:
        tags.append("receipt_missing")
    if context.receipt_evidence_unavailable:
        tags.append("receipt_unavailable")
    if context.requires_preapproval:
        tags.append("preapproval_required")
    if context.missing_preapproval:
        tags.append("preapproval_missing")
    if context.has_pending_preapproval:
        tags.append("preapproval_pending")
    if context.is_meal_or_entertainment:
        tags.extend(["meal", "meals", "entertainment", "meals_entertainment"])
    if context.is_alcohol_category:
        tags.append("alcohol")
    if context.is_ticket_or_fine:
        tags.extend(["ticket", "fine"])
    if context.is_personal_expense:
        tags.append("personal_expense")
    return tags


def ordinary_expense_evidence_rule_is_skipped(rule: ConfigurablePolicyRule, context: PolicyContext) -> bool:
    if not context.skips_normal_expense_rules:
        return False
    if rule_explicitly_targets_skipped_expense_context(rule, context):
        return False

    fields = collect_condition_fields(rule.condition)
    return bool(fields & ORDINARY_EXPENSE_EVIDENCE_FIELDS) or evidence_terms_in_rule(rule)


def evidence_terms_in_rule(rule: ConfigurablePolicyRule) -> bool:
    text = normalize_token(
        " ".join(
            [
                rule.rule_code,
                rule.name,
                str(rule.outcome),
                " ".join(rule.context_requirements),
            ]
        )
    )
    return any(normalize_token(term) in text for term in EXPENSE_EVIDENCE_TERMS)


def rule_explicitly_targets_skipped_expense_context(rule: ConfigurablePolicyRule, context: PolicyContext) -> bool:
    applies_to = rule.applies_to or {}
    eligibility_values = []
    workflow_values = []
    for key, values in applies_to.items():
        normalized_values = normalize_list(values)
        if key in {"eligibility_tags", "eligibility", "transaction_eligibilities"}:
            eligibility_values.extend(normalized_values)
        if key in {"workflow_tags", "workflow", "transaction_types", "transaction_type"}:
            workflow_values.extend(normalized_values)

    if eligibility_values and values_overlap(eligibility_values, context_eligibility_values(context)):
        return True
    if workflow_values and values_overlap(workflow_values, context_workflow_values(context)):
        return True

    return condition_targets_skipped_expense_context(rule.condition, context)


def condition_targets_skipped_expense_context(condition: dict[str, Any], context: PolicyContext) -> bool:
    if "all" in condition:
        return any(condition_targets_skipped_expense_context(child, context) for child in condition["all"])
    if "any" in condition:
        return any(condition_targets_skipped_expense_context(child, context) for child in condition["any"])
    if "not" in condition:
        return False

    field_name = condition.get("field")
    operator = condition.get("operator")
    expected = condition.get("value")
    if field_name in {"is_excluded_non_expense", "requires_finance_review", "skips_normal_expense_rules"}:
        return operator == "is_true"
    if field_name == "transaction_eligibility":
        return condition_expected_values_include(
            expected,
            [context.transaction_eligibility, *context_eligibility_tags(context)],
        )
    if field_name == "transaction_type":
        return condition_expected_values_include(
            expected,
            [context.transaction_type, *context_workflow_tags(context)],
        )
    return False


def condition_expected_values_include(expected: Any, actual_values: list[Any]) -> bool:
    if expected in (None, ""):
        return False
    expected_values = [str(value) for value in expected] if isinstance(expected, list) else [str(expected)]
    return values_overlap(expected_values, actual_values)


def category_family_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    if any(part in value for part in ["meal", "entertainment", "restaurant", "dining"]):
        tokens.update({"meal", "meals", "entertainment", "dining"})
    if any(part in value for part in ["travel", "transport", "fuel", "parking", "toll", "rental", "lodging", "hotel"]):
        tokens.add("travel")
    if any(part in value for part in ["fuel", "rental", "vehicle", "fleet", "parking", "toll", "truck", "car"]):
        tokens.update({"vehicle", "fleet"})
    if any(part in value for part in ["permit", "government fee"]):
        tokens.update({"permit", "permits", "government"})
    if "office" in value:
        tokens.add("office")
    return tokens


def context_value(context: PolicyContext, field_name: str) -> Any:
    if hasattr(context, field_name):
        return getattr(context, field_name)
    return context.extra_fields.get(field_name)


def normalize_outcome_status(value: Any) -> PolicyStatus | None:
    status = str(value or "").strip()
    aliases: dict[str, PolicyStatus] = {
        "approval_evidence_required": "approval_evidence_needed",
        "approval_required": "approval_evidence_needed",
        "receipt_evidence_required": "review_required",
        "needs_context": "context_needed",
        "manual_review": "review_required",
        "non_reimbursable": "policy_violation",
    }
    if status in aliases:
        return aliases[status]
    if status in {
        "compliant",
        "excluded_non_expense",
        "review_required",
        "context_needed",
        "approval_evidence_needed",
        "policy_violation",
    }:
        return status  # type: ignore[return-value]
    return None


def render_template(template: str, context: PolicyContext) -> str:
    values = {
        field: context_value(context, field)
        for field in ALLOWED_CONTEXT_FIELDS
    }
    return template.format_map(SafeTemplateValues(values))


class SafeTemplateValues(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
