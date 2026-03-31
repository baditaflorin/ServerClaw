from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "restic_config_backup.py"
TRIGGER_SCRIPT_PATH = REPO_ROOT / "scripts" / "trigger_restic_live_apply.py"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


restic_backup = _load_module(SCRIPT_PATH, "restic_config_backup")
trigger = _load_module(TRIGGER_SCRIPT_PATH, "trigger_restic_live_apply")


def test_filter_sources_splits_scheduled_and_live_apply_sources() -> None:
    scheduled = restic_backup.Source(
        "receipts",
        "receipts",
        (Path("receipts"),),
        360,
        "interval",
        "every_6_hours",
        {"keep_daily": 90},
        False,
        False,
        {"path": "receipts", "expected_minimum_files": 1},
    )
    live_apply = restic_backup.Source(
        "config",
        "config",
        (Path("config"),),
        1440,
        "event_driven",
        "successful_live_apply",
        {"keep_daily": 30},
        True,
        False,
        None,
    )

    assert restic_backup.filter_sources([scheduled, live_apply], only_live_apply=False) == [scheduled]
    assert restic_backup.filter_sources([scheduled, live_apply], only_live_apply=True) == [live_apply]


def test_summarize_latest_snapshots_keeps_event_driven_sources_protected(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "config" / "service.yml").write_text("service: value\n", encoding="utf-8")

    restic_backup.restic_call = lambda *args, **kwargs: types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "id": "snap-config",
                    "time": "2026-03-29T08:00:00Z",
                    "hostname": "docker-runtime-lv3",
                    "paths": [str(repo_root / "config")],
                    "tags": ["source:config", "source-label:config"],
                    "summary": {"total_files_processed": 1},
                }
            ]
        ),
        stderr="",
    )

    source = restic_backup.Source(
        "config",
        "config",
        (repo_root / "config",),
        1440,
        "event_driven",
        "successful_live_apply",
        {"keep_daily": 30},
        True,
        False,
        None,
    )
    receipt = restic_backup.summarize_latest_snapshots(
        catalog={"controller_host": {"minio": {"bucket": "restic-config-backup"}}},
        sources=[source],
        repo_root=repo_root,
        credentials={"restic_password": "pw", "minio_secret_key": "secret", "nats_password": "x", "ntfy_password": "y"},
        endpoint="http://10.10.10.20:9000",
        cache_dir=tmp_path / "cache",
        restore_verify_dir=tmp_path / "restore",
        generated_at=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
    )

    assert receipt["summary"]["protected"] == 1
    assert receipt["summary"]["uncovered"] == 0
    assert receipt["sources"][0]["state"] == "protected"
    assert receipt["sources"][0]["freshness_policy"] == "event_driven"


def test_repo_surfaces_register_restic_backup_contract() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())["workflows"]
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())["commands"]
    execution_scopes = EXECUTION_SCOPES_PATH.read_text(encoding="utf-8")

    assert "restic-config-backup" in workflow_catalog
    assert "restic-config-restore-verify" in workflow_catalog
    assert "converge-restic-config-backup" in workflow_catalog
    assert command_catalog["run-restic-config-backup"]["workflow_id"] == "restic-config-backup"
    assert command_catalog["run-restic-config-restore-verify"]["workflow_id"] == "restic-config-restore-verify"
    assert command_catalog["converge-restic-config-backup"]["workflow_id"] == "converge-restic-config-backup"
    assert "playbooks/restic-config-backup.yml" in execution_scopes


def test_trigger_remote_command_includes_live_apply_flag() -> None:
    command = trigger.build_remote_command(
        mode="backup",
        triggered_by="manual",
        repo_root="/srv/proxmox_florin_server",
        credential_file="/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json",
        live_apply_trigger=True,
    )

    assert "--live-apply-trigger" in command
