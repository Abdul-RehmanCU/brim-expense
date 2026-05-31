from app.services.risk_service import build_risk_scores


def policy_rule(threshold: float = 50.0):
    rule = type("PolicyRule", (), {})()
    rule.enabled = True
    rule.scope = {}
    rule.applies_to = {}
    rule.thresholds = {
        "preapproval_threshold_cad": {
            "value": threshold,
            "currency": "CAD",
        }
    }
    return rule


def transaction(
    transaction_id: str,
    *,
    employee_id: str = "employee_1",
    department_id: str = "department_1",
    merchant: str = "STAPLES",
    amount_cad: float = 49.0,
    transaction_date: str = "2026-05-01",
    category: str = "Office Supplies",
    source_row_number: int | None = None,
    **overrides,
) -> dict:
    row = {
        "id": transaction_id,
        "employee_id": employee_id,
        "department_id": department_id,
        "transaction_date": transaction_date,
        "merchant_name": merchant,
        "normalized_merchant_name": merchant,
        "normalized_merchant_family": merchant,
        "amount_cad": amount_cad,
        "debit_credit": "debit",
        "business_category": category,
        "transaction_eligibility": "eligible_expense",
        "source_row_number": source_row_number,
    }
    row.update(overrides)
    return row


def signal_types(score):
    return {signal.type for signal in score.signals}


def score_by_id(scores, transaction_id):
    return next(score for score in scores if score.transaction_id == transaction_id)


def test_risk_scores_detect_duplicate_charge():
    scores = build_risk_scores(
        [
            transaction("txn_1", amount_cad=125, transaction_date="2026-05-01"),
            transaction("txn_2", amount_cad=125, transaction_date="2026-05-01"),
        ]
    )

    assert "duplicate_charge" in signal_types(score_by_id(scores, "txn_1"))
    assert "duplicate_charge" in signal_types(score_by_id(scores, "txn_2"))
    assert score_by_id(scores, "txn_1").risk_level in {"medium", "high"}


def test_risk_scores_detect_same_day_near_duplicate_charge():
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="WSDOT", amount_cad=1304.17, transaction_date="2026-05-01"),
            transaction("txn_2", merchant="WSDOT", amount_cad=1304.42, transaction_date="2026-05-01"),
        ]
    )

    assert "duplicate_charge" in signal_types(score_by_id(scores, "txn_1"))
    assert "duplicate_charge" in signal_types(score_by_id(scores, "txn_2"))


def test_risk_scores_do_not_detect_cross_day_near_duplicate_charge_by_default():
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="WSDOT", amount_cad=1304.17, transaction_date="2026-05-01"),
            transaction("txn_2", merchant="WSDOT", amount_cad=1304.42, transaction_date="2026-05-02"),
        ]
    )

    assert "duplicate_charge" not in signal_types(score_by_id(scores, "txn_1"))
    assert "duplicate_charge" not in signal_types(score_by_id(scores, "txn_2"))


def test_risk_scores_detect_duplicate_groups_without_employee_scope():
    scores = build_risk_scores(
        [
            transaction("txn_1", employee_id="employee_1", amount_cad=125, transaction_date="2026-05-01", source_row_number=10),
            transaction("txn_2", employee_id="employee_2", amount_cad=125, transaction_date="2026-05-01", source_row_number=11),
            transaction("txn_3", employee_id="", amount_cad=125, transaction_date="2026-05-01", source_row_number=12),
        ]
    )

    signal = next(signal for signal in score_by_id(scores, "txn_1").signals if signal.type == "duplicate_charge")

    assert "duplicate_charge" in signal_types(score_by_id(scores, "txn_2"))
    assert "duplicate_charge" in signal_types(score_by_id(scores, "txn_3"))
    assert signal.evidence["group_id"].startswith("duplicate-exact-")
    assert signal.evidence["group_size"] == 3
    assert set(signal.evidence["transaction_ids"]) == {"txn_1", "txn_2", "txn_3"}
    assert {row["source_row_number"] for row in signal.evidence["rows"]} == {10, 11, 12}


def test_risk_scores_detect_split_transaction_pattern(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(50)])
    scores = build_risk_scores(
        [
            transaction("txn_1", amount_cad=48, transaction_date="2026-05-01"),
            transaction("txn_2", amount_cad=47, transaction_date="2026-05-01"),
            transaction("txn_3", merchant="DIFFERENT MERCHANT", amount_cad=25, transaction_date="2026-05-04"),
        ],
    )

    assert "split_transaction_pattern" in signal_types(score_by_id(scores, "txn_1"))
    assert "split_transaction_pattern" in signal_types(score_by_id(scores, "txn_2"))
    assert "split_transaction_pattern" not in signal_types(score_by_id(scores, "txn_3"))


