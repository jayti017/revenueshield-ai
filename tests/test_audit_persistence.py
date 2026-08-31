"""
RevenueShield AI — Phase 5: audit persistence tests.

DB isolation is handled by the autouse `_isolated_audit_db` fixture in
tests/conftest.py (applies to the whole suite, not just this file) — so
this module never reads or writes a developer's real local
backend/data/audit.db.
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


EXISTING_CUSTOMER_PAYLOAD = {
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


# 1, 2, 3 — a decision is persisted, retrievable, and values match
def test_decision_is_persisted_and_retrievable_with_matching_values():
    _require_models()
    payload = dict(EXISTING_CUSTOMER_PAYLOAD, transaction_id="AUDIT-RETRIEVE-1", customer_id="AUDIT-C1")

    post_response = client.post("/api/v1/decision", json=payload)
    assert post_response.status_code == 200
    posted = post_response.json()

    get_response = client.get("/api/v1/decisions/AUDIT-RETRIEVE-1")
    assert get_response.status_code == 200
    stored = get_response.json()

    assert stored["transaction_id"] == "AUDIT-RETRIEVE-1"
    assert stored["customer_id"] == "AUDIT-C1"
    assert stored["selected_action"] == posted["selected_action"]
    assert stored["predicted_failure_risk"] == pytest.approx(posted["predicted_failure_risk"])
    assert stored["expected_revenue"] == pytest.approx(posted["expected_revenue"])
    assert stored["action_success_probabilities"] == pytest.approx(posted["action_success_probabilities"])
    assert stored["explanation"] == posted["explanation"]
    assert stored["causal_disclaimer"] == posted["causal_disclaimer"]
    assert "id" in stored and "created_at" in stored


# 4 — GET /api/v1/decisions is bounded and recent-first
def test_list_decisions_is_bounded_and_recent_first():
    _require_models()
    for i in range(3):
        payload = dict(EXISTING_CUSTOMER_PAYLOAD, transaction_id=f"AUDIT-LIST-{i}")
        response = client.post("/api/v1/decision", json=payload)
        assert response.status_code == 200

    list_response = client.get("/api/v1/decisions?limit=2")
    assert list_response.status_code == 200
    body = list_response.json()

    assert body["limit"] == 2
    assert body["count"] == 2
    assert len(body["records"]) == 2
    # Most recent first: the last transaction posted appears first.
    assert body["records"][0]["transaction_id"] == "AUDIT-LIST-2"
    assert body["records"][1]["transaction_id"] == "AUDIT-LIST-1"


# 5 — unknown transaction_id -> 404
def test_unknown_transaction_id_returns_404():
    response = client.get("/api/v1/decisions/THIS-ID-DOES-NOT-EXIST")
    assert response.status_code == 404


# 6 — a database write failure does not break POST /api/v1/decision
def test_database_write_failure_does_not_break_decision_response(monkeypatch):
    _require_models()

    def _broken_save(*args, **kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr("app.api.routes.decision.save_audit_record", _broken_save)

    payload = dict(EXISTING_CUSTOMER_PAYLOAD, transaction_id="AUDIT-DB-FAIL")
    response = client.post("/api/v1/decision", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["selected_action"] in ["do_nothing", "retry", "reminder", "recovery_link"]

    # Confirms the failure was real (persistence genuinely didn't happen),
    # not silently no-opped before even trying.
    get_response = client.get("/api/v1/decisions/AUDIT-DB-FAIL")
    assert get_response.status_code == 404


# 7 — existing /health behavior unchanged
def test_health_endpoint_unchanged():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "phase": "1"}


# 8 — existing POST /api/v1/decision response shape unchanged
def test_decision_response_shape_unchanged():
    _require_models()
    response = client.post("/api/v1/decision", json=EXISTING_CUSTOMER_PAYLOAD)
    assert response.status_code == 200
    body = response.json()

    expected_keys = {
        "transaction_id", "customer_id", "selected_action",
        "predicted_failure_risk", "action_success_probabilities",
        "expected_revenue", "permitted_actions", "constraints_applied",
        "explanation", "confidence", "causal_disclaimer",
    }
    assert set(body.keys()) == expected_keys
