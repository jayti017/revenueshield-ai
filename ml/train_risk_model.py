"""
RevenueShield AI — Phase 3: Payment Failure Risk Model (training)

Trains a Logistic Regression baseline that estimates:

    P(payment failure | information available before the outcome)

This is supporting infrastructure only — it does NOT decide anything, does
NOT calculate expected revenue, and does NOT choose a recovery action. See
README.md's Phase 3 section for the full write-up.

USAGE (from the project root, virtual environment active):

    python ml/train_risk_model.py

OUTPUT:

    ml/models/risk_model.joblib
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
TRAIN_PATH = PROCESSED_DIR / "train.csv"
VAL_PATH = PROCESSED_DIR / "validation.csv"
MODEL_DIR = PROJECT_ROOT / "ml" / "models"
MODEL_PATH = MODEL_DIR / "risk_model.joblib"

RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Feature definition — ONLY information available before the outcome.
# ---------------------------------------------------------------------------
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

# Columns that must NEVER appear in the feature matrix, because they are
# outcome information, decision information made after the risk assessment
# would happen, or identifiers. `action` is deliberately excluded from
# features (not just from this forbidden list) — see README Phase 3 section
# for why: it's chosen using the risk level itself, so including it would
# leak the historical assignment policy into what is supposed to be a
# pre-decision risk estimate.
FORBIDDEN_COLUMNS = [
    "payment_success", "failure_target", "amount_recovered",
    "payment_status", "failure_reason", "action",
    "transaction_id", "customer_id",
]


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"ERROR: required file not found: {path}")
        print("Run `python ml/generate_data.py` first (Phase 2).")
        sys.exit(1)
    return pd.read_csv(path)


def validate_columns(df: pd.DataFrame, path: Path) -> None:
    missing = [c for c in FEATURE_COLUMNS + ["payment_success"] if c not in df.columns]
    if missing:
        print(f"ERROR: {path} is missing required columns: {missing}")
        sys.exit(1)


def build_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Builds the feature matrix and failure target, with an explicit,
    fail-loud leakage check.
    """
    X = df[FEATURE_COLUMNS].copy()

    leaked = [c for c in FORBIDDEN_COLUMNS if c in X.columns]
    if leaked:
        print(f"DATA LEAKAGE DETECTED: forbidden columns present in feature matrix: {leaked}")
        sys.exit(1)

    y = 1 - df["payment_success"]
    y.name = "failure_target"

    if not set(y.unique()) <= {0, 1}:
        print(f"ERROR: failure_target contains invalid values: {sorted(y.unique())}")
        sys.exit(1)

    return X, y


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ]
    )
    # Logistic Regression chosen deliberately over XGBoost/LightGBM/neural
    # nets: it's interpretable, fast, produces well-behaved probabilities
    # out of the box, and is an appropriate MVP baseline per the Phase 3
    # spec. class_weight is intentionally left at its default (unbalanced)
    # rather than "balanced" — RevenueShield will eventually use these
    # probabilities directly in an expected-value calculation, and
    # class-weighting would distort the probabilities away from being
    # calibrated to the true failure rate, which matters more here than
    # balanced classification accuracy.
    model = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
    return Pipeline(steps=[("preprocessor", preprocessor), ("model", model)])


def print_metrics(name: str, y_true: pd.Series, y_pred_proba: np.ndarray, threshold: float = 0.5) -> None:
    y_pred = (y_pred_proba >= threshold).astype(int)

    print(f"\n--- {name} ---")
    print(f"Rows: {len(y_true):,}")

    if len(set(y_true)) < 2:
        print("ROC-AUC: N/A (only one class present in this set)")
    else:
        auc = roc_auc_score(y_true, y_pred_proba)
        print(f"ROC-AUC:   {auc:.4f}")

    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    brier = brier_score_loss(y_true, y_pred_proba)

    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1:        {f1:.4f}")
    print(f"Brier:     {brier:.4f}")

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    print(f"Confusion matrix (rows=actual, cols=predicted, [0=success,1=failure]):")
    print(f"  {cm}")


def main() -> None:
    print("--- RevenueShield AI — Phase 3: Payment Failure Risk Model (training) ---\n")
    print(f"Random seed: {RANDOM_SEED}")

    train_df = load_csv(TRAIN_PATH)
    val_df = load_csv(VAL_PATH)
    validate_columns(train_df, TRAIN_PATH)
    validate_columns(val_df, VAL_PATH)

    print(f"Loaded train.csv:      {len(train_df):,} rows")
    print(f"Loaded validation.csv: {len(val_df):,} rows")

    X_train, y_train = build_xy(train_df)
    X_val, y_val = build_xy(val_df)

    print(f"\nFeature columns used ({len(FEATURE_COLUMNS)}): {FEATURE_COLUMNS}")
    print("Leakage check passed: none of", FORBIDDEN_COLUMNS, "are present in the feature matrix.")

    print(f"\nTraining-set failure rate: {y_train.mean():.4f}")
    print(f"Validation-set failure rate: {y_val.mean():.4f}")

    pipeline = build_pipeline()

    print("\nTraining Logistic Regression pipeline...")
    pipeline.fit(X_train, y_train)
    print("Training complete.")

    val_proba = pipeline.predict_proba(X_val)[:, 1]
    print_metrics("Validation set performance", y_val, val_proba)

    print("\nSample predictions (validation set, first 10 rows):")
    print("actual_failure | predicted_failure_probability")
    sample_actual = y_val.values[:10]
    sample_pred = val_proba[:10]
    for actual, pred in zip(sample_actual, sample_pred):
        print(f"{actual:>14d} | {pred:.4f}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        joblib.dump(pipeline, MODEL_PATH)
    except Exception as exc:  # fail loudly with a clear message, not a bare stack trace
        print(f"ERROR: could not save model artifact to {MODEL_PATH}: {exc}")
        sys.exit(1)

    print(f"\nSaved trained pipeline to: {MODEL_PATH}")
    print("SUCCESS: risk model training complete.")


if __name__ == "__main__":
    main()
