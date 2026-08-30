"""
Phase 1's only test: confirms the backend is up and reporting the correct
phase. No other functionality exists yet, so no other tests belong here.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_returns_ok_and_phase_1():
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["phase"] == "1"
