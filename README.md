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

**Phase 4 — FastAPI Decision API.**

Phase 1 (project foundation), Phase 2 (synthetic dataset), Phase 3A
(payment failure risk model), Phase 3B (four action-outcome models), and
Phase 3C (decision engine) are complete. Phase 4's only objective is a thin
FastAPI layer exposing the existing Phase 3C decision engine over HTTP —
`POST /api/v1/decision`. No decision-making logic was moved into the API;
it calls the existing engine and returns what it produces. See the
"Phase 4 — FastAPI Decision API" section near the end of this document for
the full write-up.

**The following are explicitly NOT implemented yet:**

- React frontend
- dashboard
- Razorpay integration
- real payment processing
- production authentication
- database persistence
- payment webhooks
- notification systems
- offline policy evaluation against baselines (Random / Always Retry / Default strategy)

## 9. Future Development Phases (indicative, not commitments)

- **Phase 5:** Offline policy evaluation (RevenueShield vs. Random / Always Retry / Default strategy), audit-trail storage, and the incremental-revenue business metric
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
│   │   ├── main.py          # FastAPI app: /health + includes the decision router
│   │   ├── api/
│   │   │   └── routes/
│   │   │       └── decision.py   # Phase 4: POST /api/v1/decision (calls the service layer only)
│   │   ├── models/           # empty — unused so far
│   │   ├── services/
│   │   │   └── decision_service.py  # Phase 4: thin wrapper calling ml/decision_engine.decide()
│   │   ├── schemas/
│   │   │   └── decision.py   # Phase 4: Pydantic request/response models
│   │   └── utils/            # empty — unused so far
│   ├── .env.example
│   └── requirements.txt      # includes -r ../ml/requirements.txt — see Phase 4 section
├── ml/
│   ├── generate_data.py       # Phase 2: synthetic dataset generator
│   ├── validate_data.py       # Phase 2: dataset validation + quality report
│   ├── train_risk_model.py    # Phase 3A: trains the failure-risk model
│   ├── evaluate_risk_model.py # Phase 3A: evaluates it on val/test/cold-start
│   ├── train_action_models.py    # Phase 3B: trains 4 per-action outcome models
│   ├── evaluate_action_models.py # Phase 3B: evaluates each on val/test/cold-start
│   ├── decision_engine.py        # Phase 3C: combines models into a decision + explanation + audit record
│   ├── requirements.txt       # pandas, numpy, scikit-learn, joblib — exact-pinned, no XGBoost/SHAP/etc.
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
│   ├── conftest.py             # makes backend/app importable from project root
│   ├── test_health.py          # Phase 1
│   ├── test_decision_engine.py # Phase 3C
│   └── test_api_decision.py    # Phase 4
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

## 15. Phase 3C — Explainable Decision Engine

### What the decision engine does

`ml/decision_engine.py` combines the Phase 3A risk model and the four
Phase 3B action-outcome models — loaded as-is, never retrained here — to
answer, for one at-risk payment: *which permitted action should be taken,
and why?* For each of the four actions it gets a predicted success
probability from that action's model, converts it to an expected revenue
figure, removes any action the merchant has excluded, picks the highest-
expected-revenue action among what's left, and returns a human-readable
explanation plus a structured audit record. It does not call any external
API, store anything in a database, or expose an HTTP endpoint.

### How expected revenue is calculated

```
expected_revenue[action] = payment_amount × P(success | features, action)
```
computed for all four actions using their respective Phase 3B models, then
the merchant-permitted subset is compared to find the maximum.

### How constraints work

`MerchantConstraints` is a small, deliberately simple dataclass:

- `allowed_actions` — a set of which of the four actions this merchant permits at all (default: all four).
- `max_retry_count` — if set, `retry` is excluded once `previous_retry_count` reaches this value.

