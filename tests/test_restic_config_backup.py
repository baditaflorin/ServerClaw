from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "restic_config_backup.py"
TRIGGER_SCRIPT_PATH = REPO_ROOT / "scripts" / "trigger_restic_live_apply.py"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
CONTROL_PLANE_LANES_PATH = REPO_ROOT / "config" / "control-plane-lanes.json"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
RESTIC_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "restic-config-backup.yml"
RESTIC_ROLE_DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "restic_config_backup"
    / "defaults"
    / "main.yml"
)
RESTIC_ROLE_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "restic_config_backup"
    / "tasks"
    / "main.yml"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


restic_backup = _load_module(SCRIPT_PATH, "restic_config_backup")
trigger = _load_module(TRIGGER_SCRIPT_PATH, "trigger_restic_live_apply")


def test_load_runtime_credentials_requires_ntfy_token_by_default(tmp_path: Path) -> None:
    credential_path = tmp_path / "runtime-config.json"
    credential_path.write_text(
        json.dumps(
            {
                "restic_password": "pw",
                "minio_secret_key": "secret",
                "nats_password": "nats",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="runtime credential payload is missing ntfy_token"):
        restic_backup.load_runtime_credentials(credential_path)


def test_load_runtime_credentials_allows_live_apply_payload_without_ntfy_token(tmp_path: Path) -> None:
    credential_path = tmp_path / "runtime-config.json"
    credential_path.write_text(
        json.dumps(
            {
                "restic_password": "pw",
                "minio_secret_key": "secret",
                "nats_password": "nats",
            }
        ),
        encoding="utf-8",
    )

    credentials = restic_backup.load_runtime_credentials(
        credential_path,
        required_fields=("restic_password", "minio_secret_key", "nats_password"),
    )

    assert credentials == {
        "restic_password": "pw",
        "minio_secret_key": "secret",
        "nats_password": "nats",
    }


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
                    "hostname": "docker-runtime",
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
        credentials={"restic_password": "pw", "minio_secret_key": "secret", "nats_password": "x", "ntfy_token": "y"},
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
                    "hostname": "docker-runtime",
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
        credentials={"restic_password": "pw", "minio_secret_key": "secret", "nats_password": "x", "ntfy_token": "y"},
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
                    "host": "docker-runtime",
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
                    "host": "docker-runtime",
                    "paths": ["config"],
                    "files": 230,
                },
                "last_restore_verification": None,
                "reasons": [
                    "Latest snapshot exists and this source is governed by the event-driven 'successful_live_apply' policy."
                ],
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
                    "host": "docker-runtime",
                    "paths": ["versions/stack.yaml"],
                    "files": 1,
                },
                "last_restore_verification": None,
                "reasons": [
                    "Latest snapshot exists and this source is governed by the event-driven 'successful_live_apply' policy."
                ],
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
        host_name="docker-runtime",
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
        host_name="docker-runtime",
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
        if argv == ["docker", "inspect", "minio"]:
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
        if argv == ["docker", "start", "minio"]:
            return types.SimpleNamespace(returncode=0, stdout="minio\n", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(restic_backup, "run_command", fake_run_command)
    monkeypatch.setattr(restic_backup.time, "sleep", lambda _: None)
    monkeypatch.setattr(restic_backup.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    host, endpoint = restic_backup.resolve_minio_endpoint(
        {"controller_host": {"minio": {"container_name": "minio", "bucket": "restic-config-backup"}}}
    )

    assert host == "10.200.18.2"
    assert endpoint == "http://10.200.18.2:9000"
    assert calls == [
        ["docker", "inspect", "minio"],
        ["docker", "start", "minio"],
        ["docker", "inspect", "minio"],
        ["docker", "inspect", "minio"],
    ]


def test_resolve_minio_endpoint_force_recreates_running_compose_managed_container_without_network(
    monkeypatch,
) -> None:
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
            networks = {} if inspect_count == 1 else {"minio_default": {"IPAddress": "10.200.18.7"}}
            return types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "State": {"Running": True, "Status": "running"},
                            "Config": {
                                "Labels": {
                                    "com.docker.compose.project.working_dir": "/opt/minio",
                                    "com.docker.compose.project.config_files": "/opt/minio/docker-compose.yml",
                                    "com.docker.compose.service": "minio",
                                }
                            },
                            "NetworkSettings": {"Networks": networks},
                        }
                    ]
                ),
                stderr="",
            )
        if argv == [
            "docker",
            "compose",
            "--file",
            "/opt/minio/docker-compose.yml",
            "up",
            "-d",
            "--force-recreate",
            "minio",
        ]:
            return types.SimpleNamespace(returncode=0, stdout="recreated\n", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(restic_backup, "run_command", fake_run_command)
    monkeypatch.setattr(restic_backup.time, "sleep", lambda _: None)
    monkeypatch.setattr(restic_backup.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    host, endpoint = restic_backup.resolve_minio_endpoint(
        {"controller_host": {"minio": {"container_name": "minio", "bucket": "restic-config-backup"}}}
    )

    assert host == "10.200.18.7"
    assert endpoint == "http://10.200.18.7:9000"
    assert calls == [
        ["docker", "inspect", "minio"],
        ["docker", "compose", "--file", "/opt/minio/docker-compose.yml", "up", "-d", "--force-recreate", "minio"],
        ["docker", "inspect", "minio"],
        ["docker", "inspect", "minio"],
    ]


def test_resolve_minio_endpoint_falls_back_to_outline_minio_when_dedicated_minio_is_absent(monkeypatch) -> None:
    commands: list[list[str]] = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_run_command(argv, **kwargs):
        commands.append(argv)
        if argv == ["docker", "inspect", "minio"]:
            return types.SimpleNamespace(returncode=1, stdout="", stderr="Error: No such object: minio")
        if argv == ["docker", "inspect", "outline-minio"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "State": {"Running": True, "Status": "running"},
                            "NetworkSettings": {"Networks": {"outline_default": {"IPAddress": "10.200.18.2"}}},
                        }
                    ]
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(restic_backup, "run_command", fake_run_command)
    monkeypatch.setattr(restic_backup.time, "sleep", lambda _: None)
    monkeypatch.setattr(restic_backup.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    host, endpoint = restic_backup.resolve_minio_endpoint(
        {"controller_host": {"minio": {"container_name": "minio", "bucket": "restic-config-backup"}}}
    )

    assert host == "10.200.18.2"
    assert endpoint == "http://10.200.18.2:9000"
    assert commands == [
        ["docker", "inspect", "minio"],
        ["docker", "inspect", "outline-minio"],
        ["docker", "inspect", "outline-minio"],
    ]


def test_resolve_minio_endpoint_reports_failed_container_restart() -> None:
    def fake_run_command(argv, **kwargs):
        if argv[:2] == ["docker", "inspect"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "State": {"Running": False, "Status": "exited"},
                            "NetworkSettings": {"Networks": {"outline_default": {"IPAddress": ""}}},
                        }
                    ]
                ),
                stderr="",
            )
        if argv[:2] == ["docker", "start"]:
            return types.SimpleNamespace(returncode=1, stdout="", stderr="permission denied")
        raise AssertionError(f"unexpected command: {argv}")

    restic_backup.run_command = fake_run_command

    try:
        restic_backup.resolve_minio_endpoint(
            {"controller_host": {"minio": {"container_name": "minio", "bucket": "restic-config-backup"}}}
        )
    except RuntimeError as exc:
        assert "minio is exited" in str(exc)
        assert "docker start failed" in str(exc)
        assert "permission denied" in str(exc)
    else:
        raise AssertionError("Expected resolve_minio_endpoint to reject containers that cannot be restarted")


