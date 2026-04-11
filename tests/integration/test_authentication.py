from __future__ import annotations

import os

import pytest

from .conftest import REALM, auth_header, decode_jwt, http_request, require_url


pytestmark = pytest.mark.integration


def test_keycloak_issues_valid_jwt(keycloak_token: str, integration_config) -> None:
    claims = decode_jwt(keycloak_token)
    assert claims["iss"] == integration_config.expected_issuer
    roles = claims.get("realm_access", {}).get("roles", [])
    assert any(role in roles for role in ("platform-read", "platform-operator"))


def test_api_gateway_accepts_keycloak_jwt(keycloak_token: str, integration_config) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for API-gateway checks",
    )
    response = http_request(
        "GET",
        f"{gateway_url}/v1/platform/health",
        headers=auth_header(keycloak_token),
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] in {"healthy", "degraded"}


def test_grafana_sso_login(grafana_bearer_token: str, integration_config) -> None:
    grafana_url = require_url(
        integration_config.grafana_url,
        "Grafana URL is not configured for this environment",
    )
    response = http_request(
        "GET",
        f"{grafana_url}/api/user",
        headers=auth_header(grafana_bearer_token),
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("login") or payload.get("email")


def test_keycloak_openid_configuration_matches_realm(integration_config) -> None:
    if (
        not integration_config.preissued_bearer_token
        and not (integration_config.keycloak_username and integration_config.keycloak_password)
        and os.environ.get("LV3_ALLOW_PUBLIC_DISCOVERY_CHECKS") != "1"
    ):
        pytest.skip("Set LV3_ALLOW_PUBLIC_DISCOVERY_CHECKS=1 or provide test-runner credentials to probe discovery")
    keycloak_url = require_url(
        integration_config.keycloak_url,
        "Keycloak URL is not configured for this environment",
    )
    response = http_request(
        "GET",
        f"{keycloak_url}/realms/{REALM}/.well-known/openid-configuration",
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["issuer"] == integration_config.expected_issuer
