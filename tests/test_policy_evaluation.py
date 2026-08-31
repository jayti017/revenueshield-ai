"""
RevenueShield AI — Phase 5: offline policy evaluation tests.

Uses the EXISTING trained Phase 3A/3B model artifacts (skipped if missing)
but only on tiny, fixed synthetic inputs — never the full ~7,600-row
test.csv — to keep this suite fast.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ML_DIR = Path(__file__).resolve().parent.parent / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import decision_engine as de  # noqa: E402
import evaluate_policy as ep  # noqa: E402


def _require_models() -> None:
    missing = [p for p in [de.RISK_MODEL_PATH, *de.ACTION_MODEL_PATHS.values()] if not p.exists()]
    if missing:
        pytest.skip(f"Required model artifact(s) missing: {missing}.")


def _make_row(**overrides) -> pd.Series:
    base = {
        "customer_type": "existing",
        "payment_method": "card",
        "merchant_category": "saas",
        "customer_tenure_days": 200.0,
        "payment_amount": 2000.0,
        "previous_payment_count": 5,
        "previous_success_count": 4,
        "previous_failure_count": 1,
        "previous_retry_count": 0,
        "days_since_last_payment": 30.0,
        "action": "retry",
        "payment_success": 1,
    }
    base.update(overrides)
    return pd.Series(base)


# 9 — evaluate_row() on a small fixed synthetic example
def test_evaluate_row_produces_all_expected_keys():
    _require_models()
    row = _make_row()
    rng = np.random.default_rng(42)

    result = ep.evaluate_row(row, rng)

    expected_keys = {
        "amount", "actual_action", "actual_revenue",
        "default_action", "default_revenue",
        "revenueshield_action", "revenueshield_direct_revenue", "revenueshield_realized_revenue",
        "always_retry_direct_revenue", "always_retry_realized_revenue",
        "random_action", "random_direct_revenue", "random_realized_revenue",
    }
    assert expected_keys.issubset(result.keys())
    assert result["revenueshield_action"] in de.ACTIONS
    assert result["random_action"] in de.ACTIONS
    assert result["revenueshield_direct_revenue"] >= 0
    assert result["always_retry_direct_revenue"] >= 0


# 11 — Default/Merchant baseline is real, non-model-derived logic
def test_default_baseline_is_never_model_derived():
    _require_models()
    row_success = _make_row(action="reminder", payment_success=1, payment_amount=1500.0)
    row_failure = _make_row(action="reminder", payment_success=0, payment_amount=1500.0)
    rng = np.random.default_rng(1)

    result_success = ep.evaluate_row(row_success, rng)
    result_failure = ep.evaluate_row(row_failure, rng)

    # Exactly amount if success, exactly 0 if failure — this must hold
    # regardless of what any model would have predicted for this row,
    # because no model is involved in computing it at all.
    assert result_success["default_revenue"] == 1500.0
    assert result_success["default_action"] == "reminder"
    assert result_failure["default_revenue"] == 0.0
    assert result_failure["default_action"] == "reminder"


# 12 — deterministic given a fixed seed
def test_results_are_deterministic_given_a_fixed_seed():
    _require_models()
    row = _make_row()

    result1 = ep.evaluate_row(row, np.random.default_rng(123))
    result2 = ep.evaluate_row(row, np.random.default_rng(123))

    assert result1["random_action"] == result2["random_action"]
    assert result1["revenueshield_action"] == result2["revenueshield_action"]  # decide() is itself deterministic
    assert result1["revenueshield_direct_revenue"] == pytest.approx(result2["revenueshield_direct_revenue"])


# 10 — aggregate() on a small fixed dataset
def test_aggregate_computes_correct_totals_on_fixed_rows():
    rows = [
        {
            "amount": 100.0, "actual_action": "retry", "actual_revenue": 100.0,
            "default_action": "retry", "default_revenue": 100.0,
            "revenueshield_action": "reminder", "revenueshield_direct_revenue": 80.0,
            "revenueshield_realized_revenue": None,
            "always_retry_direct_revenue": 70.0, "always_retry_realized_revenue": 100.0,
            "random_action": "do_nothing", "random_direct_revenue": 40.0,
            "random_realized_revenue": None,
        },
        {
            "amount": 200.0, "actual_action": "reminder", "actual_revenue": 0.0,
            "default_action": "reminder", "default_revenue": 0.0,
            "revenueshield_action": "reminder", "revenueshield_direct_revenue": 150.0,
            "revenueshield_realized_revenue": 0.0,
            "always_retry_direct_revenue": 90.0, "always_retry_realized_revenue": None,
            "random_action": "reminder", "random_direct_revenue": 150.0,
            "random_realized_revenue": 0.0,
        },
    ]

    summary = ep.aggregate(rows)

    assert summary["n_transactions"] == 2
    assert summary["total_scheduled_revenue"] == 300.0

    default = summary["policies"]["default_merchant_strategy"]
    assert default["is_fully_real"] is True
    assert default["total_revenue"] == 100.0  # 100 + 0

    rs = summary["policies"]["revenueshield"]
    assert rs["is_fully_real"] is False
    assert rs["total_direct_expected_revenue"] == 230.0  # 80 + 150
    assert rs["realized_overlap"]["n_overlap_rows"] == 1
    assert rs["realized_overlap"]["realized_total"] == 0.0

    always_retry = summary["policies"]["always_retry"]
    assert always_retry["total_direct_expected_revenue"] == 160.0  # 70 + 90
    assert always_retry["realized_overlap"]["n_overlap_rows"] == 1
    assert always_retry["realized_overlap"]["realized_total"] == 100.0

    inc = summary["incremental_revenue_vs_default"]
    assert inc["absolute"] == pytest.approx(230.0 - 100.0)
    assert inc["percent"] == pytest.approx((130.0 / 100.0) * 100)


def test_aggregate_rejects_empty_input():
    with pytest.raises(ValueError):
        ep.aggregate([])
