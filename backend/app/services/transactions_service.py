from collections.abc import Iterable
from uuid import uuid4

from app.database.supabase_client import get_supabase_client
from app.schemas.data_quality import DataQualitySummary, DataQualityValidationResponse, GreatExpectationsAudit
from app.schemas.transactions import (
    TransactionImportRequest,
    TransactionImportRow,
    TransactionImportResponse,
    TransactionEnrichmentRequest,
    TransactionEnrichmentResponse,
    TransactionResetResponse,
    TransactionsSummaryResponse,
)
from app.schemas.data_quality import DataQualityValidationRequest
from app.services.data_quality_service import validate_transaction_dataset
from app.services.transaction_enrichment import build_transaction_enrichment, enrich_existing_transactions

DELETE_BATCH_SIZE = 500
FETCH_BATCH_SIZE = 1000
INSERT_BATCH_SIZE = 500


def _count_table(table_name: str) -> int:
    response = get_supabase_client().table(table_name).select("*", count="exact", head=True).execute()
    count = getattr(response, "count", None)

    if count is None:
        return 0

    return int(count)


def get_transactions_summary() -> TransactionsSummaryResponse:
    return TransactionsSummaryResponse(
        raw_transaction_count=_count_table("raw_transactions"),
        normalized_transaction_count=_count_table("transactions"),
        employee_count=_count_table("employees"),
        department_count=_count_table("departments"),
    )


def enrich_transactions(request: TransactionEnrichmentRequest | None = None) -> TransactionEnrichmentResponse:
    return enrich_existing_transactions(request)


def validate_transaction_data_quality(request: DataQualityValidationRequest) -> DataQualityValidationResponse:
    return validate_transaction_dataset(request.rows, run_great_expectations=request.run_great_expectations)


def import_transactions(request: TransactionImportRequest) -> TransactionImportResponse:
    import_batch_id = str(uuid4())
    authoritative_rows = [_prepare_authoritative_import_row(row) for row in request.rows]
    existing_fingerprints = _fetch_existing_fingerprints(row["source_fingerprint"] for row in authoritative_rows)
    rows_to_insert = [
        row for row in authoritative_rows if row["source_fingerprint"] not in existing_fingerprints
    ]
    validation_rows = [row["transaction"] for row in rows_to_insert]
    validation = (
        validate_transaction_dataset(validation_rows, run_great_expectations=request.run_great_expectations)
        if request.run_data_quality
        else _empty_data_quality_response(len(validation_rows))
    )
    warnings: list[str] = []

    skipped_duplicate_count = len(authoritative_rows) - len(rows_to_insert)
    if skipped_duplicate_count:
        warnings.append(
            f"Skipped {skipped_duplicate_count} row(s) because their source fingerprint already exists."
        )
    if request.dry_run:
        warnings.append("Dry run only. No rows were persisted.")

    if rows_to_insert and not request.dry_run:
        _persist_import_rows(rows_to_insert, source_file_name=request.source_file_name, import_batch_id=import_batch_id)

    return TransactionImportResponse(
        inserted_count=0 if request.dry_run else len(rows_to_insert),
        skipped_duplicate_count=skipped_duplicate_count,
        import_batch_id=import_batch_id,
        validation=validation,
        persisted=not request.dry_run,
        authoritative_enrichment_applied=len(authoritative_rows),
        warnings=warnings,
    )


