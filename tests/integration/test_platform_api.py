from __future__ import annotations

import pytest

from .conftest import auth_header, http_request, require_url


pytestmark = pytest.mark.integration


def test_gateway_public_healthz_and_openapi_are_available(integration_config) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for platform API checks",
    )
    health_response = http_request(
        "GET",
        f"{gateway_url}/healthz",
        verify=integration_config.verify_tls,
    )
    assert health_response.status_code == 200, health_response.text
    assert health_response.json()["status"] == "ok"

    openapi_response = http_request(
        "GET",
        f"{gateway_url}/openapi.json",
        verify=integration_config.verify_tls,
    )
    assert openapi_response.status_code == 200, openapi_response.text
    assert str(openapi_response.json().get("openapi", "")).startswith("3.")


def test_service_catalog_returns_expected_services(keycloak_token: str, integration_config, catalog_services) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for platform API checks",
    )
    response = http_request(
        "GET",
        f"{gateway_url}/v1/platform/services",
        headers=auth_header(keycloak_token),
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    services = response.json().get("services", [])
    returned = {item["id"] for item in services}
    expected = set(integration_config.required_service_ids)
    assert expected.issubset(returned)
    assert returned.intersection(catalog_services)


def test_drift_endpoint_returns_structured_report(keycloak_token: str, integration_config) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for platform API checks",
    )
    response = http_request(
        "GET",
        f"{gateway_url}/v1/platform/drift",
        headers=auth_header(keycloak_token),
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "detected_at" in payload
    assert payload["overall"] in {"clean", "warn", "critical"}


def test_health_endpoint_reports_service_states(keycloak_token: str, integration_config) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for platform API checks",
    )
    response = http_request(
        "GET",
        f"{gateway_url}/v1/platform/health",
        headers=auth_header(keycloak_token),
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    for service in payload.get("services", []):
        assert service["status"] in {"healthy", "degraded", "down"}


def test_dependency_graph_endpoint_returns_graph_when_available(keycloak_token: str, integration_config) -> None:
    gateway_url = require_url(
        integration_config.gateway_url,
        "LV3_INTEGRATION_GATEWAY_URL is required for platform API checks",
    )
    response = http_request(
        "GET",
        f"{gateway_url}/v1/platform/dependencies",
        headers=auth_header(keycloak_token),
        verify=integration_config.verify_tls,
    )
    if response.status_code == 404:
        pytest.skip("Dependency graph endpoint is not live yet")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload.get("nodes"), list)
    assert isinstance(payload.get("edges"), list)
