"""
RevenueShield AI — Phase 6: frontend API-contract regression test.

Phase 6 added no backend code — it's a frontend (frontend/) that consumes
the EXISTING Phase 4/5 API as-is. There is no JavaScript test framework in
this project (adding one, e.g. Vitest, would be a new dependency not
otherwise needed), so the real Phase 6 "test" is `npm run build` inside
frontend/ (TypeScript compilation fails loudly on any shape mismatch).

This file adds one thing on the Python side: a guard that the exact field
names frontend/src/types.ts hard-codes are still present in the live API
responses, so a future backend change that silently renames/removes a
field used by the frontend is still caught by `pytest` even without
running the frontend at all.

Phase 7 note: DECISION_RESPONSE_FIELDS now includes "safety" — an
additive field (see ml/safety_layer.py, backend/app/schemas/decision.py).
frontend/ was NOT modified for this; the added field is inert JSON the
existing frontend simply doesn't read.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

MODEL_DIR = Path(__file__).resolve().parent.parent / "ml" / "models"
REQUIRED_MODELS = [
    MODEL_DIR / "risk_model.joblib",
    MODEL_DIR / "action_model_do_nothing.joblib",
    MODEL_DIR / "action_model_retry.joblib",
    MODEL_DIR / "action_model_reminder.joblib",
    MODEL_DIR / "action_model_recovery_link.joblib",
]


def _require_models() -> None:
    missing = [str(p) for p in REQUIRED_MODELS if not p.exists()]
    if missing:
        pytest.skip(f"Required model artifact(s) missing: {missing}.")


DECISION_RESPONSE_FIELDS = {
    "transaction_id", "customer_id", "selected_action", "predicted_failure_risk",
    "action_success_probabilities", "expected_revenue", "permitted_actions",
    "constraints_applied", "explanation", "confidence", "causal_disclaimer",
    "safety",  # Phase 7: additive field
}
CONSTRAINTS_APPLIED_FIELDS = {"allowed_actions", "max_retry_count", "removed_by_constraint"}
CONFIDENCE_FIELDS = {"level", "basis", "method"}
AUDIT_RECORD_EXTRA_FIELDS = {"id", "created_at"}

PAYLOAD = {
    "transaction_id": "P6-CONTRACT-1",
    "customer_type": "existing",
    "payment_method": "card",
    "merchant_category": "saas",
    "customer_tenure_days": 240,
    "payment_amount": 4999,
    "previous_payment_count": 8,
    "previous_success_count": 5,
    "previous_failure_count": 3,
    "previous_retry_count": 2,
    "days_since_last_payment": 31,
}


def test_decision_response_matches_frontend_types_ts():
    """Mirrors frontend/src/types.ts's DecisionResponse interface."""
    _require_models()
    response = client.post("/api/v1/decision", json=PAYLOAD)
    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == DECISION_RESPONSE_FIELDS
    assert set(body["constraints_applied"].keys()) == CONSTRAINTS_APPLIED_FIELDS
    assert set(body["confidence"].keys()) == CONFIDENCE_FIELDS
    assert isinstance(body["action_success_probabilities"], dict)
    assert isinstance(body["expected_revenue"], dict)


def test_audit_list_response_matches_frontend_types_ts():
    """Mirrors frontend/src/types.ts's AuditRecordListResponse/AuditRecordResponse."""
    _require_models()
    client.post("/api/v1/decision", json=PAYLOAD)

    response = client.get("/api/v1/decisions?limit=5")
    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == {"count", "limit", "records"}
    assert isinstance(body["records"], list)
    assert len(body["records"]) >= 1
    record = body["records"][0]
    assert set(record.keys()) == DECISION_RESPONSE_FIELDS | AUDIT_RECORD_EXTRA_FIELDS


def test_health_response_matches_frontend_types_ts():
    """Mirrors the shape frontend/src/api.ts's checkHealth() expects."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"status", "phase"}
