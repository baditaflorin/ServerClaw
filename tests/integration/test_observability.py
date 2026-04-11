from __future__ import annotations

import time
import urllib.parse
import uuid

import pytest

from .conftest import auth_header, http_request, require_url


pytestmark = pytest.mark.integration


def test_loki_query_returns_success(integration_config) -> None:
    loki_query_url = require_url(
        integration_config.loki_query_url,
        "LV3_INTEGRATION_LOKI_QUERY_URL is required for Loki integration checks",
    )
    query_url = f"{loki_query_url}?{urllib.parse.urlencode({'query': '{service=~".+"}', 'limit': 1})}"
    response = http_request(
        "GET",
        query_url,
        headers=auth_header(integration_config.grafana_api_token) if integration_config.grafana_api_token else None,
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("status") == "success"


def test_tempo_accepts_trace_ingest_when_configured(integration_config) -> None:
    tempo_push_url = require_url(
        integration_config.tempo_push_url,
        "LV3_INTEGRATION_TEMPO_PUSH_URL is required for Tempo integration checks",
    )
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    response = http_request(
        "POST",
        tempo_push_url,
        json_body=[
            {
                "traceId": trace_id,
                "id": span_id,
                "name": "adr-0111-nightly-smoke",
                "timestamp": int(time.time() * 1_000_000),
                "duration": 1_000,
                "localEndpoint": {"serviceName": "integration-suite"},
            }
        ],
        verify=integration_config.verify_tls,
    )
    assert response.status_code in {200, 202, 204}, response.text


def test_grafana_lists_expected_datasources(integration_config) -> None:
    grafana_url = require_url(
        integration_config.grafana_url,
        "Grafana URL is not configured for this environment",
    )
    if not integration_config.grafana_api_token:
        pytest.skip("LV3_GRAFANA_TOKEN is required for Grafana datasource checks")
    response = http_request(
        "GET",
        f"{grafana_url}/api/datasources",
        headers=auth_header(integration_config.grafana_api_token),
        verify=integration_config.verify_tls,
    )
    assert response.status_code == 200, response.text
    names = {item["type"] for item in response.json()}
    assert names.intersection({"loki", "tempo", "influxdb", "prometheus"})
