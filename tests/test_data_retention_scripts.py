from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


purge_old_receipts = load_module("purge_old_receipts", "scripts/purge_old_receipts.py")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def set_age(path: Path, *, days_old: int) -> None:
    timestamp = time.time() - (days_old * 24 * 60 * 60)
    os.utime(path, (timestamp, timestamp))


def test_run_purge_reports_and_deletes_expired_receipts(tmp_path: Path) -> None:
    receipts_root = tmp_path / "receipts"
    old_receipt = receipts_root / "live-applies" / "2026-01-01-old.json"
    new_receipt = receipts_root / "live-applies" / "2026-03-23-new.json"
    old_receipt.parent.mkdir(parents=True)
    old_receipt.write_text("{}", encoding="utf-8")
    new_receipt.write_text("{}", encoding="utf-8")
    set_age(old_receipt, days_old=400)
    set_age(new_receipt, days_old=10)

    audit_log = tmp_path / "mutation-audit.jsonl"
    audit_log.write_text(
        "\n".join(
            [
                json.dumps({"ts": "2025-01-01T00:00:00Z", "action": "old"}),
                json.dumps({"ts": "2026-03-20T00:00:00Z", "action": "new"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    catalog_path = tmp_path / "data-catalog.json"
    write_json(
        catalog_path,
        {
            "$schema": "docs/schema/data-catalog.schema.json",
            "schema_version": "1.0.0",
            "data_stores": [
                {
                    "id": "live-apply-receipts",
                    "service": "platform_control_plane",
                    "name": "Live applies",
                    "class": "internal",
                    "retention_days": 365,
                    "backup_included": True,
                    "access_role": "platform-read",
                    "pii_risk": "low",
                    "locations": ["receipts/live-applies"],
                    "retention_paths": ["live-applies"],
                    "notes": "test"
                },
                {
                    "id": "mutation-audit-log",
                    "service": "platform_control_plane",
                    "name": "Audit log",
                    "class": "confidential",
                    "retention_days": 365,
                    "backup_included": True,
                    "access_role": "platform-operator",
                    "pii_risk": "medium",
                    "locations": ["mutation-audit.jsonl"],
                    "notes": "test"
                },
            ]
        },
    )

    dry_run = purge_old_receipts.run_purge(
        catalog_path=catalog_path,
        receipts_root=receipts_root,
        audit_log_path=audit_log,
        execute=False,
    )
    assert "live-applies/2026-01-01-old.json" in dry_run["receipt_targets"][0]["removed"]
    assert old_receipt.exists()

    executed = purge_old_receipts.run_purge(
        catalog_path=catalog_path,
        receipts_root=receipts_root,
        audit_log_path=audit_log,
        execute=True,
    )
    assert executed["audit_log_target"]["removed_lines"] == 1
    assert not old_receipt.exists()
    assert new_receipt.exists()
    remaining_lines = audit_log.read_text(encoding="utf-8").splitlines()
    assert len(remaining_lines) == 1
    assert json.loads(remaining_lines[0])["action"] == "new"
