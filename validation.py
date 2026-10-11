
import math
import re
from datetime import datetime


VALID_SUBCOUNTIES = {
    "Gatanga",
    "Ithanga",
    "Kahuro",
    "Kandara",
    "Kangema",
    "Kigumo",
    "Mathioya",
    "Kiharu",
    "Maragua",
}


def validate_farmer_payload(payload):
    """Validate and normalize a complete farmer profile."""
    errors = {}

    # Full name
    raw_name = payload.get("full_name")

    if not isinstance(raw_name, str) or not raw_name.strip():
        errors["full_name"] = "A full name is required."
        full_name = ""
    else:
        full_name = raw_name.strip()

        if len(full_name) > 120:
            errors["full_name"] = (
                "Full name must be at most 120 characters."
            )

    # Phone number
    raw_phone = payload.get("phone")

    if not isinstance(raw_phone, str) or not raw_phone.strip():
        errors["phone"] = "A phone number is required."
        phone = ""
    else:
        phone = raw_phone.strip()
        digits = re.sub(r"\D", "", phone)

        if (
            len(phone) > 25
            or not re.fullmatch(r"[0-9+().\-\s]+", phone)
            or not 7 <= len(digits) <= 15
        ):
            errors["phone"] = (
                "Enter a valid phone number containing 7 to 15 digits."
            )

    # Sub-county
    raw_subcounty = payload.get("subcounty")

    if (
        not isinstance(raw_subcounty, str)
        or not raw_subcounty.strip()
    ):
        errors["subcounty"] = "A sub-county is required."
        subcounty = ""
    else:
        normalized_options = {
            name.casefold(): name
            for name in VALID_SUBCOUNTIES
        }

        subcounty = normalized_options.get(
            raw_subcounty.strip().casefold(),
            "",
        )

        if not subcounty:
            errors["subcounty"] = (
                "Select a valid Murang'a County sub-county."
            )

    # Optional text fields
    ward = payload.get("ward", "")
    enterprise = payload.get("main_enterprise", "")

    if ward is None:
        ward = ""

    if (
        not isinstance(ward, str)
        or len(ward.strip()) > 100
    ):
        errors["ward"] = (
            "Ward must be text of at most 100 characters."
        )
        ward = ""
    else:
        ward = ward.strip()

    if enterprise is None:
        enterprise = ""

    if (
        not isinstance(enterprise, str)
        or len(enterprise.strip()) > 120
    ):
        errors["main_enterprise"] = (
            "Main enterprise must be text of at most 120 characters."
        )
        enterprise = ""
    else:
        enterprise = enterprise.strip()

    # Optional acreage
    raw_acreage = payload.get("farm_size_acres")
    farm_size_acres = None

    if raw_acreage not in (None, ""):
        if isinstance(raw_acreage, bool):
            errors["farm_size_acres"] = (
                "Farm size must be a positive number."
            )
        else:
            try:
                farm_size_acres = float(raw_acreage)

                if (
                    not math.isfinite(farm_size_acres)
                    or farm_size_acres <= 0
                ):
                    errors["farm_size_acres"] = (
                        "Farm size must be a positive finite number."
                    )
            except (TypeError, ValueError):
                errors["farm_size_acres"] = (
                    "Farm size must be a valid number."
                )

    return {
        "full_name": full_name,
        "phone": phone,
        "subcounty": subcounty,
        "ward": ward,
        "farm_size_acres": farm_size_acres,
        "main_enterprise": enterprise,
    }, errors


