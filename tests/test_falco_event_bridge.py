from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from falco_event_bridge import (  # noqa: E402
    BridgeConfig,
    build_mutation_audit_event,
    build_security_payload,
    normalize_priority,
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