def test_resolve_minio_endpoint_rejects_invalid_container_ip_after_network_recovery(monkeypatch) -> None:
    monkeypatch.setattr(restic_backup.time, "sleep", lambda _: None)
    commands: list[list[str]] = []

    def fake_run_command(argv, **kwargs):
        commands.append(argv)
        if argv == ["docker", "inspect", "minio"]:
            return types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "State": {"Running": True, "Status": "running"},
                            "NetworkSettings": {"Networks": {"outline_default": {"IPAddress": "invalid IP"}}},
                        }
                    ]
                ),
                stderr="",
            )
        if argv == ["docker", "restart", "minio"]:
            return types.SimpleNamespace(returncode=0, stdout="minio\n", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    restic_backup.run_command = fake_run_command
    monkeypatch.setattr(
        restic_backup.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError())
    )

    try:
        restic_backup.resolve_minio_endpoint(
            {"controller_host": {"minio": {"container_name": "minio", "bucket": "restic-config-backup"}}}
        )
    except RuntimeError as exc:
        assert "minio reported an invalid container IP" in str(exc)
        assert ["docker", "restart", "minio"] in commands
    else:
        raise AssertionError("Expected resolve_minio_endpoint to reject invalid MinIO container IPs")


def test_resolve_minio_endpoint_prefers_valid_ipv4_address(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(restic_backup.time, "sleep", lambda _: None)
    restic_backup.run_command = lambda argv, **kwargs: types.SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "State": {"Running": True, "Status": "running"},
                    "NetworkSettings": {
                        "Networks": {
                            "outline_ipv6": {"GlobalIPv6Address": "2001:db8::10"},
                            "outline_default": {"IPAddress": "10.200.18.4"},
                        }
                    },
                }
            ]
        ),
        stderr="",
    )
    monkeypatch.setattr(restic_backup.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    host, endpoint = restic_backup.resolve_minio_endpoint(
        {"controller_host": {"minio": {"container_name": "minio", "bucket": "restic-config-backup"}}}
    )

    assert host == "10.200.18.4"
    assert endpoint == "http://10.200.18.4:9000"


def test_runtime_lock_can_be_reacquired_after_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "restic-config-backup.lock"

    with restic_backup.runtime_lock(
        lock_path=lock_path,
        mode="backup",
        triggered_by="manual",
        live_apply_trigger=False,
        timeout_seconds=0,
    ):
        holder = json.loads(lock_path.read_text(encoding="utf-8"))
        assert holder["mode"] == "backup"
        assert holder["triggered_by"] == "manual"

    with restic_backup.runtime_lock(
        lock_path=lock_path,
        mode="restore-verify",
        triggered_by="manual",
        live_apply_trigger=False,
        timeout_seconds=0,
    ):
        holder = json.loads(lock_path.read_text(encoding="utf-8"))
        assert holder["mode"] == "restore-verify"


def test_runtime_lock_reports_active_holder_when_timeout_elapses(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "restic-config-backup.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    holder = lock_path.open("w+", encoding="utf-8")
    holder.write('{"pid":999,"triggered_by":"live-apply-service"}\n')
    holder.flush()
    restic_backup.fcntl.flock(holder.fileno(), restic_backup.fcntl.LOCK_EX | restic_backup.fcntl.LOCK_NB)

    try:
        try:
            with restic_backup.runtime_lock(
                lock_path=lock_path,
                mode="backup",
                triggered_by="manual",
                live_apply_trigger=True,
                timeout_seconds=0,
            ):
                raise AssertionError("expected runtime_lock to reject the active holder")
        except RuntimeError as exc:
            assert "another restic config backup is still running" in str(exc)
            assert '"triggered_by":"live-apply-service"' in str(exc)
    finally:
        restic_backup.fcntl.flock(holder.fileno(), restic_backup.fcntl.LOCK_UN)
        holder.close()


def test_repo_surfaces_register_restic_backup_contract() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())["workflows"]
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())["commands"]
    execution_scopes = EXECUTION_SCOPES_PATH.read_text(encoding="utf-8")

    assert "restic-config-backup" in workflow_catalog
    assert "restic-config-restore-verify" in workflow_catalog
    assert "converge-restic-config-backup" in workflow_catalog
    assert (
        workflow_catalog["converge-restic-config-backup"]["preflight"]["required_secret_ids"][1]
        == "minio_root_password"
    )
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
        repo_root="/srv/proxmox-host_server",
        credential_file="/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json",
        live_apply_trigger=True,
    )

    assert "--live-apply-trigger" in command


