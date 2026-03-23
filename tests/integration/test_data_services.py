from __future__ import annotations

import urllib.parse

import pytest

from .conftest import http_request, maybe_import_psycopg2, parse_postgres_dsn, require_url, tcp_connects


pytestmark = pytest.mark.integration


def test_postgres_vip_accepts_sql_connections(integration_config) -> None:
    dsn = integration_config.postgres_dsn
    if not dsn:
        pytest.skip("Postgres DSN is not configured for this environment")
    parsed = urllib.parse.urlparse(dsn)
    if not parsed.password:
        pytest.skip("Postgres SQL checks require a DSN with credentials")
    psycopg2 = maybe_import_psycopg2()
    host, port = parse_postgres_dsn(dsn)
    tcp_connects(host, port)
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)


def test_netbox_status_endpoint_reports_ok(integration_config) -> None:
    netbox_url = require_url(
        integration_config.netbox_url,
        "NetBox URL is not configured for this environment",
    )
    if not integration_config.netbox_api_token:
        pytest.skip("LV3_NETBOX_TOKEN is required for NetBox status checks")
    response = http_request(
        "GET",
        f"{netbox_url}/api/status/",
        headers={"Authorization": f"Token {integration_config.netbox_api_token}"},
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "netbox-version" in payload


def test_netbox_returns_virtual_machine_data(integration_config) -> None:
    netbox_url = require_url(
        integration_config.netbox_url,
        "NetBox URL is not configured for this environment",
    )
    if not integration_config.netbox_api_token:
        pytest.skip("LV3_NETBOX_TOKEN is required for NetBox API queries")
    response = http_request(
        "GET",
        f"{netbox_url}/api/virtualization/virtual-machines/?limit=1",
        headers={"Authorization": f"Token {integration_config.netbox_api_token}"},
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "results" in payload
