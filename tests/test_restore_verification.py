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
        vm_name="postgres",
        source_vmid=150,
        target_vmid=900,
        bridge="vmbr20",
        ip_cidr="10.20.10.110/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CA",
        smoke_kind="postgres",
        resources=rv.ResourceAmount(ram_gb=4, vcpu=2, disk_gb=48),
    )
    profile = rv.RestoreReadinessProfile(
        profile_id="postgres",
        service_class="stateful-database",
        description="Postgres restore profile",
        initial_wait_seconds=10,
        max_attempts=3,
        retry_delay_seconds=10,
        network_dependency_checks=("postgres_ready",),
        synthetic_replay_enabled=False,
    )

    result = rv.build_failure_result(target, None, "restore failed", profile=profile)

    assert result["overall"] == "fail"
    assert result["tests"][0]["error"] == "restore failed"
    assert result["readiness_profile"]["profile_id"] == "postgres"


def test_build_report_counts_passes_and_failures() -> None:
    report = rv.build_report(
        [
            {"vm": "postgres", "overall": "pass"},
            {"vm": "docker-runtime", "overall": "fail"},
        ],
        triggered_by="manual",
        environment="production",
    )

    assert report["overall"] == "fail"
    assert report["summary"]["pass_count"] == 1
    assert report["summary"]["fail_count"] == 1


def test_build_restored_guest_ssh_command_honors_breakglass_port() -> None:
    command_argv = rv.build_restored_guest_ssh_command(
        {
            "bootstrap_key": Path("/tmp/bootstrap.id_ed25519"),
            "host_user": "ops",
            "host_addr": "203.0.113.1",
            "host_port": "2222",
        },
        "10.10.10.20",
        "hostname",
    )

    joined = " ".join(command_argv)
    assert "ProxyCommand=ssh" in joined
    assert " -p 2222 " in joined


