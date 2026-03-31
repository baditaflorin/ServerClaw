from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import k6_load_testing  # noqa: E402


def test_build_targets_uses_smoke_dedup_and_load_profiles(tmp_path: Path) -> None:
    (tmp_path / "config" / "k6" / "scripts").mkdir(parents=True)
    (tmp_path / "config" / "slo-catalog.json").write_text(
        json.dumps(
            {
                "$schema": "docs/schema/slo-catalog.schema.json",
                "schema_version": "1.0.0",
                "review_note": "test",
                "slos": [
                    {
                        "id": "service-a-availability",
                        "service_id": "service_a",
                        "indicator": "availability",
                        "objective_percent": 99.0,
                        "window_days": 30,
                        "target_url": "https://a.example/health",
                        "probe_module": "http_2xx_follow_redirects",
                        "description": "availability",
                    },
                    {
                        "id": "service-a-latency",
                        "service_id": "service_a",
                        "indicator": "latency",
                        "objective_percent": 95.0,
                        "window_days": 30,
                        "target_url": "https://a.example/health",
                        "probe_module": "http_2xx_follow_redirects",
                        "latency_threshold_ms": 500,
                        "description": "latency",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "capacity-model.json").write_text(
        json.dumps(
            {
                "$schema": "docs/schema/capacity-model.schema.json",
                "schema_version": "1.0.0",
                "host": {
                    "id": "proxmox_florin",
                    "name": "florin",
                    "metrics_host": "proxmox_florin",
                    "physical": {"ram_gb": 64, "vcpu": 16, "disk_gb": 1000},
                    "target_utilisation": {"ram_percent": 80, "vcpu_percent": 75, "disk_percent": 75},
                    "reserved_for_platform": {"ram_gb": 8, "vcpu": 2, "disk_gb": 100},
                },
                "guests": [],
                "reservations": [],
                "service_load_profiles": [
                    {
                        "service_id": "service_a",
                        "typical_concurrency": 5,
                        "smoke_vus": 2,
                        "request_timeout_seconds": 12,
                        "think_time_seconds": 0.5,
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "service_a",
                        "name": "Service A",
                    },
                    {
                        "id": "ntfy",
                        "name": "ntfy",
                        "internal_url": "http://10.10.10.20:2586",
                    },
                    {
                        "id": "grafana",
                        "name": "Grafana",
                        "public_url": "https://grafana.lv3.org",
                    },
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    smoke = k6_load_testing.build_targets(
        repo_root=tmp_path,
        scenario="smoke",
        service_ids=None,
        smoke_duration="60s",
        load_ramp_up_duration="1m",
        load_hold_duration="5m",
        soak_duration="30m",
    )
    load = k6_load_testing.build_targets(
        repo_root=tmp_path,
        scenario="load",
        service_ids=None,
        smoke_duration="60s",
        load_ramp_up_duration="1m",
        load_hold_duration="5m",
        soak_duration="30m",
    )

    assert len(smoke) == 1
    assert smoke[0]["vus"] == 2
    assert smoke[0]["latency_threshold_ms"] == 500.0
    assert len(load) == 1
    assert load[0]["vus"] == 5
    assert load[0]["hold_duration"] == "5m"


def test_build_regression_payload_uses_previous_receipt(tmp_path: Path) -> None:
    receipts_dir = tmp_path / "receipts" / "k6"
    receipts_dir.mkdir(parents=True)
    (receipts_dir / "load-service_a-20260330T100000Z.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "http_req_duration_p95_ms": 100.0,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = k6_load_testing.build_regression_payload(
        repo_root=tmp_path,
        receipts_dir=receipts_dir,
        scenario="load",
        service_id="service_a",
        current_p95_ms=130.0,
    )

    assert payload["checked"] is True
    assert payload["regressed"] is True
    assert round(payload["regression_ratio"], 2) == 0.30


def test_validate_k6_receipt_rejects_unbalanced_counts(tmp_path: Path) -> None:
    summary_path = tmp_path / "receipts" / "k6" / "raw" / "summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text("{}", encoding="utf-8")
    service_index = {"service_a": {"id": "service_a"}}
    receipt_path = tmp_path / "receipts" / "k6" / "load-service_a.json"
    receipt = {
        "$schema": "docs/schema/k6-receipt.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "2026-03-30-load-service_a-100000Z",
        "scenario": "load",
        "service_id": "service_a",
        "environment": "production",
        "runner_context": "manual",
        "recorded_on": "2026-03-30",
        "recorded_at": "2026-03-30T10:00:00Z",
        "recorded_by": "codex",
        "source_commit": "deadbeef",
        "repo_version_context": "0.1.0",
        "k6_image_ref": "docker.io/grafana/k6:1.7.1@sha256:test",
        "summary_export": str(summary_path.relative_to(tmp_path)),
        "prometheus_remote_write_url": "http://10.10.10.40:9090/api/v1/write",
        "scenario_config": {
            "vus": 5,
            "max_error_rate": 0.01,
            "think_time_seconds": 1.0,
            "request_timeout_seconds": 10.0,
        },
        "metrics": {
            "request_count": 10,
            "success_count": 7,
            "failed_count": 1,
            "error_rate": 0.1,
            "http_req_duration_p95_ms": 100.0,
            "http_req_duration_avg_ms": 50.0,
            "http_req_duration_max_ms": 125.0,
        },
        "slo_assessment": {
            "availability_slo_id": None,
            "latency_slo_id": None,
            "latency_threshold_ms": None,
            "availability_objective_percent": None,
            "error_budget_consumed_pct": 0.0,
            "error_budget_remaining_pct": 100.0,
            "error_budget_warning_threshold_pct": 20.0,
            "within_error_budget": True,
            "latency_threshold_passed": True,
        },
        "regression": {
            "checked": False,
            "baseline_receipt": None,
            "baseline_p95_ms": None,
            "current_p95_ms": 100.0,
            "regression_ratio": None,
            "threshold_ratio": 0.2,
            "regressed": False,
        },
        "notifications": {
            "nats_event_published": False,
            "ntfy_topic_notified": None,
        },
        "result": "passed",
        "failure_reasons": [],
    }

    try:
        k6_load_testing.validate_k6_receipt(receipt, receipt_path, service_index, tmp_path)
    except ValueError as exc:
        assert "request counts must add up" in str(exc)
    else:
        raise AssertionError("validate_k6_receipt should reject unbalanced counts")


def test_run_k6_uses_host_workspace_override(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, cwd, text, capture_output, check):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = cwd

        class Completed:
            returncode = 0
            stderr = ""
            stdout = ""

        return Completed()

    monkeypatch.setenv("LV3_DOCKER_WORKSPACE_PATH", "/host/gitea-runner/workspace")
    monkeypatch.setattr(
        k6_load_testing,
        "load_image_catalog",
        lambda: {"images": {"k6_runtime": {"ref": "docker.io/grafana/k6:1.7.1@sha256:test"}}},
    )
    monkeypatch.setattr(k6_load_testing.subprocess, "run", fake_run)

    returncode, output = k6_load_testing.run_k6(
        repo_root=tmp_path,
        run_id="20260331T060000Z",
        scenario="smoke",
        runner_context="gitea-actions",
        environment="production",
        config_path=tmp_path / ".local" / "k6" / "config.json",
        summary_path=tmp_path / "receipts" / "k6" / "raw" / "summary.json",
        prometheus_remote_write_url="http://10.10.10.40:9090/api/v1/write",
    )

    assert returncode == 0
    assert output == ""
    command = captured["command"]
    assert isinstance(command, list)
    assert f"/host/gitea-runner/workspace:{tmp_path}" in command
