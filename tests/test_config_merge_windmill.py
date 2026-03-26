from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "merge-config-changes.py"
SYNC_HELPER_PATH = REPO_ROOT / "scripts" / "sync_windmill_seed_scripts.py"


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
