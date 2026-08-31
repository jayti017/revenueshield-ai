"""
RevenueShield AI — backend entrypoint.

Phase 1 proved Python + virtual environment + FastAPI + Uvicorn + basic
testing work correctly together. Phase 4 adds the decision API
(POST /api/v1/decision), which is a thin interface around the EXISTING
Phase 3C decision engine — no decision logic lives in this file or in the
route/service layer it wires in. See README.md for the full phase-by-phase
history and what is/isn't built yet.
"""

from fastapi import FastAPI

from app.api.routes.decision import router as decision_router

app = FastAPI(
    title="RevenueShield AI",
    description="Explainable Revenue Recovery Decision Engine — backend",
    version="0.4.0",
)

app.include_router(decision_router)


@app.get("/health")
def health_check():
    """Confirms the backend process is running. Unchanged since Phase 1 —
    kept backward compatible on purpose.
    """
    return {"status": "ok", "phase": "1"}
