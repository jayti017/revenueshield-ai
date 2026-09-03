"""
RevenueShield AI — Phase 8: payment API schemas.

Pydantic request/response models for the Razorpay TEST-MODE payment
endpoints. Validate API input/output only; no decision-making, Razorpay,
or persistence logic lives here.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.decision import DecisionRequest, DecisionResponse


class PaymentOrderRequest(DecisionRequest):
    """Same customer/payment context as DecisionRequest.

    The payments route ignores any caller-supplied transaction_id and
    replaces it with the server-created Razorpay order id.
    """


class PaymentOrderResponse(BaseModel):
    razorpay_order_id: str
    razorpay_key_id: str = Field(
        description="Public Razorpay key id only — safe for the frontend."
    )
    amount: float = Field(description="Order amount in rupees.")
    currency: str
    receipt: Optional[str] = None
    decision: DecisionResponse


class PaymentVerifyRequest(BaseModel):
    """Razorpay Checkout callback data.

    Success callbacks contain order id, payment id, and signature.
    Failed payments can contain order id + payment id without a success
    signature. If checkout is abandoned before any attempt, only the order
    id is known.
    """

    razorpay_order_id: str = Field(min_length=1)
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None

    @model_validator(mode="after")
    def _signature_requires_payment_id(self) -> "PaymentVerifyRequest":
        if (
            self.razorpay_signature is not None
            and self.razorpay_payment_id is None
        ):
            raise ValueError(
                "razorpay_signature was provided without razorpay_payment_id."
            )
        return self


class PaymentVerifyResponse(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: Optional[str]
    payment_status: str = Field(
        description="Authoritative payment status returned by Razorpay, or no_attempt."
    )
    signature_verified: bool
    amount: float = Field(description="Order amount in rupees.")
    decision: DecisionResponse
