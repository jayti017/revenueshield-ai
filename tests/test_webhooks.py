from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.db import database
from app.db.payment_repository import save_payment_order, get_payment_order
from app.main import app


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _payment_payload(event: str, order_id: str, payment_id: str, status: str) -> dict:
    return {
        "entity": "event",
        "event": event,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 10000,
                    "currency": "INR",
                    "status": status,
                }
            }
        },
    }


def test_webhook_captured_updates_payment(monkeypatch, tmp_path):
    db = tmp_path / "webhook.db"
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", db)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook-secret")
    save_payment_order("order_1", transaction_id="order_1", amount=100.0, currency="INR")

    body = json.dumps(_payment_payload("payment.captured", "order_1", "pay_1", "captured"), separators=(",", ":")).encode()
    client = TestClient(app)
    response = client.post(
        "/api/v1/payments/webhook",
        content=body,
        headers={
            "X-Razorpay-Signature": _sign(body, "webhook-secret"),
            "x-razorpay-event-id": "evt_1",
            "content-type": "application/json",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert get_payment_order("order_1")["status"] == "captured"
    assert get_payment_order("order_1")["signature_verified"] is True


def test_webhook_duplicate_is_idempotent(monkeypatch, tmp_path):
    db = tmp_path / "duplicate.db"
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", db)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook-secret")
    save_payment_order("order_2", transaction_id="order_2", amount=100.0, currency="INR")
    body = json.dumps(_payment_payload("payment.captured", "order_2", "pay_2", "captured"), separators=(",", ":")).encode()
    headers = {"X-Razorpay-Signature": _sign(body, "webhook-secret"), "x-razorpay-event-id": "evt_dup"}
    client = TestClient(app)
    assert client.post("/api/v1/payments/webhook", content=body, headers=headers).status_code == 200
    second = client.post("/api/v1/payments/webhook", content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


def test_webhook_invalid_signature_rejected(monkeypatch, tmp_path):
    db = tmp_path / "invalid.db"
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", db)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook-secret")
    body = json.dumps(_payment_payload("payment.failed", "order_x", "pay_x", "failed")).encode()
    response = TestClient(app).post(
        "/api/v1/payments/webhook",
        content=body,
        headers={"X-Razorpay-Signature": "bad", "x-razorpay-event-id": "evt_bad"},
    )
    assert response.status_code == 400


def test_webhook_does_not_downgrade_captured_payment(monkeypatch, tmp_path):
    db = tmp_path / "ordering.db"
    monkeypatch.setattr(database, "DEFAULT_DB_PATH", db)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "webhook-secret")
    save_payment_order("order_3", transaction_id="order_3", amount=100.0, currency="INR", status="captured")
    body = json.dumps(_payment_payload("payment.failed", "order_3", "pay_3", "failed"), separators=(",", ":")).encode()
    response = TestClient(app).post(
        "/api/v1/payments/webhook",
        content=body,
        headers={"X-Razorpay-Signature": _sign(body, "webhook-secret"), "x-razorpay-event-id": "evt_order"},
    )
    assert response.status_code == 200
    assert get_payment_order("order_3")["status"] == "captured"
