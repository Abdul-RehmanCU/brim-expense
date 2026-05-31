from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from time import perf_counter
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from app.database.supabase_client import get_supabase_client
from app.schemas.common import PlaceholderResponse
from app.schemas.risk import RiskScanRequest, RiskScanSummary, RiskScoreItem, RiskSignal
from app.services.policy_engine import NO_CONFIGURED_MONEY_THRESHOLD, policy_thresholds_from_rules
from app.services.rule_evaluator import ConfigurablePolicyRule

ENGINE_VERSION = "risk-engine-v1"
PAGE_SIZE = 1000
QUERY_CHUNK_SIZE = 100
ISOLATION_FOREST_MIN_ROWS = 20
TARGET_OUTLIER_COUNT = 50
NEAR_DUPLICATE_AMOUNT_TOLERANCE_CAD = 0.5
NEAR_DUPLICATE_DATE_WINDOW_DAYS = 0
HIGH_POSTING_DELAY_DAYS = 30
MEDIUM_POSTING_DELAY_DAYS = 10
MISSING_VALUES = {"", "none", "null", "nan", "n/a", "na"}
WEAK_CATEGORY_VALUES = {"uncategorized", "unknown", "other", "misc", "miscellaneous"}
WEAK_CATEGORY_SOURCES = {"fallback", "unknown", "unmapped", "default"}
CASH_PATTERN_TERMS = ("atm", "cash advance", "cash withdrawal", "cash disbursement")
FOCUSED_DETECTOR_PROFILE = "focused"
FULL_DETECTOR_PROFILE = "full"
FOCUSED_ROW_SIGNAL_TYPES = frozenset(
    {
        "cash_atm_pattern",
        "missing_merchant_compliance_metadata",
        "posting_lag_outlier",
        "fx_inconsistency",
    }
)

SEVERITY_POINTS = {"low": 12, "medium": 28, "high": 48, "critical": 68}
RISK_LEVELS = ((80, "critical"), (60, "high"), (35, "medium"), (0, "low"))
RISK_FEATURE_LABELS = {
    "log_amount": "large absolute amount",
    "employee_amount_ratio": "unusual amount for this employee",
    "merchant_amount_ratio": "unusual amount for this merchant",
    "category_amount_ratio": "unusual amount for this category",
    "department_category_amount_ratio": "unusual amount for this department/category",
    "merchant_rarity": "rare merchant in the dataset",
    "employee_merchant_rarity": "rare merchant for this employee",
    "near_approval_threshold": "amount just below the approval threshold",
    "round_amount": "large round-number amount",
    "weekend": "weekend transaction timing",
    "day_of_month": "unusual day-of-month timing",
}
MERCHANT_AMOUNT_OUTLIER_MIN_PRIOR_TRANSACTIONS = 5
MERCHANT_AMOUNT_OUTLIER_MIN_AMOUNT_CAD = 250
MERCHANT_AMOUNT_OUTLIER_MEDIAN_MULTIPLIER = 3.0
MERCHANT_AMOUNT_OUTLIER_MAX_MULTIPLIER = 1.15
FIRST_TIME_HIGH_VALUE_EMPLOYEE_HISTORY_MIN_TRANSACTIONS = 5
FIRST_TIME_HIGH_VALUE_EMPLOYEE_MEDIAN_MULTIPLIER = 2.0
FIRST_TIME_HIGH_VALUE_UNCATEGORIZED_MIN_AMOUNT_CAD = 1000
FIRST_TIME_HIGH_VALUE_EXCLUDED_CATEGORIES = frozenset({"fuel", "cash advance / atm withdrawal"})
MERCHANT_NOVELTY_IGNORED_TOKENS = frozenset(
    {
        "INSIDE",
        "OUTSIDE",
        "TRAVEL",
        "CENTER",
        "CTR",
        "PLAZA",
        "STORE",
        "STOP",
        "SERVICES",
        "SERVICE",
        "FUEL",
        "TRAVELCENTER",
    }
)


class ReusableRiskDetector:
    signal_type: str

    def detect(self, transaction: dict[str, Any], amount_cad: float) -> RiskSignal | None:
        raise NotImplementedError


class CashAtmPatternDetector(ReusableRiskDetector):
    signal_type = "cash_atm_pattern"
    fields = (
        "merchant_name",
        "normalized_merchant_name",
        "normalized_merchant_family",
        "business_category",
        "policy_category",
        "normalized_category",
        "source_category",
        "transaction_type",
        "transaction_description",
        "description",
    )

    def detect(self, transaction: dict[str, Any], amount_cad: float) -> RiskSignal | None:
        if is_admin_fee_or_excluded_non_expense(transaction):
            return None

        matched = text_matches(transaction, self.fields, CASH_PATTERN_TERMS)
        cash_category = any(
            normalized_text(transaction.get(field)) == "cash"
            for field in ("business_category", "policy_category", "normalized_category", "source_category", "transaction_type")
        )
        if not matched and not cash_category:
            return None

        return RiskSignal(
            type=self.signal_type,
            severity="medium",
            message="Transaction has cash or ATM-like indicators that are harder to substantiate than card purchases.",
            evidence={
                "amount_cad": amount_cad,
                "matched_fields": matched,
                "cash_category_match": cash_category,
            },
        )


class MissingMetadataDetector(ReusableRiskDetector):
    signal_type = "missing_merchant_compliance_metadata"
    merchant_fields = ("merchant_name", "normalized_merchant_name", "normalized_merchant_family")
    metadata_fields = (
        "merchant_category_code",
        "merchant_country",
        "merchant_region",
        "transaction_eligibility",
        "business_category",
        "policy_category",
        "normalized_category",
    )

    def detect(self, transaction: dict[str, Any], amount_cad: float) -> RiskSignal | None:
        del amount_cad
        if is_admin_fee_or_excluded_non_expense(transaction):
            return None

        missing_fields: list[str] = []
        merchant_field_present = any(field in transaction for field in self.merchant_fields)
        if merchant_field_present and all(is_blank(transaction.get(field)) for field in self.merchant_fields):
            missing_fields.append("merchant")

        missing_fields.extend(
            field
            for field in self.metadata_fields
            if field in transaction and is_blank(transaction.get(field))
        )
        if not missing_fields:
            return None

        severity = "high" if "merchant" in missing_fields else "medium"
        return RiskSignal(
            type=self.signal_type,
            severity=severity,
            message="Transaction is missing merchant or compliance metadata used for policy and review context.",
            evidence={"missing_fields": sorted(set(missing_fields))},
        )


