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

**Phase 3B — Action-Outcome Models.**

Phase 1 (project foundation), Phase 2 (synthetic dataset), and Phase 3A
(payment failure risk model) are complete. Phase 3B's only objective is four
supporting models — one per recovery action — each estimating `P(success |
features, this action was taken)`. See the "Phase 3B — Action-Outcome
Models" section near the end of this document for the full write-up.

**The following are explicitly NOT implemented yet:**

- expected revenue calculation
- decision engine
- merchant constraints
- audit system
- explainability (SHAP)
- frontend
- Razorpay integration

## 9. Future Development Phases (indicative, not commitments)

- **Phase 4:** Decision engine (expected revenue, merchant constraints, explanation, action selection)
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
│   ├── train_risk_model.py    # Phase 3A: trains the failure-risk model
│   ├── evaluate_risk_model.py # Phase 3A: evaluates it on val/test/cold-start
│   ├── train_action_models.py    # Phase 3B: trains 4 per-action outcome models
│   ├── evaluate_action_models.py # Phase 3B: evaluates each on val/test/cold-start
│   ├── requirements.txt       # pandas, numpy, scikit-learn, joblib — no XGBoost/SHAP/etc.
│   ├── data/
│   │   ├── raw/
│   │   │   └── payments_raw.csv        # generated, not committed (see .gitignore)
│   │   └── processed/
│   │       ├── train.csv               # generated, not committed
│   │       ├── validation.csv          # generated, not committed
│   │       ├── test.csv                # generated, not committed
│   │       └── cold_start.csv          # generated, not committed
│   └── models/
│       ├── risk_model.joblib              # generated, not committed
│       ├── action_model_do_nothing.joblib     # generated, not committed
│       ├── action_model_retry.joblib          # generated, not committed
│       ├── action_model_reminder.joblib       # generated, not committed
│       └── action_model_recovery_link.joblib  # generated, not committed
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

## 13. Phase 3A — Payment Failure Risk Model

### Purpose

The risk model estimates `P(payment failure | information available before
the outcome)` for an upcoming recurring payment. It is supporting
infrastructure, not RevenueShield's core innovation — a later phase's
decision engine will use its output as one input among several. It does not
decide anything and does not calculate expected revenue.

### Target variable

```
failure_target = 1 - payment_success
```
So `payment_success = 1` (succeeded) → `failure_target = 0`, and
`payment_success = 0` (failed) → `failure_target = 1`. The model outputs
`failure_probability` via `predict_proba()`, a value in `[0, 1]`.

### Input features (10)

**Categorical** (one-hot encoded): `customer_type`, `payment_method`, `merchant_category`

**Numeric** (standardized): `customer_tenure_days`, `payment_amount`,
`previous_payment_count`, `previous_success_count`, `previous_failure_count`,
`previous_retry_count`, `days_since_last_payment`

### Prohibited leakage features

`payment_success`, `failure_target`, `amount_recovered`, `payment_status`,
`failure_reason`, `transaction_id`, `customer_id` are all excluded from the
feature matrix, and both `train_risk_model.py` and `evaluate_risk_model.py`
explicitly assert none of them are present before training/evaluating —
failing loudly if one ever appears.

**`action` is also deliberately excluded**, and not just because it's
"post-decision" — in the Phase 2 generator, which action was historically
applied was itself chosen based on the payment's risk level (riskier
payments were more likely to receive an active intervention). Including
`action` as a risk-model feature would leak that historical assignment
policy into what is supposed to be a pre-decision risk estimate.

### Preprocessing approach

A single `scikit-learn` `Pipeline`: a `ColumnTransformer` (`OneHotEncoder`
for the 3 categorical columns, `StandardScaler` for the 7 numeric columns)
feeding a `LogisticRegression`. No manual numeric label assignment (no
`card=1, upi=2`) — one-hot encoding avoids implying a false ordering between
categories.

### Model choice

**Logistic Regression**, as specified: interpretable, fast, produces
well-calibrated-by-default probabilities, and an appropriate MVP baseline.
`class_weight` was deliberately left at its default (not `"balanced"`) —
RevenueShield will eventually feed these probabilities directly into an
expected-value calculation, and class-weighting would distort them away
from reflecting the true failure rate, which matters more here than
balanced classification accuracy at an arbitrary threshold. XGBoost/LightGBM
were not used — not necessary for this baseline and would add complexity
without a demonstrated need.

### Training / validation / test data

Reused directly from Phase 2's customer-aware split — no re-shuffling:

