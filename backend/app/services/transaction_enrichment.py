from __future__ import annotations

import re
from datetime import date, datetime
from time import perf_counter
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.schemas.transactions import TransactionEnrichmentRequest, TransactionEnrichmentResponse

PAGE_SIZE = 500

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

MERCHANT_CATEGORY_RULES = [
    {
        "keywords": ["INTUIT", "QUICKBOOKS"],
        "category": "Software / SaaS",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["WEATHERLOGICS"],
        "category": "Software / SaaS",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["BAMBOOHR"],
        "category": "Software / SaaS",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["RIGHT NETWORKS"],
        "category": "Software / SaaS",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["HOSTPAPA", "GODADDY", "BRIGHTORDER", "BORDER CONNECT", "AUDIBLE"],
        "category": "Software / SaaS",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["TELUS", "SUNCO COMMUNICATION"],
        "category": "Telecom / Connectivity",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["BIS SAFETY", "ST. JOHN AMBULANCE"],
        "category": "Training / Safety",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["ORKIN"],
        "category": "Facilities / Site Services",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["FLAIR DIR", "FLAIR AIR"],
        "category": "Air Travel",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["PRICELN", "PRICELINE"],
        "category": "Lodging",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["LINDE", "TRACTOR SUPPLY"],
        "category": "Transportation / Fleet / Operations",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["HYDRAULIC", "LUMBER", "YARD - SERV", "STORAGE", "TOTAL MARINE TRANS"],
        "category": "Transportation / Fleet / Operations",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["BEST BUY", "WAL-MART", "WALMART"],
        "category": "Office Supplies",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["COBS BREAD"],
        "category": "Meals / Entertainment",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["TRAVEL INS", "ASSUR VOY", "FLAIR DIR", "FLAIR AIR"],
        "category": "Air Travel",
        "source": "merchant_dictionary",
    },
    {
        "keywords": ["WWIT", "MOBILE CAR", "TRUCK WASH", "CAR WASH"],
        "category": "Vehicle Maintenance",
        "source": "merchant_dictionary",
    },
]

MERCHANT_FAMILY_RULES = [
    (["INTUIT", "QUICKBOOKS"], "INTUIT"),
    (["WEATHERLOGICS"], "WEATHERLOGICS"),
    (["BAMBOOHR"], "BAMBOOHR"),
    (["RIGHT NETWORKS"], "RIGHT NETWORKS"),
    (["HOSTPAPA"], "HOSTPAPA"),
    (["GODADDY"], "GODADDY"),
    (["BRIGHTORDER"], "BRIGHTORDER"),
    (["BORDER CONNECT"], "BORDER CONNECT"),
    (["TELUS"], "TELUS"),
    (["BIS SAFETY"], "BIS SAFETY"),
    (["ST. JOHN AMBULANCE"], "ST. JOHN AMBULANCE"),
    (["ORKIN"], "ORKIN"),
    (["FLAIR"], "FLAIR"),
    (["PRICELN", "PRICELINE"], "PRICELINE"),
    (["LINDE"], "LINDE"),
    (["TRACTOR SUPPLY"], "TRACTOR SUPPLY"),
    (["BEST BUY"], "BEST BUY"),
    (["WAL-MART", "WALMART"], "WALMART"),
]

MCC_DESCRIPTIONS = {
    "3405": "Car and truck rental",
    "3357": "Car and truck rental",
    "3389": "Car and truck rental",
    "3393": "Car and truck rental",
    "4215": "Courier services",
    "4784": "Tolls and bridge fees",
    "4789": "Transportation services",
    "5013": "Motor vehicle supplies",
    "5046": "Commercial equipment",
    "5200": "Home supply warehouse",
    "5300": "Wholesale club",
    "5532": "Automotive tire stores",
    "5533": "Automotive parts stores",
    "5541": "Service stations",
    "5542": "Automated fuel dispensers",
    "5812": "Restaurants",
    "5813": "Bars and lounges",
    "5814": "Fast food restaurants",
    "5817": "Digital goods",
    "5818": "Digital goods and subscriptions",
    "5943": "Office supplies",
    "7011": "Lodging",
    "7512": "Car and truck rental",
    "7531": "Automotive body repair",
    "7538": "Automotive service shops",
    "7542": "Car washes",
    "9399": "Government services",
}

