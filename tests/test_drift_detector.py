from __future__ import annotations

import json
import subprocess
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


def test_run_tofu_drift_reads_namespaced_plan_json(monkeypatch, tmp_path: Path) -> None:
    captured_env: dict[str, str] = {}
    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        if "env" not in kwargs:
            return real_run(*args, **kwargs)
        del args
        captured_env.update(kwargs["env"])
        plan_dir = Path(kwargs["env"]["LV3_RUN_TOFU_DIR"])
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "production.plan.json").write_text(
            json.dumps(
                {
                    "resource_changes": [
                        {
                            "address": "module.nginx_lv3",
                            "change": {"actions": ["update"], "before": {"vmid": 110}, "after": {"vmid": 110}},
                        }
                    ]
                }
            )
        )
        return subprocess.CompletedProcess(["/bin/bash", "-lc", "noop"], 0, stdout="", stderr="")

    monkeypatch.setattr(detector.subprocess, "run", fake_run)
    monkeypatch.setenv("LV3_SESSION_ID", "drift-test")
    monkeypatch.setattr(detector, "REPO_ROOT", tmp_path)

    records = detector.run_tofu_drift("production")

    assert records[0]["resource"] == "module.nginx_lv3"
    assert captured_env["LV3_RUN_ID"].startswith("drift-tofu-production-")
    assert captured_env["LV3_RUN_TOFU_DIR"].startswith(str(tmp_path / ".local" / "runs"))