- Train: `ml/data/processed/train.csv` (35,062 rows)
- Validation: `ml/data/processed/validation.csv` (7,321 rows) — used during training to report held-out performance
- Test: `ml/data/processed/test.csv` (7,617 rows) — final evaluation only, in `evaluate_risk_model.py`

### Cold-start evaluation

Also evaluated on `ml/data/processed/cold_start.csv` (5,000 rows, all
brand-new customers with zero payment history). Result: **ROC-AUC drops
from 0.68 (test set) to 0.51 (cold-start)** — essentially no better than
chance. This is an honest, expected finding, not a bug: cold-start rows have
`previous_payment_count = previous_success_count = previous_failure_count =
previous_retry_count = 0` for every row, and that customer-history signal is
what the model leans on most. The model still receives `customer_type`,
`payment_amount`, `payment_method`, `merchant_category`, and
`customer_tenure_days` for cold-start rows, but that alone isn't enough to
meaningfully separate risk in this dataset. This is a real limitation worth
carrying into the next phase, not something this phase tried to paper over.

### Metrics (test set, from the actual run)

| Metric | Model | Constant baseline |
|---|---|---|
| ROC-AUC | **0.6829** | 0.5000 (by definition) |
| Brier score | **0.1406** | 0.1515 |
| Precision (@0.5) | 0.5130 | 0.0000 |
| Recall (@0.5) | 0.0558 | 0.0000 |
| F1 (@0.5) | 0.1006 | 0.0000 |

The model clearly beats the baseline on both ROC-AUC and Brier score — it
has real, if moderate, predictive signal. Precision/recall/F1 at the default
0.5 threshold are not very informative here: with an ~18% base failure
rate, a plain 0.5 cutoff is a poor operating point (predicted probabilities
cluster below 0.5 even for many true failures), which is expected for a
model whose real use is feeding a probability into an expected-value
calculation rather than making a binary call at 0.5. A later phase choosing
an actual decision threshold should tune it against the business objective,
not use 0.5 by default.

### Calibration

A simple 10-bin calibration check (mean predicted probability vs. observed
failure rate per bin) was run on the test set — see `evaluate_risk_model.py`
output. Calibration is reasonably good in the well-populated low-probability
bins (where most of the data sits) and noisier in the sparsely-populated
high-probability bins (as few as 14–41 rows per bin there), which is
expected given how few test-set rows fall above ~0.5 predicted probability.
No adjustment was made to the model to improve this metric — it's reported
as-is, per the Phase 3 spec. If a later phase needs better-calibrated
probabilities in the high-risk range specifically, Platt scaling or isotonic
regression would be the natural next step, applied on top of this model
rather than replacing it.

### Baseline comparison

A constant-probability baseline (predicting the training-set failure rate,
17.99%, for every test-set row) is computed in `evaluate_risk_model.py` for
comparison. The trained model beats it on both ROC-AUC (0.68 vs. 0.50) and
Brier score (0.1406 vs. 0.1515), demonstrating the model adds real
predictive value beyond a trivial constant guess.

### Model artifact

`ml/models/risk_model.joblib` — the complete fitted `Pipeline` (preprocessing
+ Logistic Regression), directly loadable via `joblib.load()` for future
inference. Not the raw `LogisticRegression` object alone, since raw new data
still needs the same one-hot encoding / scaling applied first.

### Reproducibility

`RANDOM_SEED = 42`, passed to `LogisticRegression(random_state=...)`.
Verified: running `train_risk_model.py` twice produces a byte-identical
`risk_model.joblib` (same MD5 hash both times).

### How to train

```powershell
python ml/train_risk_model.py
```

### How to evaluate

```powershell
python ml/evaluate_risk_model.py
```

## 14. Phase 3B — Action-Outcome Models

### Why there are four models