def test_risk_scores_do_not_detect_cross_day_split_pattern_by_default(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(500)])
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="ACME OFFICE", amount_cad=260, transaction_date="2026-05-01"),
            transaction("txn_2", merchant="ACME OFFICE", amount_cad=275, transaction_date="2026-05-03"),
        ],
    )

    assert "split_transaction_pattern" not in signal_types(score_by_id(scores, "txn_1"))
    assert "split_transaction_pattern" not in signal_types(score_by_id(scores, "txn_2"))


def test_split_only_groups_do_not_require_duplicate_signal_bucket(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(50)])
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="ACME OFFICE", amount_cad=30, transaction_date="2026-05-01"),
            transaction("txn_2", merchant="ACME OFFICE", amount_cad=45, transaction_date="2026-05-01"),
        ],
    )

    assert "split_transaction_pattern" in signal_types(score_by_id(scores, "txn_1"))
    assert "duplicate_charge" not in signal_types(score_by_id(scores, "txn_1"))


def test_risk_scores_detect_policy_threshold_split_group(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(500)])
    scores = build_risk_scores(
        [
            transaction("txn_1", employee_id="employee_1", merchant="ACME HOTEL", amount_cad=300, transaction_date="2026-05-01", category="Lodging"),
            transaction("txn_2", employee_id="employee_2", merchant="ACME HOTEL", amount_cad=300, transaction_date="2026-05-02", category="Lodging"),
        ],
        split_window_days=7,
    )

    signal = next(signal for signal in score_by_id(scores, "txn_1").signals if signal.type == "split_transaction_pattern")

    assert "split_transaction_pattern" in signal_types(score_by_id(scores, "txn_2"))
    assert signal.evidence["group_id"].startswith("split-threshold-")
    assert signal.evidence["combined_amount_cad"] == 600
    assert signal.evidence["split_threshold_cad"] == 500
    assert set(signal.evidence["transaction_ids"]) == {"txn_1", "txn_2"}


def test_risk_scores_default_to_focused_profile():
    scores = build_risk_scores(
        [
            transaction(
                "txn_1",
                amount_cad=500,
                category="Unknown",
                category_source="fallback",
                category_confidence=0.31,
            )
        ]
    )

    score = score_by_id(scores, "txn_1")

    assert "weak_categorization" not in signal_types(score)
    assert "round_number_amount" not in signal_types(score)
    assert "merchant_amount_outlier" not in signal_types(score)
    assert "first_time_high_value_merchant" not in signal_types(score)


def test_risk_scores_detect_near_threshold_amount(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(50)])
    scores = build_risk_scores(
        [transaction("txn_1", amount_cad=49.99)],
        detector_profile="full",
    )

    assert "near_approval_threshold" in signal_types(score_by_id(scores, "txn_1"))
    assert score_by_id(scores, "txn_1").risk_score >= 25


def test_risk_scores_detect_round_number_amount():
    scores = build_risk_scores([transaction("txn_1", amount_cad=500)], detector_profile="full")

    score = score_by_id(scores, "txn_1")

    assert "round_number_amount" in signal_types(score)
    assert score.risk_score >= 25


def test_risk_scores_detect_merchant_specific_amount_outlier_in_full_profile():
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="WSDOT", amount_cad=105, transaction_date="2026-05-01"),
            transaction("txn_2", merchant="WSDOT", amount_cad=110, transaction_date="2026-05-02"),
            transaction("txn_3", merchant="WSDOT", amount_cad=115, transaction_date="2026-05-03"),
            transaction("txn_4", merchant="WSDOT", amount_cad=120, transaction_date="2026-05-04"),
            transaction("txn_5", merchant="WSDOT", amount_cad=118, transaction_date="2026-05-05"),
            transaction("txn_6", merchant="WSDOT", amount_cad=400, transaction_date="2026-05-06"),
        ],
        detector_profile="full",
    )

    signal = next(signal for signal in score_by_id(scores, "txn_6").signals if signal.type == "merchant_amount_outlier")

    assert signal.severity == "medium"
    assert signal.evidence["prior_transaction_count"] == 5
    assert signal.evidence["prior_median_amount_cad"] == 115
    assert signal.evidence["amount_ratio_to_prior_median"] > 3


def test_risk_scores_do_not_detect_merchant_specific_amount_outlier_without_enough_history():
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="WSDOT", amount_cad=105, transaction_date="2026-05-01"),
            transaction("txn_2", merchant="WSDOT", amount_cad=110, transaction_date="2026-05-02"),
            transaction("txn_3", merchant="WSDOT", amount_cad=115, transaction_date="2026-05-03"),
            transaction("txn_4", merchant="WSDOT", amount_cad=400, transaction_date="2026-05-04"),
        ],
        detector_profile="full",
    )

    assert "merchant_amount_outlier" not in signal_types(score_by_id(scores, "txn_4"))