There is no equivalent numeric limit for `reminder` — the dataset does not
track a `previous_reminder_count` field (only `previous_retry_count` exists;
see Section 12's field reference), so reminder frequency can only be
controlled coarsely via `allowed_actions` for this MVP. This is a known,
documented limitation, not an oversight.

**`do_nothing` is a guaranteed fallback.** If a merchant configuration would
exclude every action (including, in principle, `do_nothing` itself), the
engine still permits `do_nothing` — it's the one action that can't violate
a friction/cost constraint since it takes no action at all. Verified by
`test_do_nothing_is_the_guaranteed_fallback`.

**Tie-breaking** is deterministic: when two or more permitted actions land
within `TIE_BREAK_EPSILON` (₹0.01) of the highest expected revenue, the
engine picks whichever of the tied actions comes first in
`ACTION_PRIORITY = ["do_nothing", "retry", "reminder", "recovery_link"]` —
ascending order of assumed customer friction, so ties are broken toward the
least intrusive option rather than arbitrarily. Verified by
`test_tie_breaking_is_deterministic`.

### How cold-start is handled

Cold-start features (`previous_payment_count = 0`, etc.) are valid,
in-range input to every model — `0` is a legitimate numeric value and
`"new"` is a category the encoder already saw during training, so nothing
crashes. What changes is the **confidence label**: see below.

### Confidence — an explicit, documented proxy, not a statistical estimate

Phase 3A/3B did not produce calibrated prediction intervals (no ensemble
variance, no Bayesian posterior). Rather than fabricate a number that looks
statistically rigorous but isn't, the engine uses a simple, transparent
heuristic based on `previous_payment_count`:

| `previous_payment_count` | Confidence level |
|---|---|
| 0 | `low` |
| 1–2 | `medium` |
| 3+ | `standard` |

This threshold isn't arbitrary marketing — it's the one thing Phase 3A/3B's
own evaluation actually demonstrated: cold-start ROC-AUC collapsed toward
0.5 across every model (Sections 13–14) specifically because
`previous_payment_count = 0` removes the history-based features those
models lean on most. Every `DecisionResult.confidence` dict includes a
`method` field stating explicitly that this is a heuristic proxy, not a
statistical confidence interval — so nothing downstream can mistake it for
one.

### How explanations are generated

`_build_explanation()` builds the explanation directly from the same
numbers used for selection — it does not free-generate text or call an LLM.
It always names the selected action and its actual expected-revenue and
predicted-probability values, lists the other permitted actions considered
(with their own values), lists any actions a merchant constraint removed
and why, states the pre-action failure risk, and — only when confidence is
`low` or `medium` — appends an explicit low/medium-confidence note. Because
the text is built from the same variables as the decision itself, it cannot
diverge from the numeric outcome by construction; `test_explanation_matches_
selected_action` checks this holds.

### What's stored in the audit record

Every `decide()` call returns a `DecisionResult.audit_record` dict with:

- `transaction_id`, `customer_id` (as passed in, or `None`)
- `predicted_failure_risk` (Phase 3A model output)
- `action_success_probabilities` — all four actions, not just the selected one
- `expected_revenue` — all four actions
- `constraints_applied` — the merchant's `allowed_actions`/`max_retry_count` plus which actions were removed and why
- `permitted_actions` — the post-constraint action list actually compared
- `selected_action`
- `reason` — the full explanation string
- `confidence` — the level/basis/method dict described above
- `causal_disclaimer` — a fixed string restating the limitation below, attached to every single record so it travels with the data rather than living only in documentation

### Limitations of observational action-outcome models

This is worth restating plainly, because it's the single most important
caveat in the whole engine: **`action_success_probabilities` are not causal
treatment effects.** The Phase 3B models are trained on synthetic historical
data where which action a transaction received was itself chosen based on
that transaction's risk level (documented in Section 12). So
`action_model_recovery_link.joblib` predicting an 88% success probability
for a given payment means "payments like this one that historically
received `recovery_link` succeeded about 88% of the time" — not "sending
this specific payment a recovery link would cause an 88% chance of success
instead of whatever else might have been tried." The engine's explanation
text and audit record both say "predicted success probability," never
"causal effect" or "if we had instead," specifically to avoid implying a
claim that Phase 3B's observational models don't support. Correcting for
this (uplift modeling, propensity weighting, or genuine causal inference)
is explicitly out of scope for Phase 3C, per the spec.

### Files

```
ml/decision_engine.py           # public API: decide(), MerchantConstraints, DecisionResult
tests/test_decision_engine.py   # 11 tests covering all 8 required scenarios (+3 extra)
```

### How to run the demo

```powershell
python ml/decision_engine.py
```

### How to run the tests

```powershell
pytest tests/test_decision_engine.py -v
```
or, for the full suite including Phase 1:
```powershell
pytest
```

## 16. Phase 4 — FastAPI Decision API

### What Phase 4 adds

A thin FastAPI layer exposing the existing Phase 3C decision engine over
HTTP: `POST /api/v1/decision`. Nothing about the decision logic itself
changed — Phase 4 is purely an interface around Phase 3C.

### How the API connects to Phase 3C

```
HTTP request
    ↓
app/schemas/decision.py   — Pydantic validates the request
    ↓
app/services/decision_service.py  — builds the features dict + MerchantConstraints,
                                     calls ml.decision_engine.decide() directly
    ↓
ml/decision_engine.py (Phase 3C, UNCHANGED)  — does the actual work
    ↓
app/api/routes/decision.py  — repackages DecisionResult into the response schema
    ↓
HTTP response
```
`decision_service.py` adds `ml/` to `sys.path` and imports `decision_engine`
the same way `tests/test_decision_engine.py` already did — no logic is
duplicated or reimplemented; the API calls the exact same `decide()`
function Phase 3C's own tests call. `test_api_output_matches_direct_
decision_engine_call` in the Phase 4 test suite verifies this directly, by
calling the engine both ways for identical input and asserting the results
match exactly.

### Available endpoints

- `GET /health` — unchanged since Phase 1, still returns `{"status": "ok", "phase": "1"}`
- `GET /docs` — FastAPI's interactive docs, now also showing `/api/v1/decision`
- `POST /api/v1/decision` — the new decision endpoint

### Request format

`DecisionRequest` (see `backend/app/schemas/decision.py`):

| Field | Type | Notes |
|---|---|---|
| `transaction_id` | string, optional | passed through to the response/audit info |
| `customer_id` | string, optional | passed through to the response/audit info |
| `customer_type` | `"new"` \| `"existing"` | required |
| `payment_method` | `"card"` \| `"upi"` \| `"netbanking"` \| `"wallet"` | required |
| `merchant_category` | one of the 6 Phase 2 categories | required |
| `customer_tenure_days` | float ≥ 0 | required |
| `payment_amount` | float > 0 | required |
| `previous_payment_count` | int ≥ 0 | required |
| `previous_success_count` | int ≥ 0 | required |
| `previous_failure_count` | int ≥ 0 | required |
| `previous_retry_count` | int ≥ 0 | required |
| `days_since_last_payment` | float ≥ 0 | required |
| `constraints` | object, optional | see below |

Field names deliberately match `ml.decision_engine.FEATURE_COLUMNS`
exactly, so the service layer passes them through without renaming
anything.

`constraints` (optional, mirrors `MerchantConstraints`):
```json
{
  "allowed_actions": ["do_nothing", "retry", "reminder"],
  "max_retry_count": 3
}
```
Both sub-fields are optional; omit `constraints` entirely for the engine's
default (all four actions permitted, no retry limit).

Beyond type/range checks, the request also rejects logically inconsistent
history — `previous_success_count + previous_failure_count >
previous_payment_count`, or `previous_retry_count > previous_payment_count`
— the same consistency rules Phase 2's `validate_data.py` already enforces
on the training data.

### Response format

`DecisionResponse` — everything the `DecisionResult` from Phase 3C already
produces, reshaped into typed fields: `transaction_id`, `customer_id`,
`selected_action`, `predicted_failure_risk`, `action_success_probabilities`
(all four actions), `expected_revenue` (all four actions),
`permitted_actions`, `constraints_applied`, `explanation`, `confidence`,
and `causal_disclaimer` — the same disclaimer text from the Phase 3C audit
record, restated on every single response so the causal-vs-observational
distinction travels with the data rather than living only in this
document.

### How to start the server

```powershell
cd RevenueShield\backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### How to test the API

```powershell
cd RevenueShield
pytest tests\test_api_decision.py -v
```
or the full suite: `pytest`

### Example API request

```bash
curl -X POST http://127.0.0.1:8000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "T1",
    "customer_id": "C1",
    "customer_type": "existing",
    "payment_method": "card",
    "merchant_category": "saas",
    "customer_tenure_days": 240,
    "payment_amount": 4999,
    "previous_payment_count": 8,
    "previous_success_count": 5,
    "previous_failure_count": 3,
    "previous_retry_count": 2,
    "days_since_last_payment": 31
  }'
```

### Example API response (real, from the actual running server)

```json
{
    "transaction_id": "T1",
    "customer_id": "C1",
    "selected_action": "recovery_link",
    "predicted_failure_risk": 0.2325396291334667,
    "action_success_probabilities": {
        "do_nothing": 0.6409923588751445,
        "retry": 0.7570610820893593,
        "reminder": 0.7982733119504528,
        "recovery_link": 0.8850975511046759
    },
    "expected_revenue": {
        "do_nothing": 3204.320802016847,
        "retry": 3784.548349364707,
        "reminder": 3990.5682864403134,
        "recovery_link": 4424.602657972275
    },
    "permitted_actions": ["do_nothing", "retry", "reminder", "recovery_link"],
    "constraints_applied": {
        "allowed_actions": ["do_nothing", "recovery_link", "reminder", "retry"],
        "max_retry_count": null,
        "removed_by_constraint": {}
    },
    "explanation": "Send recovery link selected because it had the highest expected recovered revenue (Rs 4,424.60) among permitted actions, with a predicted success probability of 88.5%. Other permitted actions considered: Send reminder (Rs 3,990.57, 79.8% predicted success), Retry (Rs 3,784.55, 75.7% predicted success), Do nothing (Rs 3,204.32, 64.1% predicted success). Predicted payment failure risk before any action: 23.3%.",
    "confidence": {
        "level": "standard",
        "basis": "Sufficient payment history available (8 prior payments).",
        "method": "Heuristic proxy based on previous_payment_count \u2014 NOT a statistically derived confidence interval. See README.md's Phase 3C section for why."
    },
    "causal_disclaimer": "action_success_probabilities are observational predictions P(success | features, action was taken), estimated from synthetic historical data where action assignment was itself risk-biased. They are NOT validated causal treatment effects."
}
```

### Important limitations

- No database — nothing persists between requests; the audit record is
  returned in the response, not stored anywhere.
- No authentication — this API has no access control and should not be
  exposed publicly as-is.
- No Razorpay integration, no real payment processing, no webhooks.
- No frontend — this is an API only, tested via `curl`/`pytest`/`/docs`.
- Same causal-interpretation limitation as Phase 3B/3C: `action_success_
  probabilities` are observational predictions, not validated causal
  treatment effects — see the `causal_disclaimer` field on every response
  and Section 14's "Limitations of observational action-outcome models".
- `backend/requirements.txt` now includes `ml/requirements.txt` via a `-r`
  reference (rather than duplicating the pins) because the API needs
  pandas/numpy/scikit-learn/joblib to load the Phase 3A/3B models — this is
  a wiring change, not a new dependency.
