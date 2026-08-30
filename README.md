# RevenueShield AI — Explainable Revenue Recovery Decision Engine

## 1. Project Name

**RevenueShield AI**

## 2. Short Description

RevenueShield AI is an explainable decision layer for recurring-payment
recovery. It does not replace Razorpay's existing payment recovery, retry,
routing, or subscription systems — it decides, for a given at-risk payment,
which of the recovery actions already available is worth using, and proves
why.

## 3. Problem Statement

Recurring-payment platforms provide multiple recovery mechanisms for at-risk
or failed transactions, including retries, reminders, and recovery links.
Applying the same recovery strategy to every customer can produce lower
collection rates, unnecessary payment attempts, and unnecessary customer
friction. RevenueShield AI will eventually estimate the expected outcome of
each permitted recovery action for an individual payment, select the action
with the highest expected economic value under merchant-defined safety
constraints, and record the full decision — including why the alternatives
were rejected — in an auditable trail.

## 4. Core Idea

For an at-risk recurring payment, the eventual system will:

1. Evaluate possible recovery actions.
2. Predict the probability of successful collection for each action.
3. Calculate expected revenue (`payment_amount × predicted_success_probability`).
4. Apply merchant safety constraints (allowed actions, retry/reminder limits,
   confidence thresholds, customer-friction limits).
5. Select the best permitted action.
6. Explain why that action was selected and why the others were rejected.
7. Store an auditable decision record.

## 5. Four Future MVP Actions

1. `do_nothing`
2. `retry`
3. `reminder`
4. `recovery_link`

None of the logic that evaluates or chooses between these actions exists
yet. They are listed here only to document the target scope.

## 6. High-Level Architecture (target — not built yet)

```
Upcoming recurring payment
        ↓
Feature processing
        ↓
Payment risk model  ──► not risky ──► default strategy
        ↓ risky
Action-outcome models (do_nothing / retry / reminder / recovery_link)
        ↓
Expected revenue calculation
        ↓
Decision engine (merchant rules + safety constraints + confidence gate)
        ↓
Best valid action + explanation (selected + rejected reasons)
        ↓
Audit trail
        ↓
Razorpay Test Mode API (simulated/real test action)
        ↓
Outcome → stored → used in offline policy evaluation
```

## 7. Technology Stack

- **Backend:** Python, FastAPI, Uvicorn
- **ML (later phase):** Pandas, NumPy, scikit-learn, XGBoost/LightGBM, SHAP
- **Database (later phase):** SQLite for MVP
- **Frontend (later phase):** React, TypeScript, Tailwind CSS
- **Payments (later phase):** Razorpay Test Mode only

## 8. Current Phase

**Phase 2 — Synthetic Payment Dataset.**

Phase 1 (project foundation: FastAPI skeleton, `/health`, tests) is
complete. Phase 2's only objective is a realistic, reproducible synthetic
payment dataset that a later phase will use to train models. See the
"Phase 2 — Synthetic Payment Dataset" section near the end of this document
for the full write-up.

**The following are explicitly NOT implemented yet:**

- ML models (risk model, action-outcome models)
- risk prediction
- action prediction
- expected revenue calculation
- decision engine
- explainability (SHAP)
- audit system
- frontend
- Razorpay integration

## 9. Future Development Phases (indicative, not commitments)

- **Phase 3:** Payment risk model + action-outcome models
- **Phase 4:** Decision engine (expected revenue, constraints, explanation)
- **Phase 5:** Audit trail + offline policy evaluation against baselines
- **Phase 6:** Frontend (dashboard, individual decision screen)
- **Phase 7:** Razorpay Test Mode integration

## 10. Windows Setup Instructions

All commands below are PowerShell-compatible and assume you are starting
from the `RevenueShield/` project root.

