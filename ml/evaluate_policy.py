"""
RevenueShield AI — Phase 5: Offline Policy Evaluation

Compares the RevenueShield decision policy against three baselines on the
held-out Phase 2 test set (ml/data/processed/test.csv — never used to train
any model):

  - Default / Merchant strategy — the action actually recorded in the data
    and its real recorded outcome. This is what "already happens" today.
  - Always Retry — always choose 'retry'.
  - Random — choose uniformly at random among the four actions.
  - RevenueShield — the Phase 3C decision engine's actual choice, reused
    via ml.decision_engine.decide(). NOT reimplemented here.

No model is trained in this file. ml/decision_engine.py is not modified —
only imported and called.

===========================================================================
METHODOLOGY — READ THIS BEFORE TRUSTING ANY NUMBER THIS SCRIPT PRINTS
===========================================================================

We can only ever observe the REAL outcome of the action that was actually
taken for a given historical transaction — never what would have happened
under a different action. That constrains what each policy's number means:

  - "Default / Merchant strategy" is a fully REAL total: the sum of amounts
    actually collected under the action that was actually used. No model
    is involved in computing it at all.

  - "Always Retry", "Random", and "RevenueShield" each report a
    MODEL-EXPECTED total: payment_amount x the relevant Phase 3B action
    model's predicted success probability for whichever action that policy
    would have chosen. This is the standard "direct method" off-policy
    evaluation estimator — NOT an observed outcome, and it inherits every
    limitation of the Phase 3B models it depends on (see README's Phase 3B
    section, especially the documented cold-start weakness).

  - For rows where a policy's chosen action happens to match the actually-
    recorded historical action, this script ALSO reports a REAL,
    non-model-based "realized" total for that overlap subset — a smaller
    sample, but grounded in real data instead of a model's prediction.

Comparing a real total (Default) against model-expected totals (the other
three) is therefore apples-to-oranges in a specific, named way — it answers
"what would we expect to collect under this policy," not "what would we
actually have collected." The incremental-revenue figure this script
reports inherits that same caveat and restates it, rather than presenting
a single clean-looking percentage with no context.

This script's action-outcome predictions use ONLY the pre-outcome feature
columns already established in Phase 3A/3B (ml.decision_engine.
FEATURE_COLUMNS). payment_success, amount_recovered, payment_status,
failure_reason, and action are read from each row ONLY to compute the
real/realized figures above — never passed to a model as an input feature.

===========================================================================
USAGE
===========================================================================

    python ml/evaluate_policy.py                  # fast dev sample (500 rows)
    python ml/evaluate_policy.py --sample-size 100 # smaller/faster
    python ml/evaluate_policy.py --full            # complete test.csv (~7,600 rows)

The full run calls the decision engine once per row, which is measurably
slow (~25ms/call in this project's benchmarking, i.e. roughly 3 minutes for
the complete test set) because it is calling the real, unmodified Phase 3C
engine rather than a fast reimplementation. --full is opt-in and documented
here and in the CLI --help text for exactly that reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ML_DIR = PROJECT_ROOT / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import decision_engine as de  # noqa: E402 — reused, not reimplemented

TEST_PATH = PROJECT_ROOT / "ml" / "data" / "processed" / "test.csv"
REPORT_DIR = PROJECT_ROOT / "ml" / "reports"
REPORT_PATH = REPORT_DIR / "policy_evaluation.json"

DEFAULT_SAMPLE_SIZE = 500
RANDOM_SEED = 42
ACTIONS = de.ACTIONS


def load_test_data(sample_size: Optional[int], seed: int) -> pd.DataFrame:
    if not TEST_PATH.exists():
        print(f"ERROR: {TEST_PATH} not found. Run `python ml/generate_data.py` first (Phase 2).")
        sys.exit(1)

    df = pd.read_csv(TEST_PATH)

    missing = [c for c in de.FEATURE_COLUMNS + ["action", "payment_success", "payment_amount"] if c not in df.columns]
    if missing:
        print(f"ERROR: {TEST_PATH} is missing required columns: {missing}")
        sys.exit(1)

    if sample_size is not None and sample_size < len(df):
        df = df.sample(n=sample_size, random_state=seed).reset_index(drop=True)

    return df


def _features_from_row(row: pd.Series) -> dict[str, Any]:
    """Only the pre-outcome features the models were trained on — never
    payment_success/payment_status/failure_reason/amount_recovered/action.
    """
    return {col: row[col] for col in de.FEATURE_COLUMNS}


def _predict_action_probability(action: str, features: dict[str, Any]) -> float:
    """Reuses the existing Phase 3B model loader from decision_engine.py —
    no reimplementation of prediction logic.
    """
    model = de._load_action_model(action)
    X = de._build_feature_row(features)
    return float(model.predict_proba(X)[:, 1][0])


def evaluate_row(row: pd.Series, rng: np.random.Generator) -> dict[str, Any]:
    """Computes each policy's chosen action and revenue figures for a
    single historical transaction. See module docstring for exactly what
    "direct" (model-expected) vs. "realized" (real) means below.
    """
    features = _features_from_row(row)
    amount = float(row["payment_amount"])
    actual_action = row["action"]
    actual_success = int(row["payment_success"])
    actual_revenue = amount * actual_success

    result: dict[str, Any] = {
        "amount": amount,
        "actual_action": actual_action,
        "actual_revenue": actual_revenue,
    }

    # --- Default / Merchant strategy: fully real, no model involved ---
    result["default_action"] = actual_action
    result["default_revenue"] = actual_revenue

    # --- RevenueShield: the real Phase 3C engine, called as-is ---
    decision = de.decide(features)
    rs_action = decision.selected_action
    rs_prob = decision.action_success_probabilities[rs_action]
    result["revenueshield_action"] = rs_action
    result["revenueshield_direct_revenue"] = amount * rs_prob
    result["revenueshield_realized_revenue"] = actual_revenue if rs_action == actual_action else None

    # --- Always Retry ---
    retry_prob = _predict_action_probability("retry", features)
    result["always_retry_direct_revenue"] = amount * retry_prob
    result["always_retry_realized_revenue"] = actual_revenue if actual_action == "retry" else None

    # --- Random ---
    random_action = str(rng.choice(ACTIONS))
    random_prob = _predict_action_probability(random_action, features)
    result["random_action"] = random_action
    result["random_direct_revenue"] = amount * random_prob
    result["random_realized_revenue"] = actual_revenue if random_action == actual_action else None

    return result


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        raise ValueError("Cannot aggregate an empty set of evaluated rows.")

    total_scheduled = sum(r["amount"] for r in rows)

    def _sum(key: str) -> float:
        return sum(r[key] for r in rows)

    def _realized_stats(key: str) -> dict[str, Any]:
        values = [r[key] for r in rows if r[key] is not None]
        return {
            "n_overlap_rows": len(values),
            "overlap_rate": len(values) / n,
            "realized_total": sum(values) if values else 0.0,
        }

    policies = {
        "default_merchant_strategy": {
            "is_fully_real": True,
            "total_revenue": _sum("default_revenue"),
        },
        "always_retry": {
            "is_fully_real": False,
            "total_direct_expected_revenue": _sum("always_retry_direct_revenue"),
            "realized_overlap": _realized_stats("always_retry_realized_revenue"),
        },
        "random": {
            "is_fully_real": False,
            "total_direct_expected_revenue": _sum("random_direct_revenue"),
            "realized_overlap": _realized_stats("random_realized_revenue"),
        },
        "revenueshield": {
            "is_fully_real": False,
            "total_direct_expected_revenue": _sum("revenueshield_direct_revenue"),
            "realized_overlap": _realized_stats("revenueshield_realized_revenue"),
        },
    }

    default_total = policies["default_merchant_strategy"]["total_revenue"]
    rs_total = policies["revenueshield"]["total_direct_expected_revenue"]
    incremental_absolute = rs_total - default_total
    incremental_percent = (incremental_absolute / default_total * 100) if default_total else None

    return {
        "n_transactions": n,
        "total_scheduled_revenue": total_scheduled,
        "policies": policies,
        "incremental_revenue_vs_default": {
            "absolute": incremental_absolute,
            "percent": incremental_percent,
            "methodology_note": (
                "Compares a MODEL-EXPECTED total (RevenueShield, direct-method "
                "estimate) against a REAL total (Default/Merchant strategy, "
                "actually collected). See this script's module docstring."
            ),
        },
    }


def print_report(summary: dict[str, Any]) -> None:
    print("\n--- RevenueShield AI — Phase 5: Offline Policy Evaluation ---")
    print(f"Transactions evaluated: {summary['n_transactions']:,}")
    print(f"Total scheduled revenue (sum of payment_amount): Rs {summary['total_scheduled_revenue']:,.2f}")

    policy_display_names = {
        "default_merchant_strategy": "Default / Merchant strategy",
        "always_retry": "Always Retry",
        "random": "Random",
        "revenueshield": "RevenueShield",
    }

    for key, name in policy_display_names.items():
        stats = summary["policies"][key]
        print(f"\n=== {name} ===")
        if stats["is_fully_real"]:
            print(f"  Total revenue (REAL, actually collected):        Rs {stats['total_revenue']:,.2f}")
        else:
            print(f"  Total direct-method EXPECTED revenue (model-based): Rs {stats['total_direct_expected_revenue']:,.2f}")
            overlap = stats["realized_overlap"]
            if overlap["n_overlap_rows"] > 0:
                print(
                    f"  Realized-outcome check: {overlap['n_overlap_rows']:,} rows "
                    f"({overlap['overlap_rate']:.1%} of transactions) where this "
                    f"policy's chosen action matched the historically-recorded "
                    f"action — REAL revenue for just those rows: "
                    f"Rs {overlap['realized_total']:,.2f}"
                )
            else:
                print("  Realized-outcome check: no overlap rows in this sample.")

    inc = summary["incremental_revenue_vs_default"]
    print("\n=== Incremental Revenue: RevenueShield vs. Default / Merchant strategy ===")
    print(f"Absolute: Rs {inc['absolute']:,.2f}")
    if inc["percent"] is not None:
        print(f"Percent:  {inc['percent']:+.2f}%")
    print(f"NOTE: {inc['methodology_note']}")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Offline policy evaluation for RevenueShield AI. Defaults to a fast "
            f"{DEFAULT_SAMPLE_SIZE}-row sample for development; use --full for "
            "the complete held-out test set (~7,600 rows, ~3 minutes — see "
            "module docstring for why it's this slow)."
        )
    )
    parser.add_argument(
        "--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE,
        help=f"Evaluate a random sample of this many test rows (default: {DEFAULT_SAMPLE_SIZE}). Ignored if --full is passed.",
    )
    parser.add_argument("--full", action="store_true", help="Evaluate the complete test.csv instead of a sample. Slow — see module docstring.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help=f"Random seed (default: {RANDOM_SEED}).")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    sample_size = None if args.full else args.sample_size
    df = load_test_data(sample_size=sample_size, seed=args.seed)

    mode = "FULL test set" if args.full else f"sample of {len(df):,} rows"
    print(f"Evaluating {mode} (seed={args.seed})...")
    if args.full:
        print("(--full was passed: this calls the real decision engine once per row and will take a few minutes.)")

    rows = [evaluate_row(row, rng) for _, row in df.iterrows()]
    summary = aggregate(rows)
    print_report(summary)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved summary to: {REPORT_PATH}")
    print("SUCCESS: offline policy evaluation complete. No model was retrained; no live API calls were made.")


if __name__ == "__main__":
    main()
