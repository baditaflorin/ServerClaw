from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest


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
    assert load[0]["duration"] == "5m"


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


def test_current_commit_prefers_snapshot_commit_env(monkeypatch, tmp_path: Path) -> None:
    snapshot_commit = "8465168a90426723fad3083b78878575cff20534"

    monkeypatch.setenv("LV3_SNAPSHOT_SOURCE_COMMIT", snapshot_commit)
    monkeypatch.setattr(
        k6_load_testing,
        "run_git",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("run_git should not be called")),
    )

    assert k6_load_testing.current_commit(tmp_path) == snapshot_commit


def test_current_commit_uses_git_when_snapshot_env_is_missing(monkeypatch, tmp_path: Path) -> None:
    expected_commit = "5ce5deae525879610a61c9065a63e951a21bc968"

    monkeypatch.delenv("LV3_SNAPSHOT_SOURCE_COMMIT", raising=False)
    monkeypatch.setattr(k6_load_testing, "run_git", lambda *_args, **_kwargs: expected_commit)

    assert k6_load_testing.current_commit(tmp_path) == expected_commit


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
    assert "--user" in command
    assert f"{k6_load_testing.os.getuid()}:{k6_load_testing.os.getgid()}" in command


def test_main_resolves_relative_repo_root_before_running_k6(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    output_dir = tmp_path / "receipts" / "k6"
    recorded_at = k6_load_testing.dt.datetime(2026, 3, 31, 6, 0, 0, tzinfo=k6_load_testing.dt.timezone.utc)

    def fake_build_targets(**kwargs):  # type: ignore[no-untyped-def]
        captured["build_targets_repo_root"] = kwargs["repo_root"]
        return [{"service_id": "openfga"}]

    def fake_write_run_config(**kwargs):  # type: ignore[no-untyped-def]
        captured["write_run_config_repo_root"] = kwargs["repo_root"]
        path = kwargs["repo_root"] / ".local" / "k6" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    def fake_run_k6(**kwargs):  # type: ignore[no-untyped-def]
        captured["run_k6_repo_root"] = kwargs["repo_root"]
        captured["run_k6_summary_path"] = kwargs["summary_path"]
        kwargs["summary_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["summary_path"].write_text("{}", encoding="utf-8")
        return 0, ""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(k6_load_testing, "utc_now", lambda: recorded_at)
    monkeypatch.setattr(k6_load_testing, "build_targets", fake_build_targets)
    monkeypatch.setattr(k6_load_testing, "write_run_config", fake_write_run_config)
    monkeypatch.setattr(k6_load_testing, "default_prometheus_remote_write_url", lambda _repo_root: "http://10.10.10.40:9090/api/v1/write")
    monkeypatch.setattr(k6_load_testing, "run_k6", fake_run_k6)
    monkeypatch.setattr(k6_load_testing, "load_json", lambda _path: {})
    monkeypatch.setattr(k6_load_testing, "build_receipts", lambda **_kwargs: [output_dir / "load-openfga-20260331T060000Z.json"])

    exit_code = k6_load_testing.main(
        [
            "--repo-root",
            ".",
            "--scenario",
            "load",
            "--runner-context",
            "build-server",
            "--environment",
            "production",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert captured["build_targets_repo_root"] == tmp_path.resolve()
    assert captured["write_run_config_repo_root"] == tmp_path.resolve()
    assert captured["run_k6_repo_root"] == tmp_path.resolve()
    assert captured["run_k6_summary_path"] == output_dir / "raw" / "20260331T060000Z-load-summary.json"


def test_main_writes_receipts_when_k6_returns_nonzero_but_summary_exists(monkeypatch, tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "receipts" / "k6"
    recorded_at = k6_load_testing.dt.datetime(2026, 3, 31, 10, 35, 58, tzinfo=k6_load_testing.dt.timezone.utc)
    build_receipts_called: dict[str, bool] = {"value": False}

    def fake_write_run_config(**kwargs):  # type: ignore[no-untyped-def]
        path = kwargs["repo_root"] / ".local" / "k6" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path

    def fake_run_k6(**kwargs):  # type: ignore[no-untyped-def]
        kwargs["summary_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["summary_path"].write_text("{}", encoding="utf-8")
        return 99, "k6 threshold failure"

    def fake_build_receipts(**kwargs):  # type: ignore[no-untyped-def]
        build_receipts_called["value"] = True
        receipt_path = kwargs["output_dir"] / "load-openfga-20260331T103558Z.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text("{}", encoding="utf-8")
        return [receipt_path]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(k6_load_testing, "utc_now", lambda: recorded_at)
    monkeypatch.setattr(k6_load_testing, "build_targets", lambda **_kwargs: [{"service_id": "openfga"}])
    monkeypatch.setattr(k6_load_testing, "write_run_config", fake_write_run_config)
    monkeypatch.setattr(k6_load_testing, "default_prometheus_remote_write_url", lambda _repo_root: "http://10.10.10.40:9090/api/v1/write")
    monkeypatch.setattr(k6_load_testing, "run_k6", fake_run_k6)
    monkeypatch.setattr(k6_load_testing, "load_json", lambda _path: {})
    monkeypatch.setattr(k6_load_testing, "build_receipts", fake_build_receipts)

    exit_code = k6_load_testing.main(
        [
            "--repo-root",
            ".",
            "--scenario",
            "load",
            "--runner-context",
            "build-server",
            "--environment",
            "production",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 99
    assert build_receipts_called["value"] is True
    assert "k6 threshold failure" in captured.err
    assert '"status": "failed"' in captured.out


def test_build_receipts_uses_service_checks_and_top_level_metric_fields(monkeypatch, tmp_path: Path) -> None:
    recorded_at = k6_load_testing.dt.datetime(2026, 3, 31, 10, 19, 30, tzinfo=k6_load_testing.dt.timezone.utc)
    summary_path = tmp_path / "receipts" / "k6" / "raw" / "20260331T101930Z-load-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        k6_load_testing,
        "load_image_catalog",
        lambda: {"images": {"k6_runtime": {"ref": "docker.io/grafana/k6:1.7.1@sha256:test"}}},
    )
    monkeypatch.setattr(k6_load_testing, "current_commit", lambda _repo_root: "deadbeef")
    monkeypatch.setattr(k6_load_testing, "current_repo_version", lambda _repo_root: "0.1.0")
    monkeypatch.setattr(k6_load_testing, "build_regression_payload", lambda **_kwargs: {"checked": False, "baseline_receipt": None, "baseline_p95_ms": None, "current_p95_ms": 5.79, "regression_ratio": None, "threshold_ratio": 0.2, "regressed": False})
    monkeypatch.setattr(k6_load_testing, "default_prometheus_remote_write_url", lambda _repo_root: "http://10.10.10.40:9090/api/v1/write")

    summary = {
        "metrics": {
            "checks{service_id:openfga}": {
                "passes": 1392,
                "fails": 0,
                "value": 1,
            },
            "http_req_duration{service_id:openfga}": {
                "p(95)": 5.790530650000001,
                "avg": 2.2285226321839082,
                "max": 35.630874,
            },
        }
    }
    targets = [
        {
            "service_id": "openfga",
            "service_name": "OpenFGA",
            "target_url": "http://10.10.10.20:8098/healthz",
            "availability_slo_id": "openfga-availability",
            "availability_objective_percent": 99.5,
            "latency_slo_id": "openfga-latency",
            "latency_threshold_ms": 500.0,
            "vus": 9,
            "duration": None,
            "ramp_up_duration": "1m",
            "hold_duration": "5m",
            "think_time_seconds": 1.0,
            "request_timeout_seconds": 10.0,
        }
    ]

    receipts = k6_load_testing.build_receipts(
        repo_root=tmp_path,
        scenario="load",
        runner_context="build-server",
        environment="production",
        recorded_at=recorded_at,
        summary_path=summary_path,
        summary=summary,
        targets=targets,
        output_dir=tmp_path / "receipts" / "k6",
        publish_nats=False,
        notify_ntfy_flag=False,
    )

    assert len(receipts) == 1
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert payload["metrics"]["request_count"] == 1392
    assert payload["metrics"]["success_count"] == 1392
    assert payload["metrics"]["failed_count"] == 0
    assert payload["metrics"]["http_req_duration_p95_ms"] == 5.790530650000001
    assert payload["metrics"]["http_req_duration_avg_ms"] == 2.2285226321839082
    assert payload["metrics"]["http_req_duration_max_ms"] == 35.630874


def test_build_receipts_keeps_failed_receipt_when_ntfy_warning_delivery_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    recorded_at = k6_load_testing.dt.datetime(2026, 3, 31, 10, 47, 16, tzinfo=k6_load_testing.dt.timezone.utc)
    summary_path = tmp_path / "receipts" / "k6" / "raw" / "20260331T104716Z-load-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        k6_load_testing,
        "load_image_catalog",
        lambda: {"images": {"k6_runtime": {"ref": "docker.io/grafana/k6:1.7.1@sha256:test"}}},
    )
    monkeypatch.setattr(k6_load_testing, "current_commit", lambda _repo_root: "deadbeef")
    monkeypatch.setattr(k6_load_testing, "current_repo_version", lambda _repo_root: "0.1.0")
    monkeypatch.setattr(k6_load_testing, "build_regression_payload", lambda **_kwargs: {"checked": False, "baseline_receipt": None, "baseline_p95_ms": None, "current_p95_ms": 900.0, "regression_ratio": None, "threshold_ratio": 0.2, "regressed": False})
    monkeypatch.setattr(k6_load_testing, "default_prometheus_remote_write_url", lambda _repo_root: "http://10.10.10.40:9090/api/v1/write")
    monkeypatch.setattr(k6_load_testing, "notify_ntfy", lambda **_kwargs: (_ for _ in ()).throw(ValueError("missing secret")))

    summary = {
        "metrics": {
            "checks{service_id:openfga}": {
                "passes": 0,
                "fails": 12,
                "value": 0,
            },
            "http_req_duration{service_id:openfga}": {
                "p(95)": 900.0,
                "avg": 800.0,
                "max": 1200.0,
            },
        }
    }
    targets = [
        {
            "service_id": "openfga",
            "service_name": "OpenFGA",
            "target_url": "http://10.10.10.20:8098/healthz",
            "availability_slo_id": "openfga-availability",
            "availability_objective_percent": 99.5,
            "latency_slo_id": "openfga-latency",
            "latency_threshold_ms": 500.0,
            "vus": 9,
            "duration": None,
            "ramp_up_duration": "1m",
            "hold_duration": "5m",
            "think_time_seconds": 1.0,
            "request_timeout_seconds": 10.0,
        }
    ]

    receipts = k6_load_testing.build_receipts(
        repo_root=tmp_path,
        scenario="load",
        runner_context="build-server",
        environment="production",
        recorded_at=recorded_at,
        summary_path=summary_path,
        summary=summary,
        targets=targets,
        output_dir=tmp_path / "receipts" / "k6",
        publish_nats=False,
        notify_ntfy_flag=True,
    )

    captured = capsys.readouterr()
    assert "failed to deliver ntfy warning" in captured.err
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert payload["result"] == "failed"
    assert payload["notifications"]["ntfy_topic_notified"] is None
    assert any("ntfy notification unavailable: missing secret" == reason for reason in payload["failure_reasons"])


def test_notify_ntfy_uses_governed_helper(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "ntfy",
                        "name": "ntfy",
                        "internal_url": "http://10.10.10.20:2586",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run(argv, cwd=None, text=None, capture_output=None, check=None):
        captured["argv"] = argv
        captured["cwd"] = cwd
        return types.SimpleNamespace(returncode=0, stdout='{"status":"published"}', stderr="")

    monkeypatch.setattr(k6_load_testing.subprocess, "run", fake_run)

    topic = k6_load_testing.notify_ntfy(
        repo_root=tmp_path,
        service_id="grafana",
        scenario="load",
        budget_remaining_pct=10.0,
        receipt_path=tmp_path / "receipts" / "k6" / "load-grafana.json",
    )

    assert topic == "platform.slo.warn"
    argv = captured["argv"]
    assert "--publisher" in argv
    assert argv[argv.index("--publisher") + 1] == "windmill"
    assert "--topic" in argv
    assert argv[argv.index("--topic") + 1] == "platform.slo.warn"
    assert "--base-url" in argv
    assert argv[argv.index("--base-url") + 1] == "http://10.10.10.20:2586"


def test_publish_regression_event_fails_fast_when_nats_endpoint_is_unreachable(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "nats",
                        "name": "NATS",
                        "internal_url": "nats://10.10.10.20:4222",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("LV3_NATS_URL", raising=False)
    monkeypatch.setattr(
        k6_load_testing.socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("timed out")),
    )
    monkeypatch.setattr(
        k6_load_testing,
        "publish_nats_events",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("publish_nats_events should not be called")),
    )

    with pytest.raises(RuntimeError, match="timed out"):
        k6_load_testing.publish_regression_event(
            repo_root=tmp_path,
            service_id="keycloak",
            scenario="load",
            receipt_path=tmp_path / "receipts" / "k6" / "load-keycloak.json",
            regression={
                "checked": True,
                "baseline_receipt": "receipts/k6/load-keycloak-previous.json",
                "baseline_p95_ms": 10.0,
                "current_p95_ms": 25.0,
                "regression_ratio": 1.5,
                "threshold_ratio": 0.2,
                "regressed": True,
            },
        )


def test_build_receipts_keeps_passed_result_when_only_nats_regression_notification_fails(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    recorded_at = k6_load_testing.dt.datetime(2026, 3, 31, 12, 4, 12, tzinfo=k6_load_testing.dt.timezone.utc)
    summary_path = tmp_path / "receipts" / "k6" / "raw" / "20260331T120412Z-load-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{}", encoding="utf-8")
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "service-capability-catalog.json").write_text(
        json.dumps(
            {
                "services": [
                    {
                        "id": "nats",
                        "name": "NATS",
                        "internal_url": "nats://10.10.10.20:4222",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("LV3_NATS_URL", raising=False)
    monkeypatch.setattr(
        k6_load_testing,
        "load_image_catalog",
        lambda: {"images": {"k6_runtime": {"ref": "docker.io/grafana/k6:1.7.1@sha256:test"}}},
    )
    monkeypatch.setattr(k6_load_testing, "current_commit", lambda _repo_root: "deadbeef")
    monkeypatch.setattr(k6_load_testing, "current_repo_version", lambda _repo_root: "0.1.0")
    monkeypatch.setattr(k6_load_testing, "default_prometheus_remote_write_url", lambda _repo_root: "http://10.10.10.40:9090/api/v1/write")
    monkeypatch.setattr(
        k6_load_testing,
        "build_regression_payload",
        lambda **_kwargs: {
            "checked": True,
            "baseline_receipt": "receipts/k6/load-keycloak-previous.json",
            "baseline_p95_ms": 10.0,
            "current_p95_ms": 25.0,
            "regression_ratio": 1.5,
            "threshold_ratio": 0.2,
            "regressed": True,
        },
    )
    monkeypatch.setattr(
        k6_load_testing.socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("connection refused")),
    )
    monkeypatch.setattr(
        k6_load_testing,
        "publish_nats_events",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("publish_nats_events should not be called")),
    )

    summary = {
        "metrics": {
            "checks{service_id:keycloak}": {
                "passes": 10,
                "fails": 0,
                "value": 1,
            },
            "http_req_duration{service_id:keycloak}": {
                "p(95)": 25.0,
                "avg": 20.0,
                "max": 30.0,
            },
        }
    }
    targets = [
        {
            "service_id": "keycloak",
            "service_name": "Keycloak",
            "target_url": "https://sso.lv3.org/realms/lv3/.well-known/openid-configuration",
            "availability_slo_id": "keycloak-availability",
            "availability_objective_percent": 99.7,
            "latency_slo_id": "keycloak-latency",
            "latency_threshold_ms": 500.0,
            "vus": 5,
            "duration": "5m",
            "ramp_up_duration": "1m",
            "hold_duration": "5m",
            "think_time_seconds": 1.0,
            "request_timeout_seconds": 10.0,
        }
    ]

    receipts = k6_load_testing.build_receipts(
        repo_root=tmp_path,
        scenario="load",
        runner_context="manual",
        environment="production",
        recorded_at=recorded_at,
        summary_path=summary_path,
        summary=summary,
        targets=targets,
        output_dir=tmp_path / "receipts" / "k6",
        publish_nats=True,
        notify_ntfy_flag=False,
    )

    captured = capsys.readouterr()
    assert "failed to publish NATS regression event" in captured.err
    payload = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert payload["result"] == "passed"
    assert payload["notifications"]["nats_event_published"] is False
    assert any(
        reason.startswith("nats regression notification unavailable:")
        for reason in payload["failure_reasons"]
    )
