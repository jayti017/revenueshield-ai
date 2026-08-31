"""
RevenueShield AI — Phase 4: Decision service.

Thin wrapper that translates between the API's Pydantic schemas and the
EXISTING Phase 3C decision engine (ml/decision_engine.py). This file
contains NO decision-making logic of its own — it only builds the feature
dict decide() expects and converts constraints, then returns whatever the
engine produces.

The engine lives outside backend/ (in ml/), so this module adds ml/ to
sys.path the same way tests/test_decision_engine.py already does, rather
than duplicating or reimplementing anything from Phase 3A/3B/3C.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ML_DIR = PROJECT_ROOT / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import decision_engine as de  # noqa: E402


def run_decision(request) -> "de.DecisionResult":
    """Calls the existing decision engine with the request's features and
    (optional) merchant constraints. `request` is a
    app.schemas.decision.DecisionRequest — typed loosely here to avoid a
    circular import, since decision_service is imported by the route module
    that also imports the schema.
    """
    features = {
        "customer_type": request.customer_type,
        "payment_method": request.payment_method,
        "merchant_category": request.merchant_category,
        "customer_tenure_days": request.customer_tenure_days,
        "payment_amount": request.payment_amount,
        "previous_payment_count": request.previous_payment_count,
        "previous_success_count": request.previous_success_count,
        "previous_failure_count": request.previous_failure_count,
        "previous_retry_count": request.previous_retry_count,
        "days_since_last_payment": request.days_since_last_payment,
    }

    constraints = None
    if request.constraints is not None:
        allowed = request.constraints.allowed_actions
        constraints = de.MerchantConstraints(
            allowed_actions=frozenset(allowed) if allowed is not None else frozenset(de.ACTIONS),
            max_retry_count=request.constraints.max_retry_count,
        )

    return de.decide(
        features,
        constraints=constraints,
        transaction_id=request.transaction_id,
        customer_id=request.customer_id,
    )
