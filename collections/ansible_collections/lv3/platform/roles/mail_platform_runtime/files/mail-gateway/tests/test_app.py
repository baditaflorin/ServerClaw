import json
import os
from tempfile import NamedTemporaryFile

from fastapi.testclient import TestClient

os.environ.setdefault("BREVO_API_KEY", "test-brevo-key")
os.environ.setdefault("DEFAULT_FROM_EMAIL", "server@example.com")
os.environ.setdefault("GATEWAY_API_KEY", "test-gateway-key")
os.environ.setdefault("STALWART_ADMIN_PASSWORD", "test-admin-password")
with NamedTemporaryFile("w", encoding="utf-8", delete=False) as profiles_file:
    json.dump(
        [
            {
                "id": "platform-transactional",
                "mailbox_localpart": "platform",
                "mailbox_address": "platform@example.com",
                "sender_email": "platform@example.com",
                "sender_name": "LV3 Platform",
                "reply_to": "server@example.com",
                "description": "Test sender",
                "owner": "Tests",
                "credential_scope": "Scoped test profile.",
                "rate_expectation": "Low volume.",
                "retention_policy": "Keep short-lived test data only.",
                "observability_policy": "Track test calls.",
                "gateway_api_key": "test-profile-key",
            }
        ],
        profiles_file,
    )
    os.environ.setdefault("NOTIFICATION_PROFILES_FILE", profiles_file.name)

from app import app
from telemetry import parse_resource_attributes


def test_healthz_reports_ok():
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_state_requires_api_key():
    client = TestClient(app)

    response = client.get("/state")

    assert response.status_code == 401


def test_parse_resource_attributes_ignores_invalid_items():
    parsed = parse_resource_attributes(
        "deployment.environment=lv3, service.namespace=lv3, invalid, empty=, =missing-key"
    )

    assert parsed == {
        "deployment.environment": "lv3",
        "service.namespace": "lv3",
    }