def clear_transactions() -> TransactionResetResponse:
    transaction_rows = _fetch_all_rows("transactions", "id, raw_transaction_id")
    transaction_ids = [str(row["id"]) for row in transaction_rows if row.get("id")]
    raw_transaction_rows = _fetch_all_rows("raw_transactions", "id")
    raw_transaction_ids = [str(row["id"]) for row in raw_transaction_rows if row.get("id")]
    report_item_rows = _fetch_rows_by_values(
        "expense_report_items",
        "transaction_id",
        transaction_ids,
        "id, report_id, transaction_id",
    )
    report_ids = [str(row["report_id"]) for row in report_item_rows if row.get("report_id")]

    deleted_expense_report_items = _delete_rows_by_values("expense_report_items", "transaction_id", transaction_ids)
    deleted_approval_requests = _delete_rows_by_values("approval_requests", "transaction_id", transaction_ids)
    deleted_risk_scores = _delete_rows_by_values("risk_scores", "transaction_id", transaction_ids)
    deleted_violations = _delete_rows_by_values("violations", "transaction_id", transaction_ids)
    deleted_policy_checks = _delete_rows_by_values("policy_checks", "transaction_id", transaction_ids)
    deleted_receipts = _delete_rows_by_values("receipts", "transaction_id", transaction_ids)
    deleted_preapprovals = _delete_rows_by_values("preapprovals", "transaction_id", transaction_ids)
    deleted_transactions = _delete_rows_by_values("transactions", "id", transaction_ids)
    deleted_raw_transactions = _delete_rows_by_values("raw_transactions", "id", raw_transaction_ids)

    orphaned_report_ids = _find_orphaned_synthetic_report_ids(report_ids)
    deleted_expense_reports = _delete_rows_by_values("expense_reports", "id", orphaned_report_ids)

    return TransactionResetResponse(
        deleted_transactions=deleted_transactions,
        deleted_raw_transactions=deleted_raw_transactions,
        deleted_receipts=deleted_receipts,
        deleted_preapprovals=deleted_preapprovals,
        deleted_policy_checks=deleted_policy_checks,
        deleted_violations=deleted_violations,
        deleted_risk_scores=deleted_risk_scores,
        deleted_approval_requests=deleted_approval_requests,
        deleted_expense_report_items=deleted_expense_report_items,
        deleted_expense_reports=deleted_expense_reports,
    )


def _prepare_authoritative_import_row(row: TransactionImportRow) -> dict:
    transaction = dict(row.transaction)
    transaction.update(build_transaction_enrichment(transaction))
    if not transaction.get("normalized_category"):
        transaction["normalized_category"] = transaction.get("business_category") or "Uncategorized"
    transaction["source_row_number"] = row.source_row_number
    transaction["source_fingerprint"] = row.source_fingerprint

    return {
        "source_row_number": row.source_row_number,
        "source_fingerprint": row.source_fingerprint,
        "raw_payload": dict(row.raw_payload),
        "transaction": transaction,
    }


def _fetch_existing_fingerprints(fingerprints: Iterable[str]) -> set[str]:
    existing_fingerprints: set[str] = set()
    client = get_supabase_client()

    for chunk in _chunked(_unique(fingerprints), DELETE_BATCH_SIZE):
        rows = (
            client.table("raw_transactions")
            .select("source_fingerprint")
            .in_("source_fingerprint", chunk)
            .execute()
            .data
            or []
        )
        for row in rows:
            fingerprint = row.get("source_fingerprint")
            if fingerprint:
                existing_fingerprints.add(str(fingerprint))

    return existing_fingerprints


def _persist_import_rows(rows: list[dict], *, source_file_name: str | None, import_batch_id: str) -> None:
    if not rows:
        return

    client = get_supabase_client()
    raw_id_by_fingerprint: dict[str, str] = {}

    for chunk in _chunked(rows, INSERT_BATCH_SIZE):
        raw_rows = (
            client.table("raw_transactions")
            .insert(
                [
                    {
                        "source_file_name": source_file_name,
                        "source_row_number": row["source_row_number"],
                        "source_fingerprint": row["source_fingerprint"],
                        "raw_payload": row["raw_payload"],
                        "import_batch_id": import_batch_id,
                        "synthetic_context_assigned": bool(row["transaction"].get("employee_id")),
                    }
                    for row in chunk
                ]
            )
            .select("id, source_fingerprint")
            .execute()
            .data
            or []
        )

        for raw_row in raw_rows:
            raw_id = raw_row.get("id")
            fingerprint = raw_row.get("source_fingerprint")
            if raw_id and fingerprint:
                raw_id_by_fingerprint[str(fingerprint)] = str(raw_id)

    for chunk in _chunked(rows, INSERT_BATCH_SIZE):
        client.table("transactions").insert(
            [_transaction_insert_payload(row["transaction"], raw_id_by_fingerprint.get(row["source_fingerprint"])) for row in chunk]
        ).execute()


