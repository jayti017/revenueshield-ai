"""Persistence helpers for Razorpay webhook idempotency."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.db.database import get_connection


def record_webhook_event(
    event_id: str,
    *,
    event_type: str,
    razorpay_order_id: Optional[str],
    razorpay_payment_id: Optional[str],
    db_path: Optional[Path] = None,
) -> bool:
    """Record an event once. Returns False when the event was already seen."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO webhook_events (
                received_at, event_id, event_type, razorpay_order_id,
                razorpay_payment_id, processed
            ) VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                event_id,
                event_type,
                razorpay_order_id,
                razorpay_payment_id,
            ),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()
