from fastapi.testclient import TestClient

from app.main import app
from app.schemas.risk import RiskScanSummary, RiskScoreItem, RiskSignal
from app.services.risk_service import ENGINE_VERSION


def test_risk_scan_endpoint_accepts_filters(monkeypatch):
    def fake_scan(request):
        assert request.employee_id == "employee_1"
        assert request.dry_run is True
        assert request.anomaly_model == "sklearn"
        assert request.detector_profile == "full"
        return RiskScanSummary(
            total_scanned=2,
            scored=2,
            persisted=0,
            high_or_critical=1,
            signal_counts={"duplicate_charge": 2},
            duration_ms=12,
            engine_version=ENGINE_VERSION,
            dry_run=True,
        )

    monkeypatch.setattr("app.routers.risk.risk_scan_transactions", fake_scan)

    response = TestClient(app).post(
        "/risk/scan",
        json={
            "employee_id": "employee_1",
            "dry_run": True,
            "anomaly_model": "sklearn",
            "detector_profile": "full",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_scanned"] == 2
    assert payload["signal_counts"]["duplicate_charge"] == 2
    assert payload["dry_run"] is True


def test_risk_scores_endpoint_returns_signals(monkeypatch):
    def fake_list_scores(min_level, limit, signal_type=None, department_id=None, employee_id=None):
        assert min_level == "high"
        assert limit == 25
        assert signal_type == "duplicate_charge"
        return [
            RiskScoreItem(
                id="risk_1",
                transaction_id="txn_1",
                risk_score=65,
                risk_level="high",
                signals=[
                    RiskSignal(
                        type="duplicate_charge",
                        severity="high",
                        message="Possible duplicate charge.",
                        evidence={"matched_transaction_ids": ["txn_1", "txn_2"]},
                    )
                ],
                employee="Sarah Chen",
                department="Marketing",
                transaction_date="2026-05-01",
                merchant="STAPLES",
                amount_cad=125,
                category="Office Supplies",
            )
        ]

    monkeypatch.setattr("app.routers.risk.risk_list_scores", fake_list_scores)

    response = TestClient(app).get("/risk/scores?min_level=high&limit=25&signal_type=duplicate_charge")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["transaction_id"] == "txn_1"
    assert payload[0]["signals"][0]["type"] == "duplicate_charge"
