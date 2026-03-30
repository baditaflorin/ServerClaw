from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from platform.events import build_envelope, load_topic_index  # noqa: E402
import validate_nats_topics  # noqa: E402


def test_topic_index_contains_active_canonical_subjects() -> None:
    topics = load_topic_index()
    assert topics["platform.findings.observation"]["status"] == "active"
    assert topics["platform.maintenance.opened"]["status"] == "active"
    assert topics["platform.mutation.recorded"]["status"] == "active"
    assert topics["platform.slo.k6_regression"]["status"] == "active"
    assert topics["platform.config.merged"]["status"] == "active"
    assert topics["platform.security.pgaudit_unknown_role"]["status"] == "active"
    assert topics["platform.intent.compiled"]["status"] == "reserved"


def test_build_envelope_wraps_payload_with_shared_fields() -> None:
    envelope = build_envelope(
        "platform.findings.observation",
        {
            "check": "check-vm-state",
            "severity": "ok",
            "summary": "All guests are healthy.",
            "details": [],
            "ts": "2026-03-24T20:00:00Z",
            "run_id": "run-123",
        },
        actor_id="agent/observation-loop",
    )

    assert envelope["topic"] == "platform.findings.observation"
    assert envelope["schema_ver"] == "1.0"
    assert envelope["actor_id"] == "agent/observation-loop"
    assert envelope["payload"]["check"] == "check-vm-state"


def test_build_envelope_rejects_missing_required_payload_keys() -> None:
    try:
        build_envelope(
            "platform.maintenance.opened",
            {
                "window": {"service_id": "grafana"},
                "key": "maintenance/grafana",
            },
        )
    except ValueError as exc:
        assert "missing required keys" in str(exc)
    else:  # pragma: no cover - defensive assertion style
        raise AssertionError("expected build_envelope to reject incomplete payload")


def test_validate_nats_topics_covers_active_topic_routing() -> None:
    result = validate_nats_topics.validate_topic_usage()
    assert result["unknown_topics"] == []
    assert result["uncovered_topics"] == []


def test_validate_nats_topics_ignores_private_ntfy_topics() -> None:
    result = validate_nats_topics.validate_topic_usage()
    assert "scripts/falco_event_bridge_server.py: platform.security.critical" not in result["unknown_topics"]


def test_build_envelope_supports_config_merge_topics() -> None:
    envelope = build_envelope(
        "platform.config.merge_conflict",
        {
            "change_id": "c-123",
            "file_path": "config/service-capability-catalog.json",
            "key_value": "grafana",
            "operation": "append",
            "status": "conflict",
            "reason": "duplicate_key",
        },
        actor_id="agent/config-merge-job",
    )

    assert envelope["topic"] == "platform.config.merge_conflict"
    assert envelope["payload"]["reason"] == "duplicate_key"


def test_build_envelope_supports_cve_delta_topics() -> None:
    envelope = build_envelope(
        "platform.security.cve_delta",
        {
            "event": "platform.security.cve_delta",
            "generated_at": "2026-03-30T15:29:34Z",
            "image_id": "step_ca_runtime",
            "image_ref": "docker.io/smallstep/step-ca:latest",
            "runtime_host": "docker-runtime-lv3",
            "finding": {
                "id": "CVE-2026-0001",
                "severity": "critical",
            },
        },
        actor_id="agent/sbom-refresh",
    )

    assert envelope["topic"] == "platform.security.cve_delta"
    assert envelope["actor_id"] == "agent/sbom-refresh"
    assert envelope["payload"]["image_id"] == "step_ca_runtime"
