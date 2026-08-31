"""
RevenueShield AI — Phase 5: read-only audit-history endpoints.

GET /api/v1/decisions and GET /api/v1/decisions/{transaction_id} — reads
from the store populated by POST /api/v1/decision (routes/decision.py).
No decision-making logic lives here; this module only reads what has
already been persisted.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.db.audit_repository import get_audit_record_by_transaction_id, list_audit_records
from app.schemas.audit import AuditRecordListResponse, AuditRecordResponse

router = APIRouter(prefix="/api/v1", tags=["audit"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


@router.get("/decisions", response_model=AuditRecordListResponse)
def get_recent_decisions(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> AuditRecordListResponse:
    """Most recent decisions first, bounded by `limit` (default 50, max 500)."""
    records = list_audit_records(limit=limit)
    return AuditRecordListResponse(count=len(records), limit=limit, records=records)


@router.get("/decisions/{transaction_id}", response_model=AuditRecordResponse)
def get_decision_by_transaction_id(transaction_id: str) -> AuditRecordResponse:
    record = get_audit_record_by_transaction_id(transaction_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No stored decision found for transaction_id={transaction_id!r}",
        )
    return record
