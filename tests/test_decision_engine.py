"""
RevenueShield AI — Phase 3C: Decision Engine Tests

Uses the EXISTING trained Phase 3A/3B model artifacts in ml/models/ — does
not retrain anything. If those artifacts are missing, the model-dependent
tests are skipped with a clear message rather than failing obscurely.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ML_DIR = Path(__file__).resolve().parent.parent / "ml"
sys.path.insert(0, str(ML_DIR))

import decision_engine as de  # noqa: E402


EXISTING_CUSTOMER_FEATURES = {
    "customer_type": "existing",
    "payment_method": "card",
    "merchant_category": "saas",
    "customer_tenure_days": 240.0,
    "payment_amount": 2500.0,
    "previous_payment_count": 8,
    "previous_success_count": 6,
    "previous_failure_count": 2,
    "previous_retry_count": 1,
    "days_since_last_payment": 30.0,
}

COLD_START_FEATURES = {
    "customer_type": "new",
    "payment_method": "upi",
    "merchant_category": "ecommerce",
    "customer_tenure_days": 5.0,
    "payment_amount": 1200.0,
    "previous_payment_count": 0,
    "previous_success_count": 0,
    "previous_failure_count": 0,
    "previous_retry_count": 0,
    "days_since_last_payment": 0.0,
}


def _require_models() -> None:
    missing = [p for p in [de.RISK_MODEL_PATH, *de.ACTION_MODEL_PATHS.values()] if not p.exists()]
    if missing:
        pytest.skip(
            f"Required model artifact(s) missing: {missing}. "
            f"Run `python ml/train_risk_model.py` and `python ml/train_action_models.py` first."
        )


# 1. Normal existing customer
def test_normal_existing_customer():
    _require_models()
    result = de.decide(EXISTING_CUSTOMER_FEATURES, transaction_id="T1", customer_id="C1")

    assert result.selected_action in de.ACTIONS
    assert set(result.action_success_probabilities) == set(de.ACTIONS)
    assert all(0.0 <= p <= 1.0 for p in result.action_success_probabilities.values())
    assert 0.0 <= result.predicted_failure_risk <= 1.0
    assert result.confidence["level"] in ("low", "medium", "standard")


# 2. New / cold-start customer
def test_cold_start_customer_does_not_crash_and_flags_low_confidence():
    _require_models()
    result = de.decide(COLD_START_FEATURES, transaction_id="T2", customer_id="CS1")

    assert result.selected_action in de.ACTIONS
    assert result.confidence["level"] == "low"
    assert "low confidence" in result.explanation.lower()
    assert "limited/no customer history" in result.explanation.lower()


# 3. Merchant disables an action
def test_merchant_disables_action():
    _require_models()
    constraints = de.MerchantConstraints(allowed_actions=frozenset({"do_nothing", "retry", "reminder"}))
    result = de.decide(EXISTING_CUSTOMER_FEATURES, constraints=constraints)

    assert result.selected_action != "recovery_link"
    assert "recovery_link" not in result.permitted_actions
    assert "recovery_link" in result.audit_record["constraints_applied"]["removed_by_constraint"]


# 4. Highest expected-revenue action is selected
def test_highest_expected_revenue_action_is_selected():
    _require_models()
    result = de.decide(EXISTING_CUSTOMER_FEATURES)

    permitted_values = {a: result.expected_revenue[a] for a in result.permitted_actions}
    assert result.selected_action == max(permitted_values, key=permitted_values.get)


# 5. Tie-breaking works deterministically
def test_tie_breaking_is_deterministic():
    permitted = ["do_nothing", "retry", "reminder", "recovery_link"]
    # do_nothing, retry, and recovery_link are (synthetically) tied for
    # highest; do_nothing should win because it is first in ACTION_PRIORITY.
    expected_revenue = {"do_nothing": 100.0, "retry": 100.0, "reminder": 50.0, "recovery_link": 100.0}

    result1 = de._select_best_action(permitted, expected_revenue)
    result2 = de._select_best_action(permitted, expected_revenue)

    assert result1 == result2 == "do_nothing"

    # A different tied subset should still resolve to the highest-priority
    # member of that subset, not always "do_nothing" specifically.
    expected_revenue_2 = {"do_nothing": 10.0, "retry": 100.0, "reminder": 100.0, "recovery_link": 50.0}
    assert de._select_best_action(permitted, expected_revenue_2) == "retry"


# 6. No forbidden action is ever selected
def test_no_forbidden_action_is_ever_selected():
    _require_models()
    constraints = de.MerchantConstraints(allowed_actions=frozenset({"do_nothing", "reminder"}))

    for features in (EXISTING_CUSTOMER_FEATURES, COLD_START_FEATURES):
        result = de.decide(features, constraints=constraints)
        assert result.selected_action in {"do_nothing", "reminder"}
        assert "retry" not in result.permitted_actions
        assert "recovery_link" not in result.permitted_actions


# 6b. Constraint-driven max_retry_count is respected
def test_max_retry_count_constraint_excludes_retry_when_limit_reached():
    _require_models()
    features = dict(EXISTING_CUSTOMER_FEATURES, previous_retry_count=3)
    constraints = de.MerchantConstraints(max_retry_count=3)

    result = de.decide(features, constraints=constraints)

    assert "retry" not in result.permitted_actions
    assert "retry" in result.audit_record["constraints_applied"]["removed_by_constraint"]
    assert result.selected_action != "retry"


# 6c. do_nothing remains available even if every other action is disabled
def test_do_nothing_is_the_guaranteed_fallback():
    _require_models()
    constraints = de.MerchantConstraints(allowed_actions=frozenset({"retry", "reminder", "recovery_link"}) - frozenset({"retry", "reminder", "recovery_link"}))
    # allowed_actions is now an empty frozenset — every action is disabled
    result = de.decide(EXISTING_CUSTOMER_FEATURES, constraints=constraints)

    assert result.selected_action == "do_nothing"
    assert result.permitted_actions == ["do_nothing"]


# 7. Explanation matches the selected action
def test_explanation_matches_selected_action():
    _require_models()
    result = de.decide(EXISTING_CUSTOMER_FEATURES)

    label = de.ACTION_LABELS[result.selected_action]
    assert label in result.explanation

    selected_revenue = result.expected_revenue[result.selected_action]
    assert f"{selected_revenue:,.2f}" in result.explanation


# 8. Audit record contains the required fields
def test_audit_record_contains_required_fields():
    _require_models()
    result = de.decide(EXISTING_CUSTOMER_FEATURES, transaction_id="T99", customer_id="C99")
    audit = result.audit_record

    required_keys = [
        "transaction_id", "customer_id", "predicted_failure_risk",
        "action_success_probabilities", "expected_revenue",
        "constraints_applied", "permitted_actions", "selected_action",
        "reason", "confidence", "causal_disclaimer",
    ]
    for key in required_keys:
        assert key in audit, f"Missing required audit field: {key}"

    assert audit["transaction_id"] == "T99"
    assert audit["customer_id"] == "C99"
    assert audit["selected_action"] == result.selected_action
    assert set(audit["expected_revenue"]) == set(de.ACTIONS)
    assert set(audit["action_success_probabilities"]) == set(de.ACTIONS)


# Missing-feature input fails clearly rather than crashing obscurely
def test_missing_feature_raises_clear_error():
    _require_models()
    incomplete_features = dict(EXISTING_CUSTOMER_FEATURES)
    del incomplete_features["payment_amount"]

    with pytest.raises(ValueError, match="Missing required feature"):
        de.decide(incomplete_features)
