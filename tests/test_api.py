
import sqlite3

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path):
    test_app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite3"),
    })

    with test_app.test_client() as test_client:
        yield test_client


def valid_farmer_payload():
    return {
        "full_name": "Jane Wanjiku",
        "phone": "0712345678",
        "county": "A county supplied by the client",
        "subcounty": "Kandara",
        "ward": "Muruka",
        "farm_size_acres": 2.5,
        "main_enterprise": "Avocado",
    }


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
        "version": "0.2.0",
    }


def test_unknown_endpoint_returns_404(client):
    response = client.get("/api/not-a-real-endpoint")

    assert response.status_code == 404


def test_create_farmer_profile(client):
    response = client.post(
        "/api/farmers",
        json=valid_farmer_payload(),
    )

    assert response.status_code == 201

    farmer = response.get_json()["farmer"]

    assert farmer["id"] > 0
    assert farmer["full_name"] == "Jane Wanjiku"
    assert farmer["phone"] == "0712345678"

    # The server, not the submitted payload, determines the county.
    assert farmer["county"] == "Murang'a County"

    assert farmer["subcounty"] == "Kandara"
    assert farmer["ward"] == "Muruka"
    assert farmer["farm_size_acres"] == 2.5
    assert farmer["main_enterprise"] == "Avocado"
    assert farmer["created_at"].endswith("Z")


def test_created_farmer_is_persisted(client):
    response = client.post(
        "/api/farmers",
        json=valid_farmer_payload(),
    )

    assert response.status_code == 201

    farmer_id = response.get_json()["farmer"]["id"]

    connection = sqlite3.connect(
        client.application.config["DATABASE"]
    )

    try:
        row = connection.execute(
            """
            SELECT full_name, subcounty, farm_size_acres
            FROM farmers
            WHERE id = ?
            """,
            (farmer_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] == "Jane Wanjiku"
    assert row[1] == "Kandara"
    assert row[2] == 2.5


def test_missing_required_field_is_rejected(client):
    payload = valid_farmer_payload()
    del payload["full_name"]

    response = client.post(
        "/api/farmers",
        json=payload,
    )

    assert response.status_code == 400
    assert "full_name" in response.get_json()["fields"]


def test_unknown_subcounty_is_rejected(client):
    payload = valid_farmer_payload()
    payload["subcounty"] = "Nairobi"

    response = client.post(
        "/api/farmers",
        json=payload,
    )

    assert response.status_code == 400
    assert "subcounty" in response.get_json()["fields"]


def test_nonpositive_farm_size_is_rejected(client):
    payload = valid_farmer_payload()
    payload["farm_size_acres"] = 0

    response = client.post(
        "/api/farmers",
        json=payload,
    )

    assert response.status_code == 400
    assert "farm_size_acres" in response.get_json()["fields"]


def test_non_json_request_is_rejected(client):
    response = client.post(
        "/api/farmers",
        data="not json",
        content_type="text/plain",
    )

    assert response.status_code == 415
