"""
RevenueShield AI — Phase 3C: Explainable Decision Engine

Combines the EXISTING trained models from Phase 3A (risk_model.joblib) and
Phase 3B (action_model_*.joblib) to select the best permitted recovery
action for a given at-risk payment, calculate its expected recovered
revenue, apply merchant safety constraints, and produce a human-readable
explanation plus a structured audit record.

This file does NOT retrain any model, does NOT build a frontend, database,
API, or Razorpay integration. It only loads and uses the artifacts already
produced by ml/train_risk_model.py and ml/train_action_models.py.

IMPORTANT — causal caveat (see README.md's Phase 3B section for the full
explanation): the four action-outcome models are observational, predictive
models. Their output is P(success | features, this action was taken) for
payments that historically received that action — NOT a validated causal
treatment effect. This engine's explanations and audit records are worded
to keep that distinction explicit rather than imply the models measure what
would have happened under a different action.

USAGE (as a library):

    from decision_engine import decide, MerchantConstraints

    result = decide(features, transaction_id="T1", customer_id="C1")
    print(result.explanation)
    print(result.audit_record)

USAGE (as a command-line demo, from the project root):

    python ml/decision_engine.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = PROJECT_ROOT / "ml" / "models"
RISK_MODEL_PATH = MODEL_DIR / "risk_model.joblib"

ACTIONS = ["do_nothing", "retry", "reminder", "recovery_link"]
ACTION_MODEL_PATHS = {action: MODEL_DIR / f"action_model_{action}.joblib" for action in ACTIONS}

ACTION_LABELS = {
    "do_nothing": "Do nothing",
    "retry": "Retry",
    "reminder": "Send reminder",
    "recovery_link": "Send recovery link",
}

# Tie-break priority when two or more permitted actions have effectively
# equal expected revenue: prefer the least customer-intrusive action. This
# list is deliberately in ascending order of assumed customer friction/cost
# (doing nothing costs the customer nothing; a recovery link is the most
# intrusive ask). Documented here and in README.md's Phase 3C section.
ACTION_PRIORITY = ["do_nothing", "retry", "reminder", "recovery_link"]

# Two expected-revenue values within this many currency units of each other
# are treated as a tie. Chosen to be small relative to typical transaction
# amounts (tens to thousands of rupees) — see README for rationale.
TIE_BREAK_EPSILON = 0.01

CATEGORICAL_FEATURES = ["customer_type", "payment_method", "merchant_category"]
NUMERIC_FEATURES = [
    "customer_tenure_days",
    "payment_amount",
    "previous_payment_count",
    "previous_success_count",
    "previous_failure_count",
    "previous_retry_count",
    "days_since_last_payment",
]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES


# ---------------------------------------------------------------------------
# Model loading (uses existing artifacts only — never trains anything here)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_risk_model():
    if not RISK_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Risk model not found at {RISK_MODEL_PATH}. "
            f"Run `python ml/train_risk_model.py` first (Phase 3A)."
        )
    return joblib.load(RISK_MODEL_PATH)


@lru_cache(maxsize=None)
def _load_action_model(action: str):
    path = ACTION_MODEL_PATHS[action]
    if not path.exists():
        raise FileNotFoundError(
            f"Action model for '{action}' not found at {path}. "
            f"Run `python ml/train_action_models.py` first (Phase 3B)."
        )
    return joblib.load(path)


def _build_feature_row(features: dict) -> pd.DataFrame:
    missing = [c for c in FEATURE_COLUMNS if c not in features]
    if missing:
        raise ValueError(f"Missing required feature(s): {missing}. Required: {FEATURE_COLUMNS}")
    row = {c: features[c] for c in FEATURE_COLUMNS}
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

def predict_failure_risk(features: dict) -> float:
    """Pre-action payment failure probability, from the Phase 3A risk model."""
    model = _load_risk_model()
    X = _build_feature_row(features)
    return float(model.predict_proba(X)[:, 1][0])


def predict_action_success_probabilities(features: dict) -> dict[str, float]:
    """P(success | features, action) for each of the four actions, from the
    Phase 3B action-outcome models. See module docstring for the causal
    caveat — these are observational predictions, not treatment effects.
    """
    X = _build_feature_row(features)
    probabilities = {}
    for action in ACTIONS:
        model = _load_action_model(action)
        probabilities[action] = float(model.predict_proba(X)[:, 1][0])
    return probabilities


# ---------------------------------------------------------------------------
# Merchant constraints
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MerchantConstraints:
    """Simple, configurable MVP constraint set.

    allowed_actions: which of the four actions this merchant permits at all.
    max_retry_count: if set, `retry` is excluded once the customer's
        previous_retry_count reaches this value. There is no equivalent
        max_reminder_count because the dataset does not track a
        previous_reminder_count field (see README's Phase 3C limitations
        note) — reminder frequency can still be controlled coarsely via
        allowed_actions.
    """
    allowed_actions: frozenset[str] = field(default_factory=lambda: frozenset(ACTIONS))
    max_retry_count: int | None = None

    def __post_init__(self):
        invalid = set(self.allowed_actions) - set(ACTIONS)
        if invalid:
            raise ValueError(f"Unknown action(s) in allowed_actions: {invalid}. Valid actions: {ACTIONS}")


def _apply_constraints(features: dict, constraints: MerchantConstraints) -> tuple[list[str], dict[str, str]]:
    """Returns (permitted_actions, removed_by_constraint) where the latter
    maps each excluded action to a human-readable reason. `do_nothing` is
    guaranteed to remain available as a safe fallback if every other action
    would otherwise be excluded — see the "always-available fallback" note
    in README.md's Phase 3C section.
    """
    removed: dict[str, str] = {}
    permitted: list[str] = []

    for action in ACTIONS:
        if action not in constraints.allowed_actions:
            removed[action] = "disabled by merchant configuration"
            continue
        if action == "retry" and constraints.max_retry_count is not None:
            prev_retries = features.get("previous_retry_count", 0)
            if prev_retries >= constraints.max_retry_count:
                removed[action] = (
                    f"retry limit reached ({prev_retries} previous retries "
                    f">= max {constraints.max_retry_count})"
                )
                continue
        permitted.append(action)

    if not permitted:
        permitted = ["do_nothing"]
        removed.pop("do_nothing", None)

    return permitted, removed


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def _select_best_action(permitted: list[str], expected_revenue: dict[str, float]) -> str:
    """Highest expected revenue among permitted actions, with a deterministic
    tie-break: when two or more permitted actions are within
    TIE_BREAK_EPSILON of the maximum, the action earliest in ACTION_PRIORITY
    wins (i.e. the least customer-intrusive of the tied options).
    """
    best_value = max(expected_revenue[a] for a in permitted)
    tied = [a for a in permitted if abs(expected_revenue[a] - best_value) <= TIE_BREAK_EPSILON]

    if len(tied) == 1:
        return tied[0]

    for action in ACTION_PRIORITY:
        if action in tied:
            return action
    return tied[0]  # unreachable in practice — ACTION_PRIORITY covers all four actions


# ---------------------------------------------------------------------------
# Confidence (explicit heuristic proxy — see README for why)
# ---------------------------------------------------------------------------

def _determine_confidence(features: dict) -> dict:
    """RevenueShield's current models produce point probability estimates,
    not statistically rigorous confidence intervals (no ensemble variance,
    no Bayesian posterior, no calibrated prediction interval was built in
    Phase 3A/3B). Rather than invent a number that looks precise but isn't,
    this uses an explicit, documented, deterministic proxy based on how
    much payment history the customer has — more history is the one thing
    this project's Phase 3A/3B evaluation actually demonstrated correlates
    with model reliability (see the cold-start ROC-AUC results in
    README.md's Phase 3A/3B sections).
    """
    previous_payment_count = features.get("previous_payment_count", 0)

    if previous_payment_count == 0:
        level = "low"
        basis = "Cold-start customer: zero prior payment history available."
    elif previous_payment_count < 3:
        level = "medium"
        basis = f"Limited payment history available ({previous_payment_count} prior payment(s))."
    else:
        level = "standard"
        basis = f"Sufficient payment history available ({previous_payment_count} prior payments)."

    return {
        "level": level,
        "basis": basis,
        "method": (
            "Heuristic proxy based on previous_payment_count — NOT a "
            "statistically derived confidence interval. See README.md's "
            "Phase 3C section for why."
        ),
    }


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------

def _build_explanation(
    selected: str,
    expected_revenue: dict[str, float],
    action_probabilities: dict[str, float],
    permitted: list[str],
    removed_by_constraint: dict[str, str],
    confidence: dict,
    risk_proba: float,
) -> str:
    label = ACTION_LABELS[selected]
    revenue = expected_revenue[selected]
    probability = action_probabilities[selected]

    parts = [
        f"{label} selected because it had the highest expected recovered "
        f"revenue (Rs {revenue:,.2f}) among permitted actions, with a "
        f"predicted success probability of {probability:.1%}."
    ]

    other_permitted = sorted(
        (a for a in permitted if a != selected),
        key=lambda a: -expected_revenue[a],
    )
    if other_permitted:
        bits = ", ".join(
            f"{ACTION_LABELS[a]} (Rs {expected_revenue[a]:,.2f}, {action_probabilities[a]:.1%} predicted success)"
            for a in other_permitted
        )
        parts.append(f"Other permitted actions considered: {bits}.")

    if removed_by_constraint:
        bits = "; ".join(f"{ACTION_LABELS[a]} — {reason}" for a, reason in removed_by_constraint.items())
        parts.append(f"Actions excluded by merchant constraints: {bits}.")

    parts.append(f"Predicted payment failure risk before any action: {risk_proba:.1%}.")

    if confidence["level"] == "low":
        parts.append(
            f"NOTE: this decision is based on LIMITED/NO customer history "
            f"({confidence['basis']}) and therefore has LOW confidence."
        )
    elif confidence["level"] == "medium":
        parts.append(f"NOTE: {confidence['basis']} Confidence in this decision is MEDIUM.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------

def _build_audit_record(
    *,
    transaction_id: str | None,
    customer_id: str | None,
    risk_proba: float,
    action_probabilities: dict[str, float],
    expected_revenue: dict[str, float],
    constraints: MerchantConstraints,
    removed_by_constraint: dict[str, str],
    permitted: list[str],
    selected: str,
    explanation: str,
    confidence: dict,
) -> dict:
    return {
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "predicted_failure_risk": risk_proba,
        "action_success_probabilities": action_probabilities,
        "expected_revenue": expected_revenue,
        "constraints_applied": {
            "allowed_actions": sorted(constraints.allowed_actions),
            "max_retry_count": constraints.max_retry_count,
            "removed_by_constraint": removed_by_constraint,
        },
        "permitted_actions": permitted,
        "selected_action": selected,
        "reason": explanation,
        "confidence": confidence,
        "causal_disclaimer": (
            "action_success_probabilities are observational predictions "
            "P(success | features, action was taken), estimated from "
            "synthetic historical data where action assignment was itself "
            "risk-biased. They are NOT validated causal treatment effects."
        ),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class DecisionResult:
    selected_action: str
    explanation: str
    audit_record: dict
    predicted_failure_risk: float
    action_success_probabilities: dict[str, float]
    expected_revenue: dict[str, float]
    permitted_actions: list[str]
    confidence: dict


def decide(
    features: dict,
    *,
    constraints: MerchantConstraints | None = None,
    transaction_id: str | None = None,
    customer_id: str | None = None,
) -> DecisionResult:
    """Selects the best permitted recovery action for one payment.

    `features` must contain all of FEATURE_COLUMNS (see module constant),
    including `payment_amount`, which is used both as a model feature and
    to convert predicted probabilities into expected revenue.
    """
    constraints = constraints or MerchantConstraints()

    risk_proba = predict_failure_risk(features)
    action_probabilities = predict_action_success_probabilities(features)

    payment_amount = features["payment_amount"]
    expected_revenue = {
        action: payment_amount * probability
        for action, probability in action_probabilities.items()
    }

    permitted, removed_by_constraint = _apply_constraints(features, constraints)
    selected = _select_best_action(permitted, expected_revenue)
    confidence = _determine_confidence(features)
    explanation = _build_explanation(
        selected, expected_revenue, action_probabilities, permitted,
        removed_by_constraint, confidence, risk_proba,
    )
    audit_record = _build_audit_record(
        transaction_id=transaction_id,
        customer_id=customer_id,
        risk_proba=risk_proba,
        action_probabilities=action_probabilities,
        expected_revenue=expected_revenue,
        constraints=constraints,
        removed_by_constraint=removed_by_constraint,
        permitted=permitted,
        selected=selected,
        explanation=explanation,
        confidence=confidence,
    )

    return DecisionResult(
        selected_action=selected,
        explanation=explanation,
        audit_record=audit_record,
        predicted_failure_risk=risk_proba,
        action_success_probabilities=action_probabilities,
        expected_revenue=expected_revenue,
        permitted_actions=permitted,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Command-line demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    print("--- RevenueShield AI — Phase 3C: Explainable Decision Engine (demo) ---\n")

    existing_customer = {
        "customer_type": "existing",
        "payment_method": "card",
        "merchant_category": "saas",
        "customer_tenure_days": 240.0,
        "payment_amount": 4999.0,
        "previous_payment_count": 8,
        "previous_success_count": 5,
        "previous_failure_count": 3,
        "previous_retry_count": 2,
        "days_since_last_payment": 31.0,
    }

    print("=== Scenario 1: existing customer, default constraints ===")
    result = decide(existing_customer, transaction_id="DEMO-T1", customer_id="DEMO-C1")
    print(f"Selected action: {result.selected_action}")
    print(f"Explanation: {result.explanation}\n")

    print("=== Scenario 2: same customer, merchant disables recovery_link ===")
    constraints = MerchantConstraints(allowed_actions=frozenset({"do_nothing", "retry", "reminder"}))
    result2 = decide(existing_customer, constraints=constraints, transaction_id="DEMO-T2", customer_id="DEMO-C1")
    print(f"Selected action: {result2.selected_action}")
    print(f"Explanation: {result2.explanation}\n")

    cold_start_customer = {
        "customer_type": "new",
        "payment_method": "upi",
        "merchant_category": "ecommerce",
        "customer_tenure_days": 3.0,
        "payment_amount": 1200.0,
        "previous_payment_count": 0,
        "previous_success_count": 0,
        "previous_failure_count": 0,
        "previous_retry_count": 0,
        "days_since_last_payment": 0.0,
    }

    print("=== Scenario 3: cold-start customer ===")
    result3 = decide(cold_start_customer, transaction_id="DEMO-T3", customer_id="DEMO-CS1")
    print(f"Selected action: {result3.selected_action}")
    print(f"Explanation: {result3.explanation}\n")

    print("=== Audit record for Scenario 3 (structured) ===")
    for key, value in result3.audit_record.items():
        print(f"  {key}: {value}")

    print("\nSUCCESS: decision engine demo complete. No model was retrained; no frontend/API/database was built.")


if __name__ == "__main__":
    try:
        _demo()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
