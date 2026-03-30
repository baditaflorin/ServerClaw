from __future__ import annotations

import sys
import urllib.error
from email.message import Message
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from falco_event_bridge import (  # noqa: E402
    BridgeConfig,
    bridge_event,
    build_mutation_audit_event,
    build_security_payload,
    normalize_priority,
    publish_ntfy_message,
    priority_at_least,
)


def test_normalize_priority_collapses_known_falco_values() -> None:
    assert normalize_priority("warning") == "WARNING"
    assert normalize_priority("informational") == "INFO"
    assert normalize_priority("bogus") == "INFO"


def test_priority_thresholds_match_warning_and_critical_routing() -> None:
    assert priority_at_least("warning", "warning") is True
    assert priority_at_least("critical", "warning") is True
    assert priority_at_least("notice", "warning") is False
    assert priority_at_least("critical", "critical") is True
    assert priority_at_least("error", "critical") is False


def test_build_security_payload_preserves_required_taxonomy_keys() -> None:
    event = {
        "priority": "Warning",
        "rule": "Test Rule",
        "time": "2026-03-30T12:00:00Z",
        "output": "something happened",
        "output_fields": {"evt.hostname": "docker-build-lv3"},
        "tags": ["lv3", "test"],
    }

    payload = build_security_payload(event, topic="platform.security.falco", source_host="docker-build-lv3")

    assert payload["event"] == "platform.security.falco"
    assert payload["host"] == "docker-build-lv3"
    assert payload["rule"] == "Test Rule"
    assert payload["priority"] == "WARNING"
    assert payload["time"] == "2026-03-30T12:00:00Z"
    assert payload["source"] == "falco"


def test_build_mutation_audit_event_uses_falco_surface() -> None:
    audit_event = build_mutation_audit_event(
        {"rule": "LV3 Falco smoke marker execution"},
        actor_id="falco-event-bridge",
        source_host="monitoring-lv3",
        correlation_id="falco:monitoring-lv3:smoke",
    )

    assert audit_event["actor"]["class"] == "service"
    assert audit_event["actor"]["id"] == "falco-event-bridge"
    assert audit_event["surface"] == "falco"
    assert audit_event["action"] == "security_anomaly_detected"
    assert audit_event["target"] == "monitoring-lv3:LV3 Falco smoke marker execution"


def test_bridge_config_requires_explicit_private_outputs() -> None:
    config = BridgeConfig(
        actor_id="falco-event-bridge",
        source_host="docker-runtime-lv3",
        event_topic="platform.security.falco",
        nats_subject="platform.security.falco",
        nats_host="127.0.0.1",
        nats_port=4222,
        nats_username="jetstream-admin",
        nats_password="secret",
        ntfy_base_url="http://127.0.0.1:2586",
        ntfy_topic="platform-security-critical",
        ntfy_username="alertmanager",
        ntfy_password="secret",
        mutation_audit_file="/var/log/platform/mutation-audit.jsonl",
    )

    assert config.nats_subject == "platform.security.falco"
    assert config.ntfy_topic == "platform-security-critical"


def test_publish_ntfy_message_retries_retryable_http_errors(monkeypatch) -> None:
    config = BridgeConfig(
        actor_id="falco-event-bridge",
        source_host="docker-runtime-lv3",
        event_topic="platform.security.falco",
        nats_subject="platform.security.falco",
        nats_host="127.0.0.1",
        nats_port=4222,
        nats_username="jetstream-admin",
        nats_password="secret",
        ntfy_base_url="http://127.0.0.1:2586",
        ntfy_topic="platform-security-critical",
        ntfy_username="alertmanager",
        ntfy_password="secret",
        mutation_audit_file="/var/log/platform/mutation-audit.jsonl",
        http_timeout_seconds=1.0,
    )
    event = {
        "priority": "Critical",
        "rule": "LV3 Falco smoke marker execution",
        "output": "LV3 Falco smoke marker executed",
    }
    attempts = {"count": 0}
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        attempts["count"] += 1
        if attempts["count"] == 1:
            headers = Message()
            headers["Retry-After"] = "0"
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                headers,
                None,
            )

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        return Response()

    monkeypatch.setattr("falco_event_bridge.time.sleep", fake_sleep)
    monkeypatch.setattr("falco_event_bridge.urllib.request.urlopen", fake_urlopen)

    publish_ntfy_message(event=event, source_host="docker-runtime-lv3", config=config)

    assert attempts["count"] == 2
    assert slept == [1.0]


def test_bridge_event_keeps_core_actions_when_ntfy_delivery_degrades(monkeypatch, tmp_path: Path) -> None:
    config = BridgeConfig(
        actor_id="falco-event-bridge",
        source_host="docker-runtime-lv3",
        event_topic="platform.security.falco",
        nats_subject="platform.security.falco",
        nats_host="127.0.0.1",
        nats_port=4222,
        nats_username="jetstream-admin",
        nats_password="secret",
        ntfy_base_url="http://127.0.0.1:2586",
        ntfy_topic="platform-security-critical",
        ntfy_username="alertmanager",
        ntfy_password="secret",
        mutation_audit_file=str(tmp_path / "mutation-audit.jsonl"),
    )
    event = {
        "priority": "Critical",
        "rule": "LV3 Falco smoke marker execution",
        "time": "2026-03-30T12:00:00Z",
        "output": "LV3 Falco smoke marker executed (host=docker-build-lv3)",
        "output_fields": {"evt.hostname": "docker-build-lv3"},
        "tags": ["lv3", "smoke"],
    }
    published: list[dict[str, object]] = []
    audited: list[dict[str, object]] = []

    def fake_publish_nats_message(*, subject, payload, config):  # type: ignore[no-untyped-def]
        published.append({"subject": subject, "payload": payload})

    def fake_append_jsonl(path, event):  # type: ignore[no-untyped-def]
        audited.append({"path": path, "event": event})

    def fake_publish_ntfy_message(*, event, source_host, config):  # type: ignore[no-untyped-def]
        raise RuntimeError("ntfy publish failed: HTTP Error 429: Too Many Requests")

    monkeypatch.setattr("falco_event_bridge.publish_nats_message", fake_publish_nats_message)
    monkeypatch.setattr("falco_event_bridge.append_jsonl", fake_append_jsonl)
    monkeypatch.setattr("falco_event_bridge.publish_ntfy_message", fake_publish_ntfy_message)

    actions = bridge_event(event, config=config)

    assert actions == ["nats", "mutation_audit", "ntfy_degraded"]
    assert len(published) == 1
    assert published[0]["subject"] == "platform.security.falco"
    assert len(audited) == 1
    assert audited[0]["path"] == str(tmp_path / "mutation-audit.jsonl")