def test_risk_scores_detect_first_time_high_value_merchant_in_full_profile(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(500)])
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="OLD MERCHANT 1", amount_cad=120, transaction_date="2026-05-01"),
            transaction("txn_2", merchant="OLD MERCHANT 2", amount_cad=135, transaction_date="2026-05-02"),
            transaction("txn_3", merchant="OLD MERCHANT 3", amount_cad=140, transaction_date="2026-05-03"),
            transaction("txn_4", merchant="OLD MERCHANT 4", amount_cad=150, transaction_date="2026-05-04"),
            transaction("txn_5", merchant="OLD MERCHANT 5", amount_cad=160, transaction_date="2026-05-05"),
            transaction("txn_6", merchant="NEW PERMIT VENDOR", amount_cad=600, transaction_date="2026-05-06"),
            transaction("txn_7", merchant="NEW PERMIT VENDOR", amount_cad=620, transaction_date="2026-05-07"),
        ],
        detector_profile="full",
    )

    first_signal = next(
        signal for signal in score_by_id(scores, "txn_6").signals if signal.type == "first_time_high_value_merchant"
    )

    assert first_signal.severity == "medium"
    assert first_signal.evidence["employee_transaction_count"] == 7
    assert first_signal.evidence["employee_median_amount_cad"] == 150
    assert "first_time_high_value_merchant" not in signal_types(score_by_id(scores, "txn_7"))


def test_risk_scores_do_not_detect_first_time_high_value_merchant_for_fuel_chain_location_fragmentation(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(500)])
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="OFFICE DEPOT", amount_cad=120, transaction_date="2026-05-01", category="Office Supplies"),
            transaction("txn_2", merchant="HOTEL", amount_cad=130, transaction_date="2026-05-02", category="Lodging"),
            transaction("txn_3", merchant="MEAL", amount_cad=140, transaction_date="2026-05-03", category="Meals / Entertainment"),
            transaction("txn_4", merchant="PARKING", amount_cad=150, transaction_date="2026-05-04", category="Parking / Tolls"),
            transaction("txn_5", merchant="TOLLS", amount_cad=160, transaction_date="2026-05-05", category="Parking / Tolls"),
            transaction("txn_6", merchant="FLYING J 663", amount_cad=1092.21, transaction_date="2026-05-06", category="Fuel"),
            transaction("txn_7", merchant="FLYING J 893", amount_cad=1462.56, transaction_date="2026-05-07", category="Fuel"),
        ],
        detector_profile="full",
    )

    assert "first_time_high_value_merchant" not in signal_types(score_by_id(scores, "txn_6"))
    assert "first_time_high_value_merchant" not in signal_types(score_by_id(scores, "txn_7"))


def test_risk_scores_require_higher_floor_for_uncategorized_first_time_merchant(monkeypatch):
    monkeypatch.setattr("app.services.risk_service.load_active_risk_policy_rules", lambda: [policy_rule(500)])
    scores = build_risk_scores(
        [
            transaction("txn_1", merchant="OFFICE DEPOT", amount_cad=120, transaction_date="2026-05-01", category="Office Supplies"),
            transaction("txn_2", merchant="HOTEL", amount_cad=130, transaction_date="2026-05-02", category="Lodging"),
            transaction("txn_3", merchant="MEAL", amount_cad=140, transaction_date="2026-05-03", category="Meals / Entertainment"),
            transaction("txn_4", merchant="PARKING", amount_cad=150, transaction_date="2026-05-04", category="Parking / Tolls"),
            transaction("txn_5", merchant="TOLLS", amount_cad=160, transaction_date="2026-05-05", category="Parking / Tolls"),
            transaction("txn_6", merchant="LINKEDIN SN P", amount_cad=800, transaction_date="2026-05-06", category="Uncategorized"),
            transaction("txn_7", merchant="LINKEDIN SN P", amount_cad=1079.88, transaction_date="2026-05-07", category="Uncategorized"),
        ],
        detector_profile="full",
    )

    assert "first_time_high_value_merchant" not in signal_types(score_by_id(scores, "txn_6"))
    assert "first_time_high_value_merchant" not in signal_types(score_by_id(scores, "txn_7"))


def test_risk_scores_detect_cash_or_atm_pattern_from_generic_fields():
    scores = build_risk_scores(
        [
            transaction(
                "txn_1",
                merchant="ATM NETWORK",
                amount_cad=80,
                transaction_type="cash_withdrawal",
            )
        ]
    )

    score = score_by_id(scores, "txn_1")
    signal = next(signal for signal in score.signals if signal.type == "cash_atm_pattern")

    assert signal.severity == "medium"
    assert signal.evidence["matched_fields"]


