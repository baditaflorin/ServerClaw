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


def test_refresh_latest_snapshot_receipt_for_live_apply_updates_cached_entries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "versions").mkdir(parents=True)
    (repo_root / "config" / "service.yml").write_text("service: value\n", encoding="utf-8")
    (repo_root / "versions" / "stack.yaml").write_text("platform_version: 0.130.75\n", encoding="utf-8")

    config_source = restic_backup.Source(
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
    versions_source = restic_backup.Source(
        "versions_stack",
        "versions_stack",
        (repo_root / "versions" / "stack.yaml",),
        1440,
        "event_driven",
        "successful_live_apply",
        {"keep_daily": 30},
        True,
        False,
        None,
    )
    receipts_source = restic_backup.Source(
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

    existing = {
        "schema_version": "1.0.0",
        "recorded_at": "2026-03-31T06:01:31Z",
        "recorded_on": "2026-03-31",
        "recorded_by": "codex",
        "repository": {"bucket": "restic-config-backup", "endpoint": "http://10.200.18.3:9000"},
        "summary": {
            "governed_sources": 3,
            "protected": 3,
            "uncovered": 0,
            "inactive": 0,
            "uncovered_sources": [],
            "inactive_sources": [],
        },
        "sources": [
            {
                "source_id": "receipts",
                "label": "receipts",
                "paths": ["receipts"],
                "state": "protected",
                "expected_schedule": "every_6_hours",
                "freshness_minutes": 360,
                "freshness_policy": "interval",
                "retention": {"keep_daily": 90},
                "latest_snapshot": {
                    "snapshot_id": "receipts-old",
                    "recorded_at": "2026-03-31T06:01:31Z",
                    "host": "docker-runtime-lv3",
                    "paths": ["receipts"],
                    "files": 10,
                },
                "last_restore_verification": None,
                "reasons": ["Latest snapshot is 0 minutes old and within the 390 minute freshness window."],
            },
            {
                "source_id": "config",
                "label": "config",
                "paths": ["config"],
                "state": "protected",
                "expected_schedule": "successful_live_apply",
                "freshness_minutes": 1440,
                "freshness_policy": "event_driven",
                "retention": {"keep_daily": 30},
                "latest_snapshot": {
                    "snapshot_id": "config-old",
                    "recorded_at": "2026-03-31T05:53:48Z",
                    "host": "docker-runtime-lv3",
                    "paths": ["config"],
                    "files": 230,
                },
                "last_restore_verification": None,
                "reasons": ["Latest snapshot exists and this source is governed by the event-driven 'successful_live_apply' policy."],
            },
            {
                "source_id": "versions_stack",
                "label": "versions_stack",
                "paths": ["versions/stack.yaml"],
                "state": "protected",
                "expected_schedule": "successful_live_apply",
                "freshness_minutes": 1440,
                "freshness_policy": "event_driven",
                "retention": {"keep_daily": 30},
                "latest_snapshot": {
                    "snapshot_id": "versions-old",
                    "recorded_at": "2026-03-31T05:53:49Z",
                    "host": "docker-runtime-lv3",
                    "paths": ["versions/stack.yaml"],
                    "files": 1,
                },
                "last_restore_verification": None,
                "reasons": ["Latest snapshot exists and this source is governed by the event-driven 'successful_live_apply' policy."],
            },
        ],
    }

    refreshed = restic_backup.refresh_latest_snapshot_receipt_for_live_apply(
        existing_receipt=existing,
        sources=[receipts_source, config_source, versions_source],
        source_results=[
            {"source_id": "config", "result": "backed_up", "snapshot_id": "config-new", "files": 239},
            {"source_id": "versions_stack", "result": "backed_up", "snapshot_id": "versions-new", "files": 1},
        ],
        repo_root=repo_root,
        endpoint="http://10.200.35.3:9000",
        host_name="docker-runtime-lv3",
        generated_at=datetime(2026, 3, 31, 10, 47, 15, tzinfo=UTC),
        bucket="restic-config-backup",
    )

    assert refreshed["repository"]["endpoint"] == "http://10.200.35.3:9000"
    assert refreshed["summary"]["protected"] == 3
    refreshed_sources = {entry["source_id"]: entry for entry in refreshed["sources"]}
    assert refreshed_sources["receipts"]["latest_snapshot"]["snapshot_id"] == "receipts-old"
    assert refreshed_sources["config"]["latest_snapshot"]["snapshot_id"] == "config-new"
    assert refreshed_sources["versions_stack"]["latest_snapshot"]["snapshot_id"] == "versions-new"


def test_build_live_apply_latest_snapshot_receipt_without_cache_only_reports_live_apply_sources(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True)
    (repo_root / "versions").mkdir(parents=True)
    (repo_root / "config" / "service.yml").write_text("service: value\n", encoding="utf-8")
    (repo_root / "versions" / "stack.yaml").write_text("platform_version: 0.130.77\n", encoding="utf-8")

    config_source = restic_backup.Source(
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
    versions_source = restic_backup.Source(
        "versions_stack",
        "versions_stack",
        (repo_root / "versions" / "stack.yaml",),
        1440,
        "event_driven",
        "successful_live_apply",
        {"keep_daily": 30},
        True,
        False,
        None,
    )
    receipts_source = restic_backup.Source(
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

    refreshed = restic_backup.build_live_apply_latest_snapshot_receipt(
        existing_receipt=None,
        resolved_sources=[receipts_source, config_source, versions_source],
        live_apply_sources=[config_source, versions_source],
        source_results=[
            {"source_id": "config", "result": "backed_up", "snapshot_id": "config-new", "files": 239},
            {"source_id": "versions_stack", "result": "backed_up", "snapshot_id": "versions-new", "files": 1},
        ],
        repo_root=repo_root,
        endpoint="http://10.200.35.3:9000",
        host_name="docker-runtime-lv3",
        generated_at=datetime(2026, 3, 31, 10, 47, 15, tzinfo=UTC),
        bucket="restic-config-backup",
    )

    assert refreshed["summary"]["governed_sources"] == 2
    assert refreshed["summary"]["protected"] == 2
    assert refreshed["summary"]["uncovered"] == 0
    assert [entry["source_id"] for entry in refreshed["sources"]] == ["config", "versions_stack"]


def test_snapshot_id_from_backup_stdout_reads_restic_json_stream() -> None:
    stdout = "\n".join(
        [
            json.dumps({"message_type": "status", "percent_done": 50}),
            json.dumps({"message_type": "summary", "snapshot_id": "abc123", "files_new": 2}),
        ]
    )

    assert restic_backup.snapshot_id_from_backup_stdout(stdout) == "abc123"


def test_resolve_minio_endpoint_recovers_compose_managed_container(monkeypatch) -> None:
    calls: list[list[str]] = []
    inspect_count = 0

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_run_command(argv, **kwargs):
        nonlocal inspect_count
        calls.append(argv)
        if argv == ["docker", "inspect", "minio"]:
            inspect_count += 1
            running = inspect_count > 1
            return types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "State": {"Running": running},
                            "Config": {
                                "Labels": {
                                    "com.docker.compose.project.working_dir": "/opt/outline",
                                    "com.docker.compose.project.config_files": "/opt/outline/docker-compose.yml",
                                    "com.docker.compose.service": "minio",
                                }
                            },
                            "NetworkSettings": {
                                "Networks": {
                                    "broken": {"IPAddress": "invalid IP"},
                                    "outline_default": {"IPAddress": "10.200.18.2" if running else ""},
                                }
                            },
                        }
                    ]
                ),
                stderr="",
            )
        if argv == ["docker", "compose", "--file", "/opt/outline/docker-compose.yml", "up", "-d", "minio"]:
            return types.SimpleNamespace(returncode=0, stdout="started\n", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(restic_backup, "run_command", fake_run_command)
    monkeypatch.setattr(restic_backup.time, "sleep", lambda _: None)
    monkeypatch.setattr(restic_backup.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    host, endpoint = restic_backup.resolve_minio_endpoint({"controller_host": {"minio": {"container_name": "minio"}}})

    assert host == "10.200.18.2"
    assert endpoint == "http://10.200.18.2:9000"
    assert calls == [
        ["docker", "inspect", "minio"],
        ["docker", "compose", "--file", "/opt/outline/docker-compose.yml", "up", "-d", "minio"],
        ["docker", "inspect", "minio"],
    ]


def test_resolve_minio_endpoint_starts_standalone_stopped_container(monkeypatch) -> None:
    calls: list[list[str]] = []
    inspect_count = 0

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_run_command(argv, **kwargs):
        nonlocal inspect_count
        calls.append(argv)
        if argv == ["docker", "inspect", "outline-minio"]:
            inspect_count += 1
            running = inspect_count > 1
            return types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "State": {"Running": running},
                            "Config": {"Labels": {}},
                            "NetworkSettings": {
                                "Networks": {
                                    "bridge": {"IPAddress": "10.200.18.2" if running else ""},
                                }
                            },
                        }
                    ]
                ),
                stderr="",
            )
        if argv == ["docker", "start", "outline-minio"]:
            return types.SimpleNamespace(returncode=0, stdout="outline-minio\n", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(restic_backup, "run_command", fake_run_command)
    monkeypatch.setattr(restic_backup.time, "sleep", lambda _: None)
    monkeypatch.setattr(restic_backup.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    host, endpoint = restic_backup.resolve_minio_endpoint(
        {"controller_host": {"minio": {"container_name": "outline-minio"}}}
    )

    assert host == "10.200.18.2"
    assert endpoint == "http://10.200.18.2:9000"
    assert calls == [
        ["docker", "inspect", "outline-minio"],
        ["docker", "start", "outline-minio"],
        ["docker", "inspect", "outline-minio"],
    ]


def test_repo_surfaces_register_restic_backup_contract() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())["workflows"]
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())["commands"]
    execution_scopes = EXECUTION_SCOPES_PATH.read_text(encoding="utf-8")

    assert "restic-config-backup" in workflow_catalog
    assert "restic-config-restore-verify" in workflow_catalog
    assert "converge-restic-config-backup" in workflow_catalog
    assert workflow_catalog["converge-restic-config-backup"]["preflight"]["required_secret_ids"][1] == "minio_root_password"
    assert command_catalog["run-restic-config-backup"]["workflow_id"] == "restic-config-backup"
    assert command_catalog["run-restic-config-restore-verify"]["workflow_id"] == "restic-config-restore-verify"
    assert command_catalog["converge-restic-config-backup"]["workflow_id"] == "converge-restic-config-backup"
    assert command_catalog["converge-restic-config-backup"]["inputs"][1]["name"] == "minio_root_password"
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


