from __future__ import annotations

import json
from typing import Any

import glitchtip_event
import glitchtip_event_smoke


class FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_parse_dsn_extracts_store_coordinates() -> None:
    parsed = glitchtip_event.parse_dsn("https://public@example.com/7")

    assert parsed is not None
    assert parsed.scheme == "https"
    assert parsed.hostport == "example.com"
    assert parsed.project_id == "7"
    assert parsed.public_key == "public"
    assert parsed.path_prefix == ""
    assert glitchtip_event.build_store_url(parsed) == "https://example.com/api/7/store/"


def test_emit_glitchtip_event_posts_raw_json_to_webhook(monkeypatch) -> None:
    observed: dict[str, Any] = {}

    def fake_urlopen(request, timeout=0):
        observed["url"] = request.full_url
        observed["headers"] = dict(request.header_items())
        observed["body"] = json.loads(request.data.decode("utf-8"))
        observed["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(glitchtip_event.urllib.request, "urlopen", fake_urlopen)

    payload = {"message": "plain webhook event", "event_id": "evt-123"}
    result = glitchtip_event.emit_glitchtip_event("https://hooks.example.invalid/glitchtip", payload, timeout=7)

    assert result == {"target_kind": "webhook", "event_id": "evt-123"}
    assert observed["url"] == "https://hooks.example.invalid/glitchtip"
    assert observed["body"] == payload
    assert observed["headers"]["Content-type"] == "application/json"
    assert observed["timeout"] == 7


def test_emit_glitchtip_event_posts_sentry_store_payload_for_dsn(monkeypatch) -> None:
    observed: dict[str, Any] = {}

    def fake_urlopen(request, timeout=0):
        observed["url"] = request.full_url
        observed["headers"] = dict(request.header_items())
        observed["body"] = json.loads(request.data.decode("utf-8"))
        observed["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(glitchtip_event.urllib.request, "urlopen", fake_urlopen)

    payload = {
        "message": "glitchtip dsn event",
        "level": "error",
        "environment": "production",
        "tags": {"component": "mail-platform", "release": "0.177.101"},
        "fingerprint": "mail-platform:smoke",
    }
    result = glitchtip_event.emit_glitchtip_event("https://public@example.com/7", payload, timeout=11)

    assert result["target_kind"] == "dsn"
    assert len(result["event_id"]) == 32
    assert observed["url"] == "https://example.com/api/7/store/"
    assert observed["headers"]["Content-type"] == "application/json"
    assert observed["headers"]["X-sentry-auth"].startswith("Sentry sentry_version=7")
    assert observed["body"]["message"] == "glitchtip dsn event"
    assert observed["body"]["environment"] == "production"
    assert observed["body"]["release"] == "0.177.101"
    assert observed["body"]["fingerprint"] == ["mail-platform:smoke"]
    assert observed["timeout"] == 11


def test_glitchtip_event_smoke_extract_issue_list_supports_list_and_paginated_payloads() -> None:
    issue = {"id": "123", "title": "Example"}

    assert glitchtip_event_smoke.extract_issue_list([issue, "skip"]) == [issue]
    assert glitchtip_event_smoke.extract_issue_list({"results": [issue, "skip"]}) == [issue]
    assert glitchtip_event_smoke.extract_issue_list({"unexpected": []}) == []
