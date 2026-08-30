"""
RevenueShield AI — Phase 3B: Action-Outcome Models (training)

Trains ONE supervised model per recovery action, each estimating:

    P(payment succeeds | customer/payment features, this action was taken)

for the four actions: do_nothing, retry, reminder, recovery_link.

IMPORTANT — these are NOT causal treatment-effect estimates. Each model is
trained only on the historical rows where that specific action was actually
taken. Which action a given transaction received was itself influenced by
that transaction's risk level (see ml/generate_data.py and README.md's
Phase 2 section on assignment confounding), so these models describe
"payments that received this action tended to succeed at this rate given
these features" — a predictive, observational estimate — not "this action
caused this success rate." A future decision engine will need to treat that
distinction carefully; this phase deliberately does not attempt to correct
for it (no uplift modeling, no causal inference — out of scope, see spec).

This file does NOT build a decision engine, does NOT calculate expected
revenue, and does NOT select between actions.

USAGE (from the project root, virtual environment active):

    python ml/train_action_models.py

OUTPUT:

    ml/models/action_model_do_nothing.joblib
    ml/models/action_model_retry.joblib
    ml/models/action_model_reminder.joblib
    ml/models/action_model_recovery_link.joblib
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
TRAIN_PATH = PROCESSED_DIR / "train.csv"
MODEL_DIR = PROJECT_ROOT / "ml" / "models"

RANDOM_SEED = 42
MIN_EXAMPLES_PER_ACTION = 50

ACTIONS = ["do_nothing", "retry", "reminder", "recovery_link"]

# Same feature philosophy as the Phase 3A risk model.
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

# `action` is included here even though every row in a given model's
# training slice shares the same action value — it is still a forbidden
# *feature* (the whole point of Phase 3B is one model per action, not one
# model with action as an input), alongside the usual outcome/identifier
# leakage columns.
FORBIDDEN_COLUMNS = [
    "payment_success", "payment_status", "failure_reason", "amount_recovered",
    "action", "transaction_id", "customer_id",
]


def model_path_for(action: str) -> Path:
    return MODEL_DIR / f"action_model_{action}.joblib"


def load_train_data() -> pd.DataFrame:
    if not TRAIN_PATH.exists():
        print(f"ERROR: required file not found: {TRAIN_PATH}")
        print("Run `python ml/generate_data.py` first (Phase 2).")
        sys.exit(1)
    df = pd.read_csv(TRAIN_PATH)

    missing = [c for c in FEATURE_COLUMNS + ["action", "payment_success"] if c not in df.columns]
    if missing:
        print(f"ERROR: {TRAIN_PATH} is missing required columns: {missing}")
        sys.exit(1)
    return df


def build_xy(df: pd.DataFrame, action: str) -> tuple[pd.DataFrame, pd.Series]:
    subset = df[df["action"] == action]

    if len(subset) < MIN_EXAMPLES_PER_ACTION:
        print(
            f"ERROR: action '{action}' has only {len(subset)} training examples "
            f"(minimum required: {MIN_EXAMPLES_PER_ACTION}). Cannot train a reliable model. "
            f"Regenerate the dataset with more samples or check the action-assignment logic."
        )
        sys.exit(1)

    y = subset["payment_success"]
    if y.nunique() < 2:
        print(
            f"ERROR: action '{action}' has only one outcome class present "
            f"({sorted(y.unique())}) in the training data. A classifier cannot be "
            f"trained without examples of both success and failure for this action."
        )
        sys.exit(1)

    X = subset[FEATURE_COLUMNS].copy()
    leaked = [c for c in FORBIDDEN_COLUMNS if c in X.columns]
    if leaked:
        print(f"DATA LEAKAGE DETECTED for action '{action}': forbidden columns present in X: {leaked}")
        sys.exit(1)

    return X, y


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ]
    )
    # Logistic Regression, matching the risk model's rationale: interpretable,
    # fast, produces usable probabilities out of the box, appropriate for an
    # MVP. handle_unknown="ignore" on the encoder (and StandardScaler, which
    # has no notion of "unknown") mean this pipeline can score cold-start
    # rows (all previous_* counts == 0, customer_type == "new") without
    # raising — those are in-range numeric values and an already-known
    # category, not unseen categories.
    model = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def train_one_action(df: pd.DataFrame, action: str) -> None:
    print(f"\n=== Action: {action} ===")

    X, y = build_xy(df, action)

    n_total = len(y)
    n_success = int(y.sum())
    n_failure = n_total - n_success
    success_rate = y.mean()

    print(f"Training rows:        {n_total:,}")
    print(f"Successful outcomes:  {n_success:,}")
    print(f"Failed outcomes:      {n_failure:,}")
    print(f"Success rate:         {success_rate:.4f}")
    print(f"Feature columns used ({len(FEATURE_COLUMNS)}): {FEATURE_COLUMNS}")
    print(f"Leakage check passed: none of {FORBIDDEN_COLUMNS} are present in X.")

    pipeline = build_pipeline()
    pipeline.fit(X, y)

    out_path = model_path_for(action)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        joblib.dump(pipeline, out_path)
    except Exception as exc:
        print(f"ERROR: could not save model artifact to {out_path}: {exc}")
        sys.exit(1)

    print(f"Model training status: SUCCESS")
    print(f"Saved model path:      {out_path}")


def main() -> None:
    print("--- RevenueShield AI — Phase 3B: Action-Outcome Models (training) ---")
    print(f"Random seed: {RANDOM_SEED}")
    print(
        "\nNOTE: these are action-specific predictive models trained on "
        "observational/synthetic action-assignment data. They estimate "
        "P(success | features, this action was taken), NOT the causal effect "
        "of the action. See README.md's Phase 3B section for details."
    )

    df = load_train_data()
    print(f"\nLoaded train.csv: {len(df):,} rows")

    for action in ACTIONS:
        train_one_action(df, action)

    print("\nSUCCESS: all four action-outcome models trained and saved.")
    print("No decision engine, expected-revenue calculation, or action selection was implemented.")


if __name__ == "__main__":
    main()