class WeakCategorizationDetector(ReusableRiskDetector):
    signal_type = "weak_categorization"

    def detect(self, transaction: dict[str, Any], amount_cad: float) -> RiskSignal | None:
        del amount_cad
        category = first_present(transaction, ("business_category", "policy_category", "normalized_category", "source_category"))
        category_source = normalized_text(transaction.get("category_source"))
        confidence = parse_amount(transaction.get("category_confidence"))
        reasons: list[str] = []

        if category is not None and normalized_text(category) in WEAK_CATEGORY_VALUES:
            reasons.append("generic_category")
        if category_source in WEAK_CATEGORY_SOURCES:
            reasons.append("weak_category_source")
        if confidence is not None and confidence < 0.5:
            reasons.append("low_category_confidence")
        if not reasons:
            return None

        return RiskSignal(
            type=self.signal_type,
            severity="low",
            message="Category assignment is weak, generic, or low-confidence.",
            evidence={
                "category": category,
                "category_source": transaction.get("category_source"),
                "category_confidence": confidence,
                "reasons": reasons,
            },
        )


class FxInconsistencyDetector(ReusableRiskDetector):
    signal_type = "fx_inconsistency"

    def detect(self, transaction: dict[str, Any], amount_cad: float) -> RiskSignal | None:
        conversion_rate = parse_amount(transaction.get("conversion_rate"))
        amount_original = parse_amount(transaction.get("amount_original"))
        original_currency = first_present(transaction, ("original_currency", "currency_original", "transaction_currency", "currency"))
        merchant_country = normalized_text(transaction.get("merchant_country")).upper()
        is_foreign = bool(transaction.get("is_foreign_transaction")) or bool(
            merchant_country and merchant_country not in {"CA", "CAN", "CANADA"}
        )

        if is_foreign and (conversion_rate is None or conversion_rate <= 0):
            return RiskSignal(
                type=self.signal_type,
                severity="high",
                message="Foreign or non-local transaction is missing a usable FX conversion rate.",
                evidence={
                    "amount_cad": amount_cad,
                    "amount_original": amount_original,
                    "conversion_rate": transaction.get("conversion_rate"),
                    "currency": original_currency,
                    "merchant_country": transaction.get("merchant_country"),
                },
            )

        if conversion_rate is None or amount_original is None:
            return None
        expected_cad = round(abs(amount_original * conversion_rate), 2)
        actual_cad = round(abs(amount_cad), 2)
        difference = round(abs(expected_cad - actual_cad), 2)
        if difference <= 0.02:
            return None

        return RiskSignal(
            type=self.signal_type,
            severity="medium",
            message="CAD amount does not reconcile with original amount and FX conversion rate.",
            evidence={
                "amount_cad": actual_cad,
                "amount_original": amount_original,
                "conversion_rate": conversion_rate,
                "expected_amount_cad": expected_cad,
                "difference_cad": difference,
                "currency": original_currency,
            },
        )


class PostingLagOutlierDetector(ReusableRiskDetector):
    signal_type = "posting_lag_outlier"

    def detect(self, transaction: dict[str, Any], amount_cad: float) -> RiskSignal | None:
        del amount_cad
        delay = parse_int(transaction.get("posting_delay_days"))
        transaction_date = parse_date(transaction.get("transaction_date"))
        posting_date = parse_date(transaction.get("posting_date"))
        if delay is None and transaction_date and posting_date:
            delay = (posting_date - transaction_date).days
        if delay is None:
            return None
        if delay < 0:
            return RiskSignal(
                type=self.signal_type,
                severity="high",
                message="Posting date is earlier than transaction date.",
                evidence={
                    "posting_delay_days": delay,
                    "transaction_date": transaction.get("transaction_date"),
                    "posting_date": transaction.get("posting_date"),
                },
            )
        if delay > HIGH_POSTING_DELAY_DAYS:
            severity = "high"
        elif delay > MEDIUM_POSTING_DELAY_DAYS:
            severity = "medium"
        else:
            return None

        return RiskSignal(
            type=self.signal_type,
            severity=severity,
            message="Transaction posted materially later than its transaction date.",
            evidence={
                "posting_delay_days": delay,
                "transaction_date": transaction.get("transaction_date"),
                "posting_date": transaction.get("posting_date"),
            },
        )


GENERIC_ROW_DETECTORS: tuple[ReusableRiskDetector, ...] = (
    CashAtmPatternDetector(),
    MissingMetadataDetector(),
    WeakCategorizationDetector(),
    FxInconsistencyDetector(),
    PostingLagOutlierDetector(),
)


def get_risk_status() -> PlaceholderResponse:
    return PlaceholderResponse(
        status="ok",
        service="risk",
        implemented=True,
        message="Deterministic risk scoring is available.",
    )


def scan_risk(request: RiskScanRequest | None = None) -> RiskScanSummary:
    return scan_risk_scores(request)


def scan_risk_scores(request: RiskScanRequest | None = None) -> RiskScanSummary:
    request = request or RiskScanRequest()
    started = perf_counter()
    transactions = fetch_transactions(request)
    policy_by_transaction = fetch_latest_policy_checks([row["id"] for row in transactions])
    violations = fetch_open_violations([row["id"] for row in transactions])
    scores = build_risk_scores(
        transactions,
        policy_checks_by_transaction_id=policy_by_transaction,
        violations=violations,
        split_window_days=request.split_window_days,
        anomaly_model=request.anomaly_model,
        detector_profile=request.detector_profile,
    )
    scored_rows = [
        {
            "transaction_id": score.transaction_id,
            "risk_score": score.risk_score,
            "risk_level": score.risk_level,
            "signals": [signal.model_dump() for signal in score.signals],
            "engine_version": ENGINE_VERSION,
        }
        for score in scores
    ]
    signal_counts: Counter[str] = Counter(signal.type for score in scores for signal in score.signals)
    high_or_critical = sum(1 for score in scores if score.risk_level in {"high", "critical"})

    persisted = 0
    if not request.dry_run:
        if request.reset_existing:
            delete_existing_scores([row["id"] for row in transactions])
        persisted = persist_scores(scored_rows)

    return RiskScanSummary(
        total_scanned=len(transactions),
        scored=len(scored_rows),
        persisted=persisted,
        high_or_critical=high_or_critical,
        signal_counts=dict(sorted(signal_counts.items())),
        duration_ms=int((perf_counter() - started) * 1000),
        engine_version=ENGINE_VERSION,
        dry_run=request.dry_run,
    )


