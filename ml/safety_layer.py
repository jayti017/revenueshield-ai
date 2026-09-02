"""
RevenueShield AI — Phase 7: Safety & Robustness Layer

Wraps the EXISTING, UNCHANGED Phase 3C decision engine
(ml/decision_engine.py) with a small, isolated safety layer. Does not
duplicate prediction, expected-revenue, constraint-application, or
tie-break logic — all of that is reused via decision_engine.decide()
exactly as-is.

What this module adds on top:

1. Defensive input validation — catches NaN/Inf/negative/inconsistent
   values BEFORE they reach a model, for callers that bypass the API's
   Pydantic validation (e.g. direct library use from scripts/notebooks).
   The API layer (backend/app/schemas/decision.py) already validates these
   for HTTP requests; this is defense-in-depth for everyone else, mirroring
   the same rules rather than inventing new ones.

2. Low-confidence override — decision_engine.py's confidence label was
   previously informational only; the engine always acted on the raw
   expected-revenue argmax regardless of confidence. This layer overrides
   the selected action to a conservative, deterministic fallback when
   confidence is "low".

3. High-risk + uncertain-confidence combo check — very high predicted
   failure risk combined with anything less than "standard" confidence is
   a second trigger for the same fallback. High risk alone, with standard
   confidence, is NOT overridden — that's RevenueShield's core intended use
   case (acting confidently on a well-understood high-risk payment), not
   something to be cautious about.

4. Out-of-trained-range payment amount — flags amounts outside the range
   the Phase 2 synthetic generator actually produced (see
   ml/generate_data.py's draw_amount(), clipped to [49.0, 200_000.0]) as a
   third trigger, since the models have no real training signal there.

5. Retry-fatigue trigger — decision_engine.py's own action models already
   learn a lower effectiveness for repeated retries from the training
   data's built-in fatigue discount (see ml/generate_data.py's
   FATIGUE_RETRY_THRESHOLD), but nothing currently stops the engine from
   still picking 'retry' again for a customer who has already been retried
   many times, if that remains the highest-expected-revenue option. This
   layer adds a FOURTH trigger — not a constraint, not an unconditional
   default — for exactly that situation: previous_retry_count at or above
   RETRY_FATIGUE_THRESHOLD (3, reusing ml/generate_data.py's own
   FATIGUE_RETRY_THRESHOLD rather than inventing a new number) AND the
   engine's own chosen action is 'retry'. It does NOT modify
   permitted_actions or inject any MerchantConstraints — a merchant who
   sets an explicit max_retry_count still controls permitted_actions
   exactly as decision_engine.py already implements it, completely
   unaffected by this layer. For every other case (no repeated-retry
   pick, or previous_retry_count below the threshold, or no constraints
   set at all), safe_decide() is a byte-for-byte pass-through of
   decide()'s own choice — normal Phase 3C behavior is unchanged unless
   one of these four conditions genuinely fires.

Deterministic safe fallback: the least customer-intrusive PERMITTED action,
i.e. the first entry of decision_engine.ACTION_PRIORITY that is in
permitted_actions — reusing the engine's own existing tie-break priority
list rather than inventing a second ordering.

USAGE:

    from safety_layer import safe_decide
    result = safe_decide(features, transaction_id="T1", customer_id="C1")
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ML_DIR = Path(__file__).resolve().parent
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import decision_engine as de  # noqa: E402 — reused, never duplicated or modified

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Confidence levels that trigger the conservative fallback on their own.
LOW_CONFIDENCE_TRIGGER_LEVELS = frozenset({"low"})

# Predicted failure risk at/above this, COMBINED with anything less than
# "standard" confidence, also triggers the fallback. A round, clearly-
# in-the-tail threshold — a deliberate choice, documented here rather than
# hidden, not derived from a specific statistic.
HIGH_RISK_THRESHOLD = 0.90
HIGH_RISK_CONFIDENCE_LEVELS_THAT_TRIGGER = frozenset({"low", "medium"})

# Matches ml/generate_data.py's draw_amount(): amounts are lognormal-drawn
# then clipped to this exact range — models have no real training signal
# outside it.
MIN_TRAINED_PAYMENT_AMOUNT = 49.0
MAX_TRAINED_PAYMENT_AMOUNT = 200_000.0

# Matches ml/generate_data.py's FATIGUE_RETRY_THRESHOLD — the same number
# already used by the synthetic data's own generating process to model
# diminishing/reversed retry effectiveness after repeated retries. Used
# here ONLY as a safety-trigger condition (see class docstring point 5) —
# it never modifies MerchantConstraints or permitted_actions.
RETRY_FATIGUE_THRESHOLD = 3


class SafetyValidationError(ValueError):
    """Raised when input features are unsafe to hand to a model at all
    (non-finite, negative-where-invalid, or internally inconsistent). A
    subclass of ValueError so it's caught anywhere existing code already
    catches ValueError from decision_engine.decide().
    """


# ---------------------------------------------------------------------------
# Input validation (defense-in-depth beyond the API's own Pydantic checks)
# ---------------------------------------------------------------------------

def _require_finite(name: str, value) -> None:
    try:
        is_finite = math.isfinite(float(value))
    except (TypeError, ValueError):
        is_finite = False
    if value is None or not is_finite:
        raise SafetyValidationError(f"{name} must be a finite number, got {value!r}.")


def validate_features_safety(features: dict) -> None:
    """Defense-in-depth validation for direct callers of safe_decide()/
    decide() that bypass the HTTP API's Pydantic validation. Mirrors the
    same consistency rules DecisionRequest already enforces
    (backend/app/schemas/decision.py) — not new rules, just re-applied for
    non-HTTP callers.
    """
    missing = [c for c in de.FEATURE_COLUMNS if c not in features]
    if missing:
        raise SafetyValidationError(f"Missing required feature(s): {missing}.")

    _require_finite("payment_amount", features["payment_amount"])
    if features["payment_amount"] <= 0:
        raise SafetyValidationError(f"payment_amount must be positive, got {features['payment_amount']!r}.")

    _require_finite("customer_tenure_days", features["customer_tenure_days"])
    if features["customer_tenure_days"] < 0:
        raise SafetyValidationError("customer_tenure_days cannot be negative.")

    _require_finite("days_since_last_payment", features["days_since_last_payment"])
    if features["days_since_last_payment"] < 0:
        raise SafetyValidationError("days_since_last_payment cannot be negative.")

    for count_field in (
        "previous_payment_count", "previous_success_count",
        "previous_failure_count", "previous_retry_count",
    ):
        value = features[count_field]
        _require_finite(count_field, value)
        if value < 0:
            raise SafetyValidationError(f"{count_field} cannot be negative, got {value!r}.")

    if features["previous_success_count"] + features["previous_failure_count"] > features["previous_payment_count"]:
        raise SafetyValidationError(
            "previous_success_count + previous_failure_count cannot exceed previous_payment_count."
        )
    if features["previous_retry_count"] > features["previous_payment_count"]:
        raise SafetyValidationError("previous_retry_count cannot exceed previous_payment_count.")

    if features["customer_type"] not in ("new", "existing"):
        raise SafetyValidationError(
            f"customer_type must be 'new' or 'existing', got {features['customer_type']!r}."
        )


# ---------------------------------------------------------------------------
# Safety trigger evaluation
# ---------------------------------------------------------------------------

def _evaluate_safety_triggers(
    features: dict, risk_proba: float, confidence: dict, original_action: str
) -> list[str]:
    reasons: list[str] = []

    if confidence["level"] in LOW_CONFIDENCE_TRIGGER_LEVELS:
        reasons.append(f"low_confidence (level={confidence['level']!r})")

    if risk_proba >= HIGH_RISK_THRESHOLD and confidence["level"] in HIGH_RISK_CONFIDENCE_LEVELS_THAT_TRIGGER:
        reasons.append(
            f"high_risk_with_uncertain_confidence (risk={risk_proba:.3f} >= "
            f"{HIGH_RISK_THRESHOLD}, confidence={confidence['level']!r})"
        )

    amount = features["payment_amount"]
    if amount < MIN_TRAINED_PAYMENT_AMOUNT or amount > MAX_TRAINED_PAYMENT_AMOUNT:
        reasons.append(
            f"payment_amount_out_of_trained_range (amount={amount!r}, "
            f"trained range=[{MIN_TRAINED_PAYMENT_AMOUNT}, {MAX_TRAINED_PAYMENT_AMOUNT}])"
        )

    if features["previous_retry_count"] >= RETRY_FATIGUE_THRESHOLD and original_action == "retry":
        reasons.append(
            f"retry_fatigue_threshold_reached (previous_retry_count="
            f"{features['previous_retry_count']!r} >= {RETRY_FATIGUE_THRESHOLD}, "
            f"engine chose 'retry' again)"
        )

    return reasons


def _safe_fallback_action(permitted: list[str]) -> str:
    """Deterministic: the least customer-intrusive PERMITTED action, using
    the engine's own existing ACTION_PRIORITY ordering — never a second,
    separately-invented priority list. Always respects permitted_actions
    because it only ever selects from that list.
    """
    for action in de.ACTION_PRIORITY:
        if action in permitted:
            return action
    return permitted[0]  # unreachable — ACTION_PRIORITY covers all four actions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class SafeDecisionResult:
    selected_action: str
    explanation: str
    audit_record: dict
    predicted_failure_risk: float
    action_success_probabilities: dict[str, float]
    expected_revenue: dict[str, float]
    permitted_actions: list[str]
    confidence: dict
    safety: dict


def safe_decide(
    features: dict,
    *,
    constraints: Optional["de.MerchantConstraints"] = None,
    transaction_id: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> SafeDecisionResult:
    """Safety-layered wrapper around the existing, unmodified
    decision_engine.decide(). For any input where no safety trigger fires,
    the returned selected_action/explanation/audit_record are identical in
    substance to calling decide() directly (only the added `safety` field
    and its note appended to the explanation differ) — see
    tests/test_safety_layer.py's regression tests.
    """
    validate_features_safety(features)

    result = de.decide(
        features,
        constraints=constraints,
        transaction_id=transaction_id,
        customer_id=customer_id,
    )

    trigger_reasons = _evaluate_safety_triggers(
        features, result.predicted_failure_risk, result.confidence, result.selected_action
    )
    triggered = len(trigger_reasons) > 0

    original_action = result.selected_action
    final_action = _safe_fallback_action(result.permitted_actions) if triggered else original_action
    overridden = triggered and final_action != original_action

    safety_info = {
        "triggered": triggered,
        "reasons": trigger_reasons,
        "original_selected_action": original_action,
        "final_selected_action": final_action,
        "overridden": overridden,
    }

    explanation = result.explanation
    if overridden:
        explanation = (
            f"{explanation} SAFETY OVERRIDE: the engine's own highest-expected-revenue "
            f"choice ({de.ACTION_LABELS[original_action]}) was overridden to "
            f"{de.ACTION_LABELS[final_action]} because: {'; '.join(trigger_reasons)}."
        )
    elif triggered:
        explanation = (
            f"{explanation} SAFETY NOTE: {'; '.join(trigger_reasons)} — the engine's own "
            f"choice already matched the conservative fallback, so no override was needed."
        )

    audit_record = dict(result.audit_record)
    audit_record["selected_action"] = final_action
    audit_record["reason"] = explanation
    audit_record["safety"] = safety_info

    return SafeDecisionResult(
        selected_action=final_action,
        explanation=explanation,
        audit_record=audit_record,
        predicted_failure_risk=result.predicted_failure_risk,
        action_success_probabilities=result.action_success_probabilities,
        expected_revenue=result.expected_revenue,
        permitted_actions=result.permitted_actions,
        confidence=result.confidence,
        safety=safety_info,
    )
