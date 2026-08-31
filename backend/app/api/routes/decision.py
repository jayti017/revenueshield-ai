"""
RevenueShield AI — Phase 4: Decision API route.

POST /api/v1/decision — accepts payment/customer features, calls the
EXISTING Phase 3C decision engine (via app/services/decision_service.py),
and returns its output. Contains no decision-making logic of its own.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.decision import (
    ConfidenceResponse,
    ConstraintsAppliedResponse,
    DecisionRequest,
    DecisionResponse,
)
from app.services.decision_service import run_decision

router = APIRouter(prefix="/api/v1", tags=["decision"])


@router.post("/decision", response_model=DecisionResponse)
def post_decision(request: DecisionRequest) -> DecisionResponse:
    try:
        result = run_decision(request)
    except FileNotFoundError as exc:
        # A Phase 3A/3B model artifact is missing — this is a server-side
        # setup problem, not something the caller did wrong.
        raise HTTPException(
            status_code=500,
            detail=(
                "A required model artifact is missing on the server. "
                "Run `python ml/train_risk_model.py` and "
                "`python ml/train_action_models.py` first."
            ),
        ) from exc
    except ValueError as exc:
        # e.g. a feature the engine needs wasn't provided — shouldn't happen
        # given DecisionRequest's validation, but handled explicitly rather
        # than leaking a raw traceback if it ever does.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — deliberately broad: last resort
        raise HTTPException(
            status_code=500,
            detail="Internal error while computing the decision.",
        ) from exc

    audit = result.audit_record

    return DecisionResponse(
        transaction_id=audit["transaction_id"],
        customer_id=audit["customer_id"],
        selected_action=result.selected_action,
        predicted_failure_risk=result.predicted_failure_risk,
        action_success_probabilities=result.action_success_probabilities,
        expected_revenue=result.expected_revenue,
        permitted_actions=result.permitted_actions,
        constraints_applied=ConstraintsAppliedResponse(**audit["constraints_applied"]),
        explanation=result.explanation,
        confidence=ConfidenceResponse(**result.confidence),
        causal_disclaimer=audit["causal_disclaimer"],
    )
