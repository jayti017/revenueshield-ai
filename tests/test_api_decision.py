"""
RevenueShield AI — Phase 4: Decision API tests.

Uses FastAPI's TestClient against the real app (which wires in the real
Phase 3C decision engine and the real Phase 3A/3B model artifacts) — no
mocking of the decision engine. If the model artifacts are missing, the
decision-dependent tests are skipped with a clear message rather than
failing obscurely.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = PROJECT_ROOT / "ml" / "models"
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
        pytest.skip(
            f"Required model artifact(s) missing: {missing}. "
            f"Run `python ml/train_risk_model.py` and `python ml/train_action_models.py` first."
        )


EXISTING_CUSTOMER_PAYLOAD = {
    "transaction_id": "T1",
    "customer_id": "C1",
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

COLD_START_PAYLOAD = {
    "customer_type": "new",
    "payment_method": "upi",
    "merchant_category": "ecommerce",
    "customer_tenure_days": 3,
    "payment_amount": 1200,
    "previous_payment_count": 0,
    "previous_success_count": 0,
    "previous_failure_count": 0,
    "previous_retry_count": 0,
    "days_since_last_payment": 0,
}

ACTIONS = ["do_nothing", "retry", "reminder", "recovery_link"]


# 1. Health endpoint still works
def test_health_endpoint_still_works():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "phase": "1"}


# 2 & 3. Valid decision request returns HTTP 200 and contains selected_action
def test_valid_decision_request_returns_200_with_selected_action():
    _require_models()
    response = client.post("/api/v1/decision", json=EXISTING_CUSTOMER_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["selected_action"] in ACTIONS


# 4. Response contains probabilities for the four actions
def test_response_contains_all_four_action_probabilities():
    _require_models()
    response = client.post("/api/v1/decision", json=EXISTING_CUSTOMER_PAYLOAD)
    body = response.json()
    assert set(body["action_success_probabilities"].keys()) == set(ACTIONS)
    assert all(0.0 <= p <= 1.0 for p in body["action_success_probabilities"].values())


# 5. Response contains expected-revenue information
def test_response_contains_expected_revenue_for_all_actions():
    _require_models()
    response = client.post("/api/v1/decision", json=EXISTING_CUSTOMER_PAYLOAD)
    body = response.json()
    assert set(body["expected_revenue"].keys()) == set(ACTIONS)
    assert all(v >= 0 for v in body["expected_revenue"].values())


# 6. Response contains explanation
def test_response_contains_explanation_naming_selected_action():
    _require_models()
    response = client.post("/api/v1/decision", json=EXISTING_CUSTOMER_PAYLOAD)
    body = response.json()
    assert isinstance(body["explanation"], str) and len(body["explanation"]) > 0
    assert body["selected_action"].replace("_", " ") in body["explanation"].lower().replace("_", " ") or \
        body["selected_action"] in body["explanation"].lower()


# 7. Invalid payment amount is rejected
def test_negative_payment_amount_is_rejected():
    payload = dict(EXISTING_CUSTOMER_PAYLOAD, payment_amount=-100)
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


def test_zero_payment_amount_is_rejected():
    payload = dict(EXISTING_CUSTOMER_PAYLOAD, payment_amount=0)
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


# 8. Missing required field is rejected
def test_missing_required_field_is_rejected():
    payload = dict(EXISTING_CUSTOMER_PAYLOAD)
    del payload["payment_amount"]
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


# 9. Invalid customer_type is rejected
def test_invalid_customer_type_is_rejected():
    payload = dict(EXISTING_CUSTOMER_PAYLOAD, customer_type="bogus")
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


def test_invalid_payment_method_is_rejected():
    payload = dict(EXISTING_CUSTOMER_PAYLOAD, payment_method="bitcoin")
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


def test_invalid_merchant_category_is_rejected():
    payload = dict(EXISTING_CUSTOMER_PAYLOAD, merchant_category="not_a_category")
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


def test_negative_historical_counts_are_rejected():
    payload = dict(EXISTING_CUSTOMER_PAYLOAD, previous_failure_count=-1)
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


def test_inconsistent_historical_counts_are_rejected():
    # success + failure > payment_count is logically impossible
    payload = dict(
        EXISTING_CUSTOMER_PAYLOAD,
        previous_payment_count=2,
        previous_success_count=5,
        previous_failure_count=5,
    )
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 422


# 10. Cold-start request works
def test_cold_start_request_works_and_flags_low_confidence():
    _require_models()
    response = client.post("/api/v1/decision", json=COLD_START_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["selected_action"] in ACTIONS
    assert body["confidence"]["level"] == "low"


# 11. Merchant constraints are respected through the API
def test_merchant_constraints_are_respected_through_the_api():
    _require_models()
    payload = dict(
        EXISTING_CUSTOMER_PAYLOAD,
        constraints={"allowed_actions": ["do_nothing", "retry", "reminder"]},
    )
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["selected_action"] != "recovery_link"
    assert "recovery_link" not in body["permitted_actions"]
    assert "recovery_link" in body["constraints_applied"]["removed_by_constraint"]


def test_max_retry_count_constraint_respected_through_the_api():
    _require_models()
    payload = dict(
        EXISTING_CUSTOMER_PAYLOAD,
        previous_retry_count=3,
        constraints={"max_retry_count": 3},
    )
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "retry" not in body["permitted_actions"]
    assert body["selected_action"] != "retry"


# 12. API does not bypass the Phase 3C decision engine — cross-check the
# API's output against calling the engine directly with identical features,
# for the same input, and confirm they match exactly.
def test_api_output_matches_direct_decision_engine_call():
    _require_models()
    import sys

    ml_dir = PROJECT_ROOT / "ml"
    if str(ml_dir) not in sys.path:
        sys.path.insert(0, str(ml_dir))
    import decision_engine as de

    features = {
        "customer_type": EXISTING_CUSTOMER_PAYLOAD["customer_type"],
        "payment_method": EXISTING_CUSTOMER_PAYLOAD["payment_method"],
        "merchant_category": EXISTING_CUSTOMER_PAYLOAD["merchant_category"],
        "customer_tenure_days": EXISTING_CUSTOMER_PAYLOAD["customer_tenure_days"],
        "payment_amount": EXISTING_CUSTOMER_PAYLOAD["payment_amount"],
        "previous_payment_count": EXISTING_CUSTOMER_PAYLOAD["previous_payment_count"],
        "previous_success_count": EXISTING_CUSTOMER_PAYLOAD["previous_success_count"],
        "previous_failure_count": EXISTING_CUSTOMER_PAYLOAD["previous_failure_count"],
        "previous_retry_count": EXISTING_CUSTOMER_PAYLOAD["previous_retry_count"],
        "days_since_last_payment": EXISTING_CUSTOMER_PAYLOAD["days_since_last_payment"],
    }
    direct_result = de.decide(
        features,
        transaction_id=EXISTING_CUSTOMER_PAYLOAD["transaction_id"],
        customer_id=EXISTING_CUSTOMER_PAYLOAD["customer_id"],
    )

    response = client.post("/api/v1/decision", json=EXISTING_CUSTOMER_PAYLOAD)
    body = response.json()

    assert body["selected_action"] == direct_result.selected_action
    assert body["predicted_failure_risk"] == pytest.approx(direct_result.predicted_failure_risk)
    for action in ACTIONS:
        assert body["expected_revenue"][action] == pytest.approx(direct_result.expected_revenue[action])
        assert body["action_success_probabilities"][action] == pytest.approx(
            direct_result.action_success_probabilities[action]
        )