RevenueShield's eventual decision engine needs `P(success | features,
action)` for each of the four candidate actions, so it can compare their
expected value. A single model with `action` as an ordinary input feature
would let the model implicitly average/interpolate across actions in ways
that are hard to inspect or trust. Training one independent model per
action — each fit only on the historical rows where that specific action
was actually taken — keeps each estimate self-contained and matches the
Phase 3B spec's explicit modeling requirement.

### What each model predicts

`action_model_<action>.joblib` predicts `P(payment_success = 1 | features)`
**for payments that historically received `<action>`**. Note the target
here is `payment_success` directly (unlike the Phase 3A risk model, which
predicts `1 - payment_success`) — Phase 3B asks for a success probability,
not a failure probability.

### Features used

The same 10 pre-outcome features as the Phase 3A risk model: `customer_type`,
`payment_method`, `merchant_category` (one-hot encoded), and
`customer_tenure_days`, `payment_amount`, `previous_payment_count`,
`previous_success_count`, `previous_failure_count`, `previous_retry_count`,
`days_since_last_payment` (standardized).

### Columns excluded to prevent leakage

`payment_success`, `payment_status`, `failure_reason`, `amount_recovered`,
`transaction_id`, `customer_id` — the usual outcome/identifier leakage
columns. **`action` itself is also excluded from the feature matrix**: since
each model is trained on a single-action subset, `action` would be constant
within that subset anyway, but excluding it explicitly keeps the modeling
approach correct in spirit — one model per action, never a model that treats
action as a switch to flip. Both `train_action_models.py` and
`evaluate_action_models.py` assert none of these columns are present before
fitting/scoring, failing loudly if one appears.

### How cold-start customers are handled

Cold-start rows (`customer_type = new`, all `previous_*` fields `0`) are
valid, in-range input to every action model — `0` is a legitimate value for
each `previous_*` feature, and `"new"` is a category the `OneHotEncoder`
already saw during training (it isn't an unseen category), so no
preprocessing errors occur. `evaluate_action_models.py` evaluates each
model on `cold_start.csv` and reports it separately.

**Actual cold-start result:** ROC-AUC drops close to (and for `reminder`,
slightly below) 0.5 for every action model — e.g. `do_nothing` 0.6228 (test)
→ 0.5157 (cold-start), `reminder` 0.7075 (test) → 0.4604 (cold-start). Every
cold-start confusion matrix shows the model predicting "success" for every
single row at the 0.5 threshold. This matches the Phase 3A risk model's
cold-start finding: with no payment history, these models currently have
little-to-no ability to discriminate for brand-new customers and default to
predicting the (high) baseline success rate for everyone. This is reported
plainly, not adjusted for — it's a genuine limitation for Phase 4 to
account for (e.g. via the confidence-threshold fallback already documented
in Section 4/Core Idea), not something this phase attempted to fix.

### Why these predictions should not be interpreted as causal treatment effects

Each model is trained on **observational, synthetic** data: which action a
transaction received was itself chosen based on that transaction's
pre-action risk level (see Section 12's "assignment confounding" note — the
same generator produced both the risk-model and action-model training data).
So `action_model_retry.joblib`'s output means "among payments that
historically received `retry`, conditional on these features, this is the
observed success rate" — it does **not** mean "if we retried this specific
payment instead of doing something else, this is the probability it would
succeed." Those are only the same thing under an assumption (no unobserved
confounding) that this phase does not attempt to verify or correct for — no
uplift modeling, propensity weighting, or causal inference was implemented,
by design (out of scope for Phase 3B). A future decision engine consuming
these models' output should treat it as a reasonable observational estimate
for an MVP, not a validated causal effect.

### Metrics (test set, from the actual run)

| Action | ROC-AUC (model) | ROC-AUC (baseline) | Brier (model) | Brier (baseline) |
|---|---|---|---|---|
| `do_nothing` | 0.6228 | 0.5000 | 0.1203 | 0.1268 |
| `retry` | 0.6639 | 0.5000 | 0.1474 | 0.1554 |
| `reminder` | 0.7075 | 0.5000 | 0.1602 | 0.1757 |
| `recovery_link` | 0.7191 | 0.5000 | 0.1437 | 0.1588 |

Every action model beats its constant-probability baseline on both ROC-AUC
and Brier score on the test set. Precision/recall/F1 at the 0.5 threshold
are high but not very informative for `do_nothing`/`retry` specifically —
success rates for those actions are 80–85%, so a model predicting "success"
most of the time scores well on recall almost by construction; ROC-AUC and
Brier are the more meaningful diagnostics here, same reasoning as Phase 3A.

### Model artifacts

```
ml/models/action_model_do_nothing.joblib
ml/models/action_model_retry.joblib
ml/models/action_model_reminder.joblib
ml/models/action_model_recovery_link.joblib
```
Each is a complete fitted `Pipeline` (preprocessing + Logistic Regression),
directly loadable via `joblib.load()`.

### Reproducibility

`RANDOM_SEED = 42`. Verified: running `train_action_models.py` twice
produces byte-identical `.joblib` files for all four actions (same MD5 hash
both times).

### How to train

```powershell
python ml/train_action_models.py
```

### How to evaluate

```powershell
python ml/evaluate_action_models.py
```
