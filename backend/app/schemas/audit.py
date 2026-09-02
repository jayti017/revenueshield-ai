"""
RevenueShield AI — Phase 5: audit-record response schemas.

Reuses Action / ConfidenceResponse / ConstraintsAppliedResponse from
schemas/decision.py rather than redefining them — a stored audit record has
exactly the same shape as a live decision response, plus `id` and
`created_at`.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.schemas.decision import Action, ConfidenceResponse, ConstraintsAppliedResponse, SafetyInfoResponse


class AuditRecordResponse(BaseModel):
    id: int
    created_at: str

    transaction_id: Optional[str]
    customer_id: Optional[str]

    selected_action: Action
    predicted_failure_risk: float
    action_success_probabilities: dict[str, float]
    expected_revenue: dict[str, float]
    permitted_actions: list[str]
    constraints_applied: ConstraintsAppliedResponse
    explanation: str
    confidence: ConfidenceResponse
    causal_disclaimer: str
    safety: SafetyInfoResponse


class AuditRecordListResponse(BaseModel):
    count: int
    limit: int
    records: list[AuditRecordResponse]
