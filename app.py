
import os
import uuid
import warnings
from datetime import datetime, timezone
from io import BytesIO

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
)
from PIL import Image, ImageOps, UnidentifiedImageError

from database import get_db, init_app as init_database
from models import Crop, Farmer, ProblemReport
from validation import (
    validate_crop_payload,
    validate_farmer_payload,
    validate_problem_report_payload,
)

from county_dashboard import register_county_dashboard

COUNTY_NAME = "Murang'a County"

SUPPORTED_PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}

MAX_PROBLEM_PHOTO_BYTES = 7 * 1024 * 1024

MAX_PROBLEM_PHOTO_PIXELS = 25_000_000


class InvalidProblemPhoto(ValueError):
    """Raised when an uploaded image cannot be safely accepted."""


def normalize_problem_photo(raw_bytes):
    """Validate an image and convert it into a clean JPEG."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )

            # Inspect the image format and dimensions before decoding.
            with Image.open(BytesIO(raw_bytes)) as source:
                if source.format not in SUPPORTED_PHOTO_FORMATS:
                    raise InvalidProblemPhoto(
                        "Upload a JPEG, PNG, or WebP image."
                    )

                if source.width * source.height > MAX_PROBLEM_PHOTO_PIXELS:
                    raise InvalidProblemPhoto(
                        "Image dimensions exceed the allowed limit."
                    )

                if getattr(source, "is_animated", False):
                    raise InvalidProblemPhoto(
                        "Animated images are not supported."
                    )

                source.verify()

            # Reopen the verified image for processing.
            with Image.open(BytesIO(raw_bytes)) as source:
                source = ImageOps.exif_transpose(source)
                source.load()

                # Flatten transparency onto a white background.
                if (
                    source.mode in ("RGBA", "LA")
                    or "transparency" in source.info
                ):
                    rgba = source.convert("RGBA")
                    normalized = Image.new(
                        "RGB",
                        rgba.size,
                        (255, 255, 255),
                    )
                    normalized.paste(
                        rgba,
                        mask=rgba.getchannel("A"),
                    )
                else:
                    normalized = source.convert("RGB")

                # Keep display images at a practical resolution.
                normalized.thumbnail(
                    (2400, 2400),
                    Image.Resampling.LANCZOS,
                )

                width, height = normalized.size

                output = BytesIO()
                normalized.save(
                    output,
                    format="JPEG",
                    quality=85,
                    optimize=True,
                )

                return output.getvalue(), width, height

    except InvalidProblemPhoto:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        EOFError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidProblemPhoto(
            "The uploaded file is not a valid supported image."
        ) from exc


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    
    app.config.from_mapping(
        DATABASE=os.path.join(
            app.instance_path,
            "agriflow.sqlite3",
        ),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        PROBLEM_REPORT_UPLOAD_DIR=os.path.join(
            app.instance_path,
            "uploads",
            "problem_reports",
        ),
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    init_database(app)

    register_county_dashboard(app)
    
    @app.errorhandler(413)
    def request_too_large(error):
        return jsonify({
            "error": "Request exceeds the maximum allowed size.",
        }), 413

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
    
    def save_problem_report_photo(
        farmer_id,
        report_id,
        replace_existing=False,
    ):
        if request.mimetype != "multipart/form-data":
            return jsonify({
                "error": "Content-Type must be multipart/form-data.",
            }), 415

        uploaded_file = request.files.get("photo")

        if uploaded_file is None or not uploaded_file.filename.strip():
            return jsonify({
                "error": "Provide an image in the 'photo' field.",
            }), 400

        db = get_db()

        report = db.execute(
            """
            SELECT id FROM problem_reports
            WHERE id = ? AND farmer_id = ?
            """,
            (report_id, farmer_id),
        ).fetchone()

        if report is None:
            return jsonify({
                "error": "Problem report not found for this farmer.",
            }), 404

        existing = db.execute(
            """
            SELECT * FROM problem_report_photos
            WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()

        if existing is not None and not replace_existing:
            return jsonify({
                "error": "This report already has a photo. Use PUT to replace it.",
            }), 409

        if existing is None and replace_existing:
            return jsonify({
                "error": "No existing photo was found to replace.",
            }), 404

        raw_bytes = uploaded_file.stream.read(
            MAX_PROBLEM_PHOTO_BYTES + 1
        )

        if not raw_bytes:
            return jsonify({
                "error": "The uploaded photo is empty.",
            }), 400

        if len(raw_bytes) > MAX_PROBLEM_PHOTO_BYTES:
            return jsonify({
                "error": "Photo must not exceed 7 MiB.",
            }), 413

        try:
            jpeg_bytes, width, height = normalize_problem_photo(
                raw_bytes
            )
        except InvalidProblemPhoto as exc:
            return jsonify({
                "error": str(exc),
            }), 400

        upload_directory = app.config[
            "PROBLEM_REPORT_UPLOAD_DIR"
        ]
        os.makedirs(upload_directory, exist_ok=True)

        stored_filename = f"{uuid.uuid4().hex}.jpg"
        stored_path = os.path.join(
            upload_directory,
            stored_filename,
        )

        uploaded_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        try:
            # Exclusive creation avoids overwriting another file.
            with open(stored_path, "xb") as destination:
                destination.write(jpeg_bytes)

            if existing is None:
                db.execute(
                    """
                    INSERT INTO problem_report_photos (
                        report_id,
                        stored_filename,
                        media_type,
                        size_bytes,
                        width,
                        height,
                        uploaded_at
                    )
                    VALUES (?, ?, 'image/jpeg', ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        stored_filename,
                        len(jpeg_bytes),
                        width,
                        height,
                        uploaded_at,
                    ),
                )
            else:
                db.execute(
                    """
                    UPDATE problem_report_photos
                    SET
                        stored_filename = ?,
                        media_type = 'image/jpeg',
                        size_bytes = ?,
                        width = ?,
                        height = ?,
                        uploaded_at = ?
                    WHERE report_id = ?
                    """,
                    (
                        stored_filename,
                        len(jpeg_bytes),
                        width,
                        height,
                        uploaded_at,
                        report_id,
                    ),
                )

            db.commit()

        except Exception:
            db.rollback()

            try:
                os.remove(stored_path)
            except OSError:
                pass

            raise

        # Remove the previous file after the replacement is committed.
        if existing is not None:
            old_filename = existing["stored_filename"]

            if (
                old_filename != stored_filename
                and os.path.basename(old_filename) == old_filename
            ):
                old_path = os.path.join(
                    upload_directory,
                    old_filename,
                )

                try:
                    os.remove(old_path)
                except OSError:
                    pass

        photo = db.execute(
            """
            SELECT * FROM problem_report_photos
            WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()

        return jsonify({
            "photo": {
                "id": photo["id"],
                "report_id": photo["report_id"],
                "media_type": photo["media_type"],
                "size_bytes": photo["size_bytes"],
                "width": photo["width"],
                "height": photo["height"],
                "uploaded_at": photo["uploaded_at"],
                "url": (
                    f"/api/farmers/{farmer_id}"
                    f"/problem-reports/{report_id}/photo"
                ),
            },
        }), 200 if replace_existing else 201

    @app.post(
        "/api/farmers/<int:farmer_id>/problem-reports/"
        "<int:report_id>/photo"
    )
    def upload_problem_report_photo(farmer_id, report_id):
        return save_problem_report_photo(
            farmer_id,
            report_id,
            replace_existing=False,
        )

    @app.put(
        "/api/farmers/<int:farmer_id>/problem-reports/"
        "<int:report_id>/photo"
    )
    def replace_problem_report_photo(farmer_id, report_id):
        return save_problem_report_photo(
            farmer_id,
            report_id,
            replace_existing=True,
        )

    @app.get(
        "/api/farmers/<int:farmer_id>/problem-reports/"
        "<int:report_id>/photo"
    )
    def get_problem_report_photo(farmer_id, report_id):
        db = get_db()

        report = db.execute(
            """
            SELECT id FROM problem_reports
            WHERE id = ? AND farmer_id = ?
            """,
            (report_id, farmer_id),
        ).fetchone()

        if report is None:
            return jsonify({
                "error": "Problem report not found for this farmer.",
            }), 404

        photo = db.execute(
            """
            SELECT * FROM problem_report_photos
            WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()

        if photo is None:
            return jsonify({
                "error": "No photo is attached to this report.",
            }), 404

        filename = photo["stored_filename"]

        # Only serve filenames generated by this application.
        if os.path.basename(filename) != filename:
            return jsonify({
                "error": "Stored photo could not be retrieved.",
            }), 500

        upload_directory = app.config[
            "PROBLEM_REPORT_UPLOAD_DIR"
        ]
        stored_path = os.path.join(upload_directory, filename)

        if not os.path.isfile(stored_path):
            return jsonify({
                "error": "Stored photo file was not found.",
            }), 404

        return send_from_directory(
            upload_directory,
            filename,
            mimetype=photo["media_type"],
            as_attachment=False,
            conditional=True,
            max_age=0,
        )
    

    return app


app = create_app()


if __name__ == "__main__":
    # Local development only.
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=True,
    )

  

