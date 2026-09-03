"""Phase 8 — Razorpay TEST-MODE payment integration tests.

Razorpay HTTP requests are mocked, so these tests never contact Razorpay and
never move real money. They verify the local order -> RevenueShield -> audit
and payment-verification integration contract.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.db.audit_repository import get_audit_record_by_transaction_id, save_audit_record
from app.db.payment_repository import get_payment_order
from app.main import app

client = TestClient(app)


PAYLOAD = {
    "transaction_id": "CLIENT-ID-MUST-BE-REPLACED",
    "customer_id": "C-PAY-1",
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


def _audit(order_id: str = "order_test_123") -> dict:
    return {
        "transaction_id": order_id,
        "customer_id": "C-PAY-1",
        "selected_action": "recovery_link",
        "predicted_failure_risk": 0.82,
        "action_success_probabilities": {
            "do_nothing": 0.20,
            "retry": 0.64,
            "reminder": 0.80,
            "recovery_link": 0.91,
        },
        "expected_revenue": {
            "do_nothing": 999.80,
            "retry": 3199.36,
            "reminder": 3999.20,
            "recovery_link": 4549.09,
        },
        "permitted_actions": [
            "do_nothing",
            "retry",
            "reminder",
            "recovery_link",
        ],
        "constraints_applied": {
            "allowed_actions": [
                "do_nothing",
                "retry",
                "reminder",
                "recovery_link",
            ],
            "max_retry_count": None,
            "removed_by_constraint": {},
        },
        "reason": "recovery_link has the highest expected revenue among permitted actions.",
        "confidence": {
            "level": "standard",
            "basis": "history",
            "method": "model",
        },
        "causal_disclaimer": "Predictions are observational and do not establish causal effects.",
        "safety": {
            "triggered": False,
            "reasons": [],
            "original_selected_action": "recovery_link",
            "final_selected_action": "recovery_link",
            "overridden": False,
        },
    }


class FakeDecisionResult:
    def __init__(self, audit: dict):
        self.audit_record = audit
        self.selected_action = audit["selected_action"]
        self.predicted_failure_risk = audit["predicted_failure_risk"]
        self.action_success_probabilities = audit["action_success_probabilities"]
        self.expected_revenue = audit["expected_revenue"]
        self.permitted_actions = audit["permitted_actions"]
        self.explanation = audit["reason"]
        self.confidence = audit["confidence"]
        self.safety = audit["safety"]


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / "phase8.db"
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", path)
    return path


def test_create_payment_order_creates_order_then_decision_and_persists(monkeypatch, isolated_db):
    events: list[str] = []
    order_id = "order_test_123"

    def fake_create_order(amount_rupees, *, currency="INR", receipt=None, notes=None):
        events.append(f"order:{amount_rupees}:{currency}")
        return {
            "id": order_id,
            "amount": 499900,
            "currency": currency,
        }

    def fake_run_decision(request):
        events.append(f"decision:{request.transaction_id}")
        assert request.transaction_id == order_id
        assert request.payment_amount == 4999
        return FakeDecisionResult(_audit(order_id))

    monkeypatch.setattr("app.api.routes.payments.create_order", fake_create_order)
    monkeypatch.setattr("app.api.routes.payments.run_decision", fake_run_decision)
    monkeypatch.setattr("app.api.routes.payments.get_public_key_id", lambda: "rzp_test_public")

    response = client.post("/api/v1/payments/order", json=PAYLOAD)

    assert response.status_code == 200
    body = response.json()

    assert events == [
        "order:4999.0:INR",
        f"decision:{order_id}",
    ]
    assert body["razorpay_order_id"] == order_id
    assert body["razorpay_key_id"] == "rzp_test_public"
    assert body["amount"] == 4999
    assert body["decision"]["transaction_id"] == order_id

    stored_payment = get_payment_order(order_id)
    assert stored_payment is not None
    assert stored_payment["transaction_id"] == order_id
    assert stored_payment["amount"] == pytest.approx(4999)

    stored_audit = get_audit_record_by_transaction_id(order_id)
    assert stored_audit is not None
    assert stored_audit["transaction_id"] == order_id


def _seed_order_and_audit(order_id: str = "order_test_123", amount: float = 4999):
    from app.db.payment_repository import save_payment_order

    save_audit_record(_audit(order_id))
    save_payment_order(
        order_id,
        transaction_id=order_id,
        amount=amount,
        currency="INR",
    )


def test_verify_no_attempt_records_no_attempt_and_returns_decision(isolated_db):
    _seed_order_and_audit()

    response = client.post(
        "/api/v1/payments/verify",
        json={"razorpay_order_id": "order_test_123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payment_status"] == "no_attempt"
    assert body["signature_verified"] is False
    assert body["razorpay_payment_id"] is None
    assert body["decision"]["transaction_id"] == "order_test_123"

    stored = get_payment_order("order_test_123")
    assert stored["status"] == "no_attempt"
    assert stored["signature_verified"] is False


def test_verify_success_fetches_payment_and_validates_signature(monkeypatch, isolated_db):
    _seed_order_and_audit()
    secret = "test_secret"

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", secret)

    monkeypatch.setattr(
        "app.api.routes.payments.fetch_payment",
        lambda payment_id: {
            "id": payment_id,
            "order_id": "order_test_123",
            "amount": 499900,
            "currency": "INR",
            "status": "captured",
        },
    )

    signature = hmac.new(
        secret.encode(),
        b"order_test_123|pay_test_123",
        hashlib.sha256,
    ).hexdigest()

    response = client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": signature,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payment_status"] == "captured"
    assert body["signature_verified"] is True
    assert body["razorpay_payment_id"] == "pay_test_123"

    stored = get_payment_order("order_test_123")
    assert stored["status"] == "captured"
    assert stored["signature_verified"] is True
    assert stored["razorpay_payment_id"] == "pay_test_123"


def test_verify_failed_payment_is_recorded_without_success_signature(monkeypatch, isolated_db):
    _seed_order_and_audit()

    monkeypatch.setattr(
        "app.api.routes.payments.fetch_payment",
        lambda payment_id: {
            "id": payment_id,
            "order_id": "order_test_123",
            "amount": 499900,
            "currency": "INR",
            "status": "failed",
        },
    )

    response = client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_failed_123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payment_status"] == "failed"
    assert body["signature_verified"] is False

    stored = get_payment_order("order_test_123")
    assert stored["status"] == "failed"
    assert stored["razorpay_payment_id"] == "pay_failed_123"


def test_verify_rejects_unknown_order(isolated_db):
    response = client.post(
        "/api/v1/payments/verify",
        json={"razorpay_order_id": "does_not_exist"},
    )
    assert response.status_code == 404


def test_verify_rejects_payment_from_different_order(monkeypatch, isolated_db):
    _seed_order_and_audit()

    monkeypatch.setattr(
        "app.api.routes.payments.fetch_payment",
        lambda payment_id: {
            "id": payment_id,
            "order_id": "different_order",
            "amount": 499900,
            "currency": "INR",
            "status": "failed",
        },
    )

    response = client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
        },
    )

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]


def test_verify_rejects_currency_mismatch(monkeypatch, isolated_db):
    _seed_order_and_audit()

    monkeypatch.setattr(
        "app.api.routes.payments.fetch_payment",
        lambda payment_id: {
            "id": payment_id,
            "order_id": "order_test_123",
            "amount": 499900,
            "currency": "USD",
            "status": "failed",
        },
    )

    response = client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
        },
    )

    assert response.status_code == 400
    assert "currency" in response.json()["detail"]


def test_verify_rejects_invalid_signature(monkeypatch, isolated_db):
    _seed_order_and_audit()

    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_secret")

    monkeypatch.setattr(
        "app.api.routes.payments.fetch_payment",
        lambda payment_id: {
            "id": payment_id,
            "order_id": "order_test_123",
            "amount": 499900,
            "currency": "INR",
            "status": "captured",
        },
    )

    response = client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "definitely-not-valid",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Razorpay payment signature."


def test_successful_payment_without_signature_is_rejected(monkeypatch, isolated_db):
    _seed_order_and_audit()

    monkeypatch.setattr(
        "app.api.routes.payments.fetch_payment",
        lambda payment_id: {
            "id": payment_id,
            "order_id": "order_test_123",
            "amount": 499900,
            "currency": "INR",
            "status": "captured",
        },
    )

    response = client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
        },
    )

    assert response.status_code == 400
    assert "requires a valid signature" in response.json()["detail"]
