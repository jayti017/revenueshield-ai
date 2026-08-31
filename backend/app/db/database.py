"""
RevenueShield AI — Phase 5: SQLite connection + schema.

Deliberately minimal: standard-library sqlite3 only — no ORM, no external
database server (no PostgreSQL/MongoDB/Redis/SQLAlchemy). The database
file is created automatically on first use; nothing needs to be run
manually to set it up.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # backend/app/db/database.py -> project root

# Module-level (not function-default-bound) so tests can redirect it via
# monkeypatch.setattr(database, "DEFAULT_DB_PATH", tmp_path / "test.db")
# and have every subsequent get_connection() call pick up the new path —
# a real local audit.db is never touched by the test suite.
DEFAULT_DB_PATH = PROJECT_ROOT / "backend" / "data" / "audit.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    transaction_id TEXT,
    customer_id TEXT,
    selected_action TEXT NOT NULL,
    predicted_failure_risk REAL NOT NULL,
    action_success_probabilities TEXT NOT NULL,
    expected_revenue TEXT NOT NULL,
    permitted_actions TEXT NOT NULL,
    constraints_applied TEXT NOT NULL,
    explanation TEXT NOT NULL,
    confidence TEXT NOT NULL,
    causal_disclaimer TEXT NOT NULL
);
"""

_INDEX = "CREATE INDEX IF NOT EXISTS idx_audit_records_transaction_id ON audit_records (transaction_id);"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Opens a fresh connection to the given (or default) database file,
    creating the parent directory and schema if they don't exist yet.

    `db_path=None` resolves DEFAULT_DB_PATH at call time (not import time),
    which is what lets tests monkeypatch it per-test for isolation.
    """
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    conn.execute(_INDEX)
    return conn