SOURCE_COMBO_ROUTES = {
    ("3001", "1", "debit"): {
        "transaction_type": "expense",
        "transaction_eligibility": "eligible_expense",
        "forced_category": None,
        "category_source": "source_combo_purchase_rail",
        "is_account_activity": False,
        "is_credit_or_refund": False,
    },
    ("3006", "1", "credit"): {
        "transaction_type": "merchant_credit",
        "transaction_eligibility": "excluded_non_expense",
        "forced_category": "Refund / Merchant Credit",
        "category_source": "source_combo_merchant_credit",
        "is_account_activity": False,
        "is_credit_or_refund": True,
    },
    ("137", "12", "debit"): {
        "transaction_type": "card_fee",
        "transaction_eligibility": "excluded_non_expense",
        "forced_category": "Card Fees / Interest",
        "category_source": "source_combo_card_fee",
        "is_account_activity": True,
        "is_credit_or_refund": False,
    },
    ("3005", "3", "debit"): {
        "transaction_type": "cash_advance",
        "transaction_eligibility": "finance_review",
        "forced_category": "Cash Advance / ATM Withdrawal",
        "category_source": "source_combo_cash_advance",
        "is_account_activity": False,
        "is_credit_or_refund": False,
    },
    ("401", "10", "debit"): {
        "transaction_type": "cash_advance_fee",
        "transaction_eligibility": "excluded_non_expense",
        "forced_category": "Cash Advance Fee",
        "category_source": "source_combo_cash_advance_fee",
        "is_account_activity": True,
        "is_credit_or_refund": False,
    },
    ("404", "2", "debit"): {
        "transaction_type": "cash_advance_interest",
        "transaction_eligibility": "excluded_non_expense",
        "forced_category": "Cash Advance Interest",
        "category_source": "source_combo_cash_advance_interest",
        "is_account_activity": True,
        "is_credit_or_refund": False,
    },
    ("108", "19", "credit"): {
        "transaction_type": "account_payment",
        "transaction_eligibility": "excluded_non_expense",
        "forced_category": "Account Payment / Transfer",
        "category_source": "source_combo_account_payment",
        "is_account_activity": True,
        "is_credit_or_refund": True,
    },
    ("375", "1", "credit"): {
        "transaction_type": "reward_redemption",
        "transaction_eligibility": "excluded_non_expense",
        "forced_category": "Reward / Redemption",
        "category_source": "source_combo_reward_redemption",
        "is_account_activity": True,
        "is_credit_or_refund": True,
    },
    ("3035", "3", "credit"): {
        "transaction_type": "cash_advance_reversal",
        "transaction_eligibility": "excluded_non_expense",
        "forced_category": "Cash Advance Reversal / Adjustment",
        "category_source": "source_combo_cash_advance_reversal",
        "is_account_activity": False,
        "is_credit_or_refund": True,
    },
}


def enrich_existing_transactions(request: TransactionEnrichmentRequest | None = None) -> TransactionEnrichmentResponse:
    request = request or TransactionEnrichmentRequest()
    started_at = perf_counter()
    batch_size = normalized_batch_size(request.batch_size)
    total_seen = 0
    updated = 0
    skipped = 0
    errors = 0
    error_messages: list[str] = []
    batch_count = 0

    for transactions in iter_transaction_batches(batch_size, request.limit):
        batch_count += 1
        total_seen += len(transactions)
        updates: list[dict[str, Any]] = []

        for transaction in transactions:
            enrichment = build_transaction_enrichment(transaction)
            changed_fields = {
                key: value
                for key, value in enrichment.items()
                if normalize_existing_value(transaction.get(key)) != normalize_existing_value(value)
            }

            if not changed_fields:
                skipped += 1
                continue

            updated += 1
            updates.append({"id": transaction["id"], **enrichment})

        if updates and not request.dry_run:
            try:
                client = get_supabase_client()
                for chunk in chunked(updates, PAGE_SIZE):
                    client.rpc("bulk_update_transaction_enrichment", {"payload": chunk}).execute()
            except Exception as error:  # pragma: no cover - network/client detail
                errors += len(updates)
                error_messages.append(str(error))

    return TransactionEnrichmentResponse(
        total_seen=total_seen,
        updated=updated,
        skipped=skipped,
        errors=errors,
        duration_ms=int((perf_counter() - started_at) * 1000),
        batch_count=batch_count,
        error_messages=error_messages[:5],
    )


