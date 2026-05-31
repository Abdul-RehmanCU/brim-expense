from app.schemas.transactions import TransactionImportRequest, TransactionImportRow
from app.services import transactions_service


def test_import_transactions_applies_authoritative_enrichment_and_skips_duplicates(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(transactions_service, "_fetch_existing_fingerprints", lambda fingerprints: {"dup-1"})

    def fake_persist(rows, *, source_file_name, import_batch_id):
        captured["rows"] = rows
        captured["source_file_name"] = source_file_name
        captured["import_batch_id"] = import_batch_id

    monkeypatch.setattr(transactions_service, "_persist_import_rows", fake_persist)

    request = TransactionImportRequest(
        source_file_name="demo.csv",
        rows=[
            TransactionImportRow(
                source_row_number=2,
                source_fingerprint="fp-1",
                raw_payload={"Transaction Date": "2026-05-01"},
                transaction={
                    "transaction_code": "3001",
                    "description": "MNDOT OSOW PERMITS FEE ATLANTA GA",
                    "source_category": "Fuel",
                    "business_category": "Fuel",
                    "normalized_category": "Fuel",
                    "category_confidence": 0.42,
                    "posting_date": "2026-05-12",
                    "transaction_date": "2026-05-10",
                    "merchant_name": "MNDOT OSOW PERMITS FEE",
                    "normalized_merchant_name": "MNDOT OSOW PERMITS FEE",
                    "amount_original": 227.9,
                    "amount_cad": 227.9,
                    "debit_credit": "debit",
                    "merchant_category_code": "5542",
                    "merchant_country": "USA",
                    "employee_id": "emp-1",
                    "department_id": "dept-1",
                },
            ),
            TransactionImportRow(
                source_row_number=3,
                source_fingerprint="dup-1",
                raw_payload={"Transaction Date": "2026-05-02"},
                transaction={
                    "amount_cad": 10,
                    "debit_credit": "debit",
                },
            ),
        ],
    )

    response = transactions_service.import_transactions(request)

    assert response.inserted_count == 1
    assert response.skipped_duplicate_count == 1
    assert response.validation.row_count == 1
    assert response.authoritative_enrichment_applied == 2
    assert captured["source_file_name"] == "demo.csv"
    persisted_rows = captured["rows"]
    assert isinstance(persisted_rows, list)
    assert persisted_rows[0]["transaction"]["business_category"] == "Permits / Government Fees"
    assert persisted_rows[0]["transaction"]["policy_category"] == "Permits / Government Fees"


def test_import_transactions_dry_run_skips_persistence(monkeypatch):
    def fail_persist(*args, **kwargs):
        raise AssertionError("dry run should not persist")

    monkeypatch.setattr(transactions_service, "_fetch_existing_fingerprints", lambda fingerprints: set())
    monkeypatch.setattr(transactions_service, "_persist_import_rows", fail_persist)

    response = transactions_service.import_transactions(
        TransactionImportRequest(
            dry_run=True,
            rows=[
                TransactionImportRow(
                    source_row_number=2,
                    source_fingerprint="fp-1",
                    raw_payload={},
                    transaction={"amount_cad": 12.5, "debit_credit": "debit"},
                )
            ],
        )
    )

    assert response.inserted_count == 0
    assert response.persisted is False
    assert "Dry run only." in response.warnings[0]
