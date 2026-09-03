"""
RevenueShield AI — Phase 8: payment-order persistence.

Reads and writes the payment_orders table (schema owned by database.py).
Contains storage logic only — never decision-making or Razorpay-API logic.
Completely separate from audit_repository.py/audit_records: a payment
order links to its RevenueShield decision by transaction_id ==
razorpay_order_id, looked up through the EXISTING
get_audit_record_by_transaction_id() — this module never reads or writes
audit_records itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.db.database import get_connection

# Status values this module writes. Razorpay's own payment statuses
# (captured/failed/authorized/...) are stored verbatim as returned by
# razorpay_client.fetch_payment() once a payment is verified — these two
# are RevenueShield's own bookkeeping states for an order that hasn't
# reached (or never reaches) a real Razorpay payment outcome.
STATUS_CREATED = "created"
STATUS_NO_ATTEMPT = "no_attempt"


def save_payment_order(
    razorpay_order_id: str,
    *,
    transaction_id: str,
    amount: float,
    currency: str,
    status: str = STATUS_CREATED,
    db_path: Optional[Path] = None,
) -> int:
    """Persists a newly-created Razorpay order and returns its new row id.
    Called right after razorpay_client.create_order() succeeds, before the
    frontend ever sees the order id — so a verify request can always be
    checked against a real, server-created row.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO payment_orders (
                created_at, razorpay_order_id, razorpay_payment_id,
                transaction_id, amount, currency, status,
                signature_verified, verified_at
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, 0, NULL)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                razorpay_order_id,
                transaction_id,
                amount,
                currency,
                status,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_payment_status(
    razorpay_order_id: str,
    *,
    razorpay_payment_id: Optional[str],
    status: str,
    signature_verified: bool,
    db_path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Updates a payment order after a verify attempt (successful or
    failed) and returns the updated row, or None if razorpay_order_id
    doesn't correspond to any order this server created.
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE payment_orders
            SET razorpay_payment_id = ?, status = ?, signature_verified = ?, verified_at = ?
            WHERE razorpay_order_id = ?
            """,
            (
                razorpay_payment_id,
                status,
                1 if signature_verified else 0,
                datetime.now(timezone.utc).isoformat(),
                razorpay_order_id,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM payment_orders WHERE razorpay_order_id = ?", (razorpay_order_id,)
        ).fetchone()
        return _row_to_dict(row) if row is not None else None
    finally:
        conn.close()


def get_payment_order(razorpay_order_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM payment_orders WHERE razorpay_order_id = ?", (razorpay_order_id,)
        ).fetchone()
        return _row_to_dict(row) if row is not None else None
    finally:
        conn.close()


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "razorpay_order_id": row["razorpay_order_id"],
        "razorpay_payment_id": row["razorpay_payment_id"],
        "transaction_id": row["transaction_id"],
        "amount": row["amount"],
        "currency": row["currency"],
        "status": row["status"],
        "signature_verified": bool(row["signature_verified"]),
        "verified_at": row["verified_at"],
    }

_STATUS_RANK = {
    "created": 0,
    "no_attempt": 0,
    "authorized": 1,
    "failed": 1,
    "captured": 2,
    "refunded": 3,
}


def update_payment_from_webhook(
    razorpay_order_id: str,
    *,
    razorpay_payment_id: Optional[str],
    status: str,
    db_path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Apply a webhook status without allowing stale events to downgrade it."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM payment_orders WHERE razorpay_order_id = ?",
            (razorpay_order_id,),
        ).fetchone()
        if row is None:
            return None

        current = str(row["status"])
        current_rank = _STATUS_RANK.get(current, 1)
        new_rank = _STATUS_RANK.get(status, 1)

        # captured/refunded must not be overwritten by a later-arriving
        # authorized/failed event. Unknown statuses are accepted only when
        # there is no stronger known status.
        if new_rank < current_rank:
            return _row_to_dict(row)

        conn.execute(
            """
            UPDATE payment_orders
            SET razorpay_payment_id = COALESCE(?, razorpay_payment_id),
                status = ?,
                signature_verified = 1,
                verified_at = ?
            WHERE razorpay_order_id = ?
            """,
            (
                razorpay_payment_id,
                status,
                datetime.now(timezone.utc).isoformat(),
                razorpay_order_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM payment_orders WHERE razorpay_order_id = ?",
            (razorpay_order_id,),
        ).fetchone()
        return _row_to_dict(updated) if updated is not None else None
    finally:
        conn.close()