def build_transaction_enrichment(transaction: dict[str, Any]) -> dict[str, Any]:
    text = searchable_text(transaction)
    transaction_code = clean_code(transaction.get("transaction_code"))
    source_category = clean_code(transaction.get("source_category"))
    debit_credit = str(transaction.get("debit_credit") or "").lower()
    mcc = clean_code(transaction.get("merchant_category_code"))
    existing_category = str(
        transaction.get("business_category") or transaction.get("normalized_category") or "Uncategorized"
    )
    route = SOURCE_COMBO_ROUTES.get((transaction_code, source_category, debit_credit))
    is_credit = bool(route["is_credit_or_refund"]) if route else debit_credit == "credit" or transaction_code == "3006"
    is_account_payment = (
        bool(route["is_account_activity"]) and route["transaction_type"] == "account_payment"
        if route
        else "CWB EFT PAYMENT" in text or transaction_code == "108"
    )
    is_reward = route["transaction_type"] == "reward_redemption" if route else "POINT REDEMPTION" in text or transaction_code == "375"
    is_fee_or_interest = contains_any(text, ["INTEREST", "FINANCE CHARGE", "ANNUAL FEE", "AUTH USER FEE", "LATE FEE", "CARD FEE"])

    if route:
        transaction_type = route["transaction_type"]
        eligibility = route["transaction_eligibility"]
        if route["forced_category"]:
            business_category = route["forced_category"]
            category_source = route["category_source"]
        else:
            business_category, category_source = infer_business_category(transaction, text, mcc, existing_category)
    elif is_account_payment:
        transaction_type = "account_payment"
        eligibility = "excluded_non_expense"
        business_category = "Account Payment / Transfer"
        category_source = "account_activity_rule"
    elif is_reward:
        transaction_type = "reward_redemption"
        eligibility = "excluded_non_expense"
        business_category = "Reward / Redemption"
        category_source = "account_activity_rule"
    elif is_credit:
        transaction_type = "merchant_credit"
        eligibility = "excluded_non_expense"
        business_category = "Refund / Merchant Credit"
        category_source = "credit_transaction_rule"
    elif is_fee_or_interest:
        transaction_type = "card_fee_interest"
        eligibility = "excluded_non_expense"
        business_category = "Card Fees / Interest"
        category_source = "card_program_fee_rule"
    else:
        transaction_type = "expense"
        eligibility = "eligible_expense"
        business_category, category_source = infer_business_category(transaction, text, mcc, existing_category)

    policy_category = (
        "Excluded Non-Expense"
        if eligibility == "excluded_non_expense"
        else "Finance Review" if eligibility == "finance_review" else business_category
    )

    return {
        "transaction_type": transaction_type,
        "transaction_eligibility": eligibility,
        "network_category_code": transaction_code or mcc or None,
        "business_category": business_category,
        "policy_category": policy_category,
        "category_source": category_source,
        "normalized_merchant_family": normalized_merchant_family(transaction),
        "mcc_description": MCC_DESCRIPTIONS.get(mcc),
        "amount_bucket": amount_bucket(to_float(transaction.get("amount_cad")), is_credit),
        "posting_delay_days": posting_delay_days(transaction.get("transaction_date"), transaction.get("posting_date")),
        "is_account_activity": bool(route["is_account_activity"]) if route else is_account_payment or is_reward,
        "is_credit_or_refund": is_credit,
        "is_foreign_transaction": is_foreign_transaction(transaction.get("merchant_country")),
    }


