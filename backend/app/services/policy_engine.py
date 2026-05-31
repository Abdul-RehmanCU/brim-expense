from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.schemas.policy import PolicyCheckResult, PolicyStatus, PolicyViolation, Severity

if TYPE_CHECKING:
    from app.services.rule_evaluator import ConfigurablePolicyRule, ConfigurableRuleOutcome


ENGINE_VERSION = "python-policy-engine-v5-platform-facts"
NO_CONFIGURED_MONEY_THRESHOLD = float("inf")

SEVERITY_RANK: dict[Severity, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

SEVERITY_POINTS: dict[Severity, int] = {
    "low": 10,
    "medium": 30,
    "high": 60,
    "critical": 90,
}

STATUS_PRIORITY: dict[PolicyStatus, int] = {
    "compliant": 0,
    "excluded_non_expense": 1,
    "review_required": 2,
    "context_needed": 3,
    "approval_evidence_needed": 4,
    "policy_violation": 5,
}

PERMIT_KEYWORDS = [
    "MNDOT",
    "UDOT",
    "WSDOT",
    "TDOT",
    "TXDMV",
    "KYTC",
    "NDHP",
    "MCSD",
    "DOT",
    "DMV",
    "DEPT OF TRANS",
    "DEPT TRANSPORT",
    "DEPARTMENT OF TRANS",
    "OSOW",
    "PERMIT",
    "HAULING PERMITS",
    "MOTOR CARRIER",
    "MOTOR CARRIERS",
    "SIZE & WEIGHTS",
    "DTOPS",
    "CROSSING",
    "VCN",
    "BC PERMIT",
    "AB TRANSP",
    "SD DEPT",
]


@dataclass(frozen=True)
class PolicyThresholds:
    # Monetary thresholds are intentionally inert until active policy rules provide values.
    preapproval_threshold_cad: float = NO_CONFIGURED_MONEY_THRESHOLD
    high_value_threshold_cad: float = NO_CONFIGURED_MONEY_THRESHOLD
    critical_value_threshold_cad: float = NO_CONFIGURED_MONEY_THRESHOLD
    repeat_violation_threshold: int = 3
    meal_context_threshold_cad: float = NO_CONFIGURED_MONEY_THRESHOLD


@dataclass(frozen=True)
class TransactionFacts:
    transaction_id: str
    amount_cad: float
    debit_credit: str | None
    category: str
    transaction_eligibility: str | None
    transaction_type: str | None
    search_text: str
    transaction_date: str | None
    employee_id: str | None = None
    department_id: str | None = None


@dataclass(frozen=True)
class EvidenceFacts:
    receipt_status: str | None
    receipt_synthetic: bool
    preapproval_status: str | None
    preapproval_synthetic: bool
    has_guest_names: bool
    has_business_purpose: bool
    receipt_submitted_current_month: bool


@dataclass(frozen=True)
class DerivedFacts:
    requires_preapproval: bool
    has_pending_preapproval: bool
    missing_preapproval: bool
    receipt_explicitly_missing: bool
    receipt_evidence_unavailable: bool
    has_receipt_evidence: bool
    receipt_sensitive_category: bool
    is_high_value: bool
    is_critical_value: bool
    is_excluded_non_expense: bool
    requires_finance_review: bool
    skips_normal_expense_rules: bool
    is_meal_or_entertainment: bool
    is_alcohol_category: bool
    is_ticket_or_fine: bool
    is_personal_expense: bool


@dataclass(frozen=True)
class PolicyContext:
    transaction_facts: TransactionFacts
    evidence_facts: EvidenceFacts
    derived_facts: DerivedFacts
    thresholds: PolicyThresholds = field(default_factory=PolicyThresholds)
    extra_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def facts(self) -> dict[str, dict[str, Any]]:
        return {
            "transaction": asdict(self.transaction_facts),
            "evidence": asdict(self.evidence_facts),
            "derived": asdict(self.derived_facts),
        }

    @property
    def transaction_id(self) -> str:
        return self.transaction_facts.transaction_id

    @property
    def amount_cad(self) -> float:
        return self.transaction_facts.amount_cad

    @property
    def debit_credit(self) -> str | None:
        return self.transaction_facts.debit_credit

    @property
    def category(self) -> str:
        return self.transaction_facts.category

    @property
    def transaction_eligibility(self) -> str | None:
        return self.transaction_facts.transaction_eligibility

    @property
    def transaction_type(self) -> str | None:
        return self.transaction_facts.transaction_type

    @property
    def search_text(self) -> str:
        return self.transaction_facts.search_text

    @property
    def transaction_date(self) -> str | None:
        return self.transaction_facts.transaction_date

    @property
    def employee_id(self) -> str | None:
        return self.transaction_facts.employee_id

    @property
    def department_id(self) -> str | None:
        return self.transaction_facts.department_id

    @property
    def receipt_status(self) -> str | None:
        return self.evidence_facts.receipt_status

    @property
    def receipt_synthetic(self) -> bool:
        return self.evidence_facts.receipt_synthetic

    @property
    def preapproval_status(self) -> str | None:
        return self.evidence_facts.preapproval_status

    @property
    def preapproval_synthetic(self) -> bool:
        return self.evidence_facts.preapproval_synthetic

    @property
    def has_guest_names(self) -> bool:
        return self.evidence_facts.has_guest_names

    @property
    def has_business_purpose(self) -> bool:
        return self.evidence_facts.has_business_purpose

    @property
    def receipt_submitted_current_month(self) -> bool:
        return self.evidence_facts.receipt_submitted_current_month

    @property
    def requires_preapproval(self) -> bool:
        return self.derived_facts.requires_preapproval

    @property
    def has_pending_preapproval(self) -> bool:
        return self.derived_facts.has_pending_preapproval

    @property
    def missing_preapproval(self) -> bool:
        return self.derived_facts.missing_preapproval

    @property
    def receipt_explicitly_missing(self) -> bool:
        return self.derived_facts.receipt_explicitly_missing

    @property
    def receipt_evidence_unavailable(self) -> bool:
        return self.derived_facts.receipt_evidence_unavailable

    @property
    def has_receipt_evidence(self) -> bool:
        return self.derived_facts.has_receipt_evidence

    @property
    def receipt_sensitive_category(self) -> bool:
        return self.derived_facts.receipt_sensitive_category

    @property
    def is_high_value(self) -> bool:
        return self.derived_facts.is_high_value

    @property
    def is_critical_value(self) -> bool:
        return self.derived_facts.is_critical_value

    @property
    def is_excluded_non_expense(self) -> bool:
        return self.derived_facts.is_excluded_non_expense

    @property
    def requires_finance_review(self) -> bool:
        return self.derived_facts.requires_finance_review

    @property
    def skips_normal_expense_rules(self) -> bool:
        return self.derived_facts.skips_normal_expense_rules

    @property
    def is_meal_or_entertainment(self) -> bool:
        return self.derived_facts.is_meal_or_entertainment

    @property
    def is_alcohol_category(self) -> bool:
        return self.derived_facts.is_alcohol_category

    @property
    def is_ticket_or_fine(self) -> bool:
        return self.derived_facts.is_ticket_or_fine

    @property
    def is_personal_expense(self) -> bool:
        return self.derived_facts.is_personal_expense


def stable_bucket(value: str, salt: str, modulo: int = 100) -> int:
    digest = hashlib.sha256(f"{value}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def synthetic_key(transaction: dict[str, Any]) -> str:
    raw_transaction = transaction.get("raw_transactions")
    if isinstance(raw_transaction, dict) and raw_transaction.get("source_fingerprint"):
        return str(raw_transaction["source_fingerprint"])

    return "|".join(
        [
            str(transaction.get("id") or ""),
            str(transaction.get("transaction_date") or ""),
            str(transaction.get("normalized_merchant_name") or transaction.get("merchant_name") or ""),
            str(transaction.get("amount_cad") or ""),
        ],
    )


def infer_synthetic_receipt(transaction: dict[str, Any]) -> dict[str, Any]:
    transaction_date = transaction.get("transaction_date")
    status = infer_synthetic_receipt_status(transaction)
    has_evidence = status in {"submitted", "approved"}

    return {
        "transaction_id": transaction["id"],
        "storage_path": f"synthetic://receipts/{transaction['id']}.pdf" if has_evidence else None,
        "file_name": f"synthetic-receipt-{transaction['id']}.pdf" if has_evidence else None,
        "receipt_date": transaction_date if has_evidence else None,
        "submitted_at": f"{transaction_date}T12:00:00+00:00" if has_evidence and transaction_date else None,
        "status": status,
        "synthetic": True,
    }


def infer_synthetic_receipt_status(transaction: dict[str, Any]) -> str:
    if skips_expense_evidence(transaction):
        return "unavailable"

    bucket = stable_bucket(synthetic_key(transaction), "receipt")
    if bucket < 48:
        return "approved"
    if bucket < 82:
        return "submitted"
    if bucket < 94:
        return "missing"
    return "unavailable"


def infer_synthetic_preapproval(
    transaction: dict[str, Any],
    thresholds: PolicyThresholds | None = None,
) -> dict[str, Any]:
    amount_cad = to_float(transaction.get("amount_cad"))
    transaction_date = transaction.get("transaction_date")
    employee_id = transaction.get("employee_id")
    thresholds = thresholds or PolicyThresholds()

    if not employee_id:
        raise ValueError("Cannot create synthetic preapproval without employee_id.")

    if skips_expense_evidence(transaction) or amount_cad <= thresholds.preapproval_threshold_cad:
        status = "not_required"
    else:
        bucket = stable_bucket(synthetic_key(transaction), "preapproval")
        status = "approved" if bucket < 60 else "missing" if bucket < 82 else "requested"

    requested_at = None
    approved_at = None
    if status in {"approved", "requested"} and transaction_date:
        requested_at = f"{transaction_date}T09:00:00+00:00"
    if status == "approved" and transaction_date:
        approved_at = f"{transaction_date}T10:00:00+00:00"

    return {
        "employee_id": employee_id,
        "transaction_id": transaction["id"],
        "department_id": transaction.get("department_id"),
        "requested_amount_cad": amount_cad,
        "status": status,
        "requested_at": requested_at,
        "approved_at": approved_at,
        "approver_employee_id": None,
        "approver_name": "Synthetic manager" if status == "approved" else None,
        "business_purpose": f"Synthetic business purpose for {finance_category(transaction) or 'expense'}."
        if status == "approved"
        else None,
        "synthetic": True,
    }


def build_policy_context(
    transaction: dict[str, Any],
    receipt: dict[str, Any] | None,
    preapproval: dict[str, Any] | None,
    thresholds: PolicyThresholds | None = None,
) -> PolicyContext:
    thresholds = thresholds or PolicyThresholds()
    category = infer_policy_category(transaction)
    extra_fields = transaction_context_fields(transaction, category)
    transaction_facts = TransactionFacts(
        transaction_id=str(transaction["id"]),
        amount_cad=to_float(transaction.get("amount_cad")),
        debit_credit=str(transaction.get("debit_credit") or "").lower() or None,
        category=category,
        transaction_eligibility=str(transaction.get("transaction_eligibility") or "") or None,
        transaction_type=str(transaction.get("transaction_type") or "") or None,
        search_text=transaction_search_text(transaction),
        transaction_date=transaction.get("transaction_date"),
        employee_id=str(transaction.get("employee_id") or "") or None,
        department_id=str(transaction.get("department_id") or "") or None,
    )
    evidence_facts = EvidenceFacts(
        receipt_status=receipt.get("status") if receipt else None,
        receipt_synthetic=bool(receipt.get("synthetic")) if receipt else True,
        preapproval_status=preapproval.get("status") if preapproval else None,
        preapproval_synthetic=bool(preapproval.get("synthetic")) if preapproval else True,
        has_guest_names=bool(transaction.get("guest_names")),
        has_business_purpose=bool(transaction.get("business_purpose")),
        receipt_submitted_current_month=True if not receipt else receipt_submitted_in_transaction_month(transaction, receipt),
    )
    return PolicyContext(
        transaction_facts=transaction_facts,
        evidence_facts=evidence_facts,
        derived_facts=derive_facts(transaction_facts, evidence_facts, thresholds),
        thresholds=thresholds,
        extra_fields=extra_fields,
    )


def derive_facts(
    transaction_facts: TransactionFacts,
    evidence_facts: EvidenceFacts,
    thresholds: PolicyThresholds,
) -> DerivedFacts:
    requires_preapproval = transaction_facts.amount_cad > thresholds.preapproval_threshold_cad
    has_pending_preapproval = evidence_facts.preapproval_status == "requested"
    is_excluded_non_expense = (
        transaction_facts.transaction_eligibility == "excluded_non_expense"
        or transaction_facts.debit_credit == "credit"
        or transaction_facts.amount_cad <= 0
    )
    requires_finance_review = transaction_facts.transaction_eligibility == "finance_review"

    return DerivedFacts(
        requires_preapproval=requires_preapproval,
        has_pending_preapproval=has_pending_preapproval,
        missing_preapproval=requires_preapproval and evidence_facts.preapproval_status in {None, "missing", "denied"},
        receipt_explicitly_missing=evidence_facts.receipt_status in {"missing", "rejected"},
        receipt_evidence_unavailable=evidence_facts.receipt_status in {None, "unavailable"},
        has_receipt_evidence=evidence_facts.receipt_status in {"submitted", "approved"},
        receipt_sensitive_category=is_receipt_sensitive_category(transaction_facts.category),
        is_high_value=transaction_facts.amount_cad >= thresholds.high_value_threshold_cad,
        is_critical_value=transaction_facts.amount_cad >= thresholds.critical_value_threshold_cad,
        is_excluded_non_expense=is_excluded_non_expense,
        requires_finance_review=requires_finance_review,
        skips_normal_expense_rules=is_excluded_non_expense or requires_finance_review,
        is_meal_or_entertainment=is_meal_or_entertainment(transaction_facts.category),
        is_alcohol_category=is_alcohol_category(transaction_facts.category),
        is_ticket_or_fine=is_ticket_or_fine(transaction_facts.category, transaction_facts.search_text),
        is_personal_expense=is_personal_expense(transaction_facts.search_text),
    )


def evaluate_policy(
    transaction: dict[str, Any],
    receipt: dict[str, Any] | None,
    preapproval: dict[str, Any] | None,
    rules: Sequence[ConfigurablePolicyRule] | None = None,
) -> PolicyCheckResult:
    from app.services.rule_evaluator import evaluate_configurable_rule

    base_thresholds = policy_thresholds_from_rules(rules or [], transaction)
    context = build_policy_context(transaction, receipt, preapproval, thresholds=base_thresholds)
    matched_outcomes: list[ConfigurableRuleOutcome] = []

    for rule in rules or []:
        rule_context = build_policy_context(
            transaction,
            receipt,
            preapproval,
            thresholds=policy_thresholds_for_rule(rule, transaction, base_thresholds),
        )
        outcome = evaluate_configurable_rule(rule, rule_context)
        if outcome.violations or outcome.missing_information or outcome.status:
            matched_outcomes.append(outcome)

    violations = dedupe_policy_violations(
        [violation for outcome in matched_outcomes for violation in outcome.violations]
    )
    missing_information = {
        item
        for outcome in matched_outcomes
        for item in outcome.missing_information
    }
    explicit_statuses = [
        outcome.status
        for outcome in matched_outcomes
        if outcome.status is not None
    ]
    status = choose_status(violations, missing_information, explicit_statuses, context)

    return PolicyCheckResult(
        transaction_id=context.transaction_id,
        status=status,
        max_severity=max_severity([violation.severity for violation in violations]),
        severity_score=calculate_severity_score(violations, context),
        scan_version=ENGINE_VERSION,
        violations=violations,
        missing_information=sorted(missing_information),
        recommended_next_action=recommended_action(status, violations),
    )


def policy_thresholds_from_rules(
    rules: Sequence[ConfigurablePolicyRule],
    transaction: dict[str, Any] | None = None,
    fallback: PolicyThresholds | None = None,
) -> PolicyThresholds:
    thresholds = fallback or PolicyThresholds()
    scoped_rules = [
        rule
        for rule in rules
        if transaction is None or rule_matches_transaction_scope(rule, transaction, thresholds)
    ]
    preapproval_values = [
        value
        for rule in scoped_rules
        for value in [
            resolved_rule_threshold_value(rule, "preapproval_threshold_cad", transaction),
            inferred_amount_threshold(rule, {"missing_preapproval", "requires_preapproval", "has_pending_preapproval"}),
        ]
        if value is not None
    ]
    meal_values = [
        value
        for rule in scoped_rules
        for value in [
            resolved_rule_threshold_value(rule, "meal_context_threshold_cad", transaction),
            inferred_amount_threshold(rule, {"has_guest_names", "has_business_purpose", "is_meal_or_entertainment"}),
        ]
        if value is not None
    ]
    high_values = [
        value
        for rule in scoped_rules
        if (value := resolved_rule_threshold_value(rule, "high_value_threshold_cad", transaction)) is not None
    ]
    critical_values = [
        value
        for rule in scoped_rules
        if (value := resolved_rule_threshold_value(rule, "critical_value_threshold_cad", transaction)) is not None
    ]
    repeat_values = [
        value
        for rule in scoped_rules
        if (value := resolved_rule_threshold_value(rule, "repeat_violation_threshold", transaction)) is not None
    ]

    return PolicyThresholds(
        preapproval_threshold_cad=min(preapproval_values) if preapproval_values else thresholds.preapproval_threshold_cad,
        high_value_threshold_cad=min(high_values) if high_values else thresholds.high_value_threshold_cad,
        critical_value_threshold_cad=min(critical_values) if critical_values else thresholds.critical_value_threshold_cad,
        repeat_violation_threshold=int(min(repeat_values)) if repeat_values else thresholds.repeat_violation_threshold,
        meal_context_threshold_cad=min(meal_values) if meal_values else thresholds.meal_context_threshold_cad,
    )


def rule_matches_transaction_scope(
    rule: ConfigurablePolicyRule,
    transaction: dict[str, Any],
    thresholds: PolicyThresholds,
) -> bool:
    from app.services.rule_evaluator import applies_to_matches, scope_matches

    context = build_policy_context(
        transaction,
        {"status": "unavailable", "synthetic": True},
        {"status": "not_required", "synthetic": True},
        thresholds=thresholds,
    )
    return scope_matches(getattr(rule, "scope", {}) or {}, context) and applies_to_matches(
        getattr(rule, "applies_to", {}) or {},
        context,
    )


def policy_thresholds_for_rule(
    rule: ConfigurablePolicyRule,
    transaction: dict[str, Any],
    fallback: PolicyThresholds | None = None,
) -> PolicyThresholds:
    return policy_thresholds_from_rules([rule], transaction, fallback)


def resolved_rule_threshold_value(
    rule: ConfigurablePolicyRule,
    threshold_name: str,
    transaction: dict[str, Any] | None,
) -> float | None:
    thresholds = getattr(rule, "thresholds", {}) or {}
    return resolve_threshold_config(thresholds.get(threshold_name), transaction)


def resolve_threshold_config(config: Any, transaction: dict[str, Any] | None) -> float | None:
    if config is None:
        return None
    if isinstance(config, (int, float)):
        return float(config)
    if not isinstance(config, dict):
        return None

    transaction = transaction or {}
    for override_key, transaction_key in (
        ("by_employee", "employee_id"),
        ("employee_overrides", "employee_id"),
        ("by_department", "department_id"),
        ("department_overrides", "department_id"),
        ("by_role", "employee_role"),
        ("role_overrides", "employee_role"),
    ):
        override = threshold_override_value(config.get(override_key), transaction.get(transaction_key))
        if override is not None:
            return override

    period_value = threshold_period_value(config.get("by_period") or config.get("periods"), transaction.get("transaction_date"))
    if period_value is not None:
        return period_value

    return to_optional_float(config.get("value", config.get("default")))


def threshold_override_value(overrides: Any, key: Any) -> float | None:
    normalized_key = str(key or "").strip()
    if not normalized_key or not overrides:
        return None
    if isinstance(overrides, dict):
        return to_optional_float(overrides.get(normalized_key))
    if isinstance(overrides, list):
        for item in overrides:
            if not isinstance(item, dict):
                continue
            item_key = str(item.get("key") or item.get("id") or item.get("name") or "").strip()
            if item_key == normalized_key:
                return to_optional_float(item.get("value") or item.get("threshold"))
    return None


def threshold_period_value(periods: Any, transaction_date: Any) -> float | None:
    if not isinstance(periods, list) or not transaction_date:
        return None
    date_value = str(transaction_date)[:10]
    for period in periods:
        if not isinstance(period, dict):
            continue
        start = str(period.get("start") or period.get("date_start") or "")[:10]
        end = str(period.get("end") or period.get("date_end") or "")[:10]
        if start and date_value < start:
            continue
        if end and date_value > end:
            continue
        value = to_optional_float(period.get("value") or period.get("threshold"))
        if value is not None:
            return value
    return None


def inferred_amount_threshold(rule: ConfigurablePolicyRule, evidence_fields: set[str]) -> float | None:
    condition = getattr(rule, "condition", {}) or {}
    fields = collect_condition_fields(condition)
    if "amount_cad" not in fields or not (fields & evidence_fields):
        return None
    values = collect_amount_threshold_literals(condition)
    return min(values) if values else None


def collect_amount_threshold_literals(condition: Any) -> list[float]:
    if not isinstance(condition, dict):
        return []
    values: list[float] = []
    if condition.get("field") == "amount_cad" and condition.get("operator") in {"gt", "gte"}:
        value = condition.get("value")
        if not isinstance(value, dict):
            threshold = to_optional_float(value)
            if threshold is not None:
                values.append(threshold)
    for key in ("all", "any"):
        children = condition.get(key)
        if isinstance(children, list):
            for child in children:
                values.extend(collect_amount_threshold_literals(child))
    if isinstance(condition.get("not"), dict):
        values.extend(collect_amount_threshold_literals(condition["not"]))
    return values


def collect_condition_fields(condition: Any) -> set[str]:
    if not isinstance(condition, dict):
        return set()
    fields = {str(condition["field"])} if isinstance(condition.get("field"), str) else set()
    for key in ("all", "any"):
        children = condition.get(key)
        if isinstance(children, list):
            for child in children:
                fields.update(collect_condition_fields(child))
    if isinstance(condition.get("not"), dict):
        fields.update(collect_condition_fields(condition["not"]))
    return fields


def to_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dedupe_policy_violations(
    violations: list[PolicyViolation],
    context: PolicyContext | None = None,
) -> list[PolicyViolation]:
    del context

    unique_by_code: dict[str, PolicyViolation] = {}
    for violation in violations:
        existing = unique_by_code.get(violation.rule_code)
        if not existing or SEVERITY_RANK[violation.severity] > SEVERITY_RANK[existing.severity]:
            unique_by_code[violation.rule_code] = violation

    return sorted(
        unique_by_code.values(),
        key=lambda violation: (SEVERITY_RANK[violation.severity], violation.rule_code),
        reverse=True,
    )


def max_severity(severities: list[Severity]) -> Severity:
    if not severities:
        return "low"

    return max(severities, key=lambda severity: SEVERITY_RANK[severity])


def calculate_severity_score(violations: list[PolicyViolation], context: PolicyContext) -> int:
    if not violations:
        return 0

    score = max(SEVERITY_POINTS[violation.severity] for violation in violations)
    score += min(30, max(0, len(violations) - 1) * 8)
    if context.is_high_value:
        score += 10
    if context.is_critical_value:
        score += 10

    return min(score, 100)


def choose_status(
    violations: list[PolicyViolation],
    missing_information: set[str],
    explicit_statuses: Sequence[PolicyStatus],
    context: PolicyContext,
) -> PolicyStatus:
    candidate_statuses: list[PolicyStatus] = []

    if context.is_excluded_non_expense:
        candidate_statuses.append("excluded_non_expense")
    elif context.requires_finance_review:
        candidate_statuses.append("review_required")
    else:
        candidate_statuses.append("compliant")

    candidate_statuses.extend(explicit_statuses)
    if missing_information:
        candidate_statuses.append("context_needed")
    elif violations and not explicit_statuses:
        candidate_statuses.append("review_required")

    return max(candidate_statuses, key=lambda status: STATUS_PRIORITY[status])


def recommended_action(status: PolicyStatus, violations: list[PolicyViolation]) -> str:
    if violations:
        return max(
            violations,
            key=lambda violation: (SEVERITY_RANK[violation.severity], violation.rule_code),
        ).required_action

    actions: dict[PolicyStatus, str] = {
        "compliant": "No policy action required.",
        "excluded_non_expense": "Exclude this credit or non-expense item from reimbursement review.",
        "review_required": "Route this transaction to finance review.",
        "context_needed": "Collect the missing business context before deciding compliance.",
        "approval_evidence_needed": "Collect or document the required approval evidence before approval.",
        "policy_violation": "Do not reimburse until finance reviews and resolves the violation.",
    }
    return actions[status]


def infer_policy_category(transaction: dict[str, Any]) -> str:
    enriched_policy_category = str(transaction.get("policy_category") or "").strip()
    if enriched_policy_category:
        return enriched_policy_category

    search_text = transaction_search_text(transaction)
    merchant = str(transaction.get("normalized_merchant_name") or transaction.get("merchant_name") or "").upper()
    source_category = str(transaction.get("source_category") or "").upper()
    mcc = str(transaction.get("merchant_category_code") or "").strip()
    business_category = finance_category(transaction)

    if contains_any(search_text, PERMIT_KEYWORDS) or mcc == "9399":
        return "Permits / Government Fees"
    if "AVETTA" in search_text:
        return "Vendor / Compliance"
    if contains_any(merchant, ["UBER", "LYFT", "TAXI"]):
        return "Ground Transportation"
    if contains_any(merchant, ["ENTERPRISE", "NATIONAL CAR", "HERTZ", "AVIS", "BUDGET RENT A CAR"]):
        return "Car / Truck Rental"
    if "TRUCKPARKINGCLUB" in search_text:
        return "Parking / Tolls"
    if source_category == "FUEL" or business_category == "Fuel":
        return "Fuel"

    return business_category or "Uncategorized"


def transaction_search_text(transaction: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in [
            transaction.get("description"),
            transaction.get("merchant_name"),
            transaction.get("normalized_merchant_name"),
            transaction.get("source_category"),
            transaction.get("business_category"),
            transaction.get("normalized_category"),
            transaction.get("policy_category"),
            transaction.get("transaction_type"),
            transaction.get("transaction_eligibility"),
        ]
        if value
    ).upper()


def finance_category(transaction: dict[str, Any]) -> str:
    return str(transaction.get("business_category") or transaction.get("normalized_category") or "")


def skips_expense_evidence(transaction: dict[str, Any]) -> bool:
    amount_cad = to_float(transaction.get("amount_cad"))
    debit_credit = str(transaction.get("debit_credit") or "").lower()
    transaction_eligibility = str(transaction.get("transaction_eligibility") or "")

    return (
        transaction_eligibility in {"excluded_non_expense", "finance_review"}
        or debit_credit == "credit"
        or amount_cad <= 0
    )


def transaction_context_fields(transaction: dict[str, Any], category: str) -> dict[str, Any]:
    debit_credit = str(transaction.get("debit_credit") or "").lower() or None
    amount_cad = to_float(transaction.get("amount_cad"))
    transaction_eligibility = str(transaction.get("transaction_eligibility") or "") or None
    transaction_type = str(transaction.get("transaction_type") or "") or None
    business_category = finance_category(transaction)
    policy_category = str(transaction.get("policy_category") or category or "").strip() or None
    normalized_category = str(transaction.get("normalized_category") or "") or None

    return {
        "amount_cad": amount_cad,
        "merchant_raw": transaction.get("merchant_name"),
        "merchant_normalized": transaction.get("normalized_merchant_name") or transaction.get("merchant_name"),
        "normalized_merchant_family": transaction.get("normalized_merchant_family"),
        "transaction_code": transaction.get("transaction_code"),
        "transaction_type": transaction_type,
        "transaction_eligibility": transaction_eligibility,
        "network_category_code": transaction.get("network_category_code"),
        "business_category": business_category,
        "normalized_category": normalized_category,
        "policy_category": policy_category,
        "category": category,
        "department_id": str(transaction.get("department_id") or "") or None,
        "department_name": transaction.get("department_name"),
        "employee_id": str(transaction.get("employee_id") or "") or None,
        "employee_name": transaction.get("employee_name"),
        "employee_role": transaction.get("employee_role"),
        "transaction_date": transaction.get("transaction_date"),
        "posting_date": transaction.get("posting_date"),
        "posting_delay_days": transaction.get("posting_delay_days"),
        "merchant_country": transaction.get("merchant_country"),
        "merchant_state_province": transaction.get("merchant_state_province"),
        "merchant_postal_code": transaction.get("merchant_postal_code"),
        "mcc": str(transaction.get("merchant_category_code") or transaction.get("mcc") or "").strip() or None,
        "mcc_description": transaction.get("mcc_description"),
        "debit_or_credit": debit_credit,
        "debit_credit": debit_credit,
        "category_confidence": transaction.get("category_confidence"),
        "category_source": transaction.get("category_source"),
        "is_foreign_transaction": bool(transaction.get("is_foreign_transaction")),
        "is_weekend": is_weekend(transaction.get("transaction_date")),
        "is_account_activity": bool(transaction.get("is_account_activity") or transaction_type == "account_payment"),
        "is_credit_or_refund": bool(transaction.get("is_credit_or_refund") or debit_credit == "credit" or amount_cad <= 0),
        "is_low_confidence_category": bool(
            transaction.get("is_low_confidence_category")
            or to_float(transaction.get("category_confidence")) < 0.5
        ),
        "is_uncategorized": category in {"", "Uncategorized"} or business_category == "Uncategorized",
        "search_text": transaction_search_text(transaction),
    }


def is_weekend(value: Any) -> bool:
    if not value:
        return False
    try:
        return datetime.fromisoformat(str(value)[:10]).weekday() >= 5
    except ValueError:
        return False


def receipt_submitted_in_transaction_month(transaction: dict[str, Any], receipt: dict[str, Any]) -> bool:
    transaction_date = transaction.get("transaction_date")
    submitted_at = receipt.get("submitted_at") or receipt.get("receipt_date")
    if not transaction_date or not submitted_at:
        return True
    return str(transaction_date)[:7] == str(submitted_at)[:7]


def is_receipt_sensitive_category(category: str) -> bool:
    return category in {
        "Fuel",
        "Car Rental",
        "Car / Truck Rental",
        "Vehicle Maintenance",
        "Transportation / Fleet / Operations",
        "Parking / Tolls",
        "Parking",
        "Tolls / Road Fees",
        "Ground Transportation",
    }


def is_meal_or_entertainment(category: str) -> bool:
    return category in {"Meals / Entertainment", "Meals"}


def is_alcohol_category(category: str) -> bool:
    return category == "Alcohol / Restricted"


def is_ticket_or_fine(category: str, text: str) -> bool:
    return category == "Non-Reimbursable Fine" or any(token in text for token in [" TICKET", " FINE", " VIOLATION"])


def is_personal_expense(text: str) -> bool:
    return any(token in text for token in ["PERSONAL", "GIFT CARD", "CLOTHING", "SHOE", "SOFTMOC"])


def contains_any(value: str, keywords: list[str]) -> bool:
    return any(keyword in value for keyword in keywords)


def to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