def list_risk_scores(
    min_level: str = "medium",
    limit: int = 100,
    signal_type: str | None = None,
    department_id: str | None = None,
    employee_id: str | None = None,
) -> list[RiskScoreItem]:
    del department_id, employee_id

    query = (
        get_supabase_client()
        .table("risk_scores")
        .select("*")
        .order("risk_score", desc=True)
        .order("scored_at", desc=True)
        .limit(max(1, min(limit, 500)))
    )
    scores = query.execute().data or []
    allowed_levels = levels_at_or_above(min_level)
    scores = [score for score in scores if score.get("risk_level") in allowed_levels]
    if signal_type:
        scores = [
            score
            for score in scores
            if any(signal.get("type") == signal_type for signal in score.get("signals") or [])
        ]
    if not scores:
        return []

    transactions = fetch_by_ids("transactions", unique_ids(score.get("transaction_id") for score in scores))
    employees = fetch_by_ids("employees", unique_ids(row.get("employee_id") for row in transactions))
    departments = fetch_by_ids("departments", unique_ids(row.get("department_id") for row in transactions))
    transactions_by_id = {row["id"]: row for row in transactions}
    employees_by_id = {row["id"]: row for row in employees}
    departments_by_id = {row["id"]: row for row in departments}

    items: list[RiskScoreItem] = []
    for score in scores:
        transaction = transactions_by_id.get(score.get("transaction_id"), {})
        employee = employees_by_id.get(transaction.get("employee_id") or "")
        department = departments_by_id.get(transaction.get("department_id") or "")
        items.append(
            RiskScoreItem(
                id=score.get("id"),
                transaction_id=score["transaction_id"],
                risk_score=int(score.get("risk_score") or 0),
                risk_level=score.get("risk_level") or "low",
                signals=[RiskSignal(**signal) for signal in score.get("signals") or []],
                scored_at=score.get("scored_at"),
                engine_version=score.get("engine_version"),
                employee=employee.get("full_name") if employee else None,
                department=department.get("name") if department else None,
                transaction_date=transaction.get("transaction_date"),
                merchant=transaction.get("normalized_merchant_name") or transaction.get("merchant_name"),
                amount_cad=float(transaction.get("amount_cad") or 0),
                category=transaction.get("business_category")
                or transaction.get("policy_category")
                or transaction.get("normalized_category")
                or "Uncategorized",
            )
        )
    return items


def build_risk_scores(
    transactions: list[dict[str, Any]],
    policy_checks_by_transaction_id: dict[str, dict[str, Any]] | None = None,
    violations: list[dict[str, Any]] | None = None,
    split_window_days: int = 0,
    anomaly_model: str = "auto",
    detector_profile: str = FOCUSED_DETECTOR_PROFILE,
) -> list[RiskScoreItem]:
    request = RiskScanRequest(
        split_window_days=split_window_days,
        anomaly_model=anomaly_model,
        detector_profile=detector_profile,
    )
    active_rules = load_active_risk_policy_rules()
    approval_threshold = resolved_policy_approval_threshold(transactions, active_rules)
    policy_by_transaction = policy_checks_by_transaction_id or {}
    violation_counts = Counter(str(row.get("transaction_id")) for row in violations or [] if row.get("transaction_id"))
    peer_context = build_peer_context(transactions) if uses_full_risk_profile(request) else {}
    grouped_signals_by_transaction_id = build_grouped_duplicate_signals(transactions)
    merge_signal_maps(
        grouped_signals_by_transaction_id,
        build_grouped_split_signals(
            transactions,
            split_threshold_cad=approval_threshold,
            split_window_days=request.split_window_days,
        ),
    )
    ml_signals_by_transaction_id = (
        build_isolation_forest_signals(
            transactions,
            approval_threshold,
            preferred_model=request.anomaly_model,
        )
        if uses_full_risk_profile(request)
        else {}
    )
    scores: list[RiskScoreItem] = []

    for transaction in transactions:
        transaction_id = str(transaction.get("id"))
        signals = score_transaction(transaction, policy_by_transaction, peer_context, request, approval_threshold)
        signals.extend(grouped_signals_by_transaction_id.get(transaction_id, []))
        signals.extend(ml_signals_by_transaction_id.get(str(transaction.get("id")), []))
        if uses_full_risk_profile(request) and violation_counts.get(str(transaction.get("id"))) and not any(
            signal.type == "policy_risk_overlap" for signal in signals
        ):
            signals.append(
                RiskSignal(
                    type="policy_risk_overlap",
                    severity="high",
                    message="Open policy violations exist for this transaction.",
                    evidence={"open_violation_count": violation_counts[str(transaction.get("id"))]},
                )
            )
        risk_score = min(100, sum(SEVERITY_POINTS[signal.severity] for signal in signals))
        scores.append(
            RiskScoreItem(
                transaction_id=str(transaction["id"]),
                risk_score=risk_score,
                risk_level=risk_level_for_score(risk_score),
                signals=signals,
                engine_version=ENGINE_VERSION,
                transaction_date=transaction.get("transaction_date"),
                merchant=transaction.get("normalized_merchant_name") or transaction.get("merchant_name"),
                amount_cad=float(transaction.get("amount_cad") or 0),
                category=transaction.get("business_category")
                or transaction.get("policy_category")
                or transaction.get("normalized_category")
                or "Uncategorized",
            )
        )
    return scores


