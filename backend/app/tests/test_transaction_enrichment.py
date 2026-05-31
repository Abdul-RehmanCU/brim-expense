from app.schemas.transactions import TransactionEnrichmentRequest
from app.services import transaction_enrichment
from app.services.transaction_enrichment import build_transaction_enrichment


def transaction(**overrides):
    return {
        "id": "txn_1",
        "transaction_code": "3001",
        "description": "MNDOT OSOW PERMITS FEE ATLANTA GA",
        "source_category": "Fuel",
        "business_category": "Fuel",
        "normalized_category": "Fuel",
        "category_confidence": 0.4,
        "posting_date": "2026-05-12",
        "transaction_date": "2026-05-10",
        "merchant_name": "MNDOT OSOW PERMITS FEE",
        "normalized_merchant_name": "MNDOT OSOW PERMITS FEE",
        "amount_cad": 227.9,
        "debit_credit": "debit",
        "merchant_category_code": "5542",
        "merchant_country": "USA",
        **overrides,
    }


def test_enrichment_prioritizes_permits_over_fuel():
    enrichment = build_transaction_enrichment(transaction())

    assert enrichment["business_category"] == "Permits / Government Fees"
    assert enrichment["policy_category"] == "Permits / Government Fees"
    assert enrichment["category_source"] == "permit_rule"
    assert enrichment["posting_delay_days"] == 2
    assert enrichment["is_foreign_transaction"] is True


def test_enrichment_returns_stable_account_activity_fields():
    enrichment = build_transaction_enrichment(
        transaction(
            transaction_code="0108",
            description="CWB EFT PAYMENT",
            merchant_name="CWB EFT PAYMENT",
            normalized_merchant_name="CWB EFT PAYMENT",
            debit_credit="credit",
            amount_cad=176060.66,
        )
    )

    assert enrichment["transaction_type"] == "account_payment"
    assert enrichment["transaction_eligibility"] == "excluded_non_expense"
    assert enrichment["business_category"] == "Account Payment / Transfer"
    assert enrichment["policy_category"] == "Excluded Non-Expense"
    assert enrichment["is_account_activity"] is True


def test_enrichment_maps_credits_to_merchant_credit():
    enrichment = build_transaction_enrichment(
        transaction(transaction_code="3006", merchant_name="LEROY SHELL", normalized_merchant_name="LEROY SHELL", debit_credit="credit")
    )

    assert enrichment["transaction_type"] == "merchant_credit"
    assert enrichment["business_category"] == "Refund / Merchant Credit"
    assert enrichment["transaction_eligibility"] == "excluded_non_expense"


def test_enrichment_maps_cash_advance_combo_to_finance_review():
    enrichment = build_transaction_enrichment(
        transaction(
            transaction_code="3005",
            source_category="0003",
            debit_credit="debit",
            description="PAI ATM SEYMOUR DC",
            merchant_name="PAI ATM",
            normalized_merchant_name="PAI ATM",
            merchant_category_code="6011",
        )
    )

    assert enrichment["transaction_type"] == "cash_advance"
    assert enrichment["business_category"] == "Cash Advance / ATM Withdrawal"
    assert enrichment["policy_category"] == "Finance Review"
    assert enrichment["transaction_eligibility"] == "finance_review"


def test_enrichment_maps_card_fee_combo_to_fee_category():
    enrichment = build_transaction_enrichment(
        transaction(
            transaction_code="0137",
            source_category="0012",
            debit_credit="debit",
            description="AUTH USER FEE 2025-26",
            merchant_name="AUTH USER FEE 2025-26",
            normalized_merchant_name="AUTH USER FEE 2025-26",
            merchant_category_code=None,
        )
    )

    assert enrichment["transaction_type"] == "card_fee"
    assert enrichment["business_category"] == "Card Fees / Interest"
    assert enrichment["policy_category"] == "Excluded Non-Expense"
    assert enrichment["transaction_eligibility"] == "excluded_non_expense"
    assert enrichment["is_account_activity"] is True


def test_enrichment_maps_cash_advance_fee_to_excluded_admin_fee():
    enrichment = build_transaction_enrichment(
        transaction(
            transaction_code="0401",
            source_category="0010",
            debit_credit="debit",
            description="CASH ADVANCE FEE",
            merchant_name="CASH ADVANCE FEE",
            normalized_merchant_name="CASH ADVANCE FEE",
            merchant_category_code=None,
        )
    )

    assert enrichment["transaction_type"] == "cash_advance_fee"
    assert enrichment["business_category"] == "Cash Advance Fee"
    assert enrichment["policy_category"] == "Excluded Non-Expense"
    assert enrichment["transaction_eligibility"] == "excluded_non_expense"


def test_enrichment_maps_intuit_to_software_saas():
    enrichment = build_transaction_enrichment(
        transaction(
            description="INTUIT *QuickBooks TORONTO ON",
            merchant_name="INTUIT *QuickBooks",
            normalized_merchant_name="INTUIT QUICKBOOKS",
            merchant_category_code="5734",
        )
    )

    assert enrichment["business_category"] == "Software / SaaS"
    assert enrichment["category_source"] == "merchant_dictionary"
    assert enrichment["normalized_merchant_family"] == "INTUIT"


def test_enrichment_maps_telus_to_telecom_connectivity():
    enrichment = build_transaction_enrichment(
        transaction(
            description="TELUS ONLINE PAYMENT P EDMONTON AB",
            merchant_name="TELUS ONLINE PAYMENT P",
            normalized_merchant_name="TELUS ONLINE PAYMENT P",
            merchant_category_code="4812",
        )
    )

    assert enrichment["business_category"] == "Telecom / Connectivity"
    assert enrichment["category_source"] == "merchant_dictionary"
    assert enrichment["normalized_merchant_family"] == "TELUS"


def test_enrichment_uses_description_for_weatherlogics_family():
    enrichment = build_transaction_enrichment(
        transaction(
            description="IN *WEATHERLOGICS INC. 204-3813708 MB",
            merchant_name="IN *WEATHERLOGICS INC.",
            normalized_merchant_name="IN INC.",
            merchant_category_code="7392",
        )
    )

    assert enrichment["business_category"] == "Software / SaaS"
    assert enrichment["category_source"] == "merchant_dictionary"
    assert enrichment["normalized_merchant_family"] == "WEATHERLOGICS"


def test_enrich_existing_transactions_dry_run_skips_persistence(monkeypatch):
    monkeypatch.setattr(transaction_enrichment, "iter_transaction_batches", lambda batch_size, limit: [[transaction()]])

    def fail_client():
        raise AssertionError("dry_run should not request a Supabase client for persistence")

    monkeypatch.setattr(transaction_enrichment, "get_supabase_client", fail_client)

    response = transaction_enrichment.enrich_existing_transactions(TransactionEnrichmentRequest(batch_size=1, dry_run=True))

    assert response.total_seen == 1
    assert response.updated == 1
    assert response.errors == 0
