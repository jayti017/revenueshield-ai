"""
RevenueShield AI — Phase 4: Decision API schemas.

Pydantic request/response models for POST /api/v1/decision. These validate
API input/output ONLY — no decision-making logic lives here. The actual
decision comes from the existing Phase 3C engine (ml/decision_engine.py),
called via app/services/decision_service.py.

Field names deliberately match ml/decision_engine.FEATURE_COLUMNS exactly,
so the service layer can pass them through without renaming.

Phase 7 addition: SafetyInfoResponse + the optional `safety` field on
DecisionResponse. Additive only — every existing field is unchanged.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Action = Literal["do_nothing", "retry", "reminder", "recovery_link"]


class MerchantConstraintsRequest(BaseModel):
    """Mirrors ml.decision_engine.MerchantConstraints. Optional — omit
    entirely for the engine's default (all four actions permitted, no
    retry limit).
    """

    allowed_actions: Optional[list[Action]] = Field(
        default=None,
        description="Which actions this merchant permits. Omit for all four (the engine default).",
    )
    max_retry_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="If set, 'retry' is excluded once previous_retry_count reaches this value.",
    )


class DecisionRequest(BaseModel):
    transaction_id: Optional[str] = None
    customer_id: Optional[str] = None

    customer_type: Literal["new", "existing"]
    payment_method: Literal["card", "upi", "netbanking", "wallet"]
    merchant_category: Literal[
        "ecommerce", "saas", "education", "travel", "healthcare", "subscription"
    ]

    customer_tenure_days: float = Field(ge=0)
    payment_amount: float = Field(gt=0)
    previous_payment_count: int = Field(ge=0)
    previous_success_count: int = Field(ge=0)
    previous_failure_count: int = Field(ge=0)
    previous_retry_count: int = Field(ge=0)
    days_since_last_payment: float = Field(ge=0)

    constraints: Optional[MerchantConstraintsRequest] = None

    @model_validator(mode="after")
    def _check_historical_counts_are_consistent(self) -> "DecisionRequest":
        """Same consistency rules Phase 2's validate_data.py enforces on the
        training data — kept here too so the API can't be fed a request that
        contradicts them.
        """
        if self.previous_success_count + self.previous_failure_count > self.previous_payment_count:
            raise ValueError(
                "previous_success_count + previous_failure_count cannot exceed previous_payment_count"
            )
        if self.previous_retry_count > self.previous_payment_count:
            raise ValueError("previous_retry_count cannot exceed previous_payment_count")
        return self


class ConfidenceResponse(BaseModel):
    level: Literal["low", "medium", "standard"]
    basis: str
    method: str


class ConstraintsAppliedResponse(BaseModel):
    allowed_actions: list[str]
    max_retry_count: Optional[int]
    removed_by_constraint: dict[str, str]


class SafetyInfoResponse(BaseModel):
    """Phase 7: mirrors ml.safety_layer's safety_info dict exactly."""

    triggered: bool
    reasons: list[str]
    original_selected_action: Action
    final_selected_action: Action
    overridden: bool


class DecisionResponse(BaseModel):
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

    # Restated on every response, not just in documentation — see
    # ml/decision_engine.py and README.md's Phase 3B/4 sections for why
    # this distinction matters.
    causal_disclaimer: str

    # Phase 7: additive field. Always present (never omitted), but
    # `triggered` is False and `original_selected_action ==
    # final_selected_action` for the normal case — see README's Phase 7
    # section.
    safety: SafetyInfoResponse