def test_trigger_remote_command_falls_back_to_api_gateway_script_and_keeps_repo_surfaces() -> None:
    command = trigger.build_remote_command(
        mode="backup",
        triggered_by="manual",
        repo_root="/srv/proxmox-host_server",
        credential_file="/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json",
        live_apply_trigger=False,
    )

    assert "/opt/api-gateway/service/scripts/restic_config_backup.py" in command
    assert "/srv/proxmox-host_server/config/restic-file-backup-catalog.json" in command
    assert "/etc/lv3/restic-config-backup/restic-file-backup-catalog.json" in command
    assert "/srv/proxmox-host_server/receipts/restic-backups" in command
    assert "/srv/proxmox-host_server/receipts/restic-restore-verifications" in command


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

    trigger.ensure_remote_runtime_support_files({"controller": "context"}, repo_root="/srv/proxmox-host_server")

    remote_commands = [entry for entry in captured if entry[0] != "stdin"]
    stdin_payloads = [entry[1] for entry in captured if entry[0] == "stdin"]

    assert len(remote_commands) == 4
    assert len(stdin_payloads) == 4
    assert any("/srv/proxmox-host_server/scripts/restic_config_backup.py" in command for _, command in remote_commands)
    assert any("/srv/proxmox-host_server/scripts/script_bootstrap.py" in command for _, command in remote_commands)
    assert any(
        "/srv/proxmox-host_server/scripts/controller_automation_toolkit.py" in command for _, command in remote_commands
    )
    assert any(
        "/srv/proxmox-host_server/config/restic-file-backup-catalog.json" in command for _, command in remote_commands
    )
    assert all("sudo tee" in command for _, command in remote_commands)
    assert stdin_payloads[0].startswith("#!/usr/bin/env python3")


