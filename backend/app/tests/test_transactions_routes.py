from fastapi.testclient import TestClient

from app.main import app
from app.schemas.data_quality import DataQualitySummary, DataQualityValidationResponse, GreatExpectationsAudit
from app.schemas.transactions import (
    TransactionEnrichmentResponse,
    TransactionImportResponse,
    TransactionResetResponse,
)


def test_enrich_existing_transactions_endpoint(monkeypatch):
    def fake_enrich_transactions(request):
        assert request.batch_size == 250
        return TransactionEnrichmentResponse(total_seen=2, updated=1, skipped=1, errors=0, duration_ms=20, batch_count=1)

    monkeypatch.setattr("app.routers.transactions.enrich_transactions", fake_enrich_transactions)

    response = TestClient(app).post("/transactions/enrich-existing", json={"batch_size": 250})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_seen"] == 2
    assert payload["updated"] == 1
    assert payload["duration_ms"] == 20


def test_validate_data_quality_endpoint(monkeypatch):
    def fake_validate_data_quality(request):
        assert request.rows[0]["id"] == "txn_1"
        assert request.run_great_expectations is False
        return DataQualityValidationResponse(
            row_count=1,
            findings=[],
            summary=DataQualitySummary(row_count=1),
            great_expectations=GreatExpectationsAudit(),
        )

    monkeypatch.setattr("app.routers.transactions.validate_transaction_data_quality", fake_validate_data_quality)

    response = TestClient(app).post(
        "/transactions/data-quality",
        json={"rows": [{"id": "txn_1"}], "run_great_expectations": False},
    )

    assert response.status_code == 200
    assert response.json()["row_count"] == 1


def test_import_transactions_endpoint(monkeypatch):
    def fake_import_transactions(request):
        assert request.source_file_name == "demo.csv"
        assert request.rows[0].source_fingerprint == "fp-1"
        return TransactionImportResponse(
            inserted_count=1,
            skipped_duplicate_count=0,
            import_batch_id="batch-1",
            validation=DataQualityValidationResponse(
                row_count=1,
                findings=[],
                summary=DataQualitySummary(row_count=1),
                great_expectations=GreatExpectationsAudit(),
            ),
            persisted=True,
            authoritative_enrichment_applied=1,
            warnings=[],
        )

    monkeypatch.setattr("app.routers.transactions.import_transactions", fake_import_transactions)

    response = TestClient(app).post(
        "/transactions/import",
        json={
            "source_file_name": "demo.csv",
            "rows": [
                {
                    "source_row_number": 2,
                    "source_fingerprint": "fp-1",
                    "raw_payload": {"Transaction Date": "2026-05-01"},
                    "transaction": {"amount_cad": 120.5, "debit_credit": "debit"},
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["inserted_count"] == 1
    assert payload["validation"]["row_count"] == 1
    assert payload["authoritative_enrichment_applied"] == 1


def test_reset_transactions_endpoint(monkeypatch):
    def fake_clear_transactions():
        return TransactionResetResponse(
            deleted_transactions=4,
            deleted_raw_transactions=4,
            deleted_receipts=3,
            deleted_preapprovals=2,
            deleted_policy_checks=2,
            deleted_violations=2,
            deleted_risk_scores=1,
            deleted_approval_requests=1,
            deleted_expense_report_items=2,
            deleted_expense_reports=1,
        )

    monkeypatch.setattr("app.routers.transactions.clear_transactions", fake_clear_transactions)

    response = TestClient(app).delete("/transactions/reset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_transactions"] == 4
    assert payload["deleted_raw_transactions"] == 4
    assert payload["deleted_expense_reports"] == 1
