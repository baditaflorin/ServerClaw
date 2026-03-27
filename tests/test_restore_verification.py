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
    )

    monkeypatch.setattr(rv, "load_controller_context", lambda: context)
    monkeypatch.setattr(rv, "load_restore_targets", lambda: [target])
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
