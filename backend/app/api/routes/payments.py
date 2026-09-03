"""
RevenueShield AI — Phase 8: Razorpay TEST-MODE payment routes.

Creates a Razorpay order, runs the existing RevenueShield decision against
that server-created order id, stores the payment-order record, and returns
the public Razorpay key plus the decision to the frontend.

Verification is server-authoritative: the backend fetches the payment from
Razorpay using the server-side secret, checks the order id, amount, currency,
and Checkout signature where applicable. No Razorpay secret is returned to
the browser.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.db.audit_repository import (
    get_audit_record_by_transaction_id,
    save_audit_record,
)
from app.db.payment_repository import (
    STATUS_NO_ATTEMPT,
    get_payment_order,
    save_payment_order,
    update_payment_status,
)
from app.schemas.decision import (
    ConfidenceResponse,
    ConstraintsAppliedResponse,
    DecisionResponse,
    SafetyInfoResponse,
)
from app.schemas.payment import (
    PaymentOrderRequest,
    PaymentOrderResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
)
from app.services.decision_service import run_decision
from app.services.razorpay_client import (
    RazorpayAPIError,
    RazorpayConfigurationError,
    create_order,
    fetch_payment,
    get_public_key_id,
    verify_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def _decision_response_from_result(result) -> DecisionResponse:
    """Convert the existing safety-layered decision result into the API schema."""
    audit = result.audit_record

    return DecisionResponse(
        transaction_id=audit["transaction_id"],
        customer_id=audit["customer_id"],
        selected_action=result.selected_action,
        predicted_failure_risk=result.predicted_failure_risk,
        action_success_probabilities=result.action_success_probabilities,
        expected_revenue=result.expected_revenue,
        permitted_actions=result.permitted_actions,
        constraints_applied=ConstraintsAppliedResponse(
            **audit["constraints_applied"]
        ),
        explanation=result.explanation,
        confidence=ConfidenceResponse(**result.confidence),
        causal_disclaimer=audit["causal_disclaimer"],
        safety=SafetyInfoResponse(**result.safety),
    )


def _decision_response_from_audit(audit: dict) -> DecisionResponse:
    """Convert a stored audit record back into the normal decision schema."""
    return DecisionResponse(
        transaction_id=audit["transaction_id"],
        customer_id=audit["customer_id"],
        selected_action=audit["selected_action"],
        predicted_failure_risk=audit["predicted_failure_risk"],
        action_success_probabilities=audit["action_success_probabilities"],
        expected_revenue=audit["expected_revenue"],
        permitted_actions=audit["permitted_actions"],
        constraints_applied=ConstraintsAppliedResponse(
            **audit["constraints_applied"]
        ),
        explanation=audit["explanation"],
        confidence=ConfidenceResponse(**audit["confidence"]),
        causal_disclaimer=audit["causal_disclaimer"],
        safety=SafetyInfoResponse(**audit["safety"]),
    )


@router.post("/order", response_model=PaymentOrderResponse)
def create_payment_order(request: PaymentOrderRequest) -> PaymentOrderResponse:
    """Create a Razorpay TEST-MODE order and compute its RevenueShield decision."""

    try:
        # The order must exist first because its server-generated id becomes
        # the trusted transaction_id for the RevenueShield audit trail.
        razorpay_order = create_order(
            request.payment_amount,
            currency="INR",
        )

        razorpay_order_id = razorpay_order.get("id")
        if not razorpay_order_id:
            raise RazorpayAPIError(
                "Razorpay returned an order without an order id."
            )

        decision_request = request.model_copy(
            update={"transaction_id": razorpay_order_id}
        )

        result = run_decision(decision_request)

        # For the payment flow, the decision must be auditable. Unlike the
        # normal decision endpoint's best-effort audit persistence, failure
        # here is treated as an integration failure rather than returning a
        # payment order with no RevenueShield decision record.
        save_audit_record(result.audit_record)

        save_payment_order(
            razorpay_order_id,
            transaction_id=razorpay_order_id,
            amount=request.payment_amount,
            currency="INR",
        )

        return PaymentOrderResponse(
            razorpay_order_id=razorpay_order_id,
            razorpay_key_id=get_public_key_id(),
            amount=request.payment_amount,
            currency="INR",
            receipt=razorpay_order.get("receipt"),
            decision=_decision_response_from_result(result),
        )

    except RazorpayConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    except RazorpayAPIError as exc:
        logger.warning("Razorpay order creation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "A required model artifact is missing on the server. "
                "Run `python ml/train_risk_model.py` and "
                "`python ml/train_action_models.py` first."
            ),
        ) from exc

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while creating payment order")
        raise HTTPException(
            status_code=500,
            detail="Internal error while creating the payment order.",
        ) from exc


@router.post("/verify", response_model=PaymentVerifyResponse)
def verify_payment(request: PaymentVerifyRequest) -> PaymentVerifyResponse:
    """Verify and persist the authoritative Razorpay payment state."""

    # Only orders created by this server can be verified.
    payment_order = get_payment_order(request.razorpay_order_id)
    if payment_order is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown Razorpay order id: "
                f"{request.razorpay_order_id!r}"
            ),
        )

    audit = get_audit_record_by_transaction_id(
        payment_order["transaction_id"]
    )
    if audit is None:
        logger.error(
            "Payment order %s has no matching audit record for transaction_id=%s",
            request.razorpay_order_id,
            payment_order["transaction_id"],
        )
        raise HTTPException(
            status_code=500,
            detail="No stored RevenueShield decision exists for this payment order.",
        )

    # Checkout was closed before a payment attempt.
    if not request.razorpay_payment_id:
        update_payment_status(
            request.razorpay_order_id,
            razorpay_payment_id=None,
            status=STATUS_NO_ATTEMPT,
            signature_verified=False,
        )

        return PaymentVerifyResponse(
            razorpay_order_id=request.razorpay_order_id,
            razorpay_payment_id=None,
            payment_status=STATUS_NO_ATTEMPT,
            signature_verified=False,
            amount=payment_order["amount"],
            decision=_decision_response_from_audit(audit),
        )

    try:
        # Never trust a payment status supplied by the browser. Ask Razorpay.
        payment = fetch_payment(request.razorpay_payment_id)
    except RazorpayConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RazorpayAPIError as exc:
        logger.warning("Razorpay payment lookup failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # A payment id from another order must never be accepted.
    if payment.get("order_id") != request.razorpay_order_id:
        raise HTTPException(
            status_code=400,
            detail="Payment does not belong to the supplied Razorpay order.",
        )

    expected_paise = round(float(payment_order["amount"]) * 100)
    actual_paise = payment.get("amount")
    if actual_paise is None or int(actual_paise) != expected_paise:
        raise HTTPException(
            status_code=400,
            detail="Payment amount does not match the stored order amount.",
        )

    if payment.get("currency") != payment_order["currency"]:
        raise HTTPException(
            status_code=400,
            detail="Payment currency does not match the stored order currency.",
        )

    payment_status = str(payment.get("status") or "unknown")
    signature_verified = False

    if request.razorpay_signature:
        signature_verified = verify_signature(
            request.razorpay_order_id,
            request.razorpay_payment_id,
            request.razorpay_signature,
        )

        if not signature_verified:
            update_payment_status(
                request.razorpay_order_id,
                razorpay_payment_id=request.razorpay_payment_id,
                status=payment_status,
                signature_verified=False,
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid Razorpay payment signature.",
            )

    # Razorpay success callbacks must include a valid Checkout signature.
    elif payment_status in {"authorized", "captured"}:
        update_payment_status(
            request.razorpay_order_id,
            razorpay_payment_id=request.razorpay_payment_id,
            status=payment_status,
            signature_verified=False,
        )
        raise HTTPException(
            status_code=400,
            detail="A successful Razorpay payment requires a valid signature.",
        )

    update_payment_status(
        request.razorpay_order_id,
        razorpay_payment_id=request.razorpay_payment_id,
        status=payment_status,
        signature_verified=signature_verified,
    )

    return PaymentVerifyResponse(
        razorpay_order_id=request.razorpay_order_id,
        razorpay_payment_id=request.razorpay_payment_id,
        payment_status=payment_status,
        signature_verified=signature_verified,
        amount=payment_order["amount"],
        decision=_decision_response_from_audit(audit),
    )
