
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


def register_test_farmer(client):
    response = client.post(
        "/api/farmers",
        json=valid_farmer_payload(),
    )

    assert response.status_code == 201

    return response.get_json()["farmer"]


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
        "version": "0.3.0",
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


def test_get_farmer_profile(client):
    created = register_test_farmer(client)

    response = client.get(
        f"/api/farmers/{created['id']}"
    )

    assert response.status_code == 200
    assert response.get_json()["farmer"] == created


def test_get_missing_farmer_returns_404(client):
    response = client.get("/api/farmers/9999")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Farmer not found."


def test_update_farmer_profile(client):
    created = register_test_farmer(client)

    payload = {
        "full_name": "Jane Wanjiku Kamau",
        "phone": "0711111111",
        "subcounty": "Kiharu",
        "ward": "Township",
        "farm_size_acres": 3.75,
        "main_enterprise": "Coffee",
    }

    response = client.put(
        f"/api/farmers/{created['id']}",
        json=payload,
    )

    assert response.status_code == 200

    updated = response.get_json()["farmer"]

    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
    assert updated["full_name"] == "Jane Wanjiku Kamau"
    assert updated["phone"] == "0711111111"
    assert updated["subcounty"] == "Kiharu"
    assert updated["ward"] == "Township"
    assert updated["farm_size_acres"] == 3.75
    assert updated["main_enterprise"] == "Coffee"

    # Verify the updated values can be retrieved again.
    fetched = client.get(
        f"/api/farmers/{created['id']}"
    )

    assert fetched.status_code == 200
    assert fetched.get_json()["farmer"] == updated


def test_update_missing_farmer_returns_404(client):
    response = client.put(
        "/api/farmers/9999",
        json=valid_farmer_payload(),
    )

    assert response.status_code == 404


def test_update_rejects_invalid_subcounty(client):
    created = register_test_farmer(client)

    payload = valid_farmer_payload()
    payload["subcounty"] = "Nairobi"

    response = client.put(
        f"/api/farmers/{created['id']}",
        json=payload,
    )

    assert response.status_code == 400
    assert "subcounty" in response.get_json()["fields"]


def test_update_rejects_missing_required_fields(client):
    created = register_test_farmer(client)

    payload = valid_farmer_payload()
    del payload["full_name"]

    response = client.put(
        f"/api/farmers/{created['id']}",
        json=payload,
    )

    assert response.status_code == 400
    assert "full_name" in response.get_json()["fields"]


def test_update_rejects_non_json_request(client):
    created = register_test_farmer(client)

    response = client.put(
        f"/api/farmers/{created['id']}",
        data="not json",
        content_type="text/plain",
    )

    assert response.status_code == 415
