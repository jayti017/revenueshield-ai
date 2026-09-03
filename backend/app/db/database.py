"""
RevenueShield AI — Phase 5: SQLite connection + schema.

Deliberately minimal: standard-library sqlite3 only — no ORM, no external
database server (no PostgreSQL/MongoDB/Redis/SQLAlchemy). The database
file is created automatically on first use; nothing needs to be run
manually to set it up.

Phase 8: adds a second, separate table — payment_orders — for Razorpay
TEST-MODE order/payment tracking. Kept entirely separate from
audit_records on purpose: the Phase 5/7 audit_records schema and its
consumers (audit_repository.py, routes/audit.py, routes/decision.py) are
completely unchanged by Phase 8. payment_orders links back to a decision
via transaction_id == razorpay_order_id, so a payment's decision is looked
up through the EXISTING get_audit_record_by_transaction_id() — no new
audit logic, no duplicated persistence logic.
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

# Phase 7: added alongside the existing columns above. New installs get it
# via _SCHEMA's CREATE TABLE; databases created before Phase 7 (Phase 5/6)
# need it added in place — SQLite has no "ADD COLUMN IF NOT EXISTS", so
# _ensure_safety_info_column checks PRAGMA table_info first and only runs
# ALTER TABLE when the column is actually missing. Nullable + no default
# requirement, so existing rows are unaffected (they simply read back as
# NULL for this column).
_SAFETY_INFO_COLUMN = "safety_info"


def _ensure_safety_info_column(conn: sqlite3.Connection) -> None:
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_records)").fetchall()}
    if _SAFETY_INFO_COLUMN not in existing_columns:
        conn.execute(f"ALTER TABLE audit_records ADD COLUMN {_SAFETY_INFO_COLUMN} TEXT")


# Phase 8: a brand-new table, so a plain CREATE TABLE IF NOT EXISTS is
# sufficient — unlike safety_info above, there is no pre-existing
# payment_orders table anywhere that could need an in-place migration.
_PAYMENT_ORDERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    razorpay_order_id TEXT NOT NULL UNIQUE,
    razorpay_payment_id TEXT,
    transaction_id TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    signature_verified INTEGER NOT NULL DEFAULT 0,
    verified_at TEXT
);
"""

_PAYMENT_ORDERS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_payment_orders_transaction_id ON payment_orders (transaction_id);"
)


# Phase 8 Batch 3: webhook idempotency/event tracking. Razorpay may retry
# the same webhook, so x-razorpay-event-id is stored uniquely.
_WEBHOOK_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    razorpay_order_id TEXT,
    razorpay_payment_id TEXT,
    processed INTEGER NOT NULL DEFAULT 1
);
"""

_WEBHOOK_EVENTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_webhook_events_order_id ON webhook_events (razorpay_order_id);"
)


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Opens a fresh connection to the given (or default) database file,
    creating the parent directory and schema if they don't exist yet, and
    migrating in the Phase 7 safety_info column if this is a database
    created before Phase 7.

    `db_path=None` resolves DEFAULT_DB_PATH at call time (not import time),
    which is what lets tests monkeypatch it per-test for isolation.
    """
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    conn.execute(_INDEX)
    _ensure_safety_info_column(conn)
    conn.execute(_PAYMENT_ORDERS_SCHEMA)
    conn.execute(_PAYMENT_ORDERS_INDEX)
    conn.execute(_WEBHOOK_EVENTS_SCHEMA)
    conn.execute(_WEBHOOK_EVENTS_INDEX)
    return conn