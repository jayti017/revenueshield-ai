"""
RevenueShield AI — backend entrypoint.

Phase 1 scope only: this file exists to prove that Python + virtual
environment + FastAPI + Uvicorn + basic testing work correctly together.

Nothing else is implemented here yet. No decision engine, no ML models, no
database logic, no Razorpay integration. See README.md for the full list of
what is and isn't built yet.
"""

from fastapi import FastAPI

app = FastAPI(
    title="RevenueShield AI",
    description="Explainable Revenue Recovery Decision Engine — backend (Phase 1 foundation)",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """Confirms the backend process is running. Nothing else exists yet."""
    return {"status": "ok", "phase": "1"}
