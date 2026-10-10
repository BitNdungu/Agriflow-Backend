
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from database import get_db, init_app as init_database
from models import Farmer
from validation import validate_farmer_payload


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
            "version": "0.3.0",
        }), 200

    @app.post("/api/farmers")
    def create_farmer():
        if not request.is_json:
            return jsonify({
                "error": "Content-Type must be application/json",
            }), 415

        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify({
                "error": "The request body must be a JSON object.",
            }), 400

        data, errors = validate_farmer_payload(payload)

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
                data["full_name"],
                data["phone"],
                COUNTY_NAME,
                data["subcounty"],
                data["ward"],
                data["farm_size_acres"],
                data["main_enterprise"],
                created_at,
            ),
        )

        db.commit()

        row = db.execute(
            "SELECT * FROM farmers WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

        return jsonify({
            "farmer": Farmer.from_row(row).to_dict(),
        }), 201

    @app.get("/api/farmers/<int:farmer_id>")
    def get_farmer(farmer_id):
        db = get_db()

        row = db.execute(
            "SELECT * FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        if row is None:
            return jsonify({
                "error": "Farmer not found.",
            }), 404

        return jsonify({
            "farmer": Farmer.from_row(row).to_dict(),
        }), 200

    @app.put("/api/farmers/<int:farmer_id>")
    def update_farmer(farmer_id):
        db = get_db()

        # Check that the requested record exists.
        existing = db.execute(
            "SELECT * FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        if existing is None:
            return jsonify({
                "error": "Farmer not found.",
            }), 404

        if not request.is_json:
            return jsonify({
                "error": "Content-Type must be application/json",
            }), 415

        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify({
                "error": "The request body must be a JSON object.",
            }), 400

        data, errors = validate_farmer_payload(payload)

        if errors:
            return jsonify({
                "error": "Validation failed.",
                "fields": errors,
            }), 400

        db.execute(
            """
            UPDATE farmers
            SET
                full_name = ?,
                phone = ?,
                subcounty = ?,
                ward = ?,
                farm_size_acres = ?,
                main_enterprise = ?
            WHERE id = ?
            """,
            (
                data["full_name"],
                data["phone"],
                data["subcounty"],
                data["ward"],
                data["farm_size_acres"],
                data["main_enterprise"],
                farmer_id,
            ),
        )

        db.commit()

        updated = db.execute(
            "SELECT * FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        return jsonify({
            "farmer": Farmer.from_row(updated).to_dict(),
        }), 200

    return app


app = create_app()


if __name__ == "__main__":
    # Local development only.
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=True,
    )
