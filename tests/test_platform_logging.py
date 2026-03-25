from __future__ import annotations

import io
import json

from platform.logging import bind_context, clear_context, get_logger


def test_platform_logger_emits_required_contract_fields() -> None:
    stream = io.StringIO()
    logger = get_logger("api_gateway", "http", name="test.platform.logging.required", stream=stream)

    with bind_context(trace_id="trace-123", actor_id="ops", workflow_id="converge-api-gateway"):
        logger.info("request completed", extra={"duration_ms": 12.4, "target": "/v1/health"})

    payload = json.loads(stream.getvalue().strip())
    assert payload["service_id"] == "api_gateway"
    assert payload["component"] == "http"
    assert payload["trace_id"] == "trace-123"
    assert payload["msg"] == "request completed"
    assert payload["actor_id"] == "ops"
    assert payload["workflow_id"] == "converge-api-gateway"
    assert payload["duration_ms"] == 12.4
    assert payload["target"] == "/v1/health"
    assert payload["level"] == "INFO"
    assert payload["vm"]


def test_platform_logger_defaults_background_trace_id() -> None:
    clear_context()
    stream = io.StringIO()
    logger = get_logger("platform_context_api", "service", name="test.platform.logging.background", stream=stream)

    logger.info("service started")

    payload = json.loads(stream.getvalue().strip())
    assert payload["trace_id"] == "background"
    assert payload["service_id"] == "platform_context_api"