def validate_crop_payload(payload):
    """Validate and normalize a crop record."""
    errors = {}

    # Crop name
    raw_name = payload.get("name")

    if not isinstance(raw_name, str) or not raw_name.strip():
        errors["name"] = "A crop name is required."
        name = ""
    else:
        name = raw_name.strip()

        if len(name) > 120:
            errors["name"] = (
                "Crop name must be at most 120 characters."
            )

    # Acreage is required and must be positive and finite.
    raw_acreage = payload.get("acreage")
    acreage = None

    if isinstance(raw_acreage, bool) or raw_acreage is None:
        errors["acreage"] = "A positive acreage is required."
    else:
        try:
            acreage = float(raw_acreage)

            if not math.isfinite(acreage) or acreage <= 0:
                errors["acreage"] = (
                    "Acreage must be a positive finite number."
                )
        except (TypeError, ValueError):
            errors["acreage"] = "Acreage must be a valid number."

    # Dates are optional but, when supplied, must use YYYY-MM-DD.
    def validate_date(field_name):
        raw_value = payload.get(field_name)

        if raw_value is None or raw_value == "":
            return None

        if not isinstance(raw_value, str):
            errors[field_name] = (
                "Date must be a string in YYYY-MM-DD format."
            )
            return None

        value = raw_value.strip()

        if not value:
            return None

        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()

            if parsed.isoformat() != value:
                raise ValueError("Date is not in canonical format.")

            return value

        except ValueError:
            errors[field_name] = (
                "Enter a valid date in YYYY-MM-DD format."
            )
            return None

    planting_date = validate_date("planting_date")
    expected_harvest_date = validate_date(
        "expected_harvest_date"
    )

    if (
        planting_date
        and expected_harvest_date
        and expected_harvest_date < planting_date
    ):
        errors["expected_harvest_date"] = (
            "Expected harvest cannot be before the planting date."
        )

    # Expected quantity is optional, but cannot be negative.
    raw_quantity = payload.get("expected_quantity")
    expected_quantity = None

    if raw_quantity not in (None, ""):
        if isinstance(raw_quantity, bool):
            errors["expected_quantity"] = (
                "Expected quantity must be a non-negative number."
            )
        else:
            try:
                expected_quantity = float(raw_quantity)

                if (
                    not math.isfinite(expected_quantity)
                    or expected_quantity < 0
                ):
                    errors["expected_quantity"] = (
                        "Expected quantity must be a non-negative "
                        "finite number."
                    )

            except (TypeError, ValueError):
                errors["expected_quantity"] = (
                    "Expected quantity must be a valid number."
                )

    # Units are optional because some crops may not have a forecast yet.
    raw_unit = payload.get("quantity_unit", "")

    if raw_unit is None:
        raw_unit = ""

    if not isinstance(raw_unit, str) or len(raw_unit.strip()) > 30:
        errors["quantity_unit"] = (
            "Quantity unit must be text of at most 30 characters."
        )
        quantity_unit = ""
    else:
        quantity_unit = raw_unit.strip()

    return {
        "name": name,
        "acreage": acreage,
        "planting_date": planting_date,
        "expected_harvest_date": expected_harvest_date,
        "expected_quantity": expected_quantity,
        "quantity_unit": quantity_unit,
    }, errors

VALID_PROBLEM_CATEGORIES = {
    "Pest infestation",
    "Suspected crop disease",
    "Weather damage",
    "Water or irrigation problem",
    "Soil or nutrient issue",
    "Physical crop damage",
    "Other",
}


def validate_problem_report_payload(payload):
    """Validate and normalize a farm problem report."""
    errors = {}

    # Problem category is required and must be supported.
    raw_category = payload.get("category")

    if not isinstance(raw_category, str) or not raw_category.strip():
        errors["category"] = "A problem category is required."
        category = ""
    else:
        category = raw_category.strip()

        if category not in VALID_PROBLEM_CATEGORIES:
            errors["category"] = "Choose a supported problem category."

    # Crop affected is optional.
    raw_crop = payload.get("crop_affected", "")

    if raw_crop is None:
        raw_crop = ""

    if not isinstance(raw_crop, str) or len(raw_crop.strip()) > 120:
        errors["crop_affected"] = (
            "Affected crop must be text of at most 120 characters."
        )
        crop_affected = ""
    else:
        crop_affected = raw_crop.strip()

    # Sub-county must match a known Murang'a County sub-county.
    raw_subcounty = payload.get("subcounty")

    if not isinstance(raw_subcounty, str) or not raw_subcounty.strip():
        errors["subcounty"] = "A sub-county is required."
        subcounty = ""
    else:
        subcounty = raw_subcounty.strip()

        if subcounty not in VALID_SUBCOUNTIES:
            errors["subcounty"] = "Choose a valid Murang'a County sub-county."

    # Ward is optional.
    raw_ward = payload.get("ward", "")

    if raw_ward is None:
        raw_ward = ""

    if not isinstance(raw_ward, str) or len(raw_ward.strip()) > 100:
        errors["ward"] = "Ward must be text of at most 100 characters."
        ward = ""
    else:
        ward = raw_ward.strip()

    # A useful description is required.
    raw_description = payload.get("description")

    if not isinstance(raw_description, str) or not raw_description.strip():
        errors["description"] = "A problem description is required."
        description = ""
    else:
        description = raw_description.strip()

        if len(description) > 2000:
            errors["description"] = (
                "Description must be at most 2000 characters."
            )

    return {
        "category": category,
        "crop_affected": crop_affected,
        "subcounty": subcounty,
        "ward": ward,
        "description": description,
    }, errors
