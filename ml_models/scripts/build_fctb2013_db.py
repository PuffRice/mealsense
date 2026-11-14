"""Materialize ``ml_models/data/fctb_2013_nutrition.db`` from the seeded
FCTB 2013 reference table.

The generated database is the runtime source of ingredient composition
records, so values are no longer read from Python source at inference time.
Every row carries provenance metadata (source name, citation, retrieval
timestamp) and an explicit ``verification_status``.

The values are ATTRIBUTED to the published *Food Composition Table for
Bangladesh, 2013* (INFS, University of Dhaka) via its food codes, but they
remain ``unverified`` until someone checks them against the publication.
Do not flip ``verification_status`` without that review.

Run from the repository root::

    python ml_models/scripts/build_fctb2013_db.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "ml_models"))

from inference.nutrition import FCTB_2013_EXTENDED  # noqa: E402

DB_PATH = REPO_ROOT / "ml_models" / "data" / "fctb_2013_nutrition.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS db_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nutrition_fctb (
    ingredient_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    fctb_code TEXT NOT NULL,
    cooking_yield_factor REAL NOT NULL,
    calories_kcal_100g REAL NOT NULL,
    protein_g_100g REAL NOT NULL,
    carbohydrates_g_100g REAL NOT NULL,
    fat_g_100g REAL NOT NULL,
    fiber_g_100g REAL,
    iron_mg_100g REAL,
    calcium_mg_100g REAL,
    potassium_mg_100g REAL,
    source_name TEXT NOT NULL,
    source_citation TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'reviewed', 'approved')),
    retrieved_at TEXT NOT NULL
);
"""

METADATA = {
    "source_name": "Food Composition Table for Bangladesh, 2013 (INFS, University of Dhaka)",
    "source_reference": "https://www.infsbd.org/ (publication; codes cited per row)",
    "basis": "per 100 g raw edible portion",
    "license_note": "Publication terms not confirmed; values require independent verification.",
    "verification_status": "unverified",
}


def build(db_path: Path = DB_PATH) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        rows = [
            (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7],
             row[8], row[9], row[10], row[11],
             METADATA["source_name"], row[12], METADATA["verification_status"],
             retrieved_at)
            for row in FCTB_2013_EXTENDED
        ]
        conn.executemany(
            """
            INSERT INTO nutrition_fctb (
                ingredient_key, display_name, fctb_code, cooking_yield_factor,
                calories_kcal_100g, protein_g_100g, carbohydrates_g_100g,
                fat_g_100g, fiber_g_100g, iron_mg_100g, calcium_mg_100g,
                potassium_mg_100g, source_name, source_citation,
                verification_status, retrieved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ingredient_key) DO UPDATE SET
                display_name = excluded.display_name,
                fctb_code = excluded.fctb_code,
                cooking_yield_factor = excluded.cooking_yield_factor,
                calories_kcal_100g = excluded.calories_kcal_100g,
                protein_g_100g = excluded.protein_g_100g,
                carbohydrates_g_100g = excluded.carbohydrates_g_100g,
                fat_g_100g = excluded.fat_g_100g,
                fiber_g_100g = excluded.fiber_g_100g,
                iron_mg_100g = excluded.iron_mg_100g,
                calcium_mg_100g = excluded.calcium_mg_100g,
                potassium_mg_100g = excluded.potassium_mg_100g,
                source_name = excluded.source_name,
                source_citation = excluded.source_citation,
                verification_status = excluded.verification_status,
                retrieved_at = excluded.retrieved_at
            """,
            rows,
        )
        metadata_rows = list(METADATA.items()) + [
            ("built_at", retrieved_at),
            ("row_count", str(len(rows))),
        ]
        conn.executemany(
            "INSERT INTO db_metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            metadata_rows,
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


if __name__ == "__main__":
    count = build()
    print(f"Wrote {count} FCTB 2013 reference rows (unverified) to {DB_PATH}")
