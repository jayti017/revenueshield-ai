"""
RevenueShield AI — Phase 2: Synthetic Payment Dataset Generator

Generates a realistic (not purely random) synthetic dataset of recurring
payment transactions: customer history, an underlying risk factor, the
recovery action actually taken on that historical transaction, and the
final outcome.

This file does NOT train any machine learning model. It only produces CSV
files that a later phase will use to train a risk model and per-action
outcome models. See README.md's "Phase 2" section for the full field
reference and design rationale.

USAGE (from the project root, virtual environment active):

    python ml/generate_data.py
    python ml/generate_data.py --n-samples 20000 --seed 7

OUTPUT:

    ml/data/raw/payments_raw.csv
    ml/data/processed/train.csv
    ml/data/processed/validation.csv
    ml/data/processed/test.csv
    ml/data/processed/cold_start.csv
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration (all overridable via CLI — see main() / parse_args())
# ---------------------------------------------------------------------------

N_SAMPLES = 50_000          # total main-dataset transactions
N_COLD_START = 5_000        # cold-start (brand-new-customer) transactions
RANDOM_SEED = 42

TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
TEST_FRACTION = 0.15        # derived as the remainder; kept explicit for clarity

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "ml" / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]
PAYMENT_METHOD_PROBS = [0.42, 0.38, 0.12, 0.08]
# Small additive effect on the failure logit — some methods decline slightly
# more often than others in practice.
PAYMENT_METHOD_LOGIT_EFFECT = {"card": -0.05, "upi": -0.10, "netbanking": 0.10, "wallet": 0.15}

MERCHANT_CATEGORIES = ["ecommerce", "saas", "education", "travel", "healthcare", "subscription"]
MERCHANT_CATEGORY_PROBS = [0.22, 0.20, 0.15, 0.13, 0.12, 0.18]

# Typical recurring payment amount (median, INR) per merchant category —
# used as the center of a lognormal draw so amounts are realistic and vary
# by business type rather than being a single flat number.
MERCHANT_AMOUNT_MEDIAN = {
    "ecommerce": 1200.0,
    "saas": 2500.0,
    "education": 3500.0,
    "travel": 4500.0,
    "healthcare": 1800.0,
    "subscription": 800.0,
}
AMOUNT_LOGNORMAL_SIGMA = 0.45

FAILURE_REASONS = [
    "insufficient_funds",
    "expired_card",
    "temporary_failure",
    "bank_decline",
    "authentication_failed",
    "network_error",
]
# Relative likelihood that a given transaction's *underlying* risk type is
# each of these categories (this is latent — it only becomes the visible
# `failure_reason` if the payment actually ends up failing).
RISK_TYPE_PROBS = [0.24, 0.14, 0.20, 0.18, 0.12, 0.12]

# Baseline severity each risk type contributes to the failure logit.
RISK_TYPE_SEVERITY = {
    "insufficient_funds": 1.55,
    "expired_card": 1.35,
    "temporary_failure": 0.75,
    "bank_decline": 1.15,
    "authentication_failed": 0.95,
    "network_error": 0.65,
}

ACTIONS = ["do_nothing", "retry", "reminder", "recovery_link"]

# Fractional reduction of the failure probability that each action provides,
# by risk type. 0.55 means "cuts the failure probability by 55% (relative)".
# These encode the intervention-effectiveness relationships required by the
# Phase 2 spec: retry helps transient issues, reminder helps funds/awareness
# issues, recovery_link helps issues that need active customer action.
ACTION_EFFECT = {
    "do_nothing": {r: 0.00 for r in FAILURE_REASONS},
    "retry": {
        "insufficient_funds": 0.10, "expired_card": 0.05, "temporary_failure": 0.55,
        "bank_decline": 0.35, "authentication_failed": 0.08, "network_error": 0.50,
    },
    "reminder": {
        "insufficient_funds": 0.45, "expired_card": 0.12, "temporary_failure": 0.15,
        "bank_decline": 0.15, "authentication_failed": 0.30, "network_error": 0.10,
    },
    "recovery_link": {
        "insufficient_funds": 0.35, "expired_card": 0.55, "temporary_failure": 0.20,
        "bank_decline": 0.30, "authentication_failed": 0.45, "network_error": 0.18,
    },
}

# Base failure logit intercept and coefficients. Tuned so the overall
# dataset failure rate lands in a realistic ~10-20% range after actions are
# applied, with clear separation between risk levels.
INTERCEPT = -2.35
NEW_CUSTOMER_LOGIT = 0.55
PREV_FAILURE_RATE_COEF = 2.10
PREV_SUCCESS_RATE_COEF = 0.90
SEVERITY_COEF = 1.00
NOISE_SD = 0.28

# Customers who have already been retried/reminded several times show
# diminishing returns from further of the same kind of intervention
# ("fatigue") — modeled as a discount on the action's effectiveness.
FATIGUE_RETRY_THRESHOLD = 3
FATIGUE_DISCOUNT = 0.6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


def draw_amount(rng: np.random.Generator, merchant_category: str) -> float:
    median = MERCHANT_AMOUNT_MEDIAN[merchant_category]
    mu = np.log(median)
    amount = rng.lognormal(mean=mu, sigma=AMOUNT_LOGNORMAL_SIGMA)
    return float(np.clip(amount, 49.0, 200_000.0))


def assign_action(rng: np.random.Generator, p_fail_base: float) -> str:
    """Choose which recovery action was historically taken, biased by the
    payment's underlying (pre-action) risk level — riskier payments were
    more likely to receive an active intervention, mirroring how a real
    merchant's existing recovery strategy would behave. Kept probabilistic
    (never deterministic) so every action appears across every risk band.
    """
    if p_fail_base < 0.15:
        probs = [0.55, 0.20, 0.15, 0.10]
    elif p_fail_base < 0.35:
        probs = [0.20, 0.30, 0.28, 0.22]
    else:
        probs = [0.08, 0.27, 0.30, 0.35]
    return rng.choice(ACTIONS, p=probs)


def simulate_customer(
    rng: np.random.Generator,
    customer_id: str,
    n_transactions: int,
    merchant_category: str,
) -> list[dict]:
    """Generates one customer's full transaction history, in order, so that
    every `previous_*` field reflects only what happened before that row —
    this is what avoids target leakage (Section 6/21 of the spec).
    """
    rows: list[dict] = []

    prev_payment_count = 0
    prev_success_count = 0
    prev_failure_count = 0
    prev_retry_count = 0
    tenure_days = 0.0

    for i in range(n_transactions):
        is_new = prev_payment_count == 0
        customer_type = "new" if is_new else "existing"

        if i == 0:
            gap = float(rng.uniform(0, 30))
            days_since_last_payment = 0.0  # sentinel: no previous payment exists
        else:
            gap = float(max(5.0, rng.normal(30, 5)))
            days_since_last_payment = gap
        tenure_days += gap

        payment_method = rng.choice(PAYMENT_METHODS, p=PAYMENT_METHOD_PROBS)
        payment_amount = draw_amount(rng, merchant_category)

        # Neutral priors for brand-new customers (no history to compute a rate from)
        prev_success_rate = (prev_success_count / prev_payment_count) if prev_payment_count > 0 else 0.55
        prev_failure_rate = (prev_failure_count / prev_payment_count) if prev_payment_count > 0 else 0.15

        risk_type = rng.choice(FAILURE_REASONS, p=RISK_TYPE_PROBS)
        severity = RISK_TYPE_SEVERITY[risk_type]

        logit = (
            INTERCEPT
            + NEW_CUSTOMER_LOGIT * is_new
            + PREV_FAILURE_RATE_COEF * prev_failure_rate
            - PREV_SUCCESS_RATE_COEF * prev_success_rate
            + PAYMENT_METHOD_LOGIT_EFFECT[payment_method]
            + SEVERITY_COEF * severity
            + rng.normal(0, NOISE_SD)
        )
        p_fail_base = float(np.clip(sigmoid(logit), 0.02, 0.90))

        action = assign_action(rng, p_fail_base)

        reduction = ACTION_EFFECT[action][risk_type]
        if action in ("retry", "reminder") and prev_retry_count >= FATIGUE_RETRY_THRESHOLD:
            reduction *= FATIGUE_DISCOUNT

        jitter = float(rng.uniform(0.85, 1.15))
        p_fail_action = float(np.clip(p_fail_base * (1 - reduction) * jitter, 0.01, 0.95))

        payment_success = int(rng.random() > p_fail_action)
        failure_reason = "none" if payment_success == 1 else risk_type
        payment_status = "success" if payment_success == 1 else "failed"
        amount_recovered = payment_amount if payment_success == 1 else 0.0

        rows.append({
            "transaction_id": f"{customer_id}-T{i + 1:03d}",
            "customer_id": customer_id,
            "customer_type": customer_type,
            "customer_tenure_days": round(tenure_days, 1),
            "payment_amount": round(payment_amount, 2),
            "payment_method": payment_method,
            "merchant_category": merchant_category,
            "previous_payment_count": prev_payment_count,
            "previous_success_count": prev_success_count,
            "previous_failure_count": prev_failure_count,
            "previous_retry_count": prev_retry_count,
            "payment_status": payment_status,
            "failure_reason": failure_reason,
            "days_since_last_payment": round(days_since_last_payment, 1),
            "action": action,
            "payment_success": payment_success,
            "amount_recovered": round(amount_recovered, 2),
        })

        prev_payment_count += 1
        prev_success_count += payment_success
        prev_failure_count += (1 - payment_success)
        prev_retry_count += int(action == "retry")

    return rows


def generate_main_dataset(rng: np.random.Generator, n_samples: int) -> pd.DataFrame:
    """Builds the main dataset by simulating customers one at a time until
    the target row count is reached, then trims the final customer so the
    total is exactly `n_samples`.
    """
    all_rows: list[dict] = []
    customer_idx = 0

    while len(all_rows) < n_samples:
        customer_idx += 1
        customer_id = f"C{customer_idx:06d}"
        n_transactions = int(rng.poisson(lam=5)) + 1  # every customer has at least 1 transaction
        merchant_category = rng.choice(MERCHANT_CATEGORIES, p=MERCHANT_CATEGORY_PROBS)

        customer_rows = simulate_customer(rng, customer_id, n_transactions, merchant_category)
        all_rows.extend(customer_rows)

    all_rows = all_rows[:n_samples]  # trim exactly to n_samples
    return pd.DataFrame(all_rows)


def generate_cold_start_dataset(rng: np.random.Generator, n_cold_start: int) -> pd.DataFrame:
    """Independently generates brand-new-customer transactions (each
    customer's first-ever payment only). Uses a separate customer_id
    namespace so it never overlaps with the main dataset's customers.
    """
    all_rows: list[dict] = []
    for i in range(n_cold_start):
        customer_id = f"CS{i + 1:06d}"
        merchant_category = rng.choice(MERCHANT_CATEGORIES, p=MERCHANT_CATEGORY_PROBS)
        rows = simulate_customer(rng, customer_id, n_transactions=1, merchant_category=merchant_category)
        all_rows.extend(rows)
    return pd.DataFrame(all_rows)


def customer_aware_split(
    df: pd.DataFrame, rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Splits by customer_id (not by row) so that all of a given customer's
    transactions land in the same split. A row-random split would let a
    customer's early transactions sit in train while a later transaction
    from the *same* customer sits in test — since previous_* fields make
    later rows partially a function of earlier ones for that customer,
    that would leak customer-specific signal across the split. Splitting by
    customer avoids that.
    """
    customer_ids = np.array(df["customer_id"].unique(), dtype=object)
    rng.shuffle(customer_ids)

    n = len(customer_ids)
    n_train = int(round(n * TRAIN_FRACTION))
    n_val = int(round(n * VALIDATION_FRACTION))

    train_ids = set(customer_ids[:n_train])
    val_ids = set(customer_ids[n_train:n_train + n_val])
    test_ids = set(customer_ids[n_train + n_val:])

    train_df = df[df["customer_id"].isin(train_ids)].reset_index(drop=True)
    val_df = df[df["customer_id"].isin(val_ids)].reset_index(drop=True)
    test_df = df[df["customer_id"].isin(test_ids)].reset_index(drop=True)
    return train_df, val_df, test_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the RevenueShield AI synthetic payment dataset.")
    parser.add_argument("--n-samples", type=int, default=N_SAMPLES, help="Number of main-dataset transactions.")
    parser.add_argument("--cold-start-n", type=int, default=N_COLD_START, help="Number of cold-start transactions.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Random seed for reproducibility.")
    parser.add_argument("--output-dir", type=str, default=None, help="Override ml/data/ base directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = time.time()

    raw_dir = RAW_DIR
    processed_dir = PROCESSED_DIR
    if args.output_dir:
        base = Path(args.output_dir)
        raw_dir = base / "raw"
        processed_dir = base / "processed"

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(args.seed)

    print(f"Generating {args.n_samples:,} main-dataset transactions (seed={args.seed})...")
    main_df = generate_main_dataset(rng, args.n_samples)

    print(f"Generating {args.cold_start_n:,} cold-start transactions...")
    cold_start_df = generate_cold_start_dataset(rng, args.cold_start_n)

    raw_path = raw_dir / "payments_raw.csv"
    main_df.to_csv(raw_path, index=False)

    print("Splitting main dataset by customer (70/15/15)...")
    train_df, val_df, test_df = customer_aware_split(main_df, rng)

    train_path = processed_dir / "train.csv"
    val_path = processed_dir / "validation.csv"
    test_path = processed_dir / "test.csv"
    cold_start_path = processed_dir / "cold_start.csv"

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)
    cold_start_df.to_csv(cold_start_path, index=False)

    elapsed = time.time() - start

    print("\n--- RevenueShield AI — Phase 2 dataset generation complete ---")
    print(f"Raw dataset:        {raw_path}  ({len(main_df):,} rows)")
    print(f"Train split:        {train_path}  ({len(train_df):,} rows, {train_df['customer_id'].nunique():,} customers)")
    print(f"Validation split:   {val_path}  ({len(val_df):,} rows, {val_df['customer_id'].nunique():,} customers)")
    print(f"Test split:         {test_path}  ({len(test_df):,} rows, {test_df['customer_id'].nunique():,} customers)")
    print(f"Cold-start dataset: {cold_start_path}  ({len(cold_start_df):,} rows)")
    print(f"Total customers (main dataset): {main_df['customer_id'].nunique():,}")
    print(f"Generation time: {elapsed:.2f}s")
    print("SUCCESS: dataset generation complete. No model was trained.")


if __name__ == "__main__":
    main()
