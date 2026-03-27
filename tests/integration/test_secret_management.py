from __future__ import annotations

import os

import pytest

from .conftest import auth_header, http_request, poll_job, require_url


pytestmark = [pytest.mark.integration, pytest.mark.mutation]


def test_secret_rotation_leaves_service_healthy(keycloak_token: str, integration_config) -> None:
    if os.environ.get("LV3_RUN_SECRET_ROTATION_TEST") != "1":
        pytest.skip("Set LV3_RUN_SECRET_ROTATION_TEST=1 to run the mutation rotation test")

    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for secret-rotation checks",
    )
    response = http_request(
        "POST",
        f"{gateway_url}/v1/platform/secrets/rotate",
        headers=auth_header(keycloak_token),
        json_body={"service": "netbox"},
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    result = poll_job(integration_config, keycloak_token, job_id, timeout_seconds=180)
    assert result["state"] in {"complete", "completed"}, result

    health = http_request(
        "GET",
        f"{gateway_url}/v1/platform/health/netbox",
        headers=auth_header(keycloak_token),
        verify=integration_config.verify_tls,
    )
    assert health.status_code == 200, health.text
    assert health.json()["status"] == "healthy"
