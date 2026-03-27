from __future__ import annotations

import os
import time

import pytest

from .conftest import auth_header, http_request, require_url


pytestmark = [pytest.mark.integration, pytest.mark.destructive]


@pytest.mark.skipif(
    os.environ.get("LV3_ENABLE_FAILOVER_TEST") != "1",
    reason="Destructive failover test requires LV3_ENABLE_FAILOVER_TEST=1",
)
def test_postgres_failover_services_recover(
    integration_config,
    keycloak_token: str,
    proxmox_agent_exec,
) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for failover checks",
    )
    primary_vmid = int(os.environ.get("LV3_POSTGRES_PRIMARY_VMID", "150"))
    proxmox_agent_exec(primary_vmid, "systemctl", "stop", "postgresql")
    time.sleep(35)

    for service_id in ("keycloak", "windmill", "netbox", "mattermost"):
        response = http_request(
            "GET",
            f"{gateway_url}/v1/platform/health/{service_id}",
            headers=auth_header(keycloak_token),
            verify=integration_config.verify_tls,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "healthy"

    proxmox_agent_exec(primary_vmid, "systemctl", "start", "postgresql")
