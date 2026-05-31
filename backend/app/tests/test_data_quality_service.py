import pandas as pd

from app.services.data_quality_service import validate_transaction_dataset


def transaction(**overrides):
    row = {
        "id": "txn_1",
        "raw_transactions": {"source_row_number": 7, "source_fingerprint": "fp-1"},
        "transaction_date": "2026-05-01",
        "posting_date": "2026-05-03",
        "amount_original": 100,
        "amount_cad": 100,
        "debit_credit": "debit",
        "merchant_name": "STAPLES",
        "normalized_merchant_name": "STAPLES",
        "merchant_category_code": "5943",
        "merchant_country": "CA",
        "merchant_region": "ON",
        "source_category": "Office",
        "business_category": "Office Supplies",
        "normalized_category": "Office Supplies",
        "category_source": "merchant_dictionary",
        "category_confidence": 0.9,
        "conversion_rate": None,
        "transaction_type": "expense",
        "transaction_eligibility": "eligible_expense",
        "posting_delay_days": 2,
    }
    row.update(overrides)
    return row


def rule_ids(response):
    return {finding.rule_id for finding in response.findings}


def findings_for(response, rule_id):
    return [finding for finding in response.findings if finding.rule_id == rule_id]


def test_missing_merchant_metadata_is_flagged_for_expense_rows():
    response = validate_transaction_dataset(
        [
            transaction(
                id="txn_missing_meta",
                merchant_category_code=None,
                merchant_country="",
                merchant_region=None,
            )
        ],
        run_great_expectations=False,
    )

    fields = {finding.field for finding in findings_for(response, "merchant_metadata_complete")}

    assert {"merchant_category_code", "merchant_country", "merchant_region"} <= fields
    assert response.summary.rows_with_findings == 1


def test_foreign_merchant_with_zero_fx_rate_is_flagged():
    response = validate_transaction_dataset(
        [
            transaction(
                id="txn_fx",
                merchant_country="US",
                merchant_region="WA",
                conversion_rate=0,
            )
        ],
        run_great_expectations=False,
    )

    finding = findings_for(response, "foreign_transaction_conversion_rate")[0]
    assert finding.severity == "high"
    assert finding.field == "conversion_rate"
    assert finding.transaction_id == "txn_fx"


def test_weak_source_category_and_prevalence_are_flagged():
    response = validate_transaction_dataset(
        [
            transaction(id="txn_1", source_category="0001"),
            transaction(id="txn_2", source_category="0001"),
            transaction(id="txn_3", source_category="Fuel"),
        ],
        run_great_expectations=False,
    )

    assert "weak_source_category_0001" in rule_ids(response)
    assert "weak_source_category_0001_prevalence" in rule_ids(response)


def test_long_posting_delay_is_flagged_from_persisted_or_computed_delay():
    response = validate_transaction_dataset(
        [
            transaction(
                id="txn_delay",
                transaction_date="2026-05-01",
                posting_date="2026-06-15",
                posting_delay_days=None,
            )
        ],
        run_great_expectations=False,
    )

    finding = findings_for(response, "posting_delay_outlier")[0]
    assert finding.severity == "high"
    assert finding.observed_value == 45


def test_validation_accepts_dataframe_input_without_supabase():
    dataframe = pd.DataFrame([transaction(id="txn_dataframe", category_source="fallback", category_confidence=0.4)])

    response = validate_transaction_dataset(dataframe, run_great_expectations=False)

    assert response.row_count == 1
    assert {"category_source_strength", "category_confidence_low"} <= rule_ids(response)
