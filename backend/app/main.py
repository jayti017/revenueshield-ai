"""
RevenueShield AI — FastAPI application entrypoint.

Phases 4/5/7 provide the decision, audit, and safety endpoints.
Phase 8 adds the Razorpay TEST-MODE payment integration.
"""

from fastapi import FastAPI

from app.api.routes.audit import router as audit_router
from app.api.routes.decision import router as decision_router
from app.api.routes.payments import router as payments_router
from app.api.routes.webhooks import router as webhook_router

app = FastAPI(
    title="RevenueShield AI",
    description="Explainable Revenue Recovery Decision Engine — backend",
    version="0.8.0",
)

app.include_router(decision_router)
app.include_router(audit_router)
app.include_router(payments_router)
app.include_router(webhook_router)


@app.get("/health")
def health_check():
    """Confirms the backend process is running."""
    return {"status": "ok", "phase": "1"}