def score_transaction(
    transaction: dict[str, Any],
    policy_by_transaction: dict[str, dict[str, Any]],
    peer_context: dict[str, Any],
    request: RiskScanRequest,
    approval_threshold_cad: float,
) -> list[RiskSignal]:
    amount = abs(float(transaction.get("amount_cad") or 0))
    if transaction.get("debit_credit") == "credit" or amount <= 0 or is_admin_fee_or_excluded_non_expense(transaction):
        return []

    signals: list[RiskSignal] = []
    signals.extend(detect_generic_row_risks(transaction, amount, request.detector_profile))

    if not uses_full_risk_profile(request):
        return signals

    transaction_id = str(transaction.get("id"))
    employee_id = transaction.get("employee_id")
    merchant = normalized_merchant(transaction)
    category = transaction.get("business_category") or transaction.get("policy_category") or transaction.get("normalized_category")

    merchant_prior_stats = peer_context["merchant_prior_amount_stats"].get(transaction_id)
    if merchant_prior_stats and merchant_prior_stats["count"] >= MERCHANT_AMOUNT_OUTLIER_MIN_PRIOR_TRANSACTIONS:
        prior_median = merchant_prior_stats["median_amount_cad"]
        prior_max = merchant_prior_stats["max_amount_cad"]
        median_ratio = safe_ratio(amount, prior_median)
        max_ratio = safe_ratio(amount, prior_max)
        merchant_outlier_floor = max(
            MERCHANT_AMOUNT_OUTLIER_MIN_AMOUNT_CAD,
            prior_median * MERCHANT_AMOUNT_OUTLIER_MEDIAN_MULTIPLIER,
            prior_max * MERCHANT_AMOUNT_OUTLIER_MAX_MULTIPLIER,
        )
        if prior_median > 0 and prior_max > 0 and amount >= merchant_outlier_floor:
            severity = (
                "high"
                if amount >= max(prior_median * 5, prior_max * 1.5, approval_threshold_cad * 2)
                else "medium"
            )
            signals.append(
                RiskSignal(
                    type="merchant_amount_outlier",
                    severity=severity,
                    message="Amount is unusually large for this merchant compared with its prior imported activity.",
                    evidence={
                        "merchant": merchant,
                        "amount_cad": amount,
                        "prior_transaction_count": merchant_prior_stats["count"],
                        "prior_median_amount_cad": round(prior_median, 2),
                        "prior_max_amount_cad": round(prior_max, 2),
                        "amount_ratio_to_prior_median": round(median_ratio, 2),
                        "amount_ratio_to_prior_max": round(max_ratio, 2),
                    },
                )
            )

    merchant_prior_count = peer_context["merchant_novelty_prior_counts"].get(transaction_id, 0)
    employee_amount_median = peer_context["employee_amount_medians"].get(employee_id) or 0.0
    employee_transaction_count = peer_context["employee_transaction_counts"].get(employee_id) or 0
    category_key = normalized_text(category)
    first_time_floor = max(
        approval_threshold_cad,
        employee_amount_median * FIRST_TIME_HIGH_VALUE_EMPLOYEE_MEDIAN_MULTIPLIER
        if employee_transaction_count >= FIRST_TIME_HIGH_VALUE_EMPLOYEE_HISTORY_MIN_TRANSACTIONS and employee_amount_median > 0
        else approval_threshold_cad,
    )
    if category_key in WEAK_CATEGORY_VALUES:
        first_time_floor = max(
            first_time_floor,
            FIRST_TIME_HIGH_VALUE_UNCATEGORIZED_MIN_AMOUNT_CAD,
            employee_amount_median * 3 if employee_transaction_count >= FIRST_TIME_HIGH_VALUE_EMPLOYEE_HISTORY_MIN_TRANSACTIONS else 0,
        )
    if (
        merchant
        and merchant_prior_count == 0
        and amount >= first_time_floor
        and category_key not in FIRST_TIME_HIGH_VALUE_EXCLUDED_CATEGORIES
    ):
        severity = "high" if amount >= max(approval_threshold_cad * 2, employee_amount_median * 3) else "medium"
        signals.append(
            RiskSignal(
                type="first_time_high_value_merchant",
                severity=severity,
                message="First imported charge for this merchant is already high-value relative to policy and employee spend context.",
                evidence={
                    "merchant": merchant,
                    "merchant_novelty_key": merchant_novelty_key(transaction),
                    "amount_cad": amount,
                    "approval_threshold_cad": approval_threshold_cad,
                    "prior_merchant_occurrences": merchant_prior_count,
                    "employee_transaction_count": employee_transaction_count,
                    "employee_median_amount_cad": round(employee_amount_median, 2),
                    "first_time_floor_cad": round(first_time_floor, 2),
                },
            )
        )

    if approval_threshold_cad * 0.8 <= amount <= approval_threshold_cad:
        signals.append(
            RiskSignal(
                type="near_approval_threshold",
                severity="medium",
                message="Transaction sits just below the approval threshold.",
                evidence={"amount_cad": amount, "approval_threshold_cad": approval_threshold_cad},
            )
        )

    if amount >= 100 and amount % 100 == 0:
        signals.append(
            RiskSignal(
                type="round_number_amount",
                severity="medium",
                message="Large round-number transaction may merit a quick review.",
                evidence={"amount_cad": amount},
            )
        )

    employee_merchants = peer_context["employee_merchants"].get(employee_id, set())
    if merchant and len(employee_merchants) >= 5 and merchant not in employee_merchants:
        signals.append(
            RiskSignal(
                type="merchant_novelty_employee",
                severity="medium",
                message="Merchant is unusual for this employee compared with their other imported transactions.",
                evidence={"merchant": merchant, "known_employee_merchants": len(employee_merchants)},
            )
        )

    category_amounts = peer_context["department_category_amounts"].get((transaction.get("department_id"), category), [])
    if len(category_amounts) >= 5:
        average = sum(category_amounts) / len(category_amounts)
        if average > 0 and amount >= average * 3 and amount >= 250:
            signals.append(
                RiskSignal(
                    type="department_category_outlier",
                    severity="medium",
                    message="Amount is materially higher than this department's category average.",
                    evidence={"amount_cad": amount, "department_category_average_cad": round(average, 2)},
                )
            )

    policy_check = policy_by_transaction.get(transaction.get("id"))
    if policy_check and policy_check.get("status") in {"approval_evidence_needed", "policy_violation"}:
        signals.append(
            RiskSignal(
                type="policy_risk_overlap",
                severity="high" if policy_check.get("max_severity") in {"high", "critical"} else "medium",
                message="Latest compliance scan already flagged this transaction.",
                evidence={"policy_status": policy_check.get("status"), "max_severity": policy_check.get("max_severity")},
            )
        )

    return signals


def detect_generic_row_risks(
    transaction: dict[str, Any],
    amount_cad: float,
    detector_profile: str,
) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    for detector in GENERIC_ROW_DETECTORS:
        if detector_profile == FOCUSED_DETECTOR_PROFILE and detector.signal_type not in FOCUSED_ROW_SIGNAL_TYPES:
            continue
        signal = detector.detect(transaction, amount_cad)
        if signal:
            signals.append(signal)
    return signals


def uses_full_risk_profile(request: RiskScanRequest) -> bool:
    return request.detector_profile == FULL_DETECTOR_PROFILE


