from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import restore_verification as rv  # noqa: E402


def test_select_backup_prefers_latest_when_requested() -> None:
    backups = [
        {
            "volid": "lv3-backup-pbs:backup/qemu/150/2026-03-22T02:30:00Z",
            "timestamp": rv.extract_backup_timestamp("lv3-backup-pbs:backup/qemu/150/2026-03-22T02:30:00Z"),
        },
        {
            "volid": "lv3-backup-pbs:backup/qemu/150/2026-03-21T02:30:00Z",
            "timestamp": rv.extract_backup_timestamp("lv3-backup-pbs:backup/qemu/150/2026-03-21T02:30:00Z"),
        },
    ]

    selected = rv.select_backup(
        backups,
        lookback_days=7,
        selection_strategy="latest",
        rng=__import__("random").Random(7),
    )

    assert selected["volid"].endswith("2026-03-22T02:30:00Z")


def test_build_failure_result_marks_target_failed() -> None:
    target = rv.RestoreTarget(
        vm_name="postgres-lv3",
        source_vmid=150,
        target_vmid=900,
        bridge="vmbr20",
        ip_cidr="10.20.10.110/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CA",
        smoke_kind="postgres",
        resources=rv.ResourceAmount(ram_gb=4, vcpu=2, disk_gb=48),
    )

    result = rv.build_failure_result(target, None, "restore failed")

    assert result["overall"] == "fail"
    assert result["tests"][0]["error"] == "restore failed"


def test_build_report_counts_passes_and_failures() -> None:
    report = rv.build_report(
        [
            {"vm": "postgres-lv3", "overall": "pass"},
            {"vm": "docker-runtime-lv3", "overall": "fail"},
        ],
        triggered_by="manual",
        environment="production",
    )

    assert report["overall"] == "fail"
    assert report["summary"]["pass_count"] == 1
    assert report["summary"]["fail_count"] == 1


def test_build_target_result_fails_when_synthetic_replay_fails() -> None:
    target = rv.RestoreTarget(
        vm_name="docker-runtime-lv3",
        source_vmid=120,
        target_vmid=901,
        bridge="vmbr20",
        ip_cidr="10.20.10.100/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CB",
        smoke_kind="docker-runtime",
        resources=rv.ResourceAmount(ram_gb=6, vcpu=4, disk_gb=96),
    )
    backup = {
        "volid": "lv3-backup-pbs:backup/qemu/120/2026-03-27T02:30:00Z",
        "timestamp": rv.extract_backup_timestamp("lv3-backup-pbs:backup/qemu/120/2026-03-27T02:30:00Z"),
    }
    smoke_tests = [{"name": "windmill_ready", "status": "pass", "required": True}]
    synthetic_replay = {
        "overall": "fail",
        "summary": "2/3 synthetic requests passed across 1 scenarios on target 'restore-docker-runtime'",
        "success_rate": 0.6667,
        "latency_ms": {"count": 3, "p50": 20, "p95": 31, "max": 31},
        "window_assessment": {"window": "post_restore_recovery"},
    }

    result = rv.build_target_result(
        target=target,
        backup=backup,
        restore_duration_seconds=10,
        boot_time_seconds=20,
        execution_mode="qga",
        tests=smoke_tests,
        synthetic_replay=synthetic_replay,
    )

    assert result["overall"] == "fail"
    assert result["execution_mode"] == "qga"
    assert result["synthetic_replay"]["overall"] == "fail"
    assert result["tests"][-1]["name"] == "synthetic_transaction_replay"
    assert result["tests"][-1]["status"] == "fail"


def test_maybe_write_metrics_skips_without_environment(monkeypatch, tmp_path: Path) -> None:
    report = rv.build_report(
        [{"vm": "postgres-lv3", "overall": "pass"}],
        triggered_by="manual",
        environment="production",
    )
    monkeypatch.delenv("RESTORE_VERIFICATION_INFLUXDB_URL", raising=False)
    monkeypatch.delenv("RESTORE_VERIFICATION_INFLUXDB_BUCKET", raising=False)
    monkeypatch.delenv("RESTORE_VERIFICATION_INFLUXDB_ORG", raising=False)
    monkeypatch.delenv("RESTORE_VERIFICATION_INFLUXDB_TOKEN", raising=False)

    rv.maybe_write_metrics(report, receipt_dir=tmp_path, environment="production")


