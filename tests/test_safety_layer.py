"""
RevenueShield AI — Phase 7: safety layer tests.

Uses the EXISTING trained Phase 3A/3B model artifacts (skipped if missing).
Deterministic, fast, no live services — every scenario runs decide()/
safe_decide() directly against fixed feature dicts.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ML_DIR = Path(__file__).resolve().parent.parent / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import decision_engine as de  # noqa: E402
import safety_layer as sl  # noqa: E402


def _require_models() -> None:
    missing = [p for p in [de.RISK_MODEL_PATH, *de.ACTION_MODEL_PATHS.values()] if not p.exists()]
    if missing:
        pytest.skip(f"Required model artifact(s) missing: {missing}.")


EXISTING_CUSTOMER = {
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

COLD_START_CUSTOMER = {
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

SPARSE_HISTORY_CUSTOMER = {
    "customer_type": "existing",
    "payment_method": "card",
    "merchant_category": "saas",
    "customer_tenure_days": 40.0,
    "payment_amount": 2000.0,
    "previous_payment_count": 2,
    "previous_success_count": 1,
    "previous_failure_count": 1,
    "previous_retry_count": 0,
    "days_since_last_payment": 30.0,
}

HEAVY_RETRY_CUSTOMER = {
    "customer_type": "existing",
    "payment_method": "netbanking",
    "merchant_category": "ecommerce",
    "customer_tenure_days": 300.0,
    "payment_amount": 3000.0,
    "previous_payment_count": 10,
    "previous_success_count": 3,
    "previous_failure_count": 5,
    "previous_retry_count": 5,
    "days_since_last_payment": 5.0,
}


# ---------------------------------------------------------------------------
# 1. Cold-start / new customer
# ---------------------------------------------------------------------------

def test_cold_start_customer_does_not_crash_and_uses_conservative_fallback():
    _require_models()
    result = sl.safe_decide(COLD_START_CUSTOMER, transaction_id="T-COLD", customer_id="C-COLD")

    assert result.confidence["level"] == "low"
    assert result.safety["triggered"] is True
    assert "low_confidence" in " ".join(result.safety["reasons"])
    assert result.selected_action in result.permitted_actions
    # The deterministic fallback is the least-intrusive permitted action.
    assert result.selected_action == sl._safe_fallback_action(result.permitted_actions)


# ---------------------------------------------------------------------------
# 2. Sparse customer history
# ---------------------------------------------------------------------------

def test_sparse_history_does_not_crash_and_is_medium_confidence():
    _require_models()
    result = sl.safe_decide(SPARSE_HISTORY_CUSTOMER)

    assert result.confidence["level"] == "medium"
    assert result.selected_action in result.permitted_actions
    # Medium confidence alone (no high risk) must NOT force an override —
    # only "low" confidence triggers on its own (per spec: "do not blindly
    # trust a LOW-confidence recommendation").
    assert "low_confidence" not in " ".join(result.safety["reasons"])


# ---------------------------------------------------------------------------
# 3. Low-confidence model predictions
# ---------------------------------------------------------------------------

def test_low_confidence_overrides_to_permitted_fallback():
    _require_models()
    result = sl.safe_decide(COLD_START_CUSTOMER)

    assert result.confidence["level"] == "low"
    assert result.safety["overridden"] in (True, False)  # may already match fallback
    assert result.selected_action == sl._safe_fallback_action(result.permitted_actions)
    if result.safety["original_selected_action"] != result.selected_action:
        assert result.safety["overridden"] is True
        assert "SAFETY OVERRIDE" in result.explanation


# ---------------------------------------------------------------------------
# 4. High-risk transactions (pure unit test of the trigger logic — real
#    model outputs on realistic synthetic features don't reach the 0.90
#    threshold, so this tests the deterministic combination rule directly).
# ---------------------------------------------------------------------------

def test_high_risk_combined_with_uncertain_confidence_triggers():
    features = dict(EXISTING_CUSTOMER)  # amount/counts irrelevant to this check

    for level in ("low", "medium"):
        confidence = {"level": level, "basis": "test", "method": "test"}
        reasons = sl._evaluate_safety_triggers(features, risk_proba=0.95, confidence=confidence, original_action="do_nothing")
        assert any("high_risk_with_uncertain_confidence" in r for r in reasons)


def test_high_risk_with_standard_confidence_does_not_trigger_on_its_own():
    features = dict(EXISTING_CUSTOMER)
    confidence = {"level": "standard", "basis": "test", "method": "test"}
    reasons = sl._evaluate_safety_triggers(features, risk_proba=0.99, confidence=confidence, original_action="do_nothing")
    assert reasons == []


def test_moderate_risk_does_not_trigger_regardless_of_confidence():
    features = dict(EXISTING_CUSTOMER)
    for level in ("low", "medium", "standard"):
        confidence = {"level": level, "basis": "test", "method": "test"}
        reasons = sl._evaluate_safety_triggers(features, risk_proba=0.50, confidence=confidence, original_action="do_nothing")
        assert not any("high_risk" in r for r in reasons)


# ---------------------------------------------------------------------------
# 5 & 6. Low-value and high-value payments
# ---------------------------------------------------------------------------

def test_unusually_low_payment_amount_is_flagged_and_handled_safely():
    _require_models()
    features = dict(EXISTING_CUSTOMER, payment_amount=5.0)  # below MIN_TRAINED_PAYMENT_AMOUNT
    result = sl.safe_decide(features)

    assert result.safety["triggered"] is True
    assert any("payment_amount_out_of_trained_range" in r for r in result.safety["reasons"])
    assert result.selected_action in result.permitted_actions
    assert math.isfinite(result.expected_revenue[result.selected_action])


def test_unusually_high_payment_amount_is_flagged_and_handled_safely():
    _require_models()
    features = dict(EXISTING_CUSTOMER, payment_amount=5_000_000.0)  # above MAX_TRAINED_PAYMENT_AMOUNT
    result = sl.safe_decide(features)

    assert result.safety["triggered"] is True
    assert any("payment_amount_out_of_trained_range" in r for r in result.safety["reasons"])
    assert result.selected_action in result.permitted_actions
    for revenue in result.expected_revenue.values():
        assert math.isfinite(revenue)


def test_payment_amount_within_trained_range_is_not_flagged():
    _require_models()
    result = sl.safe_decide(EXISTING_CUSTOMER)
    assert not any("payment_amount_out_of_trained_range" in r for r in result.safety["reasons"])


# ---------------------------------------------------------------------------
# 7. Missing / invalid / unusual input values
# ---------------------------------------------------------------------------

def test_missing_feature_raises_safety_validation_error():
    features = dict(EXISTING_CUSTOMER)
    del features["payment_amount"]
    with pytest.raises(sl.SafetyValidationError, match="Missing required feature"):
        sl.safe_decide(features)


def test_negative_payment_amount_raises_safety_validation_error():
    features = dict(EXISTING_CUSTOMER, payment_amount=-100.0)
    with pytest.raises(sl.SafetyValidationError, match="positive"):
        sl.safe_decide(features)


def test_nan_amount_raises_safety_validation_error():
    features = dict(EXISTING_CUSTOMER, payment_amount=float("nan"))
    with pytest.raises(sl.SafetyValidationError, match="finite"):
        sl.safe_decide(features)


def test_infinite_tenure_raises_safety_validation_error():
    features = dict(EXISTING_CUSTOMER, customer_tenure_days=float("inf"))
    with pytest.raises(sl.SafetyValidationError, match="finite"):
        sl.safe_decide(features)


def test_inconsistent_historical_counts_raise_safety_validation_error():
    features = dict(EXISTING_CUSTOMER, previous_payment_count=1, previous_success_count=5, previous_failure_count=5)
    with pytest.raises(sl.SafetyValidationError, match="cannot exceed previous_payment_count"):
        sl.safe_decide(features)


def test_retry_count_exceeding_payment_count_raises_safety_validation_error():
    features = dict(
        EXISTING_CUSTOMER,
        previous_payment_count=1,
        previous_success_count=1,
        previous_failure_count=0,
        previous_retry_count=5,
    )
    with pytest.raises(sl.SafetyValidationError, match="previous_retry_count cannot exceed"):
        sl.safe_decide(features)


def test_invalid_customer_type_raises_safety_validation_error():
    features = dict(EXISTING_CUSTOMER, customer_type="bogus")
    with pytest.raises(sl.SafetyValidationError, match="customer_type"):
        sl.safe_decide(features)


# ---------------------------------------------------------------------------
# 8. permitted_actions constraint enforcement
# ---------------------------------------------------------------------------

def test_selected_action_always_within_permitted_actions_merchant_disabled():
    _require_models()
    constraints = de.MerchantConstraints(allowed_actions=frozenset({"do_nothing", "reminder"}))
    for features in (EXISTING_CUSTOMER, COLD_START_CUSTOMER, HEAVY_RETRY_CUSTOMER):
        result = sl.safe_decide(features, constraints=constraints)
        assert result.selected_action in result.permitted_actions
        assert result.selected_action in {"do_nothing", "reminder"}


def test_selected_action_always_within_permitted_actions_across_all_scenarios():
    _require_models()
    scenarios = [
        EXISTING_CUSTOMER,
        COLD_START_CUSTOMER,
        SPARSE_HISTORY_CUSTOMER,
        HEAVY_RETRY_CUSTOMER,
        dict(EXISTING_CUSTOMER, payment_amount=5.0),
        dict(EXISTING_CUSTOMER, payment_amount=5_000_000.0),
    ]
    for features in scenarios:
        result = sl.safe_decide(features)
        assert result.selected_action in result.permitted_actions


# ---------------------------------------------------------------------------
# Safe fallback behavior (deterministic, respects constraints)
# ---------------------------------------------------------------------------

def test_safe_fallback_action_is_deterministic_and_priority_ordered():
    assert sl._safe_fallback_action(["do_nothing", "retry", "reminder", "recovery_link"]) == "do_nothing"
    assert sl._safe_fallback_action(["retry", "reminder", "recovery_link"]) == "retry"
    assert sl._safe_fallback_action(["reminder", "recovery_link"]) == "reminder"
    assert sl._safe_fallback_action(["recovery_link"]) == "recovery_link"
    # Order of the input list must not matter — only ACTION_PRIORITY does.
    assert sl._safe_fallback_action(["recovery_link", "reminder", "retry"]) == "retry"


def test_safe_fallback_action_never_picks_a_non_permitted_action():
    for permitted in (["retry"], ["reminder", "recovery_link"], de.ACTIONS):
        fallback = sl._safe_fallback_action(permitted)
        assert fallback in permitted


# ---------------------------------------------------------------------------
# 10. Repeated interventions / repeated retries
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 10. Repeated interventions / repeated retries — a SAFETY TRIGGER, not an
# unconditional default constraint. permitted_actions is never modified by
# this layer; only decision_engine's own MerchantConstraints mechanism
# controls permitted_actions, completely unaffected by this layer.
# ---------------------------------------------------------------------------

def test_retry_fatigue_trigger_fires_when_engine_would_pick_retry_again():
    # Unit-level, deterministic: the real trained models learn a lower
    # retry-effectiveness for high-retry customers from the training data's
    # own fatigue discount (see ml/generate_data.py), so decide() rarely
    # picks 'retry' again for such a customer in practice — which is exactly
    # why this trigger exists as a safety net for if it ever does. Testing
    # the trigger rule directly, rather than hoping to find a live
    # feature combination that reproduces it, keeps this deterministic.
    features = dict(HEAVY_RETRY_CUSTOMER, previous_retry_count=5)
    confidence = {"level": "standard", "basis": "test", "method": "test"}
    reasons = sl._evaluate_safety_triggers(features, risk_proba=0.3, confidence=confidence, original_action="retry")
    assert any("retry_fatigue_threshold_reached" in r for r in reasons)


def test_retry_fatigue_trigger_does_not_fire_below_threshold():
    features = dict(HEAVY_RETRY_CUSTOMER, previous_retry_count=2)  # below RETRY_FATIGUE_THRESHOLD (3)
    confidence = {"level": "standard", "basis": "test", "method": "test"}
    reasons = sl._evaluate_safety_triggers(features, risk_proba=0.3, confidence=confidence, original_action="retry")
    assert not any("retry_fatigue" in r for r in reasons)


def test_retry_fatigue_trigger_does_not_fire_if_engine_did_not_choose_retry():
    features = dict(HEAVY_RETRY_CUSTOMER, previous_retry_count=5)
    confidence = {"level": "standard", "basis": "test", "method": "test"}
    reasons = sl._evaluate_safety_triggers(
        features, risk_proba=0.3, confidence=confidence, original_action="recovery_link"
    )
    assert not any("retry_fatigue" in r for r in reasons)


def test_high_retry_history_does_not_crash_and_permitted_actions_are_engine_owned():
    _require_models()
    # No merchant constraint set: permitted_actions must be EXACTLY what
    # decision_engine.decide() itself would produce — the safety layer must
    # never inject or modify MerchantConstraints on its own.
    safe = sl.safe_decide(HEAVY_RETRY_CUSTOMER)
    direct = de.decide(HEAVY_RETRY_CUSTOMER)
    assert safe.permitted_actions == direct.permitted_actions
    assert safe.selected_action in safe.permitted_actions


def test_explicit_merchant_retry_limit_still_works_unaffected_by_safety_layer():
    _require_models()
    # decision_engine's OWN constraint mechanism (unchanged) — the safety
    # layer must not interfere with it either way.
    constraints = de.MerchantConstraints(max_retry_count=2)
    safe = sl.safe_decide(HEAVY_RETRY_CUSTOMER, constraints=constraints)
    direct = de.decide(HEAVY_RETRY_CUSTOMER, constraints=constraints)
    assert safe.permitted_actions == direct.permitted_actions
    assert "retry" not in safe.permitted_actions


# ---------------------------------------------------------------------------
# 9 / 11. Regression — normal valid input, safety layer NOT triggered,
# behavior must match calling decision_engine.decide() directly.
# ---------------------------------------------------------------------------

def test_regression_untriggered_case_matches_decide_directly():
    _require_models()
    # No constraint injection happens in safe_decide() at all now — passing
    # constraints=None to both must be exactly equivalent.
    direct = de.decide(EXISTING_CUSTOMER, constraints=None)
    safe = sl.safe_decide(EXISTING_CUSTOMER, constraints=None)

    assert safe.safety["triggered"] is False
    assert safe.selected_action == direct.selected_action
    assert safe.predicted_failure_risk == pytest.approx(direct.predicted_failure_risk)
    assert safe.expected_revenue == pytest.approx(direct.expected_revenue)
    assert safe.action_success_probabilities == pytest.approx(direct.action_success_probabilities)
    assert safe.permitted_actions == direct.permitted_actions
    # The base explanation is preserved verbatim (safety adds nothing when untriggered).
    assert safe.explanation == direct.explanation


def test_regression_decide_engine_itself_is_never_modified_by_import():
    """Importing/using safety_layer must not monkeypatch or otherwise
    mutate decision_engine's module-level state.
    """
    _require_models()
    before = de.ACTION_PRIORITY.copy()
    sl.safe_decide(EXISTING_CUSTOMER)
    after = de.ACTION_PRIORITY.copy()
    assert before == after
