"""
RevenueShield AI — backend entrypoint.

Phase 1 proved Python + virtual environment + FastAPI + Uvicorn + basic
testing work correctly together. Phase 4 added the decision API
(POST /api/v1/decision), a thin interface around the EXISTING Phase 3C
decision engine. Phase 5 adds audit-trail persistence and two read-only
endpoints (GET /api/v1/decisions, GET /api/v1/decisions/{transaction_id})
for retrieving past decisions — no decision logic lives in this file or in
any route/service layer it wires in. See README.md for the full
phase-by-phase history and what is/isn't built yet.
"""

from fastapi import FastAPI

from app.api.routes.audit import router as audit_router
from app.api.routes.decision import router as decision_router

app = FastAPI(
    title="RevenueShield AI",
    description="Explainable Revenue Recovery Decision Engine — backend",
    version="0.5.0",
)

app.include_router(decision_router)
app.include_router(audit_router)


@app.get("/health")
def health_check():
    """Confirms the backend process is running. Unchanged since Phase 1 —
    kept backward compatible on purpose.
    """
    return {"status": "ok", "phase": "1"}
