
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app import create_app


MAX_UPLOAD_BYTES = 7 * 1024 * 1024


@pytest.fixture()
def client(tmp_path):
    test_app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite3"),
        "PROBLEM_REPORT_UPLOAD_DIR": str(
            tmp_path / "uploads" / "problem_reports"
        ),
    })

    with test_app.test_client() as test_client:
        yield test_client


def register_farmer(client):
    response = client.post(
        "/api/farmers",
        json={
            "full_name": "Jane Wanjiku",
            "phone": "0712345678",
            "county": "Murang'a County",
            "subcounty": "Kandara",
            "ward": "Muruka",
            "farm_size_acres": 2.5,
            "main_enterprise": "Avocado",
        },
    )

    assert response.status_code == 201
    return response.get_json()["farmer"]


def register_problem_report(client, farmer_id):
    response = client.post(
        f"/api/farmers/{farmer_id}/problem-reports",
        json={
            "category": "Pest infestation",
            "crop_affected": "Tomatoes",
            "subcounty": "Kiharu",
            "ward": "Township",
            "description": "Insects are damaging the leaves.",
        },
    )

    assert response.status_code == 201
    return response.get_json()["report"]


def make_image_bytes(
    image_format="PNG",
    size=(64, 48),
    color=(220, 40, 40),
):
    output = BytesIO()

    Image.new("RGB", size, color).save(
        output,
        format=image_format,
    )

    return output.getvalue()


def photo_url(farmer_id, report_id):
    return (
        f"/api/farmers/{farmer_id}"
        f"/problem-reports/{report_id}/photo"
    )


def post_photo(
    client,
    farmer_id,
    report_id,
    image_bytes=None,
    filename="evidence.png",
):
    if image_bytes is None:
        image_bytes = make_image_bytes()

    return client.post(
        photo_url(farmer_id, report_id),
        data={
            "photo": (
                BytesIO(image_bytes),
                filename,
            ),
        },
        content_type="multipart/form-data",
    )


def test_upload_photo_normalizes_and_stores_jpeg(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    response = post_photo(
        client,
        farmer["id"],
        report["id"],
    )

    assert response.status_code == 201

    photo = response.get_json()["photo"]

    assert photo["id"] > 0
    assert photo["report_id"] == report["id"]
    assert photo["media_type"] == "image/jpeg"
    assert photo["size_bytes"] > 0
    assert photo["width"] == 64
    assert photo["height"] == 48
    assert photo["url"] == photo_url(
        farmer["id"],
        report["id"],
    )

    upload_dir = Path(
        client.application.config["PROBLEM_REPORT_UPLOAD_DIR"]
    )
    files = list(upload_dir.glob("*.jpg"))

    assert len(files) == 1
    assert len(files[0].read_bytes()) == photo["size_bytes"]


def test_retrieve_uploaded_photo_serves_valid_jpeg(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    upload = post_photo(
        client,
        farmer["id"],
        report["id"],
    )

    assert upload.status_code == 201

    response = client.get(
        photo_url(farmer["id"], report["id"])
    )

    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"

    with Image.open(BytesIO(response.data)) as image:
        assert image.format == "JPEG"
        assert image.size == (64, 48)


def test_put_replaces_existing_photo_and_removes_old_file(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    first_upload = post_photo(
        client,
        farmer["id"],
        report["id"],
    )

    assert first_upload.status_code == 201
    first_photo = first_upload.get_json()["photo"]

    upload_dir = Path(
        client.application.config["PROBLEM_REPORT_UPLOAD_DIR"]
    )
    old_file = next(upload_dir.glob("*.jpg"))

    replacement_bytes = make_image_bytes(
        image_format="PNG",
        size=(120, 80),
        color=(40, 180, 70),
    )

    replacement = client.put(
        photo_url(farmer["id"], report["id"]),
        data={
            "photo": (
                BytesIO(replacement_bytes),
                "replacement.png",
            ),
        },
        content_type="multipart/form-data",
    )

    assert replacement.status_code == 200

    updated_photo = replacement.get_json()["photo"]

    assert updated_photo["id"] == first_photo["id"]
    assert updated_photo["width"] == 120
    assert updated_photo["height"] == 80

    files = list(upload_dir.glob("*.jpg"))

    assert len(files) == 1
    assert files[0] != old_file
    assert not old_file.exists()

    retrieved = client.get(
        photo_url(farmer["id"], report["id"])
    )

    with Image.open(BytesIO(retrieved.data)) as image:
        assert image.size == (120, 80)


def test_post_duplicate_photo_returns_conflict(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    first = post_photo(
        client,
        farmer["id"],
        report["id"],
    )

    assert first.status_code == 201

    duplicate = post_photo(
        client,
        farmer["id"],
        report["id"],
    )

    assert duplicate.status_code == 409


def test_put_without_existing_photo_returns_404(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    response = client.put(
        photo_url(farmer["id"], report["id"]),
        data={
            "photo": (
                BytesIO(make_image_bytes()),
                "evidence.png",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 404


def test_upload_rejects_invalid_image_bytes(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    response = post_photo(
        client,
        farmer["id"],
        report["id"],
        image_bytes=b"this is not a real image",
    )

    assert response.status_code == 400


def test_upload_rejects_unsupported_gif(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    response = post_photo(
        client,
        farmer["id"],
        report["id"],
        image_bytes=make_image_bytes(image_format="GIF"),
        filename="evidence.gif",
    )

    assert response.status_code == 400


def test_upload_rejects_missing_photo_field(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    response = client.post(
        photo_url(farmer["id"], report["id"]),
        data={},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400


def test_upload_rejects_oversized_file(client):
    farmer = register_farmer(client)
    report = register_problem_report(client, farmer["id"])

    oversized_bytes = b"x" * (MAX_UPLOAD_BYTES + 1)

    response = post_photo(
        client,
        farmer["id"],
        report["id"],
        image_bytes=oversized_bytes,
    )

    assert response.status_code == 413


def test_upload_rejects_missing_report(client):
    farmer = register_farmer(client)

    response = post_photo(
        client,
        farmer["id"],
        9999,
    )

    assert response.status_code == 404


def test_photo_cannot_be_retrieved_under_another_farmer(client):
    first_farmer = register_farmer(client)
    second_farmer = register_farmer(client)

    report = register_problem_report(
        client,
        first_farmer["id"],
    )

    upload = post_photo(
        client,
        first_farmer["id"],
        report["id"],
    )

    assert upload.status_code == 201

    response = client.get(
        photo_url(second_farmer["id"], report["id"])
    )

    assert response.status_code == 404
