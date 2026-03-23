from __future__ import annotations

import pytest

from .conftest import auth_header, http_request, poll_job, require_url


pytestmark = pytest.mark.integration


def test_deployment_trigger_runs_in_check_mode(keycloak_token: str, integration_config) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for deployment checks",
    )
    response = http_request(
        "POST",
        f"{gateway_url}/v1/platform/deploy",
        headers=auth_header(keycloak_token),
        json_body={"service": "uptime-kuma", "check_mode": True},
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    result = poll_job(integration_config, keycloak_token, job_id, timeout_seconds=180)
    assert result["state"] in {"complete", "completed"}, result
    changed_count = result.get("changed_count")
    if changed_count is not None:
        assert changed_count == 0