def test_sync_reported_receipt_artifacts_downloads_reported_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(trigger, "LOCAL_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        trigger,
        "fetch_remote_repo_file",
        lambda context, target, repo_root, relative_path: (
            json.dumps({"path": relative_path, "repo_root": repo_root, "target": target}) + "\n"
        ),
    )

    synced = trigger.sync_reported_receipt_artifacts(
        {"controller": "context"},
        target="docker-runtime",
        repo_root="/srv/proxmox-host_server",
        report={
            "receipt_path": "receipts/restic-backups/20260401T112837Z.json",
            "latest_snapshot_receipt": "receipts/restic-snapshots-latest.json",
        },
    )

    assert synced == [
        "receipts/restic-backups/20260401T112837Z.json",
        "receipts/restic-snapshots-latest.json",
    ]
    assert json.loads(
        (tmp_path / "receipts" / "restic-backups" / "20260401T112837Z.json").read_text(encoding="utf-8")
    ) == {
        "path": "receipts/restic-backups/20260401T112837Z.json",
        "repo_root": "/srv/proxmox-host_server",
        "target": "docker-runtime",
    }
    assert json.loads((tmp_path / "receipts" / "restic-snapshots-latest.json").read_text(encoding="utf-8")) == {
        "path": "receipts/restic-snapshots-latest.json",
        "repo_root": "/srv/proxmox-host_server",
        "target": "docker-runtime",
    }


def test_ensure_remote_runtime_credentials_runs_converge_when_missing(monkeypatch) -> None:
    exists_sequence = iter([False, True])
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        trigger,
        "remote_file_exists",
        lambda context, target, path: next(exists_sequence),
    )
    monkeypatch.setattr(
        trigger,
        "run_local_converge_restic",
        lambda env: captured.update({"env": env}),
    )

    trigger.ensure_remote_runtime_credentials(
        {"controller": "context"},
        env="production",
        credential_file="/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json",
    )

    assert captured == {"env": "production"}


def test_ensure_remote_runtime_credentials_raises_when_converge_does_not_restore_file(monkeypatch) -> None:
    monkeypatch.setattr(
        trigger,
        "remote_file_exists",
        lambda context, target, path: False,
    )
    monkeypatch.setattr(trigger, "run_local_converge_restic", lambda env: None)

    try:
        trigger.ensure_remote_runtime_credentials(
            {"controller": "context"},
            env="production",
            credential_file="/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json",
        )
    except RuntimeError as exc:
        assert "restic runtime credentials are still missing" in str(exc)
    else:
        raise AssertionError(
            "expected ensure_remote_runtime_credentials to fail when the credential file stays missing"
        )


