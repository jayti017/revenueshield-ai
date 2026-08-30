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

**Phase 1 — Project Foundation.**

Phase 1's only objective is a clean, organized project structure and a
minimal backend application that runs successfully, proving Python + virtual
environment + FastAPI + Uvicorn + basic testing all work correctly before any
complexity is added.

**The following are explicitly NOT implemented yet:**

- synthetic dataset
- ML models
- risk prediction
- action prediction
- decision engine
- explainability
- audit system
- frontend
- Razorpay integration

## 9. Future Development Phases (indicative, not commitments)

- **Phase 2:** Synthetic dataset generation and schema
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
│   ├── data/
│   │   ├── raw/               # empty — synthetic data lands here later
│   │   └── processed/         # empty — later
│   └── models/                # empty — trained model artifacts land here later
├── frontend/                  # empty — not built yet
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # makes backend/app importable from project root
│   └── test_health.py
├── docs/
├── .gitignore
└── README.md
```