def infer_business_category(
    transaction: dict[str, Any],
    text: str,
    mcc: str,
    existing_category: str,
) -> tuple[str, str]:
    merchant = str(transaction.get("normalized_merchant_name") or transaction.get("merchant_name") or "").upper()
    source_category = str(transaction.get("source_category") or "").upper()

    if contains_any(text, PERMIT_KEYWORDS) or mcc == "9399":
        return "Permits / Government Fees", "permit_rule"
    if "AVETTA" in text:
        return "Vendor / Compliance", "merchant_rule"
    if contains_any(merchant, ["UBER", "LYFT", "TAXI"]):
        return "Ground Transportation", "merchant_rule"
    if contains_any(merchant, ["ENTERPRISE", "NATIONAL CAR", "HERTZ", "AVIS", "BUDGET RENT A CAR"]):
        return "Car / Truck Rental", "merchant_rule"
    if "TRUCKPARKINGCLUB" in text:
        return "Parking / Tolls", "merchant_rule"
    for rule in MERCHANT_CATEGORY_RULES:
        if contains_any(text, rule["keywords"]) or contains_any(merchant, rule["keywords"]):
            return rule["category"], rule["source"]
    if source_category == "FUEL" or contains_any(
        text,
        ["LOVE'S", "PILOT", "FLYING J", "CENEX", "PETRO", "KWIK TRIP", "CIRCLE K", "SHELL", "ESSO", "CHEVRON"],
    ):
        return "Fuel", "fuel_rule"
    if existing_category and existing_category != "Uncategorized":
        return existing_category, "existing_category"
    return "Uncategorized", "fallback"


def iter_transaction_batches(batch_size: int, limit: int | None = None):
    start = 0
    remaining = limit

    while True:
        requested_size = batch_size if remaining is None else min(batch_size, remaining)
        if requested_size <= 0:
            break

        batch = (
            get_supabase_client()
            .table("transactions")
            .select("*")
            .order("created_at")
            .range(start, start + requested_size - 1)
            .execute()
            .data
            or []
        )

        if not batch:
            break

        yield batch

        if remaining is not None:
            remaining -= len(batch)
            if remaining <= 0:
                break
        if len(batch) < requested_size:
            break

        start += len(batch)


def searchable_text(transaction: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in [
            transaction.get("description"),
            transaction.get("merchant_name"),
            transaction.get("normalized_merchant_name"),
            transaction.get("source_category"),
            transaction.get("business_category"),
            transaction.get("normalized_category"),
        ]
        if value
    ).upper()


def normalized_merchant_family(transaction: dict[str, Any]) -> str | None:
    primary_merchant = str(transaction.get("normalized_merchant_name") or transaction.get("merchant_name") or "").upper().strip()
    searchable = " ".join(
        part
        for part in [
            str(transaction.get("normalized_merchant_name") or "").upper().strip(),
            str(transaction.get("merchant_name") or "").upper().strip(),
            str(transaction.get("description") or "").upper().strip(),
        ]
        if part
    )
    if not primary_merchant:
        return None
    if "POINT REDEMPTION" in searchable:
        return "POINT REDEMPTION"
    if "CWB EFT PAYMENT" in searchable:
        return "CWB EFT PAYMENT"
    for keywords, family in MERCHANT_FAMILY_RULES:
        if contains_any(searchable, keywords):
            return family

    merchant = re.sub(r"^[0-9]+\\s+", "", primary_merchant)
    merchant = re.sub(r"\\b[0-9]{2,}\\b", "", merchant)
    merchant = re.sub(r"\\s+", " ", merchant.replace("*", " ")).strip(" -")
    return merchant or None


def posting_delay_days(transaction_date: Any, posting_date: Any) -> int | None:
    parsed_transaction_date = parse_date(transaction_date)
    parsed_posting_date = parse_date(posting_date)
    if not parsed_transaction_date or not parsed_posting_date:
        return None
    return (parsed_posting_date - parsed_transaction_date).days


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)[:10]).date()


def amount_bucket(amount: float, is_credit: bool) -> str:
    if is_credit:
        return "credit"
    if amount < 50:
        return "under_50"
    if amount < 500:
        return "50_to_499"
    if amount < 1000:
        return "500_to_999"
    return "1000_plus"


def is_foreign_transaction(country: Any) -> bool:
    normalized = str(country or "").strip().upper()
    return bool(normalized) and normalized not in {"CA", "CAN", "CANADA"}


def clean_code(value: Any) -> str:
    normalized = str(value or "").strip()
    if normalized.isdigit():
        return str(int(normalized))
    return normalized


def contains_any(value: str, keywords: list[str]) -> bool:
    return any(keyword in value for keyword in keywords)


def normalize_existing_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def normalized_batch_size(batch_size: int) -> int:
    return max(1, min(int(batch_size or PAGE_SIZE), 1000))


def to_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