def _transaction_insert_payload(transaction: dict, raw_transaction_id: str | None) -> dict:
    return {
        "raw_transaction_id": raw_transaction_id,
        "employee_id": transaction.get("employee_id"),
        "department_id": transaction.get("department_id"),
        "transaction_code": transaction.get("transaction_code"),
        "transaction_type": transaction.get("transaction_type"),
        "transaction_eligibility": transaction.get("transaction_eligibility"),
        "description": transaction.get("description"),
        "source_category": transaction.get("source_category"),
        "network_category_code": transaction.get("network_category_code"),
        "business_category": transaction.get("business_category"),
        "policy_category": transaction.get("policy_category"),
        "category_source": transaction.get("category_source"),
        "normalized_category": transaction.get("normalized_category"),
        "normalized_merchant_family": transaction.get("normalized_merchant_family"),
        "category_confidence": transaction.get("category_confidence"),
        "amount_bucket": transaction.get("amount_bucket"),
        "posting_delay_days": transaction.get("posting_delay_days"),
        "is_account_activity": transaction.get("is_account_activity"),
        "is_credit_or_refund": transaction.get("is_credit_or_refund"),
        "is_foreign_transaction": transaction.get("is_foreign_transaction"),
        "posting_date": transaction.get("posting_date"),
        "transaction_date": transaction.get("transaction_date"),
        "merchant_name": transaction.get("merchant_name"),
        "normalized_merchant_name": transaction.get("normalized_merchant_name"),
        "amount_original": transaction.get("amount_original"),
        "amount_cad": transaction.get("amount_cad"),
        "debit_credit": transaction.get("debit_credit"),
        "merchant_category_code": transaction.get("merchant_category_code"),
        "merchant_city": transaction.get("merchant_city"),
        "merchant_country": transaction.get("merchant_country"),
        "merchant_postal_code": transaction.get("merchant_postal_code"),
        "merchant_region": transaction.get("merchant_region"),
        "conversion_rate": transaction.get("conversion_rate"),
        "synthetic_assignment": bool(transaction.get("employee_id")),
        "business_purpose": transaction.get("business_purpose"),
        "guest_names": transaction.get("guest_names"),
    }


def _empty_data_quality_response(row_count: int) -> DataQualityValidationResponse:
    return DataQualityValidationResponse(
        row_count=row_count,
        findings=[],
        summary=DataQualitySummary(row_count=row_count),
        great_expectations=GreatExpectationsAudit(),
    )


def _fetch_all_rows(table_name: str, columns: str, order_column: str = "created_at") -> list[dict]:
    client = get_supabase_client()
    rows: list[dict] = []
    start = 0

    while True:
        batch = (
            client.table(table_name)
            .select(columns)
            .order(order_column)
            .range(start, start + FETCH_BATCH_SIZE - 1)
            .execute()
            .data
            or []
        )
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < FETCH_BATCH_SIZE:
            break
        start += FETCH_BATCH_SIZE

    return rows


def _fetch_rows_by_values(table_name: str, column_name: str, values: Iterable[str], columns: str) -> list[dict]:
    rows: list[dict] = []
    client = get_supabase_client()

    for chunk in _chunked(_unique(values), DELETE_BATCH_SIZE):
        batch = client.table(table_name).select(columns).in_(column_name, chunk).execute().data or []
        rows.extend(batch)

    return rows


def _find_orphaned_synthetic_report_ids(report_ids: Iterable[str]) -> list[str]:
    unique_report_ids = _unique(report_ids)
    if not unique_report_ids:
        return []

    reports = _fetch_rows_by_values("expense_reports", "id", unique_report_ids, "id, synthetic")
    remaining_items = _fetch_rows_by_values("expense_report_items", "report_id", unique_report_ids, "report_id")
    remaining_report_ids = {str(item["report_id"]) for item in remaining_items if item.get("report_id")}

    return [
        str(report["id"])
        for report in reports
        if report.get("id") and report.get("synthetic") and str(report["id"]) not in remaining_report_ids
    ]


def _delete_rows_by_values(table_name: str, column_name: str, values: Iterable[str]) -> int:
    deleted = 0
    client = get_supabase_client()

    for chunk in _chunked(_unique(values), DELETE_BATCH_SIZE):
        rows = client.table(table_name).delete().in_(column_name, chunk).execute().data or []
        deleted += len(rows)

    return deleted


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _chunked(values: list[str], chunk_size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), chunk_size):
        yield values[index : index + chunk_size]
