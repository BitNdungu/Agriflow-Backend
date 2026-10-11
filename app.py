
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from database import get_db, init_app as init_database
from models import Crop, Farmer, ProblemReport
from validation import (
    validate_crop_payload,
    validate_farmer_payload,
    validate_problem_report_payload,
)

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

    @app.post("/api/farmers/<int:farmer_id>/crops")
    def create_crop(farmer_id):
        db = get_db()

        farmer = db.execute(
            "SELECT id FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        if farmer is None:
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

        data, errors = validate_crop_payload(payload)

        if errors:
            return jsonify({
                "error": "Validation failed.",
                "fields": errors,
            }), 400

        now = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        cursor = db.execute(
            """
            INSERT INTO crops (
                farmer_id,
                name,
                acreage,
                planting_date,
                expected_harvest_date,
                expected_quantity,
                quantity_unit,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                farmer_id,
                data["name"],
                data["acreage"],
                data["planting_date"],
                data["expected_harvest_date"],
                data["expected_quantity"],
                data["quantity_unit"],
                now,
                now,
            ),
        )

        db.commit()

        row = db.execute(
            "SELECT * FROM crops WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

        return jsonify({
            "crop": Crop.from_row(row).to_dict(),
        }), 201

    @app.get("/api/farmers/<int:farmer_id>/crops")
    def get_farmer_crops(farmer_id):
        db = get_db()

        farmer = db.execute(
            "SELECT id FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        if farmer is None:
            return jsonify({
                "error": "Farmer not found.",
            }), 404

        rows = db.execute(
            """
            SELECT *
            FROM crops
            WHERE farmer_id = ?
            ORDER BY id DESC
            """,
            (farmer_id,),
        ).fetchall()

        crops = [
            Crop.from_row(row).to_dict()
            for row in rows
        ]

        return jsonify({
            "farmer_id": farmer_id,
            "count": len(crops),
            "crops": crops,
        }), 200

    @app.put(
        "/api/farmers/<int:farmer_id>/crops/<int:crop_id>"
    )
    def update_crop(farmer_id, crop_id):
        db = get_db()

        row = db.execute(
            """
            SELECT *
            FROM crops
            WHERE id = ? AND farmer_id = ?
            """,
            (crop_id, farmer_id),
        ).fetchone()

        if row is None:
            return jsonify({
                "error": "Crop not found for this farmer.",
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

        data, errors = validate_crop_payload(payload)

        if errors:
            return jsonify({
                "error": "Validation failed.",
                "fields": errors,
            }), 400

        updated_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        db.execute(
            """
            UPDATE crops
            SET
                name = ?,
                acreage = ?,
                planting_date = ?,
                expected_harvest_date = ?,
                expected_quantity = ?,
                quantity_unit = ?,
                updated_at = ?
            WHERE id = ? AND farmer_id = ?
            """,
            (
                data["name"],
                data["acreage"],
                data["planting_date"],
                data["expected_harvest_date"],
                data["expected_quantity"],
                data["quantity_unit"],
                updated_at,
                crop_id,
                farmer_id,
            ),
        )

        db.commit()

        updated = db.execute(
            "SELECT * FROM crops WHERE id = ?",
            (crop_id,),
        ).fetchone()

        return jsonify({
            "crop": Crop.from_row(updated).to_dict(),
        }), 200

    @app.delete(
        "/api/farmers/<int:farmer_id>/crops/<int:crop_id>"
    )
    def delete_crop(farmer_id, crop_id):
        db = get_db()

        cursor = db.execute(
            """
            DELETE FROM crops
            WHERE id = ? AND farmer_id = ?
            """,
            (crop_id, farmer_id),
        )

        if cursor.rowcount == 0:
            return jsonify({
                "error": "Crop not found for this farmer.",
            }), 404

        db.commit()

        return jsonify({
            "message": "Crop deleted successfully.",
            "crop_id": crop_id,
            "farmer_id": farmer_id,
        }), 200


    @app.post("/api/farmers/<int:farmer_id>/problem-reports")
    def create_problem_report(farmer_id):
        if not request.is_json:
            return jsonify({
                "error": "Content-Type must be application/json",
            }), 415

        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify({
                "error": "The request body must be a JSON object.",
            }), 400

        db = get_db()

        farmer = db.execute(
            "SELECT id FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        if farmer is None:
            return jsonify({
                "error": "Farmer not found.",
            }), 404

        data, errors = validate_problem_report_payload(payload)

        if errors:
            return jsonify({
                "error": "Validation failed.",
                "fields": errors,
            }), 400

        timestamp = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        cursor = db.execute(
            """
            INSERT INTO problem_reports (
                farmer_id,
                category,
                crop_affected,
                subcounty,
                ward,
                description,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
            """,
            (
                farmer_id,
                data["category"],
                data["crop_affected"],
                data["subcounty"],
                data["ward"],
                data["description"],
                timestamp,
                timestamp,
            ),
        )

        db.commit()

        report = db.execute(
            """
            SELECT * FROM problem_reports
            WHERE id = ? AND farmer_id = ?
            """,
            (cursor.lastrowid, farmer_id),
        ).fetchone()

        return jsonify({
            "report": ProblemReport.from_row(report).to_dict(),
        }), 201

    @app.get("/api/farmers/<int:farmer_id>/problem-reports")
    def get_farmer_problem_reports(farmer_id):
        db = get_db()

        farmer = db.execute(
            "SELECT id FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        if farmer is None:
            return jsonify({
                "error": "Farmer not found.",
            }), 404

        rows = db.execute(
            """
            SELECT * FROM problem_reports
            WHERE farmer_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (farmer_id,),
        ).fetchall()

        reports = [
            ProblemReport.from_row(row).to_dict()
            for row in rows
        ]

        return jsonify({
            "farmer_id": farmer_id,
            "count": len(reports),
            "reports": reports,
        }), 200

    @app.get(
        "/api/farmers/<int:farmer_id>/problem-reports/<int:report_id>"
    )
    def get_problem_report(farmer_id, report_id):
        db = get_db()

        farmer = db.execute(
            "SELECT id FROM farmers WHERE id = ?",
            (farmer_id,),
        ).fetchone()

        if farmer is None:
            return jsonify({
                "error": "Farmer not found.",
            }), 404

        row = db.execute(
            """
            SELECT * FROM problem_reports
            WHERE id = ? AND farmer_id = ?
            """,
            (report_id, farmer_id),
        ).fetchone()

        if row is None:
            return jsonify({
                "error": "Problem report not found for this farmer.",
            }), 404

        return jsonify({
            "report": ProblemReport.from_row(row).to_dict(),
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

  