def test_risk_scores_ignore_cash_advance_fee_admin_rows():
    scores = build_risk_scores(
        [
            transaction(
                "txn_1",
                merchant="CASH ADVANCE FEE",
                amount_cad=5,
                transaction_type="cash_advance_fee",
                transaction_eligibility="excluded_non_expense",
                category="Cash Advance Fee",
                merchant_category_code=None,
                merchant_country="",
            )
        ]
    )

    assert score_by_id(scores, "txn_1").risk_score == 0
    assert signal_types(score_by_id(scores, "txn_1")) == set()


def test_risk_scores_detect_missing_merchant_and_compliance_metadata_when_fields_exist():
    scores = build_risk_scores(
        [
            transaction(
                "txn_1",
                merchant="",
                amount_cad=84,
                merchant_category_code=None,
                merchant_country="",
                policy_category=None,
            )
        ]
    )

    signal = next(signal for signal in score_by_id(scores, "txn_1").signals if signal.type == "missing_merchant_compliance_metadata")

    assert signal.severity == "high"
    assert set(signal.evidence["missing_fields"]) >= {"merchant", "merchant_category_code", "merchant_country", "policy_category"}


def test_risk_scores_detect_weak_categorization_from_category_facts():
    scores = build_risk_scores(
        [
            transaction(
                "txn_1",
                category="Unknown",
                category_source="fallback",
                category_confidence=0.31,
            )
        ],
        detector_profile="full",
    )

    signal = next(signal for signal in score_by_id(scores, "txn_1").signals if signal.type == "weak_categorization")

    assert set(signal.evidence["reasons"]) == {
        "generic_category",
        "weak_category_source",
        "low_category_confidence",
    }


def test_risk_scores_detect_fx_inconsistency_when_conversion_facts_exist():
    scores = build_risk_scores(
        [
            transaction(
                "txn_1",
                amount_cad=150,
                amount_original=100,
                conversion_rate=1.2,
                original_currency="USD",
            )
        ]
    )

    signal = next(signal for signal in score_by_id(scores, "txn_1").signals if signal.type == "fx_inconsistency")

    assert signal.evidence["expected_amount_cad"] == 120
    assert signal.evidence["difference_cad"] == 30


def test_risk_scores_detect_posting_lag_outlier_from_dates_or_delay_fact():
    scores = build_risk_scores(
        [
            transaction(
                "txn_1",
                transaction_date="2026-05-01",
                posting_date="2026-06-15",
            ),
            transaction(
                "txn_2",
                transaction_date="2026-05-01",
                posting_delay_days=12,
            ),
        ]
    )

    high_signal = next(signal for signal in score_by_id(scores, "txn_1").signals if signal.type == "posting_lag_outlier")
    medium_signal = next(signal for signal in score_by_id(scores, "txn_2").signals if signal.type == "posting_lag_outlier")

    assert high_signal.severity == "high"
    assert high_signal.evidence["posting_delay_days"] == 45
    assert medium_signal.severity == "medium"
    assert medium_signal.evidence["posting_delay_days"] == 12


def test_risk_scores_include_policy_overlap():
    scores = build_risk_scores(
        [transaction("txn_1", amount_cad=75)],
        policy_checks_by_transaction_id={
            "txn_1": {
                "transaction_id": "txn_1",
                "status": "policy_violation",
                "max_severity": "high",
                "severity_score": 80,
            }
        },
        violations=[
            {
                "transaction_id": "txn_1",
                "status": "open",
                "rule_code": "TICKETS_NOT_REIMBURSABLE",
            }
        ],
        detector_profile="full",
    )

    score = score_by_id(scores, "txn_1")

    assert "policy_risk_overlap" in signal_types(score)
    assert score.risk_level in {"medium", "high", "critical"}


def test_risk_scores_include_isolation_forest_outlier():
    normal_transactions = [
        transaction(
            f"txn_{index}",
            amount_cad=42 + (index % 4),
            transaction_date=f"2026-05-{(index % 20) + 1:02d}",
        )
        for index in range(30)
    ]
    scores = build_risk_scores(
        [
            *normal_transactions,
            transaction(
                "txn_outlier",
                merchant="RARE LUXURY MERCHANT",
                amount_cad=5000,
                transaction_date="2026-05-31",
                category="Executive Travel",
            ),
        ],
        detector_profile="full",
    )

    outlier_score = score_by_id(scores, "txn_outlier")

    assert "ml_isolation_forest_outlier" in signal_types(outlier_score)
    assert outlier_score.risk_level in {"high", "critical"}
    signal = next(signal for signal in outlier_score.signals if signal.type == "ml_isolation_forest_outlier")
    assert signal.evidence["model_name"]
    assert signal.evidence["score_direction"] == "higher means more anomalous"
    assert signal.evidence["top_drivers"]