def build_grouped_duplicate_signals(transactions: list[dict[str, Any]]) -> dict[str, list[RiskSignal]]:
    eligible_transactions = eligible_debit_transactions(transactions)
    signals_by_transaction_id: dict[str, list[RiskSignal]] = defaultdict(list)
    exact_groups: dict[tuple[str, str | None, int], list[dict[str, Any]]] = defaultdict(list)

    for row in eligible_transactions:
        merchant = normalized_merchant(row)
        tx_date = str(row.get("transaction_date") or "")
        if not merchant or not tx_date:
            continue
        exact_groups[(merchant, tx_date, amount_cents(row))].append(row)

    exact_member_ids: set[str] = set()
    for key, rows in exact_groups.items():
        if len(rows) < 2:
            continue
        merchant, tx_date, amount = key
        group_id = deterministic_group_id("duplicate-exact", [str(row["id"]) for row in rows])
        evidence = group_evidence(
            rows,
            group_id=group_id,
            group_type="exact_duplicate",
            extra={
                "merchant": merchant,
                "date": tx_date,
                "amount_cad": round(amount / 100, 2),
                "duplicate_kind": "exact",
            },
        )
        for row in rows:
            exact_member_ids.add(str(row["id"]))
            signals_by_transaction_id[str(row["id"])].append(
                RiskSignal(
                    type="duplicate_charge",
                    severity="high",
                    message="Same merchant, date, and amount appears more than once in the imported transactions.",
                    evidence=evidence,
                )
            )

    near_groups = grouped_near_duplicates(
        [row for row in eligible_transactions if str(row.get("id")) not in exact_member_ids]
    )
    for rows in near_groups:
        group_id = deterministic_group_id("duplicate-near", [str(row["id"]) for row in rows])
        evidence = group_evidence(
            rows,
            group_id=group_id,
            group_type="near_duplicate",
            extra={
                "merchant": normalized_merchant(rows[0]),
                "duplicate_kind": "near",
                "amount_tolerance_cad": NEAR_DUPLICATE_AMOUNT_TOLERANCE_CAD,
                "date_window_days": NEAR_DUPLICATE_DATE_WINDOW_DAYS,
            },
        )
        for row in rows:
            signals_by_transaction_id[str(row["id"])].append(
                RiskSignal(
                    type="duplicate_charge",
                    severity="high",
                    message="Similar charges at the same merchant landed close together and may be duplicates.",
                    evidence=evidence,
                )
            )

    return dict(signals_by_transaction_id)


