
import pytest

from app import app


@pytest.fixture()
def client():
    app.config.update(TESTING=True)

    with app.test_client() as test_client:
        yield test_client


def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200

    data = response.get_json()

    assert data["application"] == "MURANG'A AGRIFLOW"
    assert data["message"] == "Backend API is running"
    assert data["health_endpoint"] == "/api/health"


def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200

    assert response.get_json() == {
        "status": "ok",
        "service": "muranga-agriflow-api",
        "version": "0.1.0",
    }


def test_unknown_endpoint_returns_404(client):
    response = client.get("/api/not-a-real-endpoint")

    assert response.status_code == 404
