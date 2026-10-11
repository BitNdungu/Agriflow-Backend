
import os
import sqlite3

from flask import current_app, g



SCHEMA = """
CREATE TABLE IF NOT EXISTS farmers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    county TEXT NOT NULL,
    subcounty TEXT NOT NULL,
    ward TEXT NOT NULL DEFAULT '',
    farm_size_acres REAL,
    main_enterprise TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,

    CHECK (length(trim(full_name)) BETWEEN 1 AND 120),
    CHECK (farm_size_acres IS NULL OR farm_size_acres > 0)
);

CREATE TABLE IF NOT EXISTS crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    acreage REAL NOT NULL,
    planting_date TEXT,
    expected_harvest_date TEXT,
    expected_quantity REAL,
    quantity_unit TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (length(trim(name)) BETWEEN 1 AND 120),
    CHECK (acreage > 0),
    CHECK (
        expected_quantity IS NULL
        OR expected_quantity >= 0
    ),

    FOREIGN KEY (farmer_id)
        REFERENCES farmers(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_crops_farmer_id
ON crops(farmer_id);
CREATE TABLE IF NOT EXISTS problem_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    crop_affected TEXT NOT NULL DEFAULT '',
    subcounty TEXT NOT NULL,
    ward TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (
        category IN (
            'Pest infestation',
            'Suspected crop disease',
            'Weather damage',
            'Water or irrigation problem',
            'Soil or nutrient issue',
            'Physical crop damage',
            'Other'
        )
    ),
    CHECK (length(trim(subcounty)) BETWEEN 1 AND 80),
    CHECK (length(trim(ward)) <= 100),
    CHECK (length(trim(crop_affected)) <= 120),
    CHECK (length(trim(description)) BETWEEN 1 AND 2000),
    CHECK (
        status IN ('submitted', 'under_review', 'resolved')
    ),

    FOREIGN KEY (farmer_id)
        REFERENCES farmers(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_problem_reports_farmer_id
ON problem_reports(farmer_id);
"""



def get_db():
    """Return the database connection for the current request."""
    if "db" not in g:
        database_path = current_app.config["DATABASE"]

        parent_directory = os.path.dirname(
            os.path.abspath(database_path)
        )
        os.makedirs(parent_directory, exist_ok=True)

        db = sqlite3.connect(database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")

        g.db = db

    return g.db


def close_db(exception=None):
    """Close this request's database connection."""
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_app(app):
    """Register cleanup and create required tables."""
    app.teardown_appcontext(close_db)

    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