def test_build_target_result_fails_when_synthetic_replay_fails() -> None:
    target = rv.RestoreTarget(
        vm_name="docker-runtime",
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
    profile = rv.RestoreReadinessProfile(
        profile_id="docker-runtime",
        service_class="stateful-control-plane-runtime",
        description="Docker runtime restore profile",
        initial_wait_seconds=90,
        max_attempts=10,
        retry_delay_seconds=30,
        network_dependency_checks=("keycloak_ready", "netbox_ready", "windmill_ready"),
        synthetic_replay_enabled=True,
        synthetic_replay_target="restore-docker-runtime",
    )
    ladder = rv.build_readiness_ladder_payload(
        [
            {
                "id": "restore_completed",
                "label": "restore completed",
                "required": True,
                "status": "pass",
            },
            {
                "id": "guest_boot_completed",
                "label": "guest boot completed",
                "required": True,
                "status": "pass",
            },
            {
                "id": "guest_access_path_ready",
                "label": "guest access path ready",
                "required": True,
                "status": "pass",
            },
            {
                "id": "network_and_dependency_path_ready",
                "label": "network and dependency path ready",
                "required": True,
                "status": "pass",
            },
            {
                "id": "service_specific_warm_up_completed",
                "label": "service-specific warm-up completed",
                "required": True,
                "status": "pass",
            },
            {
                "id": "synthetic_replay_window_passed",
                "label": "synthetic replay window passed",
                "required": True,
                "status": "fail",
            },
        ]
    )

    result = rv.build_target_result(
        target=target,
        backup=backup,
        profile=profile,
        restore_duration_seconds=10,
        boot_time_seconds=20,
        execution_mode="qga",
        tests=smoke_tests,
        readiness_ladder=ladder,
        warm_up_attempts=[{"attempt": 1, "elapsed_seconds": 90, "test_statuses": {"windmill_ready": "pass"}}],
        synthetic_replay=synthetic_replay,
        warm_up_outcome=rv.WarmUpOutcome(
            tests=smoke_tests,
            attempts=[{"attempt": 1, "elapsed_seconds": 90, "test_statuses": {"windmill_ready": "pass"}}],
            attempts_used=1,
            network_dependency_ready_after_attempt=1,
            service_warm_up_ready_after_attempt=1,
        ),
    )

    assert result["overall"] == "fail"
    assert result["execution_mode"] == "qga"
    assert result["synthetic_replay"]["overall"] == "fail"
    assert result["tests"][-1]["name"] == "synthetic_transaction_replay"
    assert result["tests"][-1]["status"] == "fail"
    assert result["readiness_ladder"]["highest_completed_stage"]["id"] == "service_specific_warm_up_completed"


def test_maybe_write_metrics_skips_without_environment(monkeypatch, tmp_path: Path) -> None:
    report = rv.build_report(
        [{"vm": "postgres", "overall": "pass"}],
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
            "postgres",
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
            "docker-runtime",
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

    selected = rv.select_restore_targets(["docker-runtime"])

    assert [item.vm_name for item in selected] == ["docker-runtime"]


def test_execute_profiled_smoke_tests_retries_until_required_checks_pass(monkeypatch) -> None:
    target = rv.RestoreTarget(
        vm_name="docker-runtime",
        source_vmid=120,
        target_vmid=901,
        bridge="vmbr20",
        ip_cidr="10.20.10.100/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CB",
        smoke_kind="docker-runtime",
        resources=rv.ResourceAmount(ram_gb=6, vcpu=4, disk_gb=96),
    )
    profile = rv.RestoreReadinessProfile(
        profile_id="docker-runtime",
        service_class="stateful-control-plane-runtime",
        description="Docker runtime restore profile",
        initial_wait_seconds=90,
        max_attempts=3,
        retry_delay_seconds=30,
        network_dependency_checks=("keycloak_ready", "netbox_ready", "windmill_ready"),
        synthetic_replay_enabled=True,
        synthetic_replay_target="restore-docker-runtime",
    )
    attempts = iter(
        [
            [
                {"name": "keycloak_ready", "status": "fail", "required": True},
                {"name": "netbox_ready", "status": "fail", "required": True},
                {"name": "windmill_ready", "status": "fail", "required": True},
                {"name": "openbao_ready", "status": "fail", "required": False},
            ],
            [
                {"name": "keycloak_ready", "status": "pass", "required": True},
                {"name": "netbox_ready", "status": "pass", "required": True},
                {"name": "windmill_ready", "status": "pass", "required": True},
                {"name": "openbao_ready", "status": "fail", "required": False},
            ],
        ]
    )
    monkeypatch.setattr(rv, "execute_smoke_tests", lambda *_args, **_kwargs: next(attempts))
    sleep_calls: list[int] = []
    monkeypatch.setattr(rv.time, "sleep", lambda seconds: sleep_calls.append(int(seconds)))

    outcome = rv.execute_profiled_smoke_tests(
        {"restored_guests": {"docker-runtime": "10.20.10.100"}},
        target,
        execution_mode="qga",
        profile=profile,
        docker_wait_seconds=30,
    )

    assert outcome.attempts_used == 2
    assert outcome.network_dependency_ready_after_attempt == 2
    assert outcome.service_warm_up_ready_after_attempt == 2
    assert outcome.tests[0]["status"] == "pass"
    assert sleep_calls == [90, 30]


def test_build_report_counts_highest_completed_stages() -> None:
    report = rv.build_report(
        [
            {
                "vm": "postgres",
                "overall": "pass",
                "readiness_ladder": {"highest_completed_stage": {"id": "service_specific_warm_up_completed"}},
            },
            {
                "vm": "docker-runtime",
                "overall": "fail",
                "readiness_ladder": {"highest_completed_stage": {"id": "network_and_dependency_path_ready"}},
            },
        ],
        triggered_by="manual",
        environment="production",
    )

    assert report["summary"]["highest_completed_stage_counts"] == {
        "network_and_dependency_path_ready": 1,
        "service_specific_warm_up_completed": 1,
    }


def test_emit_mutation_audit_accepts_external_receipt_path(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_build_event(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(rv, "build_event", fake_build_event)
    monkeypatch.setattr(rv, "emit_event_best_effort", lambda *_args, **_kwargs: None)

    rv.emit_mutation_audit(
        {"overall": "fail"},
        tmp_path / "2026-03-29.json",
        actor_id="ws-0272-premerge",
        triggered_by="ws-0272-premerge",
    )

    assert captured["evidence_ref"] == str(tmp_path / "2026-03-29.json")


def test_wait_for_guest_access_falls_back_to_qga(monkeypatch) -> None:
    target = rv.RestoreTarget(
        vm_name="docker-runtime",
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
        vm_name="postgres",
        source_vmid=150,
        target_vmid=900,
        bridge="vmbr20",
        ip_cidr="10.20.10.110/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CA",
        smoke_kind="postgres",
        resources=rv.ResourceAmount(ram_gb=4, vcpu=2, disk_gb=48),
    )
    profile = rv.RestoreReadinessProfile(
        profile_id="postgres",
        service_class="stateful-database",
        description="Postgres restore profile",
        initial_wait_seconds=10,
        max_attempts=3,
        retry_delay_seconds=10,
        network_dependency_checks=("postgres_ready",),
        synthetic_replay_enabled=False,
    )

    monkeypatch.setattr(rv, "load_controller_context", lambda: context)
    monkeypatch.setattr(rv, "load_restore_targets", lambda: [target])
    monkeypatch.setattr(rv, "load_restore_readiness_profiles", lambda: {"postgres": profile})
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
                "timestamp": rv.extract_backup_timestamp("lv3-backup-pbs:backup/qemu/150/2026-03-22T02:30:00Z"),
            }
        ],
    )
    monkeypatch.setattr(
        rv, "restore_backup", lambda context, target, backup: (_ for _ in ()).throw(RuntimeError("boom"))
    )
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


def test_build_target_result_records_seed_snapshot() -> None:
    target = rv.RestoreTarget(
        vm_name="postgres",
        source_vmid=150,
        target_vmid=900,
        bridge="vmbr20",
        ip_cidr="10.20.10.110/24",
        gateway="10.20.10.1",
        mac_address="BC:24:11:2A:2E:CA",
        smoke_kind="postgres",
        resources=rv.ResourceAmount(ram_gb=4, vcpu=2, disk_gb=48),
    )
    backup = {
        "volid": "lv3-backup-pbs:backup/qemu/150/2026-03-22T02:30:00Z",
        "timestamp": rv.extract_backup_timestamp("lv3-backup-pbs:backup/qemu/150/2026-03-22T02:30:00Z"),
    }
    profile = rv.RestoreReadinessProfile(
        profile_id="postgres",
        service_class="stateful-database",
        description="Postgres restore profile",
        initial_wait_seconds=10,
        max_attempts=3,
        retry_delay_seconds=10,
        network_dependency_checks=("postgres_ready",),
        synthetic_replay_enabled=False,
    )

    result = rv.build_target_result(
        target=target,
        backup=backup,
        profile=profile,
        restore_duration_seconds=20,
        boot_time_seconds=15,
        execution_mode="ssh",
        tests=[{"name": "restore_workflow", "status": "pass", "required": True}],
        readiness_ladder={
            "highest_completed_stage": {"id": "service_specific_warm_up_completed"},
            "stages": [],
        },
        warm_up_attempts=[],
        seed_snapshot={
            "seed_class": "tiny",
            "snapshot_id": "tiny-abc123",
            "remote_dir": "/var/lib/lv3-seed-data/restore-verification/postgres",
        },
    )

    assert result["seed_class"] == "tiny"
    assert result["seed_snapshot_id"] == "tiny-abc123"
    assert result["readiness_profile"]["profile_id"] == "postgres"