def test_ensure_remote_runtime_support_files_uploads_required_bundle(tmp_path: Path, monkeypatch) -> None:
    scripts_dir = tmp_path / "scripts"
    config_dir = tmp_path / "config"
    scripts_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    (scripts_dir / "restic_config_backup.py").write_text("#!/usr/bin/env python3\nprint('restic')\n", encoding="utf-8")
    (scripts_dir / "script_bootstrap.py").write_text("print('bootstrap')\n", encoding="utf-8")
    (scripts_dir / "controller_automation_toolkit.py").write_text("print('toolkit')\n", encoding="utf-8")
    (config_dir / "restic-file-backup-catalog.json").write_text('{"schema_version":"1.0.0"}\n', encoding="utf-8")

    captured: list[tuple[str, str]] = []

    monkeypatch.setattr(trigger, "LOCAL_REPO_ROOT", tmp_path)

    def fake_build_guest_ssh_command(context, target, remote_command):
        captured.append((target, remote_command))
        return ["ssh", target]

    def fake_run(command, input=None, text=None, capture_output=None, check=None):
        captured.append(("stdin", input))
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(trigger, "build_guest_ssh_command", fake_build_guest_ssh_command)
    monkeypatch.setattr(trigger.subprocess, "run", fake_run)

    trigger.ensure_remote_runtime_support_files({"controller": "context"}, repo_root="/srv/proxmox_florin_server")

    remote_commands = [entry for entry in captured if entry[0] != "stdin"]
    stdin_payloads = [entry[1] for entry in captured if entry[0] == "stdin"]

    assert len(remote_commands) == 4
    assert len(stdin_payloads) == 4
    assert any("/srv/proxmox_florin_server/scripts/restic_config_backup.py" in command for _, command in remote_commands)
    assert any("/srv/proxmox_florin_server/scripts/script_bootstrap.py" in command for _, command in remote_commands)
    assert any("/srv/proxmox_florin_server/scripts/controller_automation_toolkit.py" in command for _, command in remote_commands)
    assert any("/srv/proxmox_florin_server/config/restic-file-backup-catalog.json" in command for _, command in remote_commands)
    assert all("sudo tee" in command for _, command in remote_commands)
    assert stdin_payloads[0].startswith("#!/usr/bin/env python3")


def test_trigger_main_syncs_runtime_support_files_before_remote_execution(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(trigger, "load_controller_context", lambda: {"controller": "context"})
    monkeypatch.setattr(
        trigger,
        "ensure_remote_runtime_support_files",
        lambda context, repo_root, target="docker-runtime-lv3": captured.update(
            {"context": context, "repo_root": repo_root, "target": target}
        ),
    )
    monkeypatch.setattr(trigger, "build_guest_ssh_command", lambda context, target, remote_command: ["ssh", target, remote_command])
    monkeypatch.setattr(
        trigger,
        "run_command",
        lambda command: types.SimpleNamespace(returncode=0, stdout='REPORT_JSON={"summary":{"protected":1}}', stderr=""),
    )

    assert (
        trigger.main(
            [
                "--env",
                "production",
                "--mode",
                "backup",
                "--repo-root",
                "/srv/proxmox_florin_server",
            ]
        )
        == 0
    )
    assert captured == {
        "context": {"controller": "context"},
        "repo_root": "/srv/proxmox_florin_server",
        "target": "docker-runtime-lv3",
    }


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
