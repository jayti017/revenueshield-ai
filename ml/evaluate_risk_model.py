"""
RevenueShield AI — Phase 3: Payment Failure Risk Model (evaluation)

Loads the saved risk model and evaluates it on validation.csv, test.csv, and
cold_start.csv, compares it against a trivial constant-probability baseline
on the test set, and runs a simple calibration analysis. No decision-making,
expected-revenue calculation, or action model exists in this file.

USAGE (from the project root, virtual environment active):

    python ml/evaluate_risk_model.py
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
MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "risk_model.joblib"

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
    "payment_success", "failure_target", "amount_recovered",
    "payment_status", "failure_reason", "action",
    "transaction_id", "customer_id",
]

CLASSIFICATION_THRESHOLD = 0.5
N_CALIBRATION_BINS = 10


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"ERROR: required file not found: {path}")
        print("Run `python ml/generate_data.py` first (Phase 2), then `python ml/train_risk_model.py` (Phase 3).")
        sys.exit(1)
    return pd.read_csv(path)


def build_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    X = df[FEATURE_COLUMNS].copy()
    leaked = [c for c in FORBIDDEN_COLUMNS if c in X.columns]
    if leaked:
        print(f"DATA LEAKAGE DETECTED: forbidden columns present in feature matrix: {leaked}")
        sys.exit(1)
    y = 1 - df["payment_success"]
    y.name = "failure_target"
    return X, y


def compute_metrics(y_true: pd.Series, y_pred_proba: np.ndarray, threshold: float = CLASSIFICATION_THRESHOLD) -> dict:
    y_pred = (y_pred_proba >= threshold).astype(int)

    metrics: dict = {
        "n_rows": len(y_true),
        "n_classes_present": len(set(y_true)),
    }

    if metrics["n_classes_present"] < 2:
        metrics["roc_auc"] = None
        metrics["roc_auc_note"] = "N/A — only one class present in this dataset/subset."
    else:
        metrics["roc_auc"] = roc_auc_score(y_true, y_pred_proba)

    metrics["precision"] = precision_score(y_true, y_pred, zero_division=0)
    metrics["recall"] = recall_score(y_true, y_pred, zero_division=0)
    metrics["f1"] = f1_score(y_true, y_pred, zero_division=0)
    metrics["brier"] = brier_score_loss(y_true, y_pred_proba)
    metrics["confusion_matrix"] = confusion_matrix(y_true, y_pred, labels=[0, 1])
    return metrics


def print_metrics(name: str, metrics: dict) -> None:
    print(f"\n--- {name} ---")
    print(f"Rows: {metrics['n_rows']:,}")
    if metrics["roc_auc"] is None:
        print(f"ROC-AUC:   {metrics['roc_auc_note']}")
    else:
        print(f"ROC-AUC:   {metrics['roc_auc']:.4f}")
    print(f"Precision: {metrics['precision']:.4f}  (at threshold {CLASSIFICATION_THRESHOLD})")
    print(f"Recall:    {metrics['recall']:.4f}  (at threshold {CLASSIFICATION_THRESHOLD})")
    print(f"F1:        {metrics['f1']:.4f}  (at threshold {CLASSIFICATION_THRESHOLD})")
    print(f"Brier:     {metrics['brier']:.4f}")
    print("Confusion matrix (rows=actual, cols=predicted, [0=success,1=failure]):")
    print(f"  {metrics['confusion_matrix']}")


def calibration_report(y_true: pd.Series, y_pred_proba: np.ndarray, n_bins: int = N_CALIBRATION_BINS) -> None:
    """Simple, understandable calibration check: bin predictions into equal-
    width probability bins and compare mean predicted probability against
    observed failure rate in each bin. Reported honestly — this script does
    not adjust the model to make calibration look better.
    """
    df = pd.DataFrame({"y_true": y_true.values, "y_pred": y_pred_proba})
    bin_edges = np.linspace(0, 1, n_bins + 1)
    df["bin"] = pd.cut(df["y_pred"], bins=bin_edges, include_lowest=True)

    print(f"\n--- Calibration report ({n_bins} equal-width bins, predicted vs. observed failure rate) ---")
    print(f"{'bin range':<16}{'n':>8}{'mean predicted':>18}{'observed rate':>18}")
    grouped = df.groupby("bin", observed=True)
    for bin_range, group in grouped:
        if len(group) == 0:
            continue
        mean_pred = group["y_pred"].mean()
        observed = group["y_true"].mean()
        print(f"{str(bin_range):<16}{len(group):>8}{mean_pred:>18.4f}{observed:>18.4f}")


def main() -> None:
    print("--- RevenueShield AI — Phase 3: Payment Failure Risk Model (evaluation) ---\n")

    if not MODEL_PATH.exists():
        print(f"ERROR: model artifact not found at {MODEL_PATH}")
        print("Run `python ml/train_risk_model.py` first.")
        sys.exit(1)

    pipeline = joblib.load(MODEL_PATH)
    print(f"Loaded model: {MODEL_PATH}")

    train_df = load_csv(TRAIN_PATH)
    val_df = load_csv(VAL_PATH)
    test_df = load_csv(TEST_PATH)
    cold_start_df = load_csv(COLD_START_PATH)

    _, y_train = build_xy(train_df)
    baseline_probability = y_train.mean()
    print(f"\nBaseline: constant predicted failure probability = training-set failure rate = {baseline_probability:.4f}")

    # --- Validation ---
    X_val, y_val = build_xy(val_df)
    val_proba = pipeline.predict_proba(X_val)[:, 1]
    val_metrics = compute_metrics(y_val, val_proba)
    print_metrics("Validation set (validation.csv)", val_metrics)

    # --- Test ---
    X_test, y_test = build_xy(test_df)
    test_proba = pipeline.predict_proba(X_test)[:, 1]
    test_metrics = compute_metrics(y_test, test_proba)
    print_metrics("Test set (test.csv) — final evaluation", test_metrics)

    # --- Baseline comparison on test set ---
    baseline_proba_test = np.full(shape=len(y_test), fill_value=baseline_probability)
    baseline_metrics = compute_metrics(y_test, baseline_proba_test)
    print_metrics("Baseline (constant training-set failure rate) — test set", baseline_metrics)

    print("\n--- Model vs. baseline (test set) ---")
    model_auc = test_metrics["roc_auc"]
    baseline_auc = baseline_metrics["roc_auc"]
    if model_auc is not None and baseline_auc is not None:
        print(f"Model ROC-AUC:    {model_auc:.4f}")
        print(f"Baseline ROC-AUC: {baseline_auc:.4f}  (a constant prediction is non-informative — AUC 0.5 by definition)")
    print(f"Model Brier:      {test_metrics['brier']:.4f}")
    print(f"Baseline Brier:   {baseline_metrics['brier']:.4f}")
    if test_metrics["brier"] < baseline_metrics["brier"]:
        print("The trained model has a lower (better) Brier score than the constant baseline on the test set.")
    else:
        print("WARNING: the trained model did NOT beat the constant baseline on Brier score for this run.")

    # --- Cold-start ---
    X_cold, y_cold = build_xy(cold_start_df)
    cold_proba = pipeline.predict_proba(X_cold)[:, 1]
    cold_metrics = compute_metrics(y_cold, cold_proba)
    print_metrics("Cold-start set (cold_start.csv)", cold_metrics)

    print("\n--- Cold-start vs. test set comparison ---")
    print(
        "Cold-start rows are all first-time, brand-new customers with zero "
        "payment history, so previous_payment_count/previous_success_count/"
        "previous_failure_count/previous_retry_count are all 0 for every "
        "row. The model still uses customer_type='new' and the transaction- "
        "and population-level features (amount, method, merchant category, "
        "tenure), but loses the customer-history signal that helps it on "
        "the main test set. A gap between cold-start and test-set ROC-AUC "
        "is therefore expected, not a bug — it quantifies exactly how much "
        "the model currently relies on history it doesn't have for brand-"
        "new customers."
    )
    if test_metrics["roc_auc"] is not None and cold_metrics["roc_auc"] is not None:
        gap = test_metrics["roc_auc"] - cold_metrics["roc_auc"]
        print(f"Test ROC-AUC:       {test_metrics['roc_auc']:.4f}")
        print(f"Cold-start ROC-AUC: {cold_metrics['roc_auc']:.4f}")
        print(f"Gap:                {gap:+.4f}")

    # --- Calibration (test set) ---
    calibration_report(y_test, test_proba)
    print(
        "\nCalibration note: this is a simple equal-width-bin check, reported "
        "as-is. No adjustment was made to the model to improve this metric. "
        "If bins show mean-predicted-probability values consistently above "
        "or below the observed rate, that is genuine miscalibration a later "
        "phase would need to address (e.g. via Platt scaling / isotonic "
        "regression) before using these probabilities directly in an "
        "expected-revenue calculation."
    )

    print("\nSUCCESS: evaluation complete. No action-outcome model or decision engine was built.")


if __name__ == "__main__":
    main()