### 10.1 Create and activate the virtual environment

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
```

### 10.2 Install requirements

```powershell
pip install -r requirements.txt
```

### 10.3 Run the backend

```powershell
uvicorn app.main:app --reload
```

Run this from inside `backend/`, with the virtual environment active.

### 10.4 Test `/health`

With the server running, open a browser to:

```
http://127.0.0.1:8000/health
```

Expected response:

```json
{
    "status": "ok",
    "phase": "1"
}
```

### 10.5 Access `/docs`

With the server running, open:

```
http://127.0.0.1:8000/docs
```

This is FastAPI's automatically generated interactive documentation.

### 10.6 Run the automated test

From the project root (`RevenueShield/`), with the virtual environment
active:

```powershell
pytest
```

This runs `tests/test_health.py`, which verifies `/health` returns
`status: ok` and `phase: 1`.

## 11. Project Structure

```
RevenueShield/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI app, /health only
│   │   ├── api/              # empty — route handlers land here later
│   │   ├── models/           # empty — later
│   │   ├── services/         # empty — decision engine logic lands here later
│   │   ├── schemas/          # empty — Pydantic schemas land here later
│   │   └── utils/            # empty — later
│   ├── .env.example
│   └── requirements.txt
├── ml/
│   ├── generate_data.py       # Phase 2: synthetic dataset generator
│   ├── validate_data.py       # Phase 2: dataset validation + quality report
│   ├── requirements.txt       # pandas, numpy only — no ML training libraries yet
│   ├── data/
│   │   ├── raw/
│   │   │   └── payments_raw.csv        # generated, not committed (see .gitignore)
│   │   └── processed/
│   │       ├── train.csv               # generated, not committed
│   │       ├── validation.csv          # generated, not committed
│   │       ├── test.csv                # generated, not committed
│   │       └── cold_start.csv          # generated, not committed
│   └── models/                # empty — trained model artifacts land here in a later phase
├── frontend/                  # empty — not built yet
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # makes backend/app importable from project root
│   └── test_health.py
├── docs/
├── .gitignore
└── README.md
```

## 12. Phase 2 — Synthetic Payment Dataset

### Why synthetic data is required

Real Razorpay production/customer data is not available for this project.
To train and validate a payment-risk model and per-action outcome models in
a later phase, we need a dataset that is realistic — internally consistent
customer histories, plausible failure patterns, and recovery actions that
actually influence the outcome — rather than columns generated independently
at random.

### Dataset size

- **Main dataset:** 50,000 transactions (configurable via `--n-samples`)
- **Cold-start dataset:** 5,000 transactions (configurable via `--cold-start-n`)

Both sizes are constants at the top of `ml/generate_data.py` and can also be
overridden from the command line — see "How to generate the dataset" below.

### Dataset fields

| Field | Description |
|---|---|
| `transaction_id` | Unique per transaction |
| `customer_id` | Unique per customer; repeats across a customer's transactions |
| `customer_type` | `new` on a customer's first-ever transaction, `existing` afterward |
| `customer_tenure_days` | Days since the customer's first payment, as of this transaction |
| `payment_amount` | Positive amount, drawn from a merchant-category-specific distribution |
| `payment_method` | `card`, `upi`, `netbanking`, or `wallet` |
| `merchant_category` | `ecommerce`, `saas`, `education`, `travel`, `healthcare`, or `subscription` |
| `previous_payment_count` | Number of this customer's transactions *before* this one |
| `previous_success_count` | Of those, how many succeeded |
| `previous_failure_count` | Of those, how many failed |
| `previous_retry_count` | Of those, how many used the `retry` action |
| `payment_status` | `success` or `failed` — always agrees with `payment_success` |
| `failure_reason` | `none` if successful; otherwise one of 6 realistic decline categories |
| `days_since_last_payment` | Days since this customer's previous transaction (`0` sentinel if there wasn't one) |
| `action` | The recovery action historically applied to this transaction |
| `payment_success` | `1` or `0` |
| `amount_recovered` | `payment_amount` if successful, else `0` |

All `previous_*` fields are computed strictly from transactions that came
*before* the current row for that customer — never from the current or
future rows — to avoid target leakage.

### Four actions

`do_nothing`, `retry`, `reminder`, `recovery_link` — matching the MVP scope.
Each has a different, deliberately-designed effect on the failure
probability depending on the transaction's underlying risk type (e.g.
`retry` is most effective for `temporary_failure`/`network_error`;
`recovery_link` is most effective for `expired_card`/`authentication_failed`;
`reminder` is most effective for `insufficient_funds`). Customers who have
already been retried/reminded several times show a discounted effect
("fatigue"), per the spec.

**Important — assignment confounding is intentional.** Which action a
transaction received is itself biased by that transaction's *pre-action*
risk level (riskier payments were more likely to get an active
intervention), the same way a real merchant's existing recovery strategy
would behave. This means the raw, unconditional success rate *by action* in
the dataset does **not** reflect each action's true causal effect — e.g.
`do_nothing` can show a higher raw success rate than `retry` simply because
`do_nothing` was disproportionately used on already-low-risk payments. A
future model must condition on risk/context to recover the true per-action
effect. `ml/validate_data.py` prints an explicit note about this so it isn't
mistaken for a bug.

### Cold-start dataset

`ml/data/processed/cold_start.csv` — 5,000 independently-generated
transactions, each a distinct brand-new customer's first-ever payment
(`customer_type = new`, all `previous_*` fields `0`). Generated with its own
customer-ID namespace (`CS######`) so it never overlaps with the main
dataset, for evaluating future model behavior specifically on customers with
no history.

### Train/validation/test split

70% / 15% / 15%, split by **customer**, not by row: all of a given
customer's transactions land in the same split. A row-random split would let
a customer's earlier transactions sit in `train` while a later transaction
from that *same* customer sits in `test` — since `previous_*` fields make a
later row partially a function of that customer's earlier rows, that would
leak customer-specific signal across the split boundary. `validate_data.py`
explicitly checks that no `customer_id` appears in more than one split.

Actual split sizes from the default run (50,000 rows, seed 42):

| Split | Rows | Customers |
|---|---|---|
| Train | 35,062 | 5,835 |
| Validation | 7,321 | 1,250 |
| Test | 7,617 | 1,251 |

### Reproducibility / random seed

`RANDOM_SEED = 42` by default, overridable via `--seed`. The generator uses
`numpy.random.default_rng(seed)` throughout — re-running with the same seed
produces a byte-identical `payments_raw.csv` (verified: identical MD5 hash
across two separate runs).

### Data validation

`ml/validate_data.py` runs 16 checks (schema, duplicates, missing values,
value ranges, historical-count consistency, `failure_reason`/`payment_status`
agreement, minimum examples per action, split ratios and customer-level
leakage, cold-start conditions) and prints a PASS/FAIL summary per check plus
a data-quality report. All 16 checks currently pass against the generated
data.

### How to generate the dataset

```powershell
cd ml
pip install -r requirements.txt
cd ..
python ml/generate_data.py
```

Optional arguments:

```powershell
python ml/generate_data.py --n-samples 20000 --cold-start-n 2000 --seed 7
```

### How to validate the dataset

```powershell
python ml/validate_data.py
```