def test_trigger_main_syncs_runtime_support_files_before_remote_execution(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(trigger, "load_controller_context", lambda: {"controller": "context"})
    monkeypatch.setattr(
        trigger,
        "ensure_remote_runtime_support_files",
        lambda context, repo_root, target="docker-runtime": captured.update(
            {"context": context, "repo_root": repo_root, "target": target}
        ),
    )
    monkeypatch.setattr(
        trigger,
        "ensure_remote_runtime_credentials",
        lambda context, env, credential_file, target="docker-runtime": captured.update(
            {
                "credential_context": context,
                "credential_env": env,
                "credential_file": credential_file,
                "credential_target": target,
            }
        ),
    )
    monkeypatch.setattr(
        trigger, "build_guest_ssh_command", lambda context, target, remote_command: ["ssh", target, remote_command]
    )
    monkeypatch.setattr(
        trigger,
        "run_command",
        lambda command: types.SimpleNamespace(
            returncode=0, stdout='REPORT_JSON={"summary":{"protected":1}}', stderr=""
        ),
    )
    monkeypatch.setattr(
        trigger,
        "sync_reported_receipt_artifacts",
        lambda context, target, repo_root, report: (
            captured.update(
                {
                    "sync_context": context,
                    "sync_target": target,
                    "sync_repo_root": repo_root,
                    "sync_report": report,
                }
            )
            or ["receipts/restic-snapshots-latest.json"]
        ),
    )

    assert (
        trigger.main(
            [
                "--env",
                "production",
                "--mode",
                "backup",
                "--repo-root",
                "/srv/proxmox-host_server",
            ]
        )
        == 0
    )
    assert captured == {
        "context": {"controller": "context"},
        "repo_root": "/srv/proxmox-host_server",
        "target": "docker-runtime",
        "credential_context": {"controller": "context"},
        "credential_env": "production",
        "credential_file": "/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json",
        "credential_target": "docker-runtime",
        "sync_context": {"controller": "context"},
        "sync_target": "docker-runtime",
        "sync_repo_root": "/srv/proxmox-host_server",
        "sync_report": {"summary": {"protected": 1}},
    }


def test_main_live_apply_backup_omits_ntfy_requirement(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_load_runtime_credentials(path, *, required_fields):
        captured["required_fields"] = required_fields
        return {
            "restic_password": "pw",
            "minio_secret_key": "secret",
            "nats_password": "nats",
        }

    monkeypatch.setattr(
        restic_backup,
        "load_catalog",
        lambda path: ({"controller_host": {"minio": {"bucket": "restic-config-backup"}}}, []),
    )
    monkeypatch.setattr(restic_backup, "load_runtime_credentials", fake_load_runtime_credentials)
    monkeypatch.setattr(restic_backup, "ensure_directory", lambda path: None)
    monkeypatch.setattr(
        restic_backup,
        "runtime_lock",
        lambda **kwargs: types.SimpleNamespace(
            __enter__=lambda self: None, __exit__=lambda self, exc_type, exc, tb: False
        ),
    )
    monkeypatch.setattr(
        restic_backup, "resolve_minio_endpoint", lambda catalog: ("10.10.10.20", "http://10.10.10.20:9000")
    )
    monkeypatch.setattr(restic_backup, "ensure_restic_repository", lambda **kwargs: None)
    monkeypatch.setattr(restic_backup, "resolve_source_paths", lambda raw_sources, repo_root: [])
    monkeypatch.setattr(restic_backup, "filter_sources", lambda sources, only_live_apply: [])
    monkeypatch.setattr(
        restic_backup,
        "restic_call",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    monkeypatch.setattr(restic_backup, "load_existing_latest_snapshot_receipt", lambda path: None)
    monkeypatch.setattr(
        restic_backup,
        "build_live_apply_latest_snapshot_receipt",
        lambda **kwargs: {"summary": {"protected": 0, "governed_sources": 0, "uncovered": 0}, "sources": []},
    )
    monkeypatch.setattr(restic_backup, "write_json", lambda path, payload: None)
    monkeypatch.setattr(restic_backup, "repo_source_commit", lambda repo_root: "abc123")
    monkeypatch.setattr(restic_backup, "build_backup_receipt", lambda **kwargs: {"status": "ok"})
    monkeypatch.setattr(restic_backup, "utc_now", lambda: datetime(2026, 4, 3, 10, 0, tzinfo=UTC))

    class _FakeLock:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(restic_backup, "runtime_lock", lambda **kwargs: _FakeLock())

    result = restic_backup.main(
        [
            "--repo-root",
            str(tmp_path / "repo"),
            "--catalog",
            str(tmp_path / "catalog.json"),
            "--backup-receipts-dir",
            str(tmp_path / "receipts" / "backups"),
            "--latest-snapshot-receipt",
            str(tmp_path / "receipts" / "latest.json"),
            "--restore-verification-dir",
            str(tmp_path / "receipts" / "restore"),
            "--runtime-state-dir",
            str(tmp_path / "state"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--credential-file",
            str(tmp_path / "runtime-config.json"),
            "--mode",
            "backup",
            "--triggered-by",
            "live-apply-service",
            "--live-apply-trigger",
        ]
    )

    assert result == 0
    assert captured["required_fields"] == ("restic_password", "minio_secret_key", "nats_password")


def test_restic_role_prefers_runtime_control_openbao_with_local_fallback() -> None:
    defaults = RESTIC_ROLE_DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = RESTIC_ROLE_TASKS_PATH.read_text(encoding="utf-8")

    assert "restic_config_backup_openbao_service_topology" in defaults
    assert "restic_config_backup_runtime_openbao_address" in defaults
    assert "restic_config_backup_runtime_openbao_local_address" in defaults
    assert "Probe whether the dedicated OpenBao API is reachable from the backup runtime" in tasks
    assert "restic_config_backup_runtime_openbao_effective_address" in tasks
    assert (
        'common_openbao_systemd_credentials_openbao_address: "{{ restic_config_backup_runtime_openbao_effective_address }}"'
        in tasks
    )
    assert (
        'common_openbao_systemd_credentials_manage_local_openbao_runtime: "{{ restic_config_backup_runtime_openbao_effective_manage_local_runtime }}"'
        in tasks
    )


def test_restic_playbook_enables_bridge_chain_recovery_on_docker_runtime() -> None:
    playbook = yaml.safe_load(RESTIC_PLAYBOOK_PATH.read_text(encoding="utf-8"))
    roles = playbook[0]["roles"]
    firewall_role = next(role for role in roles if role["role"] == "lv3.platform.linux_guest_firewall")

    assert firewall_role["vars"]["linux_guest_firewall_recover_missing_docker_bridge_chains"] is True


def test_make_live_apply_targets_bootstrap_pyyaml_for_restic_trigger() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    for target in ("live-apply-group", "live-apply-service", "live-apply-site", "live-apply-waves"):
        start = makefile.index(f"{target}:")
        next_target = makefile.find("\n\n", start)
        if next_target == -1:
            next_target = len(makefile)
        block = makefile[start:next_target]
        assert "uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py" in block
        assert "--syntax-check" in block
        assert "skipping canonical truth gate for syntax-check run" in block
        assert "skipping restic live-apply trigger for syntax-check run" in block


def test_post_ntfy_notification_uses_human_readable_title(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_command(argv, *, env=None, cwd=None, timeout=None):
        captured["argv"] = argv
        captured["cwd"] = cwd
        captured["timeout"] = timeout
        return types.SimpleNamespace(returncode=0, stdout='{"status":"published"}', stderr="")

    monkeypatch.setattr(restic_backup, "run_command", fake_run_command)

    result = restic_backup.post_ntfy_notification(
        {
            "controller_host": {
                "ntfy": {
                    "url": "http://10.10.10.20:2586",
                    "topic": "platform-backup-critical",
                    "publisher": "windmill",
                }
            }
        },
        {"ntfy_token": "secret"},
        "stale backup detected",
    )

    assert result["status"] == "sent"
    argv = captured["argv"]
    assert "--publisher" in argv
    assert argv[argv.index("--publisher") + 1] == "windmill"
    assert "--topic" in argv
    assert argv[argv.index("--topic") + 1] == "platform-backup-critical"
    assert "--title" in argv
    assert argv[argv.index("--title") + 1] == "Restic backup critical"
    assert "--message" in argv
    assert argv[argv.index("--message") + 1] == "stale backup detected"


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
        credentials={"nats_password": "x", "ntfy_token": "y"},
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
