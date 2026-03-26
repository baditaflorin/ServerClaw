from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "merge-config-changes.py"
SYNC_HELPER_PATH = REPO_ROOT / "scripts" / "sync_windmill_seed_scripts.py"
SCHEDULE_SYNC_HELPER_PATH = REPO_ROOT / "scripts" / "sync_windmill_seed_schedules.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_wrapper_blocks_when_repo_checkout_is_missing(tmp_path: Path) -> None:
    module = load_module("config_merge_missing", WRAPPER_PATH)
    payload = module.main(repo_path=str(tmp_path / "missing"))
    assert payload["status"] == "blocked"


def test_wrapper_executes_repo_script_via_uv_and_parses_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("config_merge_ok", WRAPPER_PATH)
    repo_root = tmp_path
    (repo_root / "scripts").mkdir(parents=True)
    (repo_root / "scripts" / "config_merge_protocol.py").write_text("# repo stub\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(command, cwd, text, capture_output, check):
        captured["command"] = command
        captured["cwd"] = cwd
        assert text is True
        assert capture_output is True
        assert check is False
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": "ok", "argv": command[4:]}),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root), dsn="sqlite:////tmp/config-merge.sqlite3", publish_nats=True)

    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "ok"
    assert captured["cwd"] == repo_root
    assert captured["command"] == [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "--with",
        "psycopg[binary]",
        "python3",
        str(repo_root / "scripts" / "config_merge_protocol.py"),
        "--repo-root",
        str(repo_root),
        "merge",
        "--dsn",
        "sqlite:////tmp/config-merge.sqlite3",
        "--actor",
        "agent/config-merge-job",
        "--publish-nats",
    ]
    assert "--publish-nats" in payload["result"]["argv"]


def test_wrapper_reads_dsn_from_proc_environ_fallback(tmp_path: Path) -> None:
    module = load_module("config_merge_proc_env", WRAPPER_PATH)
    proc_environ = tmp_path / "proc-1-environ"
    proc_environ.write_bytes(
        b"PATH=/usr/bin\0DATABASE_URL=postgres://windmill_admin:secret@10.10.10.50:5432/windmill?sslmode=disable\0"
    )

    assert (
        module.resolve_dsn(None, proc_environ_path=str(proc_environ))
        == "postgres://windmill_admin:secret@10.10.10.50:5432/windmill?sslmode=disable"
    )


def test_sync_helper_tolerates_missing_row_delete_response(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_missing_rows", SYNC_HELPER_PATH)

    def fake_request_json_or_text(**kwargs):
        assert kwargs["method"] == "POST"
        return 400, "No rows returned"

    monkeypatch.setattr(module, "request_json_or_text", fake_request_json_or_text)

    module.delete_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        script_path="f/lv3/config_merge/merge_config_changes",
    )


def test_sync_helper_rejects_unexpected_delete_400(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_bad_delete", SYNC_HELPER_PATH)

    def fake_request_json_or_text(**kwargs):
        assert kwargs["method"] == "POST"
        return 400, "constraint violation"

    monkeypatch.setattr(module, "request_json_or_text", fake_request_json_or_text)

    with pytest.raises(module.SyncError, match="returned 400"):
        module.delete_script(
            base_url="http://windmill.internal",
            workspace="lv3",
            token="token",
            script_path="f/lv3/config_merge/merge_config_changes",
        )


def test_sync_helper_bootstraps_repo_platform_package(monkeypatch: pytest.MonkeyPatch) -> None:
    import platform as stdlib_platform
    import sys

    monkeypatch.setitem(sys.modules, "platform", stdlib_platform)

    module = load_module("sync_helper_repo_platform", SYNC_HELPER_PATH)

    assert hasattr(module, "with_retry")
    assert module.REPO_ROOT == REPO_ROOT


def test_sync_helper_reports_missing_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    module = load_module("sync_helper_missing_token", SYNC_HELPER_PATH)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]\n", encoding="utf-8")

    monkeypatch.delenv("WINDMILL_TOKEN", raising=False)
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {
                "base_url": "http://windmill.internal",
                "workspace": "lv3",
                "manifest": manifest,
                "max_attempts": 1,
                "settle_interval": 0.0,
            },
        )(),
    )

    assert module.main() == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["reason"] == "WINDMILL_TOKEN is required"


def test_sync_helper_retries_connection_reset_during_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("sync_helper_retry_reset", SYNC_HELPER_PATH)
    local_file = tmp_path / "script.py"
    local_file.write_text("print('ok')\n", encoding="utf-8")
    spec = {
        "path": "f/lv3/operator_onboard",
        "local_file": str(local_file),
        "language": "python3",
        "summary": "ADR 0108 operator onboarding",
        "description": "Repo-managed sync test",
    }
    attempts = {"count": 0}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "wait_for_absent", lambda **kwargs: None)
    monkeypatch.setattr(module, "wait_for_content", lambda **kwargs: None)

    def fake_create_script(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ConnectionResetError(54, "Connection reset by peer")
        return 201, ""

    monkeypatch.setattr(module, "create_script", fake_create_script)

    payload = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert payload == {"path": "f/lv3/operator_onboard", "attempts": 2, "status": "synced"}


def test_schedule_sync_helper_retries_connection_reset_during_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("schedule_sync_helper_retry_reset", SCHEDULE_SYNC_HELPER_PATH)
    spec = {
        "path": "f/lv3/quarterly_access_review_every_monday_0900",
        "schedule": "0 0 9 * * 1",
        "timezone": "Europe/Bucharest",
        "script_path": "f/lv3/quarterly_access_review",
        "summary": "ADR 0108 quarterly access review",
        "description": "Repo-managed schedule sync test",
        "args": {"schedule_guard": "first_monday_of_quarter"},
    }
    attempts = {"count": 0}

    monkeypatch.setattr(module, "schedule_exists", lambda **kwargs: True)

    def fake_update_schedule(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ConnectionResetError(54, "Connection reset by peer")

    monkeypatch.setattr(module, "update_schedule", fake_update_schedule)

    payload = module.sync_schedule(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert payload == {"path": "f/lv3/quarterly_access_review_every_monday_0900", "attempts": 2, "status": "updated"}
