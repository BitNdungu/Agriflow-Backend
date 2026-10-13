"""Local-first county dashboard blueprint for MURANG'A AGRIFLOW.

This module is registered into the existing Flask application. It uses the same
SQLite database and report-photo storage as the farmer API. It is intended for
local development/demo use; review authentication and deployment security before
exposing the application beyond localhost.
"""

from __future__ import annotations

import hmac
import io
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

bp = Blueprint(
    "county_dashboard",
    __name__,
    template_folder="templates/county_dashboard",
    static_folder="static/county_dashboard",
    static_url_path="/county-assets",
)
gallery_api_bp = Blueprint("agriflow_gallery_api", __name__)

ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_GALLERY_IMAGE_BYTES = 7 * 1024 * 1024
VALID_REPORT_STATUSES = {
    "submitted": "Submitted",
    "under_review": "Under review",
    "resolved": "Resolved",
}


def _database_path() -> str:
    path = current_app.config.get("DATABASE")
    if not path:
        path = os.path.join(current_app.instance_path, "agriflow.sqlite3")
    return os.fspath(path)


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _has_table(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _photo_column_expression(connection: sqlite3.Connection) -> str:
    if _has_table(connection, "problem_report_photos"):
        return "EXISTS (SELECT 1 FROM problem_report_photos pp WHERE pp.report_id = pr.id)"
    return "0"


def _get_report(connection: sqlite3.Connection, report_id: int):
    photo_expr = _photo_column_expression(connection)
    return connection.execute(
        f"""
        SELECT pr.*, f.full_name AS farmer_name, f.phone AS farmer_phone,
               f.county AS farmer_county, f.subcounty AS farmer_subcounty,
               f.ward AS farmer_ward, {photo_expr} AS has_photo
        FROM problem_reports pr
        JOIN farmers f ON f.id = pr.farmer_id
        WHERE pr.id = ?
        """,
        (report_id,),
    ).fetchone()


def csrf_token() -> str:
    token = session.get("county_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["county_csrf_token"] = token
    return token


def _require_csrf() -> None:
    submitted = request.form.get("csrf_token", "")
    expected = session.get("county_csrf_token", "")
    if not submitted or not expected or not hmac.compare_digest(submitted, expected):
        abort(400, description="The form expired. Refresh the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("county_authenticated"):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("county_dashboard.login", next=next_url))
        return view(*args, **kwargs)
    return wrapped


@bp.context_processor
def inject_dashboard_globals():
    return {
        "county_csrf_token": csrf_token,
        "county_admin_name": session.get("county_admin_name", "County administrator"),
        "valid_report_statuses": VALID_REPORT_STATUSES,
    }


@bp.after_app_request
def add_basic_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.path.startswith("/county") or request.path.startswith("/api/gallery"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@bp.route("/", methods=["GET"])
def dashboard_root():
    if session.get("county_authenticated"):
        return redirect(url_for("county_dashboard.dashboard"))
    return redirect(url_for("county_dashboard.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("county_authenticated"):
        return redirect(url_for("county_dashboard.dashboard"))

    if request.method == "POST":
        _require_csrf()
        expected_user = os.environ.get("AGRIFLOW_COUNTY_USER", "countyadmin")
        expected_password = os.environ.get("AGRIFLOW_COUNTY_PASSWORD", "ChangeMe123!")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        valid_user = hmac.compare_digest(username, expected_user)
        valid_password = hmac.compare_digest(password, expected_password)
        if valid_user and valid_password:
            session.clear()
            session["county_authenticated"] = True
            session["county_admin_name"] = username
            session["county_csrf_token"] = secrets.token_urlsafe(32)
            flash("Welcome. County dashboard session started.", "success")
            target = request.args.get("next", "")
            if target.startswith("/county") and not target.startswith("//"):
                return redirect(target)
            return redirect(url_for("county_dashboard.dashboard"))

        flash("Username or password was not recognised.", "error")

    return render_template("login.html", page_title="County staff sign in")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    _require_csrf()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("county_dashboard.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    connection = db_connect()
    try:
        farmers_total = connection.execute("SELECT COUNT(*) FROM farmers").fetchone()[0]
        reports_total = connection.execute("SELECT COUNT(*) FROM problem_reports").fetchone()[0]
        submitted = connection.execute(
            "SELECT COUNT(*) FROM problem_reports WHERE status='submitted'"
        ).fetchone()[0]
        under_review = connection.execute(
            "SELECT COUNT(*) FROM problem_reports WHERE status='under_review'"
        ).fetchone()[0]
        resolved = connection.execute(
            "SELECT COUNT(*) FROM problem_reports WHERE status='resolved'"
        ).fetchone()[0]
        photo_count = 0
        if _has_table(connection, "problem_report_photos"):
            photo_count = connection.execute(
                "SELECT COUNT(*) FROM problem_report_photos"
            ).fetchone()[0]

        categories = connection.execute(
            "SELECT category, COUNT(*) AS count FROM problem_reports GROUP BY category ORDER BY count DESC"
        ).fetchall()
        maximum_category_count = max((row["count"] for row in categories), default=1)
        category_rows = [
            {"name": row["category"], "count": row["count"],
             "percent": max(4, round(row["count"] * 100 / maximum_category_count))}
            for row in categories
        ]
        photo_expr = _photo_column_expression(connection)
        recent = connection.execute(
            f"""
            SELECT pr.id, pr.category, pr.crop_affected, pr.subcounty, pr.ward,
                   pr.status, pr.created_at, f.full_name AS farmer_name,
                   f.phone AS farmer_phone, f.id AS farmer_id,
                   {photo_expr} AS has_photo
            FROM problem_reports pr JOIN farmers f ON f.id=pr.farmer_id
            ORDER BY pr.created_at DESC, pr.id DESC LIMIT 7
            """
        ).fetchall()
        latest_gallery = 0
        if _has_table(connection, "county_gallery_images"):
            latest_gallery = connection.execute(
                "SELECT COUNT(*) FROM county_gallery_images WHERE is_active=1"
            ).fetchone()[0]
    finally:
        connection.close()

    return render_template(
        "dashboard.html",
        page_title="Overview",
        active_page="dashboard",
        farmers_total=farmers_total,
        reports_total=reports_total,
        submitted=submitted,
        under_review=under_review,
        resolved=resolved,
        photo_count=photo_count,
        category_rows=category_rows,
        recent=recent,
        latest_gallery=latest_gallery,
    )


@bp.route("/reports")
@login_required
def reports():
    query = request.args.get("q", "").strip()[:120]
    status_filter = request.args.get("status", "").strip()
    subcounty_filter = request.args.get("subcounty", "").strip()
    page = max(1, request.args.get("page", default=1, type=int))
    page_size = 25

    conditions = []
    parameters = []
    if status_filter in VALID_REPORT_STATUSES:
        conditions.append("pr.status = ?")
        parameters.append(status_filter)
    if subcounty_filter:
        conditions.append("pr.subcounty = ?")
        parameters.append(subcounty_filter)
    if query:
        wildcard = f"%{query}%"
        conditions.append(
            "(f.full_name LIKE ? OR f.phone LIKE ? OR pr.category LIKE ? "
            "OR pr.crop_affected LIKE ? OR pr.description LIKE ? OR CAST(pr.id AS TEXT) LIKE ?)"
        )
        parameters.extend([wildcard] * 6)
    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""

    connection = db_connect()
    try:
        total = connection.execute(
            f"SELECT COUNT(*) FROM problem_reports pr JOIN farmers f ON f.id=pr.farmer_id{where_sql}",
            parameters,
        ).fetchone()[0]
        photo_expr = _photo_column_expression(connection)
        rows = connection.execute(
            f"""
            SELECT pr.id, pr.farmer_id, pr.category, pr.crop_affected,
                   pr.subcounty, pr.ward, pr.description, pr.status,
                   pr.created_at, pr.updated_at, f.full_name AS farmer_name,
                   f.phone AS farmer_phone, {photo_expr} AS has_photo
            FROM problem_reports pr JOIN farmers f ON f.id=pr.farmer_id
            {where_sql}
            ORDER BY pr.created_at DESC, pr.id DESC
            LIMIT ? OFFSET ?
            """,
            parameters + [page_size, (page - 1) * page_size],
        ).fetchall()
        subcounties = [row[0] for row in connection.execute(
            "SELECT DISTINCT subcounty FROM problem_reports ORDER BY subcounty COLLATE NOCASE"
        ).fetchall()]
    finally:
        connection.close()

    pages = max(1, (total + page_size - 1) // page_size)
    return render_template(
        "reports.html",
        page_title="Problem reports",
        active_page="reports",
        reports=rows,
        query=query,
        status_filter=status_filter,
        subcounty_filter=subcounty_filter,
        subcounties=subcounties,
        page=page,
        pages=pages,
        total=total,
    )


@bp.route("/reports/<int:report_id>")
@login_required
def report_detail(report_id: int):
    connection = db_connect()
    try:
        report = _get_report(connection, report_id)
        if report is None:
            abort(404)
    finally:
        connection.close()
    return render_template(
        "report_detail.html",
        page_title=f"Report #{report_id}",
        active_page="reports",
        report=report,
        status_labels=VALID_REPORT_STATUSES,
    )


@bp.route("/reports/<int:report_id>/status", methods=["POST"])
@login_required
def update_report_status(report_id: int):
    _require_csrf()
    status = request.form.get("status", "")
    if status not in VALID_REPORT_STATUSES:
        flash("Choose a valid report status.", "error")
        return redirect(url_for("county_dashboard.report_detail", report_id=report_id))

    connection = db_connect()
    try:
        cursor = connection.execute(
            "UPDATE problem_reports SET status=?, updated_at=? WHERE id=?",
            (status, datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), report_id),
        )
        connection.commit()
        if cursor.rowcount == 0:
            abort(404)
    finally:
        connection.close()
    flash(f"Report #{report_id} status updated to {VALID_REPORT_STATUSES[status]}.", "success")
    return redirect(url_for("county_dashboard.report_detail", report_id=report_id))


@bp.route("/farmers")
@login_required
def farmers():
    query = request.args.get("q", "").strip()[:120]
    connection = db_connect()
    try:
        conditions = ""
        parameters = []
        if query:
            wildcard = f"%{query}%"
            conditions = "WHERE f.full_name LIKE ? OR f.phone LIKE ? OR f.subcounty LIKE ? OR f.ward LIKE ?"
            parameters = [wildcard] * 4
        farmer_rows = connection.execute(
            f"""
            SELECT f.*, COUNT(pr.id) AS reports_count
            FROM farmers f LEFT JOIN problem_reports pr ON pr.farmer_id=f.id
            {conditions}
            GROUP BY f.id
            ORDER BY f.created_at DESC, f.id DESC
            LIMIT 300
            """,
            parameters,
        ).fetchall()
    finally:
        connection.close()
    return render_template(
        "farmers.html",
        page_title="Farmers",
        active_page="farmers",
        farmers=farmer_rows,
        query=query,
    )


def _gallery_directory() -> str:
    configured = current_app.config.get("COUNTY_GALLERY_UPLOAD_DIR")
    if configured:
        return os.fspath(configured)
    return os.path.join(current_app.instance_path, "uploads", "county_gallery")


def _gallery_row(connection: sqlite3.Connection, image_id: int):
    return connection.execute(
        "SELECT * FROM county_gallery_images WHERE id=?", (image_id,)
    ).fetchone()


@bp.route("/gallery", methods=["GET", "POST"])
@login_required
def gallery():
    if request.method == "POST":
        _require_csrf()
        uploaded = request.files.get("image")
        title = request.form.get("title", "").strip()[:120]
        caption = request.form.get("caption", "").strip()[:300]

        if uploaded is None or not uploaded.filename:
            flash("Choose an image file to upload.", "error")
            return redirect(url_for("county_dashboard.gallery"))
        if not title:
            flash("Add a short title for this gallery image.", "error")
            return redirect(url_for("county_dashboard.gallery"))

        raw = uploaded.stream.read(MAX_GALLERY_IMAGE_BYTES + 1)
        if not raw:
            flash("The selected file is empty.", "error")
            return redirect(url_for("county_dashboard.gallery"))
        if len(raw) > MAX_GALLERY_IMAGE_BYTES:
            flash("Gallery images must not exceed 7 MiB.", "error")
            return redirect(url_for("county_dashboard.gallery"))

        try:
            from PIL import Image
            image = Image.open(io.BytesIO(raw))
            image_format = image.format
            if image.width * image.height > 40_000_000:
                raise ValueError("Image dimensions are too large.")
            image.verify()
        except Exception:
            flash("That file is not a supported image. Use JPEG, PNG or WebP.", "error")
            return redirect(url_for("county_dashboard.gallery"))

        extension = ALLOWED_IMAGE_FORMATS.get(image_format)
        if extension is None:
            flash("Use a JPEG, PNG or WebP image.", "error")
            return redirect(url_for("county_dashboard.gallery"))

        directory = _gallery_directory()
        os.makedirs(directory, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{extension}"
        file_path = os.path.join(directory, stored_name)
        with open(file_path, "wb") as destination:
            destination.write(raw)

        mimetype = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[image_format]
        original_name = secure_filename(uploaded.filename)[:200] or "gallery-image"
        connection = db_connect()
        try:
            connection.execute(
                """INSERT INTO county_gallery_images
                   (title, caption, filename, original_filename, mimetype, size_bytes, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
                (title, caption, stored_name, original_name, mimetype, len(raw),
                 datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")),
            )
            connection.commit()
        except Exception:
            try:
                os.remove(file_path)
            except OSError:
                pass
            raise
        finally:
            connection.close()
        flash("Gallery image uploaded and made available to the app gallery API.", "success")
        return redirect(url_for("county_dashboard.gallery"))

    connection = db_connect()
    try:
        rows = connection.execute(
            "SELECT * FROM county_gallery_images ORDER BY created_at DESC, id DESC"
        ).fetchall()
    finally:
        connection.close()
    return render_template(
        "gallery.html",
        page_title="Home gallery",
        active_page="gallery",
        images=rows,
    )


@bp.route("/gallery/<int:image_id>/toggle", methods=["POST"])
@login_required
def toggle_gallery_image(image_id: int):
    _require_csrf()
    connection = db_connect()
    try:
        row = _gallery_row(connection, image_id)
        if row is None:
            abort(404)
        new_value = 0 if row["is_active"] else 1
        connection.execute(
            "UPDATE county_gallery_images SET is_active=? WHERE id=?",
            (new_value, image_id),
        )
        connection.commit()
    finally:
        connection.close()
    flash("Gallery image is now " + ("active in the app" if new_value else "hidden from the app") + ".", "success")
    return redirect(url_for("county_dashboard.gallery"))


@bp.route("/gallery/<int:image_id>/delete", methods=["POST"])
@login_required
def delete_gallery_image(image_id: int):
    _require_csrf()
    connection = db_connect()
    try:
        row = _gallery_row(connection, image_id)
        if row is None:
            abort(404)
        connection.execute("DELETE FROM county_gallery_images WHERE id=?", (image_id,))
        connection.commit()
    finally:
        connection.close()
    try:
        os.remove(os.path.join(_gallery_directory(), row["filename"]))
    except OSError:
        current_app.logger.warning("Could not delete gallery file for image id %s", image_id)
    flash("Gallery image deleted.", "success")
    return redirect(url_for("county_dashboard.gallery"))


@bp.route("/gallery/<int:image_id>/preview")
@login_required
def gallery_preview(image_id: int):
    connection = db_connect()
    try:
        row = _gallery_row(connection, image_id)
        if row is None:
            abort(404)
        filename = row["filename"]
        mimetype = row["mimetype"]
    finally:
        connection.close()
    return send_from_directory(_gallery_directory(), filename, mimetype=mimetype, as_attachment=False)


@bp.route("/report-photo/<int:farmer_id>/<int:report_id>")
@login_required
def report_photo(farmer_id: int, report_id: int):
    connection = db_connect()
    try:
        if not _has_table(connection, "problem_report_photos"):
            abort(404)
        row = connection.execute(
            """SELECT pp.* FROM problem_report_photos pp
               JOIN problem_reports pr ON pr.id=pp.report_id
               WHERE pr.id=? AND pr.farmer_id=?""",
            (report_id, farmer_id),
        ).fetchone()
        if row is None:
            abort(404)
        filename = row["stored_filename"]
        mimetype = row["media_type"]
    finally:
        connection.close()
    directory = current_app.config.get(
        "PROBLEM_REPORT_UPLOAD_DIR",
        os.path.join(current_app.instance_path, "uploads", "problem_reports"),
    )
    return send_from_directory(directory, filename, mimetype=mimetype, as_attachment=False)


@gallery_api_bp.route("/api/gallery", methods=["GET"])
def gallery_api():
    connection = db_connect()
    try:
        rows = connection.execute(
            "SELECT id, title, caption, mimetype, created_at FROM county_gallery_images WHERE is_active=1 ORDER BY created_at DESC, id DESC"
        ).fetchall()
    finally:
        connection.close()
    images = [
        {
            "id": row["id"],
            "title": row["title"],
            "caption": row["caption"],
            "media_type": row["mimetype"],
            "created_at": row["created_at"],
            "url": url_for("agriflow_gallery_api.gallery_image", image_id=row["id"], _external=False),
        }
        for row in rows
    ]
    return jsonify({"count": len(images), "images": images}), 200


@gallery_api_bp.route("/api/gallery/<int:image_id>/image", methods=["GET"])
def gallery_image(image_id: int):
    connection = db_connect()
    try:
        row = connection.execute(
            "SELECT filename, mimetype FROM county_gallery_images WHERE id=? AND is_active=1",
            (image_id,),
        ).fetchone()
        if row is None:
            abort(404)
        filename = row["filename"]
        mimetype = row["mimetype"]
    finally:
        connection.close()
    response = send_from_directory(_gallery_directory(), filename, mimetype=mimetype, as_attachment=False, max_age=3600)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


def register_county_dashboard(app) -> None:
    """Register dashboard routes and add its gallery table to the shared DB."""
    if "county_dashboard" in app.blueprints:
        return

    if not app.secret_key:
        app.secret_key = os.environ.get("AGRIFLOW_DASHBOARD_SECRET") or secrets.token_hex(32)
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("COUNTY_GALLERY_UPLOAD_DIR", os.path.join(app.instance_path, "uploads", "county_gallery"))

    database_path = app.config.get("DATABASE") or os.path.join(app.instance_path, "agriflow.sqlite3")
    os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=15)
    try:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS county_gallery_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                caption TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL UNIQUE,
                original_filename TEXT NOT NULL,
                mimetype TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL
            )"""
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_county_gallery_active ON county_gallery_images(is_active, created_at)")
        connection.commit()
    finally:
        connection.close()

    os.makedirs(app.config["COUNTY_GALLERY_UPLOAD_DIR"], exist_ok=True)
    app.register_blueprint(bp, url_prefix="/county")
    app.register_blueprint(gallery_api_bp)
