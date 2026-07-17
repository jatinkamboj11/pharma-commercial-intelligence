"""SQLite connection helper.

Analytics queries live in app/queries.py as raw SQL on purpose:
window functions (NTILE, RANK) and multi-join aggregations are the
heart of this project, and hiding them behind an ORM would bury the
skill the project exists to demonstrate.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get(
    "WAREHOUSE_DB",
    Path(__file__).resolve().parents[1] / "data" / "warehouse.db",
))


def get_db():
    """FastAPI dependency yielding a per-request connection."""
    if not DB_PATH.exists():
        raise RuntimeError(
            f"Warehouse not found at {DB_PATH}. "
            "Run: python etl/generate_sample_data.py && python etl/load_data.py"
        )
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