def grouped_near_duplicates(transactions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    candidates: list[list[dict[str, Any]]] = []
    by_merchant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in transactions:
        if normalized_merchant(row):
            by_merchant[normalized_merchant(row)].append(row)

    for rows in by_merchant.values():
        dated_rows = [row for row in rows if parse_date(row.get("transaction_date"))]
        dated_rows.sort(key=lambda row: (str(row.get("transaction_date")), abs(float(row.get("amount_cad") or 0))))
        for index, row in enumerate(dated_rows):
            window = [
                peer
                for peer in dated_rows[index + 1 :]
                if days_between(peer.get("transaction_date"), row.get("transaction_date")) <= NEAR_DUPLICATE_DATE_WINDOW_DAYS
                and abs(abs(float(peer.get("amount_cad") or 0)) - abs(float(row.get("amount_cad") or 0)))
                <= NEAR_DUPLICATE_AMOUNT_TOLERANCE_CAD
            ]
            if window:
                candidates.append([row, *window])

    return dedupe_group_candidates(candidates)


def build_grouped_split_signals(
    transactions: list[dict[str, Any]],
    *,
    split_threshold_cad: float,
    split_window_days: int,
) -> dict[str, list[RiskSignal]]:
    if split_threshold_cad <= 0 or split_window_days < 0:
        return {}

    by_vendor_category: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible_debit_transactions(transactions):
        amount = abs(float(row.get("amount_cad") or 0))
        merchant = normalized_merchant(row)
        if not merchant or amount <= 0 or amount >= split_threshold_cad or not parse_date(row.get("transaction_date")):
            continue
        by_vendor_category[(merchant, risk_category(row))].append(row)

    candidate_groups: list[list[dict[str, Any]]] = []
    for rows in by_vendor_category.values():
        rows.sort(key=lambda row: (str(row.get("transaction_date")), abs(float(row.get("amount_cad") or 0))))
        if split_window_days == 0:
            rows_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                transaction_date = str(row.get("transaction_date") or "")
                if transaction_date:
                    rows_by_date[transaction_date].append(row)
            for same_day_rows in rows_by_date.values():
                group_sum = sum(abs(float(peer.get("amount_cad") or 0)) for peer in same_day_rows)
                if len(same_day_rows) >= 2 and group_sum > split_threshold_cad:
                    candidate_groups.append(same_day_rows)
            continue

        for row in rows:
            start_date = parse_date(row.get("transaction_date"))
            if not start_date:
                continue
            window_rows = [
                peer
                for peer in rows
                if parse_date(peer.get("transaction_date"))
                and 0 <= (parse_date(peer.get("transaction_date")) - start_date).days <= split_window_days
            ]
            group_sum = sum(abs(float(peer.get("amount_cad") or 0)) for peer in window_rows)
            if len(window_rows) >= 2 and group_sum > split_threshold_cad:
                candidate_groups.append(window_rows)

    signals_by_transaction_id: dict[str, list[RiskSignal]] = defaultdict(list)
    for rows in dedupe_group_candidates(candidate_groups):
        group_sum = round(sum(abs(float(row.get("amount_cad") or 0)) for row in rows), 2)
        group_id = deterministic_group_id("split-threshold", [str(row["id"]) for row in rows])
        evidence = group_evidence(
            rows,
            group_id=group_id,
            group_type="split_threshold",
            extra={
                "merchant": normalized_merchant(rows[0]),
                "category": risk_category(rows[0]),
                "combined_amount_cad": group_sum,
                "split_threshold_cad": split_threshold_cad,
                "window_days": split_window_days,
                "all_individual_charges_below_threshold": all(
                    abs(float(row.get("amount_cad") or 0)) < split_threshold_cad for row in rows
                ),
            },
        )
        for row in rows:
            signals_by_transaction_id[str(row["id"])].append(
                RiskSignal(
                    type="split_transaction_pattern",
                    severity="high",
                    message=(
                        "Charges at the same merchant and category are individually below the split threshold "
                        "but exceed it as a group."
                    ),
                    evidence=evidence,
                )
            )

    return dict(signals_by_transaction_id)


def dedupe_group_candidates(candidates: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    unique: dict[frozenset[str], list[dict[str, Any]]] = {}
    for rows in candidates:
        key = frozenset(str(row.get("id")) for row in rows if row.get("id"))
        if len(key) >= 2:
            unique.setdefault(key, rows)

    selected: list[tuple[frozenset[str], list[dict[str, Any]]]] = []
    for key, rows in sorted(
        unique.items(),
        key=lambda item: (len(item[0]), sum(abs(float(row.get("amount_cad") or 0)) for row in item[1])),
        reverse=True,
    ):
        if any(key < selected_key for selected_key, _rows in selected):
            continue
        selected.append((key, rows))

    return [rows for _key, rows in selected]


def group_evidence(
    rows: list[dict[str, Any]],
    *,
    group_id: str,
    group_type: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transaction_ids = [str(row["id"]) for row in rows]
    evidence = {
        "group_id": group_id,
        "group_type": group_type,
        "group_size": len(rows),
        "transaction_ids": transaction_ids,
        "matched_transaction_ids": transaction_ids,
        "rows": [transaction_evidence(row) for row in rows],
    }
    if extra:
        evidence.update(extra)
    return evidence


def transaction_evidence(row: dict[str, Any]) -> dict[str, Any]:
    raw_transaction = row.get("raw_transactions") if isinstance(row.get("raw_transactions"), dict) else {}
    return {
        "transaction_id": str(row.get("id")),
        "raw_transaction_id": row.get("raw_transaction_id"),
        "source_row_number": row.get("source_row_number") or raw_transaction.get("source_row_number"),
        "source_fingerprint": row.get("source_fingerprint") or raw_transaction.get("source_fingerprint"),
        "employee_id": row.get("employee_id"),
        "merchant": normalized_merchant(row),
        "transaction_date": row.get("transaction_date"),
        "amount_cad": round(abs(float(row.get("amount_cad") or 0)), 2),
        "category": risk_category(row),
    }


def eligible_debit_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in transactions
        if row.get("id")
        and str(row.get("debit_credit") or "").lower() != "credit"
        and abs(float(row.get("amount_cad") or 0)) > 0
        and not is_admin_fee_or_excluded_non_expense(row)
    ]


def is_admin_fee_or_excluded_non_expense(transaction: dict[str, Any]) -> bool:
    transaction_type = normalized_text(transaction.get("transaction_type"))
    return normalized_text(transaction.get("transaction_eligibility")) == "excluded_non_expense" or transaction_type in {
        "card_fee",
        "card_fee_interest",
        "cash_advance_fee",
        "cash_advance_interest",
    }


def deterministic_group_id(prefix: str, transaction_ids: list[str]) -> str:
    digest = hashlib.sha1("|".join(sorted(transaction_ids)).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def amount_cents(row: dict[str, Any]) -> int:
    return int(round(abs(float(row.get("amount_cad") or 0)) * 100))


def merge_signal_maps(
    target: dict[str, list[RiskSignal]],
    source: dict[str, list[RiskSignal]],
) -> None:
    for transaction_id, signals in source.items():
        target.setdefault(transaction_id, []).extend(signals)


def load_active_risk_policy_rules() -> list[ConfigurablePolicyRule]:
    try:
        from app.services.policy_service import load_active_configurable_rules

        return load_active_configurable_rules()
    except Exception:
        return []


def resolved_policy_approval_threshold(
    transactions: list[dict[str, Any]],
    active_rules: list[ConfigurablePolicyRule],
) -> float:
    values = [
        policy_thresholds_from_rules(active_rules, transaction).preapproval_threshold_cad
        for transaction in transactions
    ]
    configured_values = [value for value in values if isfinite(value) and value > 0]
    return min(configured_values) if configured_values else NO_CONFIGURED_MONEY_THRESHOLD


@dataclass(frozen=True)
class AnomalyModelResult:
    model_name: str
    labels: np.ndarray
    scores: np.ndarray
    fallback_reason: str | None = None


def build_isolation_forest_signals(
    transactions: list[dict[str, Any]],
    approval_threshold_cad: float,
    preferred_model: str = "auto",
) -> dict[str, list[RiskSignal]]:
    eligible_transactions = eligible_debit_transactions(transactions)
    if len(eligible_transactions) < ISOLATION_FOREST_MIN_ROWS:
        return {}

    feature_rows, feature_names = isolation_forest_features(eligible_transactions, approval_threshold_cad)
    if len(feature_rows) < ISOLATION_FOREST_MIN_ROWS:
        return {}

    matrix = np.array(feature_rows, dtype=float)
    if matrix.shape[0] < ISOLATION_FOREST_MIN_ROWS or matrix.shape[1] == 0:
        return {}

    contamination = min(0.03, max(0.005, TARGET_OUTLIER_COUNT / matrix.shape[0]))
    model_result = fit_anomaly_model(matrix, contamination, preferred_model)
    if model_result is None:
        return {}

    medians = np.median(matrix, axis=0)
    spreads = np.std(matrix, axis=0)
    signals_by_transaction_id: dict[str, list[RiskSignal]] = defaultdict(list)
    anomaly_scores = model_result.scores
    ranked_score_cutoff = np.quantile(anomaly_scores, 1 - contamination)
    critical_score_cutoff = np.quantile(anomaly_scores, 0.995)

    for index, transaction in enumerate(eligible_transactions):
        if not model_result.labels[index] and anomaly_scores[index] < ranked_score_cutoff:
            continue

        outlier_strength = max(0.0, float(anomaly_scores[index] - ranked_score_cutoff))
        severity = "critical" if anomaly_scores[index] >= critical_score_cutoff else "high"
        feature_deviations = []
        for feature_index, feature_name in enumerate(feature_names):
            spread = spreads[feature_index] or 1.0
            deviation = abs((matrix[index][feature_index] - medians[feature_index]) / spread)
            feature_deviations.append((feature_name, deviation, matrix[index][feature_index]))
        top_features = [
            {"feature": name, "label": RISK_FEATURE_LABELS.get(name, name.replace("_", " ")), "value": round(float(value), 4)}
            for name, _deviation, value in sorted(feature_deviations, key=lambda item: item[1], reverse=True)[:3]
        ]
        driver_text = ", ".join(str(feature["label"]).lower() for feature in top_features)

        signals_by_transaction_id[str(transaction["id"])].append(
            RiskSignal(
                type="ml_isolation_forest_outlier",
                severity=severity,
                message=(
                    f"{model_result.model_name} flagged this as one of the most unusual debit transactions "
                    f"in the imported dataset, mainly because of {driver_text}."
                ),
                evidence={
                    "model": model_result.model_name,
                    "model_name": model_result.model_name,
                    "contamination": round(contamination, 4),
                    "score": round(float(anomaly_scores[index]), 6),
                    "score_direction": "higher means more anomalous",
                    "outlier_strength": round(outlier_strength, 6),
                    "top_drivers": top_features,
                    "top_features": top_features,
                    **({"fallback_reason": model_result.fallback_reason} if model_result.fallback_reason else {}),
                },
            )
        )

    return dict(signals_by_transaction_id)


def fit_anomaly_model(
    matrix: np.ndarray,
    contamination: float,
    preferred_model: str,
) -> AnomalyModelResult | None:
    if preferred_model in {"auto", "pyod"}:
        try:
            from pyod.models.iforest import IForest

            model = IForest(contamination=contamination, n_estimators=150, random_state=42)
            model.fit(matrix)
            return AnomalyModelResult(
                model_name="PyOD IForest",
                labels=np.array(model.labels_, dtype=bool),
                scores=np.array(model.decision_scores_, dtype=float),
            )
        except Exception as exc:
            if preferred_model == "pyod":
                fallback_reason = f"PyOD unavailable or failed: {type(exc).__name__}"
            else:
                fallback_reason = f"PyOD unavailable; used sklearn fallback ({type(exc).__name__})"
        else:
            fallback_reason = None
    else:
        fallback_reason = None

    try:
        model = IsolationForest(
            contamination=contamination,
            n_estimators=150,
            random_state=42,
        )
        predictions = model.fit_predict(matrix)
        decision_scores = model.decision_function(matrix)
    except ValueError:
        return None

    return AnomalyModelResult(
        model_name="sklearn IsolationForest",
        labels=np.array(predictions == -1, dtype=bool),
        scores=np.array(-decision_scores, dtype=float),
        fallback_reason=fallback_reason,
    )


def isolation_forest_features(
    transactions: list[dict[str, Any]],
    approval_threshold_cad: float,
) -> tuple[list[list[float]], list[str]]:
    merchant_counts = Counter(normalized_merchant(row) for row in transactions)
    employee_merchant_counts = Counter((row.get("employee_id"), normalized_merchant(row)) for row in transactions)
    merchant_amounts: dict[str, list[float]] = defaultdict(list)
    employee_amounts: dict[str | None, list[float]] = defaultdict(list)
    category_amounts: dict[str, list[float]] = defaultdict(list)
    department_category_amounts: dict[tuple[str | None, str], list[float]] = defaultdict(list)

    for row in transactions:
        amount = abs(float(row.get("amount_cad") or 0))
        merchant = normalized_merchant(row)
        category = risk_category(row)
        merchant_amounts[merchant].append(amount)
        employee_amounts[row.get("employee_id")].append(amount)
        category_amounts[category].append(amount)
        department_category_amounts[(row.get("department_id"), category)].append(amount)

    merchant_medians = {merchant: median(values) for merchant, values in merchant_amounts.items()}
    employee_medians = {employee_id: median(values) for employee_id, values in employee_amounts.items()}
    category_medians = {category: median(values) for category, values in category_amounts.items()}
    department_category_medians = {
        key: median(values)
        for key, values in department_category_amounts.items()
    }
    feature_names = [
        "log_amount",
        "employee_amount_ratio",
        "merchant_amount_ratio",
        "category_amount_ratio",
        "department_category_amount_ratio",
        "merchant_rarity",
        "employee_merchant_rarity",
        "near_approval_threshold",
        "round_amount",
        "weekend",
        "day_of_month",
    ]
    feature_rows: list[list[float]] = []

    for row in transactions:
        amount = abs(float(row.get("amount_cad") or 0))
        merchant = normalized_merchant(row)
        category = risk_category(row)
        merchant_baseline = merchant_medians.get(merchant) or amount or 1
        employee_baseline = employee_medians.get(row.get("employee_id")) or amount or 1
        category_baseline = category_medians.get(category) or amount or 1
        department_category_baseline = department_category_medians.get((row.get("department_id"), category)) or category_baseline or 1
        transaction_date = parse_date(row.get("transaction_date"))
        near_threshold_floor = approval_threshold_cad * 0.8
        feature_rows.append(
            [
                float(np.log1p(amount)),
                safe_ratio(amount, employee_baseline),
                safe_ratio(amount, merchant_baseline),
                safe_ratio(amount, category_baseline),
                safe_ratio(amount, department_category_baseline),
                safe_ratio(1, merchant_counts.get(merchant) or 1),
                safe_ratio(1, employee_merchant_counts.get((row.get("employee_id"), merchant)) or 1),
                1.0 if near_threshold_floor <= amount <= approval_threshold_cad else 0.0,
                1.0 if amount >= 100 and amount % 100 == 0 else 0.0,
                1.0 if transaction_date and transaction_date.weekday() >= 5 else 0.0,
                safe_ratio(transaction_date.day if transaction_date else 15, 31),
            ]
        )

    return feature_rows, feature_names


def fetch_transactions(request: RiskScanRequest) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    limit = request.limit if request.limit is not None else 10000
    while len(rows) < limit:
        end = min(start + PAGE_SIZE - 1, limit - 1)
        query = (
            get_supabase_client()
            .table("transactions")
            .select("*, raw_transactions(source_row_number, source_fingerprint, source_file_name)")
            .order("transaction_date")
            .range(start, end)
        )
        if request.employee_id:
            query = query.eq("employee_id", request.employee_id)
        if request.department_id:
            query = query.eq("department_id", request.department_id)
        if request.date_start:
            query = query.gte("transaction_date", request.date_start)
        if request.date_end:
            query = query.lte("transaction_date", request.date_end)
        batch = query.execute().data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return rows[:limit]


def build_peer_context(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    employee_merchants: dict[str, set[str]] = defaultdict(set)
    department_category_amounts: dict[tuple[str | None, str | None], list[float]] = defaultdict(list)
    employee_amounts: dict[str | None, list[float]] = defaultdict(list)
    merchant_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    novelty_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in transactions:
        amount = abs(float(row.get("amount_cad") or 0))
        merchant = normalized_merchant(row)
        novelty_key = merchant_novelty_key(row)
        if row.get("employee_id") and merchant:
            employee_merchants[row["employee_id"]].add(merchant)
        category = row.get("business_category") or row.get("policy_category") or row.get("normalized_category")
        department_category_amounts[(row.get("department_id"), category)].append(amount)
        employee_amounts[row.get("employee_id")].append(amount)
        if merchant and row.get("id") and str(row.get("debit_credit") or "").lower() != "credit" and amount > 0:
            merchant_rows[merchant].append(row)
        if novelty_key and row.get("id") and str(row.get("debit_credit") or "").lower() != "credit" and amount > 0:
            novelty_rows[novelty_key].append(row)

    merchant_prior_amount_stats: dict[str, dict[str, float | int]] = {}
    for merchant, rows in merchant_rows.items():
        del merchant
        sorted_rows = sorted(
            rows,
            key=lambda row: (
                str(row.get("transaction_date") or ""),
                str(row.get("posting_date") or ""),
                str(row.get("id") or ""),
            ),
        )
        prior_amounts: list[float] = []
        for row in sorted_rows:
            transaction_id = str(row.get("id"))
            merchant_prior_amount_stats[transaction_id] = {
                "count": len(prior_amounts),
                "median_amount_cad": median(prior_amounts),
                "max_amount_cad": max(prior_amounts) if prior_amounts else 0.0,
            }
            prior_amounts.append(abs(float(row.get("amount_cad") or 0)))

    merchant_novelty_prior_counts: dict[str, int] = {}
    for rows in novelty_rows.values():
        sorted_rows = sorted(
            rows,
            key=lambda row: (
                str(row.get("transaction_date") or ""),
                str(row.get("posting_date") or ""),
                str(row.get("id") or ""),
            ),
        )
        prior_count = 0
        for row in sorted_rows:
            merchant_novelty_prior_counts[str(row.get("id"))] = prior_count
            prior_count += 1

    return {
        "employee_merchants": employee_merchants,
        "department_category_amounts": department_category_amounts,
        "employee_amount_medians": {
            employee_id: median(values)
            for employee_id, values in employee_amounts.items()
        },
        "employee_transaction_counts": {
            employee_id: len(values)
            for employee_id, values in employee_amounts.items()
        },
        "merchant_prior_amount_stats": merchant_prior_amount_stats,
        "merchant_novelty_prior_counts": merchant_novelty_prior_counts,
    }


def fetch_latest_policy_checks(transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not transaction_ids:
        return {}
    checks: list[dict[str, Any]] = []
    for chunk in chunked(unique_ids(transaction_ids), QUERY_CHUNK_SIZE):
        checks.extend(
            get_supabase_client()
            .table("policy_checks")
            .select("*")
            .in_("transaction_id", chunk)
            .order("checked_at", desc=True)
            .execute()
            .data
            or []
        )
    latest: dict[str, dict[str, Any]] = {}
    for check in checks:
        latest.setdefault(check["transaction_id"], check)
    return latest


def fetch_open_violations(transaction_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunked(unique_ids(transaction_ids), QUERY_CHUNK_SIZE):
        rows.extend(
            get_supabase_client()
            .table("violations")
            .select("transaction_id, status, rule_code, severity")
            .in_("transaction_id", chunk)
            .execute()
            .data
            or []
        )
    return rows


def delete_existing_scores(transaction_ids: list[str]) -> None:
    for chunk in chunked(unique_ids(transaction_ids), QUERY_CHUNK_SIZE):
        get_supabase_client().table("risk_scores").delete().in_("transaction_id", chunk).execute()


def persist_scores(rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for chunk in chunked(rows, PAGE_SIZE):
        get_supabase_client().table("risk_scores").insert(chunk).execute()
        inserted += len(chunk)
    return inserted


def fetch_by_ids(table_name: str, ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunked(unique_ids(ids), QUERY_CHUNK_SIZE):
        rows.extend(get_supabase_client().table(table_name).select("*").in_("id", chunk).execute().data or [])
    return rows


def normalized_merchant(row: dict[str, Any]) -> str:
    return str(row.get("normalized_merchant_family") or row.get("normalized_merchant_name") or row.get("merchant_name") or "").upper()


def merchant_novelty_key(row: dict[str, Any]) -> str:
    merchant = normalized_merchant(row)
    if not merchant:
        return ""
    tokens = [
        token
        for token in re.sub(r"[^A-Z0-9 ]+", " ", merchant).split()
        if token and not token.isdigit() and token not in MERCHANT_NOVELTY_IGNORED_TOKENS
    ]
    return " ".join(tokens[:2])


def risk_category(row: dict[str, Any]) -> str:
    return str(row.get("business_category") or row.get("policy_category") or row.get("normalized_category") or "Uncategorized")


def first_present(row: dict[str, Any], fields: tuple[str, ...]) -> Any:
    for field in fields:
        value = row.get(field)
        if not is_blank(value):
            return value
    return None


def text_matches(row: dict[str, Any], fields: tuple[str, ...], terms: tuple[str, ...]) -> dict[str, str]:
    matches: dict[str, str] = {}
    for field in fields:
        value = normalized_text(row.get(field))
        if not value:
            continue
        for term in terms:
            if term in value:
                matches[field] = term
                break
    return matches


def parse_amount(value: Any) -> float | None:
    if is_blank(value):
        return None
    try:
        parsed = float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def parse_int(value: Any) -> int | None:
    parsed = parse_amount(value)
    return int(parsed) if parsed is not None else None


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in MISSING_VALUES


def normalized_text(value: Any) -> str:
    return "" if is_blank(value) else str(value).strip().lower()


def safe_ratio(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(np.median(np.array(values, dtype=float)))


def risk_level_for_score(score: int) -> str:
    for minimum, level in RISK_LEVELS:
        if score >= minimum:
            return level
    return "low"


def levels_at_or_above(min_level: str) -> set[str]:
    order = ["low", "medium", "high", "critical"]
    if min_level not in order:
        min_level = "medium"
    return set(order[order.index(min_level) :])


def days_between(left: Any, right: Any) -> int:
    try:
        return abs((datetime_from_value(left) - datetime_from_value(right)).days)
    except (TypeError, ValueError):
        return 9999


def datetime_from_value(value: Any):
    return datetime.strptime(str(value), "%Y-%m-%d")


def parse_date(value: Any) -> datetime | None:
    try:
        return datetime_from_value(value)
    except (TypeError, ValueError):
        return None


def unique_ids(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