def test_select_restore_targets_filters_requested_names(monkeypatch) -> None:
    targets = [
        rv.RestoreTarget(
            "postgres-lv3",
            150,
            900,
            "vmbr20",
            "10.20.10.110/24",
            "10.20.10.1",
            "BC:24:11:2A:2E:CA",
            "postgres",
            rv.ResourceAmount(ram_gb=4, vcpu=2, disk_gb=48),
        ),
        rv.RestoreTarget(
            "docker-runtime-lv3",
            120,
            901,
            "vmbr20",
            "10.20.10.100/24",
            "10.20.10.1",
            "BC:24:11:2A:2E:CB",
            "docker-runtime",
            rv.ResourceAmount(ram_gb=6, vcpu=4, disk_gb=96),
        ),
    ]
    monkeypatch.setattr(rv, "load_restore_targets", lambda: targets)

    selected = rv.select_restore_targets(["docker-runtime-lv3"])

    assert [item.vm_name for item in selected] == ["docker-runtime-lv3"]


def test_wait_for_guest_access_falls_back_to_qga(monkeypatch) -> None:
    target = rv.RestoreTarget(
        vm_name="docker-runtime-lv3",
        source_vmid=120,
        target_vmid=901,
        bridge="vmbr20",
        ip_cidr="10.20.10.100/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CB",
        smoke_kind="docker-runtime",
        resources=rv.ResourceAmount(ram_gb=6, vcpu=4, disk_gb=96),
    )
    ssh_attempts = iter(
        [
            rv.CommandOutcome(command="true", returncode=255, stdout="", stderr="banner timeout"),
            rv.CommandOutcome(command="true", returncode=255, stdout="", stderr="banner timeout"),
        ]
    )
    monkeypatch.setattr(rv, "run_restored_guest_command", lambda *_args, **_kwargs: next(ssh_attempts))
    monkeypatch.setattr(rv, "guest_agent_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        rv,
        "run_restored_guest_agent_command",
        lambda *_args, **_kwargs: rv.CommandOutcome(command="true", returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(rv.time, "sleep", lambda *_args, **_kwargs: None)

    mode, boot_time_seconds = rv.wait_for_guest_access({}, target, timeout_seconds=30)

    assert mode == "qga"
    assert boot_time_seconds >= 0


def test_main_records_failure_receipt_and_cleans_up(monkeypatch, tmp_path: Path) -> None:
    context = {
        "bootstrap_key": Path("/tmp/bootstrap"),
        "host_user": "ops",
        "host_addr": "100.118.189.95",
        "host_vars": {"proxmox_guests": []},
    }
    target = rv.RestoreTarget(
        vm_name="postgres-lv3",
        source_vmid=150,
        target_vmid=900,
        bridge="vmbr20",
        ip_cidr="10.20.10.110/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CA",
        smoke_kind="postgres",
        resources=rv.ResourceAmount(ram_gb=4, vcpu=2, disk_gb=48),
    )

    monkeypatch.setattr(rv, "load_controller_context", lambda: context)
    monkeypatch.setattr(rv, "load_restore_targets", lambda: [target])
    monkeypatch.setattr(
        rv,
        "load_capacity_model",
        lambda: object(),
    )
    monkeypatch.setattr(
        rv,
        "check_capacity_class_request",
        lambda *args, **kwargs: {"approved": True, "reasons": []},
    )
    monkeypatch.setattr(
        rv,
        "list_backups_for_vmid",
        lambda context, source_vmid: [
            {
                "volid": "lv3-backup-pbs:backup/qemu/150/2026-03-22T02:30:00Z",
                "timestamp": rv.extract_backup_timestamp(
                    "lv3-backup-pbs:backup/qemu/150/2026-03-22T02:30:00Z"
                ),
            }
        ],
    )
    monkeypatch.setattr(rv, "restore_backup", lambda context, target, backup: (_ for _ in ()).throw(RuntimeError("boom")))
    destroyed: list[int] = []
    monkeypatch.setattr(rv, "destroy_restored_vm", lambda context, target_vmid: destroyed.append(target_vmid))
    monkeypatch.setattr(rv, "maybe_write_metrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(rv, "maybe_publish_nats", lambda *args, **kwargs: None)
    monkeypatch.setattr(rv, "maybe_notify_mattermost", lambda *args, **kwargs: None)
    monkeypatch.setattr(rv, "emit_mutation_audit", lambda *args, **kwargs: None)

    exit_code = rv.main(["--receipt-dir", str(tmp_path)])

    receipt_files = list(tmp_path.glob("*.json"))
    assert exit_code == 1
    assert destroyed == [900]
    assert len(receipt_files) == 1
    payload = json.loads(receipt_files[0].read_text())
    assert payload["results"][0]["overall"] == "fail"
