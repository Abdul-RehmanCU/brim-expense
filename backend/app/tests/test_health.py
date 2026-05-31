from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "brim-expense-copilot-backend",
    }


def test_root_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "brim-expense-copilot-backend",
    }


def test_favicon_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/favicon.ico")

    assert response.status_code == 204
