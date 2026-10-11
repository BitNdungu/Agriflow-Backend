
import pytest

from validation import validate_problem_report_payload


VALID_REPORT = {
    "category": "Pest infestation",
    "crop_affected": "Tomatoes",
    "subcounty": "Kiharu",
    "ward": "Township",
    "description": "White insects are damaging the tomato leaves.",
}


def test_valid_report_returns_normalized_data():
    data, errors = validate_problem_report_payload(VALID_REPORT)

    assert errors == {}
    assert data == VALID_REPORT


def test_report_text_is_trimmed():
    payload = {
        **VALID_REPORT,
        "category": " Pest infestation ",
        "crop_affected": " Tomatoes ",
        "subcounty": " Kiharu ",
        "ward": " Township ",
        "description": " Leaves are being damaged. ",
    }

    data, errors = validate_problem_report_payload(payload)

    assert errors == {}
    assert data["category"] == "Pest infestation"
    assert data["crop_affected"] == "Tomatoes"
    assert data["subcounty"] == "Kiharu"
    assert data["ward"] == "Township"
    assert data["description"] == "Leaves are being damaged."


@pytest.mark.parametrize("category", ["Unknown problem", None])
def test_invalid_category_is_rejected(category):
    payload = {**VALID_REPORT, "category": category}

    data, errors = validate_problem_report_payload(payload)

    assert "category" in errors


def test_unknown_subcounty_is_rejected():
    payload = {**VALID_REPORT, "subcounty": "Unknown place"}

    data, errors = validate_problem_report_payload(payload)

    assert "subcounty" in errors


def test_blank_description_is_rejected():
    payload = {**VALID_REPORT, "description": "   "}

    data, errors = validate_problem_report_payload(payload)

    assert "description" in errors


def test_description_over_2000_characters_is_rejected():
    payload = {**VALID_REPORT, "description": "A" * 2001}

    data, errors = validate_problem_report_payload(payload)

    assert "description" in errors


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("crop_affected", "C" * 121),
        ("ward", "W" * 101),
    ],
)
def test_optional_text_limits_are_enforced(field, value):
    payload = {**VALID_REPORT, field: value}

    data, errors = validate_problem_report_payload(payload)

    assert field in errors
