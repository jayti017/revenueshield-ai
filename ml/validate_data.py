"""
RevenueShield AI — Phase 2: Synthetic Dataset Validator

Runs schema, consistency, and leakage checks against the files produced by
ml/generate_data.py, and prints a PASS/FAIL summary plus a data-quality
report. No machine learning happens here.

USAGE (from the project root, virtual environment active):

    python ml/validate_data.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = PROJECT_ROOT / "ml" / "data" / "raw" / "payments_raw.csv"
PROCESSED_DIR = PROJECT_ROOT / "ml" / "data" / "processed"
TRAIN_PATH = PROCESSED_DIR / "train.csv"
VAL_PATH = PROCESSED_DIR / "validation.csv"
TEST_PATH = PROCESSED_DIR / "test.csv"
COLD_START_PATH = PROCESSED_DIR / "cold_start.csv"

REQUIRED_COLUMNS = [
    "transaction_id", "customer_id",
    "customer_type", "customer_tenure_days",
    "payment_amount", "payment_method", "merchant_category",
    "previous_payment_count", "previous_success_count",
    "previous_failure_count", "previous_retry_count",
    "payment_status", "failure_reason", "days_since_last_payment",
    "action",
    "payment_success", "amount_recovered",
]

VALID_CUSTOMER_TYPES = {"new", "existing"}
VALID_ACTIONS = {"do_nothing", "retry", "reminder", "recovery_link"}
VALID_FAILURE_REASONS = {
    "none", "insufficient_funds", "expired_card", "temporary_failure",
    "bank_decline", "authentication_failed", "network_error",
}
MIN_EXAMPLES_PER_ACTION = 100


class CheckResult:
    def __init__(self, number: int, description: str):
        self.number = number
        self.description = description
        self.passed = True
        self.details: list[str] = []

    def fail(self, detail: str) -> None:
        self.passed = False
        self.details.append(detail)

    def report(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        line = f"[{status}] {self.number:2d}. {self.description}"
        if not self.passed:
            for d in self.details[:5]:
                line += f"\n        - {d}"
            if len(self.details) > 5:
                line += f"\n        - ... and {len(self.details) - 5} more"
        return line


def load_all() -> dict[str, pd.DataFrame]:
    paths = {
        "raw": RAW_PATH,
        "train": TRAIN_PATH,
        "validation": VAL_PATH,
        "test": TEST_PATH,
        "cold_start": COLD_START_PATH,
    }
    missing = [name for name, p in paths.items() if not p.exists()]
    if missing:
        print("FAIL: the following expected files do not exist yet:")
        for name in missing:
            print(f"  - {paths[name]}")
        print("\nRun `python ml/generate_data.py` first.")
        raise SystemExit(1)
    return {name: pd.read_csv(p) for name, p in paths.items()}


def run_checks(data: dict[str, pd.DataFrame]) -> list[CheckResult]:
    raw = data["raw"]
    train, val, test = data["train"], data["validation"], data["test"]
    cold_start = data["cold_start"]
    results: list[CheckResult] = []

    # 1. Required columns exist
    c = CheckResult(1, "Required columns exist in raw dataset")
    missing_cols = set(REQUIRED_COLUMNS) - set(raw.columns)
    if missing_cols:
        c.fail(f"Missing columns: {sorted(missing_cols)}")
    results.append(c)

    # 2. No duplicate transaction IDs (within raw, and no overlap across splits)
    c = CheckResult(2, "No duplicate transaction_id values")
    dup_raw = raw["transaction_id"].duplicated().sum()
    if dup_raw:
        c.fail(f"{dup_raw} duplicate transaction_id(s) in raw dataset")
    split_ids = pd.concat([train["transaction_id"], val["transaction_id"], test["transaction_id"]])
    dup_split = split_ids.duplicated().sum()
    if dup_split:
        c.fail(f"{dup_split} transaction_id(s) appear in more than one of train/validation/test")
    results.append(c)

    # 3. No missing values in required fields
    c = CheckResult(3, "No missing values in required fields")
    for col in REQUIRED_COLUMNS:
        if col in raw.columns:
            n_missing = raw[col].isna().sum()
            if n_missing:
                c.fail(f"{col}: {n_missing} missing values")
    results.append(c)

    # 4. Payment amounts are positive
    c = CheckResult(4, "payment_amount is positive for all rows")
    n_bad = (raw["payment_amount"] <= 0).sum()
    if n_bad:
        c.fail(f"{n_bad} rows with payment_amount <= 0")
    results.append(c)

    # 5. payment_success is binary
    c = CheckResult(5, "payment_success contains only 0 and 1")
    bad_values = set(raw["payment_success"].unique()) - {0, 1}
    if bad_values:
        c.fail(f"Unexpected values: {bad_values}")
    results.append(c)

    # 6. action contains only the four allowed values
    c = CheckResult(6, "action contains only the four allowed values")
    bad_actions = set(raw["action"].unique()) - VALID_ACTIONS
    if bad_actions:
        c.fail(f"Unexpected action values: {bad_actions}")
    results.append(c)

    # 7. customer_type contains only new/existing
    c = CheckResult(7, "customer_type contains only new/existing")
    bad_types = set(raw["customer_type"].unique()) - VALID_CUSTOMER_TYPES
    if bad_types:
        c.fail(f"Unexpected customer_type values: {bad_types}")
    results.append(c)

    # 8. New customers have zero historical counts
    c = CheckResult(8, "New customers have zero historical counts")
    new_rows = raw[raw["customer_type"] == "new"]
    for col in ["previous_payment_count", "previous_success_count", "previous_failure_count", "previous_retry_count"]:
        n_bad = (new_rows[col] != 0).sum()
        if n_bad:
            c.fail(f"{col}: {n_bad} 'new' rows with a non-zero value")
    results.append(c)

    # 9. Historical counts are logically consistent
    c = CheckResult(9, "Historical counts are logically consistent")
    n_bad = (raw["previous_success_count"] + raw["previous_failure_count"] > raw["previous_payment_count"]).sum()
    if n_bad:
        c.fail(f"{n_bad} rows where previous_success_count + previous_failure_count > previous_payment_count")
    n_bad2 = (raw["previous_retry_count"] > raw["previous_payment_count"]).sum()
    if n_bad2:
        c.fail(f"{n_bad2} rows where previous_retry_count > previous_payment_count")
    results.append(c)

    # 10 & 11. failure_reason agrees with payment_success
    c = CheckResult(10, "Successful payments have failure_reason == 'none'")
    n_bad = ((raw["payment_success"] == 1) & (raw["failure_reason"] != "none")).sum()
    if n_bad:
        c.fail(f"{n_bad} successful rows with a non-'none' failure_reason")
    results.append(c)

    c = CheckResult(11, "Failed payments have a valid, non-'none' failure_reason")
    n_bad = ((raw["payment_success"] == 0) & (raw["failure_reason"] == "none")).sum()
    if n_bad:
        c.fail(f"{n_bad} failed rows with failure_reason == 'none'")
    bad_reasons = set(raw["failure_reason"].unique()) - VALID_FAILURE_REASONS
    if bad_reasons:
        c.fail(f"Unexpected failure_reason values: {bad_reasons}")
    results.append(c)

    # 12. payment_status agrees with payment_success
    c = CheckResult(12, "payment_status agrees with payment_success")
    n_bad = (
        ((raw["payment_success"] == 1) & (raw["payment_status"] != "success"))
        | ((raw["payment_success"] == 0) & (raw["payment_status"] != "failed"))
    ).sum()
    if n_bad:
        c.fail(f"{n_bad} rows where payment_status disagrees with payment_success")
    results.append(c)

    # 13. All four actions have sufficient examples
    c = CheckResult(13, f"All four actions have at least {MIN_EXAMPLES_PER_ACTION} examples")
    counts = raw["action"].value_counts()
    for action in VALID_ACTIONS:
        n = int(counts.get(action, 0))
        if n < MIN_EXAMPLES_PER_ACTION:
            c.fail(f"{action}: only {n} examples")
    results.append(c)

    # 14. Train/validation/test files exist (already loaded — check non-empty + reasonable ratios)
    c = CheckResult(14, "Train/validation/test files exist and are non-empty")
    for name, d in [("train", train), ("validation", val), ("test", test)]:
        if len(d) == 0:
            c.fail(f"{name}.csv is empty")
    total = len(train) + len(val) + len(test)
    if total > 0:
        train_frac = len(train) / total
        val_frac = len(val) / total
        test_frac = len(test) / total
        if not (0.60 <= train_frac <= 0.80):
            c.fail(f"train fraction {train_frac:.2%} is outside the expected ~70% range")
        if not (0.08 <= val_frac <= 0.22):
            c.fail(f"validation fraction {val_frac:.2%} is outside the expected ~15% range")
        if not (0.08 <= test_frac <= 0.22):
            c.fail(f"test fraction {test_frac:.2%} is outside the expected ~15% range")
    # customer-level leakage check
    train_customers = set(train["customer_id"])
    val_customers = set(val["customer_id"])
    test_customers = set(test["customer_id"])
    overlap = (train_customers & val_customers) | (train_customers & test_customers) | (val_customers & test_customers)
    if overlap:
        c.fail(f"{len(overlap)} customer_id(s) appear in more than one split (customer-level leakage)")
    results.append(c)

    # 15. Cold-start dataset exists
    c = CheckResult(15, "Cold-start dataset exists and is non-empty")
    if len(cold_start) == 0:
        c.fail("cold_start.csv is empty")
    results.append(c)

    # 16. Cold-start customers satisfy the required conditions
    c = CheckResult(16, "Cold-start customers satisfy required conditions")
    n_bad_type = (cold_start["customer_type"] != "new").sum()
    if n_bad_type:
        c.fail(f"{n_bad_type} cold_start rows with customer_type != 'new'")
    for col in ["previous_payment_count", "previous_success_count", "previous_failure_count", "previous_retry_count"]:
        n_bad = (cold_start[col] != 0).sum()
        if n_bad:
            c.fail(f"{col}: {n_bad} cold_start rows with a non-zero value")
    overlap_ids = set(cold_start["customer_id"]) & set(raw["customer_id"])
    if overlap_ids:
        c.fail(f"{len(overlap_ids)} customer_id(s) appear in both cold_start and the main dataset")
    results.append(c)

    return results


def print_data_quality_report(data: dict[str, pd.DataFrame]) -> None:
    raw = data["raw"]
    cold_start = data["cold_start"]

    print("\n--- Data Quality Report: main dataset (payments_raw.csv) ---")
    print(f"Total rows:              {len(raw):,}")
    print(f"Unique customers:        {raw['customer_id'].nunique():,}")
    print(f"New-customer rows:       {(raw['customer_type'] == 'new').sum():,}")
    print(f"Existing-customer rows:  {(raw['customer_type'] == 'existing').sum():,}")
    print(f"Success rate:            {raw['payment_success'].mean():.2%}")
    print(f"Failure rate:            {1 - raw['payment_success'].mean():.2%}")
    print(f"Average payment amount:  Rs {raw['payment_amount'].mean():,.2f}")
    print("\nAction distribution:")
    for action, count in raw["action"].value_counts().items():
        print(f"  {action:15s} {count:>7,}  ({count / len(raw):.1%})")
    print("\nFailure reason distribution:")
    for reason, count in raw["failure_reason"].value_counts().items():
        print(f"  {reason:22s} {count:>7,}  ({count / len(raw):.1%})")
    print(
        "\nNote: raw success-rate-by-action is confounded by design — riskier "
        "payments were more likely to receive an active intervention (see "
        "README Phase 2 section). Do not read raw per-action success rate as "
        "the action's causal effect; that requires modeling conditional on risk."
    )

    print("\n--- Data Quality Report: cold_start.csv ---")
    print(f"Total rows:              {len(cold_start):,}")
    print(f"Unique customers:        {cold_start['customer_id'].nunique():,}")
    print(f"Success rate:            {cold_start['payment_success'].mean():.2%}")
    print(f"Average payment amount:  Rs {cold_start['payment_amount'].mean():,.2f}")


def main() -> None:
    data = load_all()
    results = run_checks(data)

    print("--- RevenueShield AI — Phase 2 Data Validation ---\n")
    for r in results:
        print(r.report())

    n_passed = sum(1 for r in results if r.passed)
    n_total = len(results)
    print(f"\n{n_passed}/{n_total} checks passed.")

    if n_passed == n_total:
        print("OVERALL RESULT: PASS")
    else:
        print("OVERALL RESULT: FAIL")

    print_data_quality_report(data)

    if n_passed != n_total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
