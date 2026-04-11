from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import backup_coverage_ledger as ledger


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_governed_assets_uses_existing_redundancy_sources() -> None:
    host_vars = {
        "proxmox_guests": [
            {"vmid": 110, "name": "nginx-lv3"},
            {"vmid": 160, "name": "backup-lv3"},
            {"vmid": 170, "name": "coolify-lv3"},
        ]
    }
    redundancy_catalog = {
        "services": {
            "homepage": {"backup_sources": ["pbs_vm_110"]},
            "backup_pbs": {"backup_sources": ["proxmox_offsite_vm_160"]},
            "coolify": {"backup_sources": ["pbs_vm_170"]},
            "coolify_apps": {"backup_sources": ["pbs_vm_170"]},
        }
    }
    dr_targets = {"offsite_backup": {"storage_id": "lv3-backup-offsite", "schedule_utc": "04:00"}}

    assets = ledger.build_governed_assets(host_vars, redundancy_catalog, dr_targets)

    assert sorted(asset.asset_id for asset in assets) == ["backup-lv3", "coolify-lv3", "nginx-lv3"]
    backup_asset = next(asset for asset in assets if asset.asset_id == "backup-lv3")
    assert backup_asset.storage_id == "lv3-backup-offsite"
    coolify_asset = next(asset for asset in assets if asset.asset_id == "coolify-lv3")
    assert coolify_asset.dependent_services == ["coolify", "coolify_apps"]


def test_evaluate_asset_marks_uncovered_when_offsite_storage_is_missing() -> None:
    asset = ledger.GovernedAsset(
        asset_id="backup-lv3",
        vmid=160,
        source_id="proxmox_offsite_vm_160",
        source_kind="offsite",
        storage_id="lv3-backup-offsite",
        expected_schedule="04:00",
        expected_max_age_hours=36,
        dependent_services=["backup_pbs"],
    )
    report = ledger.evaluate_asset(
        asset,
        jobs=[],
        storage_listing={
            "storage_id": "lv3-backup-offsite",
            "available": False,
            "error": "storage 'lv3-backup-offsite' does not exist",
            "rows": [],
        },
        restore_evidence={
            160: {"recorded_at": "2026-03-28T04:00:00Z", "path": "receipts/restore-verifications/2026-03-28.json"}
        },
        dr_targets={"offsite_backup": {"retention": {"keep_daily": 7}}},
        now=datetime(2026, 3, 29, 10, 0, tzinfo=UTC),
    )

    assert report["coverage_state"] == "uncovered"
    assert "does not exist" in report["state_reasons"][0]
    assert report["last_verified_restore"]["recorded_at"] == "2026-03-28T04:00:00Z"


def test_load_restore_evidence_prefers_latest_successful_receipt(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "receipts" / "restore-verifications"
    write_json(
        receipt_dir / "2026-03-27.json",
        {
            "recorded_on": "2026-03-27",
            "results": [
                {
                    "source_vmid": 120,
                    "overall": "pass",
                    "backup_date": "2026-03-27T01:30:00Z",
                }
            ],
        },
    )
    write_json(
        receipt_dir / "2026-03-28.json",
        {
            "recorded_on": "2026-03-28",
            "results": [
                {
                    "source_vmid": 120,
                    "overall": "fail",
                    "backup_date": "2026-03-28T01:30:00Z",
                }
            ],
        },
    )

    evidence = ledger.load_restore_evidence(receipt_dir)

    assert evidence[120]["backup_date"] == "2026-03-27T01:30:00Z"
    assert evidence[120]["path"].endswith("2026-03-27.json")


def test_restic_file_assets_are_covered_from_latest_snapshot_receipt(tmp_path: Path, monkeypatch) -> None:
    host_vars_path = tmp_path / "inventory" / "host_vars" / "proxmox_florin.yml"
    redundancy_catalog_path = tmp_path / "config" / "service-redundancy-catalog.json"
    dr_targets_path = tmp_path / "config" / "disaster-recovery-targets.json"
    restic_catalog_path = tmp_path / "config" / "restic-file-backup-catalog.json"
    restic_latest_path = tmp_path / "receipts" / "restic-snapshots-latest.json"
    restore_dir = tmp_path / "receipts" / "restore-verifications"

    write_json(host_vars_path, {"proxmox_guests": [{"vmid": 110, "name": "nginx-lv3"}]})
    write_json(redundancy_catalog_path, {"services": {"homepage": {"backup_sources": ["pbs_vm_110"]}}})
    write_json(dr_targets_path, {"offsite_backup": {"storage_id": "lv3-backup-offsite", "schedule_utc": "04:00"}})
    write_json(
        restic_catalog_path,
        {
            "schema_version": "1.0.0",
            "controller_host": {"minio": {"bucket": "restic-config-backup"}},
            "sources": [
                {
                    "id": "config",
                    "label": "config",
                    "paths": ["config"],
                    "freshness_minutes": 1440,
                    "freshness_policy": "event_driven",
                    "expected_schedule": "successful_live_apply",
                    "retention": {"keep_daily": 30},
                    "trigger_on_live_apply": True,
                }
            ],
        },
    )
    write_json(
        restic_latest_path,
        {
            "recorded_at": "2026-03-30T10:00:00Z",
            "sources": [
                {
                    "source_id": "config",
                    "state": "protected",
                    "expected_schedule": "successful_live_apply",
                    "freshness_policy": "event_driven",
                    "reasons": ["Latest snapshot exists and this source is event-driven."],
                    "latest_snapshot": {"snapshot_id": "snap-config", "recorded_at": "2026-03-29T18:00:00Z"},
                }
            ],
        },
    )

    monkeypatch.setattr(ledger, "load_controller_context", lambda: {})
    monkeypatch.setattr(ledger, "load_backup_jobs", lambda context: [])
    monkeypatch.setattr(
        ledger,
        "load_storage_listing",
        lambda context, storage_id: {
            "storage_id": storage_id,
            "available": False,
            "error": "storage unavailable in test",
            "rows": [],
        },
    )

    report = ledger.build_backup_coverage_report(
        now=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
        host_vars_path=host_vars_path,
        redundancy_catalog_path=redundancy_catalog_path,
        dr_targets_path=dr_targets_path,
        restic_catalog_path=restic_catalog_path,
        restic_latest_path=restic_latest_path,
        restore_dir=restore_dir,
    )

    config_asset = next(asset for asset in report["assets"] if asset["source_id"] == "config")
    assert config_asset["source_kind"] == "restic_file"
    assert config_asset["coverage_state"] == "protected"
    assert config_asset["last_successful_backup"]["snapshot_id"] == "snap-config"
    rendered = ledger.render_text(report)
    assert "2026-03-29T18:00:00Z" in rendered
