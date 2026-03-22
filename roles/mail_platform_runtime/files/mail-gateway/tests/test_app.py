import os

from fastapi.testclient import TestClient

os.environ.setdefault("BREVO_API_KEY", "test-brevo-key")
os.environ.setdefault("DEFAULT_FROM_EMAIL", "server@lv3.org")
os.environ.setdefault("GATEWAY_API_KEY", "test-gateway-key")
os.environ.setdefault("STALWART_ADMIN_PASSWORD", "test-admin-password")

from app import app


def test_healthz_reports_ok():
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_state_requires_api_key():
    client = TestClient(app)

    response = client.get("/state")

    assert response.status_code == 401
