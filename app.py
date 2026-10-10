
import math
import os
import re
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from database import get_db, init_app as init_database
from models import Farmer


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

COUNTY_NAME = "Murang'a County"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        DATABASE=os.path.join(
            app.instance_path,
            "agriflow.sqlite3",
        )
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    init_database(app)

    @app.get("/")
    def index():
        return jsonify({
            "application": "MURANG'A AGRIFLOW",
            "message": "Backend API is running",
            "health_endpoint": "/api/health",
        })

    @app.get("/api/health")
    def health_check():
        return jsonify({
            "status": "ok",
            "service": "muranga-agriflow-api",
            "version": "0.2.0",
        }), 200

    @app.post("/api/farmers")
    def create_farmer():
        # This endpoint is for development.
        # Public access must be protected before deployment.
        if not request.is_json:
            return jsonify({
                "error": "Content-Type must be application/json",
            }), 415

        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify({
                "error": "The request body must be a JSON object.",
            }), 400

        errors = {}

        # Validate the required name.
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

        # Validate the phone number without assuming a single format.
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

        # Validate the sub-county against the Android dropdown values.
        raw_subcounty = payload.get("subcounty")

        if not isinstance(raw_subcounty, str) or not raw_subcounty.strip():
            errors["subcounty"] = "A sub-county is required."
            subcounty = ""
        else:
            supplied_subcounty = raw_subcounty.strip()

            matches = {
                name.casefold(): name
                for name in VALID_SUBCOUNTIES
            }

            subcounty = matches.get(
                supplied_subcounty.casefold(),
                "",
            )

            if not subcounty:
                errors["subcounty"] = (
                    "Select a valid Murang'a County sub-county."
                )

        # Optional fields.
        ward = payload.get("ward", "")
        enterprise = payload.get("main_enterprise", "")

        if ward is None:
            ward = ""

        if enterprise is None:
            enterprise = ""

        if not isinstance(ward, str) or len(ward.strip()) > 100:
            errors["ward"] = (
                "Ward must be text of at most 100 characters."
            )
            ward = ""
        else:
            ward = ward.strip()

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

        # Acreage may be omitted, but a supplied value must be positive.
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

        if errors:
            return jsonify({
                "error": "Validation failed.",
                "fields": errors,
            }), 400

        created_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        db = get_db()

        cursor = db.execute(
            """
            INSERT INTO farmers (
                full_name,
                phone,
                county,
                subcounty,
                ward,
                farm_size_acres,
                main_enterprise,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                full_name,
                phone,
                COUNTY_NAME,
                subcounty,
                ward,
                farm_size_acres,
                enterprise,
                created_at,
            ),
        )

        db.commit()

        row = db.execute(
            "SELECT * FROM farmers WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

        farmer = Farmer.from_row(row)

        return jsonify({
            "farmer": farmer.to_dict(),
        }), 201

    return app


app = create_app()


if __name__ == "__main__":
    # Development server only; keep it local for now.
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=True,
    )
