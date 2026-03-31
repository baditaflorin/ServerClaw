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
CONTROL_PLANE_LANES_PATH = REPO_ROOT / "config" / "control-plane-lanes.json"


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


def test_summarize_latest_snapshots_clamps_negative_interval_age(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "receipts").mkdir(parents=True)
    (repo_root / "receipts" / "one.json").write_text("{}\n", encoding="utf-8")

    restic_backup.restic_call = lambda *args, **kwargs: types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "id": "snap-receipts",
                    "time": "2026-03-30T12:00:01Z",
                    "hostname": "docker-runtime-lv3",
                    "paths": [str(repo_root / "receipts")],
                    "tags": ["source:receipts", "source-label:receipts"],
                    "summary": {"total_files_processed": 1},
                }
            ]
        ),
        stderr="",
    )

    source = restic_backup.Source(
        "receipts",
        "receipts",
        (repo_root / "receipts",),
        360,
        "interval",
        "every_6_hours",
        {"keep_daily": 90},
        False,
        False,
        {"path": "receipts", "expected_minimum_files": 1},
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

    assert receipt["sources"][0]["reasons"][0].startswith("Latest snapshot is 0 minutes old")


def test_snapshot_id_from_backup_stdout_reads_restic_json_stream() -> None:
    stdout = "\n".join(
        [
            json.dumps({"message_type": "status", "percent_done": 50}),
            json.dumps({"message_type": "summary", "snapshot_id": "abc123", "files_new": 2}),
        ]
    )

    assert restic_backup.snapshot_id_from_backup_stdout(stdout) == "abc123"


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


def test_control_plane_lane_routes_backup_topic_family() -> None:
    lanes = json.loads(CONTROL_PLANE_LANES_PATH.read_text())
    event_surfaces = lanes["lanes"]["event"]["current_surfaces"]
    backup_surface = next(surface for surface in event_surfaces if surface["id"] == "platform-backup-subjects")

    assert backup_surface["endpoint"] == "platform.backup.*"


def test_trigger_remote_command_includes_live_apply_flag() -> None:
    command = trigger.build_remote_command(
        mode="backup",
        triggered_by="manual",
        repo_root="/srv/proxmox_florin_server",
        credential_file="/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json",
        live_apply_trigger=True,
    )

    assert "--live-apply-trigger" in command


def test_makefile_live_apply_targets_invoke_restic_trigger_with_pyyaml() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert (
        "uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode backup --triggered-by live-apply-group --live-apply-trigger"
        in makefile
    )
    assert (
        "uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode backup --triggered-by live-apply-service --live-apply-trigger"
        in makefile
    )
    assert (
        "uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode backup --triggered-by live-apply-site --live-apply-trigger"
        in makefile
    )
    assert (
        'uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env "$(or $(env),production)" --mode backup --triggered-by live-apply-waves --live-apply-trigger'
        in makefile
    )


def test_post_ntfy_notification_uses_human_readable_title(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["title"] = request.headers["Title"]
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(restic_backup.urllib.request, "urlopen", fake_urlopen)

    result = restic_backup.post_ntfy_notification(
        {"controller_host": {"ntfy": {"url": "http://127.0.0.1:2586", "topic": "platform-alerts"}}},
        {"ntfy_password": "secret"},
        "stale backup detected",
    )

    assert result["status"] == "sent"
    assert captured["title"] == "Restic backup critical"
    assert captured["body"] == "stale backup detected"


def test_emit_stale_signals_uses_human_readable_notification_text(tmp_path: Path, monkeypatch) -> None:
    latest_receipt = {
        "recorded_at": "2026-03-31T06:02:17Z",
        "sources": [
            {
                "source_id": "receipts",
                "freshness_policy": "interval",
                "state": "uncovered",
                "reasons": ["Latest snapshot is 420 minutes old; threshold is 390 minutes."],
                "freshness_minutes": 360,
            }
        ],
    }
    receipt_path = tmp_path / "latest.json"
    messages: list[str] = []

    monkeypatch.setattr(
        restic_backup,
        "publish_stale_event",
        lambda catalog, credentials, payload: {"channel": "nats", "status": "sent", "payload": payload},
    )

    def fake_post_ntfy_notification(catalog, credentials, message):
        messages.append(message)
        return {"channel": "ntfy", "status": "sent"}

    monkeypatch.setattr(restic_backup, "post_ntfy_notification", fake_post_ntfy_notification)

    notifications = restic_backup.emit_stale_signals(
        catalog={"controller_host": {}},
        credentials={"nats_password": "x", "ntfy_password": "y"},
        latest_receipt=latest_receipt,
        latest_receipt_path=receipt_path,
    )

    assert len(notifications) == 2
    assert messages == [
        "Restic backup source is stale\n"
        "Source: receipts\n"
        f"Latest snapshot receipt: {receipt_path}\n"
        "Latest snapshot is 420 minutes old; threshold is 390 minutes."
    ]
