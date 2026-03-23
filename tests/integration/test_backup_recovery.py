from __future__ import annotations

import os

import pytest

from .conftest import auth_header, http_request, poll_job, require_url


pytestmark = [pytest.mark.integration, pytest.mark.destructive]


@pytest.mark.skipif(
    os.environ.get("LV3_ENABLE_BACKUP_RECOVERY_TEST") != "1",
    reason="Destructive restore-verification test requires LV3_ENABLE_BACKUP_RECOVERY_TEST=1",
)
def test_backup_restore_verification_job_completes(keycloak_token: str, integration_config) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for backup-recovery checks",
    )
    response = http_request(
        "POST",
        f"{gateway_url}/v1/platform/backups/restore-verification",
        headers=auth_header(keycloak_token),
        json_body={"scope": "weekly"},
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]

    result = poll_job(integration_config, keycloak_token, job_id, timeout_seconds=1800, interval_seconds=15)
    assert result["state"] in {"complete", "completed"}, result
