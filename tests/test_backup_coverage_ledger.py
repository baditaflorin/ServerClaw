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
        restore_evidence={160: {"recorded_at": "2026-03-28T04:00:00Z", "path": "receipts/restore-verifications/2026-03-28.json"}},
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
