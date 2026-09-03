"""Razorpay TEST-MODE webhook receiver.

The endpoint verifies the raw request body before parsing it, uses the
x-razorpay-event-id header for idempotency, and updates only payment-order
bookkeeping. RevenueShield decisions are not recomputed from webhook data.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.db.payment_repository import update_payment_from_webhook
from app.db.webhook_repository import record_webhook_event
from app.services.razorpay_client import (
    RazorpayConfigurationError,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/payments", tags=["payments"])

SUPPORTED_EVENTS = {"payment.authorized", "payment.captured", "payment.failed", "order.paid"}


def _extract_payment(payload: dict, event_type: str) -> tuple[str | None, str | None, str | None]:
    """Return (order_id, payment_id, status) from supported event payloads."""
    if event_type == "order.paid":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order = payload.get("payload", {}).get("order", {}).get("entity", {})
        order_id = order.get("id")
        payment_id = payment.get("id")
        return order_id, payment_id, "captured"

    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    return payment.get("order_id"), payment.get("id"), payment.get("status")


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str | None = Header(default=None, alias="x-razorpay-event-id"),
):
    """Receive and safely process Razorpay payment webhooks."""
    raw_body = await request.body()

    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing Razorpay webhook signature.")
    if not x_razorpay_event_id:
        raise HTTPException(status_code=400, detail="Missing Razorpay webhook event id.")

    try:
        if not verify_webhook_signature(raw_body, x_razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature.")
    except RazorpayConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON payload.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object.")

    event_type = str(payload.get("event") or "")
    if not event_type:
        raise HTTPException(status_code=400, detail="Webhook event type is missing.")

    order_id, payment_id, status = _extract_payment(payload, event_type)

    # Idempotency is recorded only after signature and payload validation.
    is_new = record_webhook_event(
        x_razorpay_event_id,
        event_type=event_type,
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
    )
    if not is_new:
        return {"status": "ok", "duplicate": True}

    if event_type not in SUPPORTED_EVENTS:
        return {"status": "ignored", "duplicate": False, "event": event_type}

    if not order_id or not status:
        raise HTTPException(status_code=400, detail="Webhook payment data is incomplete.")

    updated = update_payment_from_webhook(
        order_id,
        razorpay_payment_id=payment_id,
        status=status,
    )

    # A valid Razorpay event can refer to an order that this RevenueShield
    # instance did not create. Acknowledge it rather than causing retries.
    if updated is None:
        logger.info("Ignoring valid webhook for unknown order %s", order_id)
        return {"status": "ignored", "duplicate": False, "reason": "unknown_order"}

    return {
        "status": "processed",
        "duplicate": False,
        "event": event_type,
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "payment_status": updated["status"],
    }
