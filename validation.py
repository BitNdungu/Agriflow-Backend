
import math
import re


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
