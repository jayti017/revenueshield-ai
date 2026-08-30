"""
RevenueShield AI — Phase 3B: Action-Outcome Models (evaluation)

Evaluates each of the four saved action-outcome models on the rows of
validation.csv, test.csv, and cold_start.csv where that specific action was
actually taken, and compares each against a constant-probability baseline.

Same causal caveat as train_action_models.py: these are predictive models
on observational/synthetic action-assignment data, not causal
treatment-effect estimates. See README.md's Phase 3B section.

This file does NOT build a decision engine and does NOT select between
actions.

USAGE (from the project root, virtual environment active):

    python ml/evaluate_action_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
TRAIN_PATH = PROCESSED_DIR / "train.csv"
VAL_PATH = PROCESSED_DIR / "validation.csv"
TEST_PATH = PROCESSED_DIR / "test.csv"
COLD_START_PATH = PROCESSED_DIR / "cold_start.csv"
MODEL_DIR = PROJECT_ROOT / "ml" / "models"

ACTIONS = ["do_nothing", "retry", "reminder", "recovery_link"]

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
FORBIDDEN_COLUMNS = [
    "payment_success", "payment_status", "failure_reason", "amount_recovered",
    "action", "transaction_id", "customer_id",
]

CLASSIFICATION_THRESHOLD = 0.5
MIN_ROWS_FOR_EVAL = 20  # below this, skip rather than report a noisy/meaningless metric


def model_path_for(action: str) -> Path:
    return MODEL_DIR / f"action_model_{action}.joblib"


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"ERROR: required file not found: {path}")
        print("Run `python ml/generate_data.py` first (Phase 2).")
        sys.exit(1)
    return pd.read_csv(path)


def build_xy_for_action(df: pd.DataFrame, action: str) -> tuple[pd.DataFrame, pd.Series]:
    subset = df[df["action"] == action]
    X = subset[FEATURE_COLUMNS].copy()
    leaked = [c for c in FORBIDDEN_COLUMNS if c in X.columns]
    if leaked:
        print(f"DATA LEAKAGE DETECTED for action '{action}': forbidden columns present in X: {leaked}")
        sys.exit(1)
    y = subset["payment_success"]
    return X, y


def compute_metrics(y_true: pd.Series, y_pred_proba: np.ndarray, threshold: float = CLASSIFICATION_THRESHOLD) -> dict:
    y_pred = (y_pred_proba >= threshold).astype(int)
    metrics: dict = {"n_rows": len(y_true), "n_classes_present": len(set(y_true))}

    if metrics["n_classes_present"] < 2:
        metrics["roc_auc"] = None
        metrics["roc_auc_note"] = "N/A — only one outcome class present in this subset."
    else:
        metrics["roc_auc"] = roc_auc_score(y_true, y_pred_proba)

    metrics["precision"] = precision_score(y_true, y_pred, zero_division=0)
    metrics["recall"] = recall_score(y_true, y_pred, zero_division=0)
    metrics["f1"] = f1_score(y_true, y_pred, zero_division=0)
    metrics["brier"] = brier_score_loss(y_true, y_pred_proba)
    metrics["confusion_matrix"] = confusion_matrix(y_true, y_pred, labels=[0, 1])
    return metrics


def print_metrics(name: str, metrics: dict) -> None:
    print(f"\n  --- {name} ---")
    print(f"  Rows: {metrics['n_rows']:,}")
    if metrics["roc_auc"] is None:
        print(f"  ROC-AUC:   {metrics['roc_auc_note']}")
    else:
        print(f"  ROC-AUC:   {metrics['roc_auc']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}  (at threshold {CLASSIFICATION_THRESHOLD})")
    print(f"  Recall:    {metrics['recall']:.4f}  (at threshold {CLASSIFICATION_THRESHOLD})")
    print(f"  F1:        {metrics['f1']:.4f}  (at threshold {CLASSIFICATION_THRESHOLD})")
    print(f"  Brier:     {metrics['brier']:.4f}")
    print(f"  Confusion matrix (rows=actual, cols=predicted, [0=fail,1=success]):")
    print(f"    {metrics['confusion_matrix']}")


def evaluate_one_action(action: str, train_df: pd.DataFrame, val_df: pd.DataFrame,
                         test_df: pd.DataFrame, cold_start_df: pd.DataFrame) -> None:
    print(f"\n=== Action: {action} ===")

    model_path = model_path_for(action)
    if not model_path.exists():
        print(f"ERROR: model artifact not found at {model_path}")
        print("Run `python ml/train_action_models.py` first.")
        sys.exit(1)
    pipeline = joblib.load(model_path)

    # Baseline: constant predicted success probability = this action's
    # observed success rate in the training data.
    X_train, y_train = build_xy_for_action(train_df, action)
    baseline_probability = y_train.mean()
    print(f"Baseline (constant, training-set success rate for this action): {baseline_probability:.4f}")

    for name, df in [("Validation", val_df), ("Test", test_df)]:
        X, y = build_xy_for_action(df, action)
        if len(y) < MIN_ROWS_FOR_EVAL:
            print(f"\n  --- {name} ---")
            print(f"  SKIPPED: only {len(y)} rows for this action (minimum {MIN_ROWS_FOR_EVAL}).")
            continue

        proba = pipeline.predict_proba(X)[:, 1]
        metrics = compute_metrics(y, proba)
        print_metrics(name, metrics)

        baseline_proba = np.full(shape=len(y), fill_value=baseline_probability)
        baseline_metrics = compute_metrics(y, baseline_proba)
        print(f"  vs. baseline — Brier: model={metrics['brier']:.4f}  baseline={baseline_metrics['brier']:.4f}", end="")
        if metrics["roc_auc"] is not None and baseline_metrics["roc_auc"] is not None:
            print(f"  |  ROC-AUC: model={metrics['roc_auc']:.4f}  baseline={baseline_metrics['roc_auc']:.4f}")
        else:
            print()

    # Cold-start — evaluate only where meaningful (enough rows of this action)
    X_cold, y_cold = build_xy_for_action(cold_start_df, action)
    if len(y_cold) < MIN_ROWS_FOR_EVAL:
        print(f"\n  --- Cold-start ---")
        print(f"  SKIPPED: only {len(y_cold)} cold-start rows for this action (minimum {MIN_ROWS_FOR_EVAL}).")
    else:
        cold_proba = pipeline.predict_proba(X_cold)[:, 1]
        cold_metrics = compute_metrics(y_cold, cold_proba)
        print_metrics("Cold-start", cold_metrics)


def main() -> None:
    print("--- RevenueShield AI — Phase 3B: Action-Outcome Models (evaluation) ---")
    print(
        "\nNOTE: these are action-specific predictive models trained on "
        "observational/synthetic action-assignment data. Their output is "
        "P(success | features, this action was taken) for payments that "
        "historically received that action — NOT a causal treatment effect. "
        "See README.md's Phase 3B section for details."
    )

    train_df = load_csv(TRAIN_PATH)
    val_df = load_csv(VAL_PATH)
    test_df = load_csv(TEST_PATH)
    cold_start_df = load_csv(COLD_START_PATH)

    for action in ACTIONS:
        evaluate_one_action(action, train_df, val_df, test_df, cold_start_df)

    print("\nSUCCESS: evaluation complete for all four action-outcome models.")
    print("No decision engine, expected-revenue calculation, or action selection was implemented.")


if __name__ == "__main__":
    main()
