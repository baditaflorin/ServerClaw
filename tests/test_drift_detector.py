from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import drift_detector as detector  # noqa: E402


def test_build_summary_counts_unsuppressed_records() -> None:
    summary = detector.build_summary(
        [
            {"severity": "warn", "source": "dns", "workstream_suppressed": False},
            {"severity": "critical", "source": "tls", "workstream_suppressed": True},
        ]
    )

    assert summary["warn_count"] == 1
    assert summary["critical_count"] == 1
    assert summary["unsuppressed_count"] == 1
    assert summary["status"] == "warn"


def test_enrich_records_escalates_unhealthy_service_and_marks_suppression(monkeypatch) -> None:
    monkeypatch.setattr(detector, "backoff_health", lambda service_id, service_map, health_probes: False)
    monkeypatch.setattr(detector, "workstream_suppression", lambda shared_surfaces: (True, ["adr-0091"]))

    records = detector.enrich_records(
        [
            {
                "source": "docker-image",
                "service": "windmill",
                "resource": "windmill-server",
                "severity": "warn",
                "event": "platform.drift.warn",
                "detail": "digest mismatch",
                "shared_surfaces": ["windmill"],
            }
        ],
        service_map={"windmill": {"id": "windmill"}},
        health_probes={},
    )

    assert records[0]["severity"] == "critical"
    assert records[0]["workstream_suppressed"] is True
    assert records[0]["suppressed_by"] == ["adr-0091"]
