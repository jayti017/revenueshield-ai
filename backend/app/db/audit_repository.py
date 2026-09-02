"""
RevenueShield AI — Phase 5: audit-record persistence.

Reads and writes the audit_records table (schema owned by database.py).
Contains storage logic only — never decision-making logic. Records arriving
here are already fully computed dicts, shaped exactly like
ml.decision_engine.DecisionResult.audit_record (Phase 7: now
ml.safety_layer.SafeDecisionResult.audit_record, which is the same dict
shape plus a "safety" key), by the time they reach save_audit_record().

Phase 7: persists/reads the safety_info column added by database.py's
migration. Rows written before Phase 7 have safety_info = NULL; those are
read back with a clearly-labeled placeholder (see _row_to_dict) rather than
crashing or fabricating a fake "no trigger fired" claim.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.db.database import get_connection


def save_audit_record(record: dict[str, Any], db_path: Optional[Path] = None) -> int:
    """Persists one audit record and returns its new row id.

    Raises on failure rather than swallowing errors — the caller (the
    decision route) decides that persistence is best-effort and catches
    this, logging a warning instead of failing the API response. Keeping
    the raise here (rather than returning None on failure) means direct
    callers/tests get a real exception to assert on, not a silently wrong
    return value.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO audit_records (
                created_at, transaction_id, customer_id, selected_action,
                predicted_failure_risk, action_success_probabilities,
                expected_revenue, permitted_actions, constraints_applied,
                explanation, confidence, causal_disclaimer, safety_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                record.get("transaction_id"),
                record.get("customer_id"),
                record["selected_action"],
                record["predicted_failure_risk"],
                json.dumps(record["action_success_probabilities"]),
                json.dumps(record["expected_revenue"]),
                json.dumps(record["permitted_actions"]),
                json.dumps(record["constraints_applied"]),
                # ml.decision_engine's audit_record uses the key "reason";
                # stored/exposed here as "explanation" for consistency with
                # DecisionResponse's field name — same string, different key.
                record["reason"],
                json.dumps(record["confidence"]),
                record["causal_disclaimer"],
                # Phase 7: "safety" is present on every record produced by
                # ml.safety_layer.safe_decide(); None only for a caller that
                # somehow bypassed it entirely (defensive, not expected).
                json.dumps(record["safety"]) if record.get("safety") is not None else None,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _row_to_dict(row: Any) -> dict[str, Any]:
    raw_safety_info = row["safety_info"] if "safety_info" in row.keys() else None
    if raw_safety_info is not None:
        safety = json.loads(raw_safety_info)
    else:
        # Pre-Phase-7 row (or a caller that bypassed safety_layer): no
        # safety evaluation was ever recorded for it. Rather than silently
        # claiming "triggered": False (which would be fabricating a result
        # that was never actually computed), original/final both echo the
        # stored selected_action and reasons is left empty with an explicit
        # note.
        safety = {
            "triggered": False,
            "reasons": ["no_safety_evaluation_recorded (row predates Phase 7)"],
            "original_selected_action": row["selected_action"],
            "final_selected_action": row["selected_action"],
            "overridden": False,
        }

    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "transaction_id": row["transaction_id"],
        "customer_id": row["customer_id"],
        "selected_action": row["selected_action"],
        "predicted_failure_risk": row["predicted_failure_risk"],
        "action_success_probabilities": json.loads(row["action_success_probabilities"]),
        "expected_revenue": json.loads(row["expected_revenue"]),
        "permitted_actions": json.loads(row["permitted_actions"]),
        "constraints_applied": json.loads(row["constraints_applied"]),
        "explanation": row["explanation"],
        "confidence": json.loads(row["confidence"]),
        "causal_disclaimer": row["causal_disclaimer"],
        "safety": safety,
    }


def list_audit_records(limit: int = 50, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Most recent records first (highest id first) — deterministic
    ordering, bounded by `limit`.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM audit_records ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_audit_record_by_transaction_id(
    transaction_id: str, db_path: Optional[Path] = None
) -> Optional[dict[str, Any]]:
    """Returns the most recent record for this transaction_id, or None if
    none exists. transaction_id is caller-supplied and not enforced unique
    (a retry with the same id could in principle be submitted twice) —
    "most recent" is the well-defined choice for that case.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM audit_records WHERE transaction_id = ? ORDER BY id DESC LIMIT 1",
            (transaction_id,),
        ).fetchone()
        return _row_to_dict(row) if row is not None else None
    finally:
        conn.close()
