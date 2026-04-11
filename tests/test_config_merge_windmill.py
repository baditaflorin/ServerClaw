from __future__ import annotations

import importlib.util
import http.client
import io
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "merge-config-changes.py"
SYNC_HELPER_PATH = REPO_ROOT / "scripts" / "sync_windmill_seed_scripts.py"
SCHEDULE_SYNC_HELPER_PATH = REPO_ROOT / "scripts" / "sync_windmill_seed_schedules.py"
INTENT_QUEUE_WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "intent-queue-dispatcher.py"
SCHEDULER_WATCHDOG_WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "scheduler-watchdog-loop.py"
LANE_SCHEDULER_WRAPPER_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "lane-scheduler.py"
WATCHDOG_IMPL_PATH = REPO_ROOT / "windmill" / "scheduler" / "watchdog-loop.py"
RUN_WAIT_RESULT_HELPER_PATH = REPO_ROOT / "scripts" / "windmill_run_wait_result.py"


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


def test_sync_helper_reports_missing_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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


def test_sync_helper_uses_configured_http_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_timeout", SYNC_HELPER_PATH)
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"path":"f/lv3/operator_onboard","content":"print(\\"ok\\")"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    status, body = module.request_json_or_text(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        path="scripts/get/p/f%2Flv3%2Foperator_onboard",
        method="GET",
        expected_statuses=(200,),
        timeout_s=7.5,
    )

    assert status == 200
    assert json.loads(body)["path"] == "f/lv3/operator_onboard"
    assert captured["timeout"] == 7.5
    assert captured["url"] == "http://windmill.internal/api/w/lv3/scripts/get/p/f%2Flv3%2Foperator_onboard"


def test_sync_helper_request_json_or_text_retries_connection_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_request_retry", SYNC_HELPER_PATH)
    calls = {"count": 0}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"path":"f/lv3/operator_onboard","content":"print(\\"ok\\")"}'

    def fake_urlopen(_request, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionResetError(54, "Connection reset by peer")
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    status, body = module.request_json_or_text(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        path="scripts/get/p/f%2Flv3%2Foperator_onboard",
        method="GET",
        expected_statuses=(200,),
    )

    assert status == 200
    assert json.loads(body)["path"] == "f/lv3/operator_onboard"
    assert calls["count"] == 2


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
    monkeypatch.setattr(module, "get_script", lambda **kwargs: (404, None))
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


def test_sync_helper_treats_delete_transport_error_as_converged_when_remote_content_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("sync_helper_delete_transport_already_converged", SYNC_HELPER_PATH)
    local_file = tmp_path / "script.py"
    local_file.write_text("print('ok')\n", encoding="utf-8")
    spec = {
        "path": "f/lv3/runbook_executor",
        "local_file": str(local_file),
        "language": "python3",
        "summary": "Repo-managed runbook executor",
        "description": "Repo-managed sync test",
    }

    def fake_delete_script(**kwargs):
        raise module.SyncTransportError(
            "POST scripts/delete/p/f%2Flv3%2Frunbook_executor transport error: [Errno 54] Connection reset by peer"
        )

    monkeypatch.setattr(module, "delete_script", fake_delete_script)
    monkeypatch.setattr(
        module,
        "get_script",
        lambda **kwargs: (
            200,
            {
                "path": "f/lv3/runbook_executor",
                "content": "print('ok')\n",
                "language": "python3",
                "summary": "Repo-managed runbook executor",
                "description": "Repo-managed sync test",
            },
        ),
    )

    def fail_if_called(**kwargs):
        raise AssertionError("create or settle helpers should not run when the remote script already matches")

    monkeypatch.setattr(module, "wait_for_absent", fail_if_called)
    monkeypatch.setattr(module, "create_script", fail_if_called)
    monkeypatch.setattr(module, "wait_for_content", fail_if_called)

    payload = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert payload == {"path": "f/lv3/runbook_executor", "attempts": 1, "status": "synced"}


def test_sync_helper_skips_delete_when_remote_script_already_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("sync_helper_remote_precheck_match", SYNC_HELPER_PATH)
    local_file = tmp_path / "script.py"
    local_file.write_text("print('ok')\n", encoding="utf-8")
    spec = {
        "path": "f/lv3/stage-smoke-suites",
        "local_file": str(local_file),
        "language": "python3",
        "summary": "Stage smoke suites",
        "description": "Repo-managed sync test",
    }

    monkeypatch.setattr(
        module,
        "get_script",
        lambda **kwargs: (
            200,
            {
                "path": "f/lv3/stage-smoke-suites",
                "content": "print('ok')\n",
                "language": "python3",
                "summary": "Stage smoke suites",
                "description": "Repo-managed sync test",
            },
        ),
    )

    def fail_if_called(**kwargs):
        raise AssertionError("delete or create helpers should not run when the remote script already matches")

    monkeypatch.setattr(module, "delete_script", fail_if_called)
    monkeypatch.setattr(module, "wait_for_absent", fail_if_called)
    monkeypatch.setattr(module, "create_script", fail_if_called)
    monkeypatch.setattr(module, "wait_for_content", fail_if_called)

    payload = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert payload == {"path": "f/lv3/stage-smoke-suites", "attempts": 1, "status": "synced"}


def test_sync_helper_uses_extended_settle_timeouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("sync_helper_settle_timeouts", SYNC_HELPER_PATH)
    local_file = tmp_path / "script.py"
    local_file.write_text("print('ok')\n", encoding="utf-8")
    spec = {
        "path": "f/lv3/world_state/refresh_openbao_secret_expiry",
        "local_file": str(local_file),
        "language": "python3",
        "summary": "Refresh world-state OpenBao secret expiry",
        "description": "Repo-managed sync timeout test",
    }
    captured: dict[str, float] = {}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "get_script", lambda **kwargs: (404, None))

    def fake_wait_for_absent(**kwargs):
        captured["absent_timeout_s"] = kwargs["timeout_s"]

    def fake_wait_for_content(**kwargs):
        captured["content_timeout_s"] = kwargs["timeout_s"]

    monkeypatch.setattr(module, "wait_for_absent", fake_wait_for_absent)
    monkeypatch.setattr(module, "wait_for_content", fake_wait_for_content)
    monkeypatch.setattr(module, "create_script", lambda **kwargs: (201, "created"))

    result = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=1,
        settle_interval_s=2.0,
    )

    assert result == {
        "path": "f/lv3/world_state/refresh_openbao_secret_expiry",
        "attempts": 1,
        "status": "synced",
    }
    assert captured == {"absent_timeout_s": 20.0, "content_timeout_s": 60.0}


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

    monkeypatch.setattr(module, "script_exists", lambda **kwargs: True)
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
        request_timeout_s=5.0,
    )

    assert payload == {"path": "f/lv3/quarterly_access_review_every_monday_0900", "attempts": 2, "status": "updated"}


def test_schedule_payload_keeps_enabled_and_script_binding() -> None:
    module = load_module("schedule_sync_helper_payload", SCHEDULE_SYNC_HELPER_PATH)
    spec = {
        "path": "f/lv3/scheduler_watchdog_loop_every_10s",
        "schedule": "*/10 * * * * *",
        "timezone": "Europe/Bucharest",
        "script_path": "f/lv3/scheduler_watchdog_loop",
        "summary": "ADR 0172 scheduler watchdog loop",
        "description": "Repo-managed schedule payload test",
        "enabled": True,
    }

    assert module.schedule_payload(spec) == {
        "schedule": "*/10 * * * * *",
        "timezone": "Europe/Bucharest",
        "script_path": "f/lv3/scheduler_watchdog_loop",
        "is_flow": False,
        "args": {},
        "enabled": True,
        "summary": "ADR 0172 scheduler watchdog loop",
        "description": "Repo-managed schedule payload test",
        "no_flow_overlap": True,
    }


def test_schedule_sync_helper_retries_until_script_target_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("schedule_sync_helper_waits_for_script", SCHEDULE_SYNC_HELPER_PATH)
    spec = {
        "path": "f/lv3/world_state/refresh_container_inventory_every_minute",
        "schedule": "0 * * * * *",
        "timezone": "Europe/Bucharest",
        "script_path": "f/lv3/world_state/refresh_container_inventory",
        "summary": "ADR 0113 container inventory world-state refresh",
        "description": "Repo-managed schedule sync test",
    }
    attempts = {"count": 0}

    def fake_script_exists(**kwargs):
        attempts["count"] += 1
        return attempts["count"] >= 2

    monkeypatch.setattr(module, "script_exists", fake_script_exists)
    monkeypatch.setattr(module, "schedule_exists", lambda **kwargs: True)
    monkeypatch.setattr(module, "update_schedule", lambda **kwargs: None)

    payload = module.sync_schedule(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.0,
        request_timeout_s=5.0,
    )

    assert payload == {
        "path": "f/lv3/world_state/refresh_container_inventory_every_minute",
        "attempts": 2,
        "status": "updated",
    }


def test_schedule_sync_helper_treats_missing_script_update_error_as_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("schedule_sync_helper_missing_script_retry", SCHEDULE_SYNC_HELPER_PATH)

    def fake_request_json_or_text(**kwargs):
        raise module.SyncError(
            "POST schedules/update/f%2Flv3%2Fworld_state%2Frefresh_container_inventory_every_minute "
            "returned 404: Not found: script not found at name "
            "f/lv3/world_state/refresh_container_inventory (lib.rs:1154)"
        )

    monkeypatch.setattr(module, "request_json_or_text", fake_request_json_or_text)

    with pytest.raises(module.RetryableSyncError, match="script not found at name"):
        module.update_schedule(
            base_url="http://windmill.internal",
            workspace="lv3",
            token="token",
            spec={
                "path": "f/lv3/world_state/refresh_container_inventory_every_minute",
                "schedule": "0 * * * * *",
                "timezone": "Europe/Bucharest",
                "script_path": "f/lv3/world_state/refresh_container_inventory",
                "summary": "summary",
                "description": "desc",
            },
            timeout_s=5.0,
        )


def test_schedule_sync_helper_uses_configured_http_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("schedule_sync_helper_timeout", SCHEDULE_SYNC_HELPER_PATH)
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"true"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    status, body = module.request_json_or_text(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        path="schedules/exists/f%2Flv3%2Fquarterly_access_review_every_monday_0900",
        method="GET",
        expected_statuses=(200,),
        timeout_s=7.5,
    )

    assert status == 200
    assert body == "true"
    assert captured["timeout"] == 7.5
    assert captured["url"] == (
        "http://windmill.internal/api/w/lv3/schedules/exists/f%2Flv3%2Fquarterly_access_review_every_monday_0900"
    )


def test_schedule_sync_helper_retries_sqlerr_backend_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("schedule_sync_helper_retryable_sqlerr", SCHEDULE_SYNC_HELPER_PATH)

    def fake_urlopen(_request, timeout=None):
        raise module.urllib.error.HTTPError(
            "http://windmill.internal/api/w/lv3/scripts/get/p/f%2Flv3%2Fworld_state%2Frefresh_tls_certs",
            400,
            "Bad Request",
            None,
            io.BytesIO(b"SqlErr: error communicating with database: Connection reset by peer (os error 104)"),
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(module.RetryableSyncError, match="Connection reset by peer"):
        module.request_json_or_text(
            base_url="http://windmill.internal",
            workspace="lv3",
            token="token",
            path="scripts/get/p/f%2Flv3%2Fworld_state%2Frefresh_tls_certs",
            method="GET",
            expected_statuses=(200,),
            timeout_s=5.0,
        )


def test_script_sync_helper_retries_sqlerr_backend_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("script_sync_helper_retryable_sqlerr", SYNC_HELPER_PATH)

    def fake_urlopen(_request, timeout=None):
        raise module.urllib.error.HTTPError(
            "http://windmill.internal/api/w/lv3/scripts/get/p/f%2Flv3%2Foperator_onboard",
            400,
            "Bad Request",
            None,
            io.BytesIO(b"SqlErr: error communicating with database: Connection reset by peer (os error 104)"),
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(module.RetryableSyncError, match="Connection reset by peer"):
        module.request_json_or_text(
            base_url="http://windmill.internal",
            workspace="lv3",
            token="token",
            path="scripts/get/p/f%2Flv3%2Foperator_onboard",
            method="GET",
            expected_statuses=(200,),
            timeout_s=5.0,
        )


def test_sync_helper_resolves_repo_root_from_shard_adjacent_script_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    shard_script = repo_root / ".ansible" / "shards" / "run-123" / ".." / "scripts" / "sync_windmill_seed_scripts.py"
    (repo_root / "platform").mkdir(parents=True)
    (repo_root / "platform" / "__init__.py").write_text("# stub\n", encoding="utf-8")
    (repo_root / "platform" / "retry.py").write_text("# stub\n", encoding="utf-8")
    shard_script.parent.mkdir(parents=True, exist_ok=True)
    shard_script.write_text("# stub\n", encoding="utf-8")

    module = load_module("sync_helper_repo_root", SYNC_HELPER_PATH)

    assert module.resolve_repo_root(shard_script) == repo_root.resolve()


def test_sync_helper_bootstraps_repo_root_for_direct_script_execution(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("[]\n", encoding="utf-8")
    env = os.environ.copy()
    env["WINDMILL_TOKEN"] = "token"
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            "python3",
            str(SYNC_HELPER_PATH),
            "--base-url",
            "http://windmill.internal",
            "--workspace",
            "lv3",
            "--manifest",
            str(manifest),
            "--max-attempts",
            "1",
            "--settle-interval",
            "0",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload == {"count": 0, "results": [], "status": "ok"}


def test_sync_helper_retries_retryable_create_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_retries", SYNC_HELPER_PATH)
    script_path = tmp_path / "script.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    calls = {"create": 0}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "get_script", lambda **kwargs: (404, None))
    monkeypatch.setattr(module, "wait_for_absent", lambda **kwargs: None)
    monkeypatch.setattr(module, "wait_for_content", lambda **kwargs: None)

    def fake_create_script(**kwargs):
        calls["create"] += 1
        if calls["create"] == 1:
            raise module.RetryableSyncError("connection reset by peer")
        return 201, "created"

    monkeypatch.setattr(module, "create_script", fake_create_script)

    result = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec={
            "path": "f/lv3/config_merge/merge_config_changes",
            "language": "python3",
            "summary": "summary",
            "description": "desc",
            "local_file": str(script_path),
        },
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert result == {
        "path": "f/lv3/config_merge/merge_config_changes",
        "attempts": 2,
        "status": "synced",
    }


def test_sync_helper_retries_when_delete_settle_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_delete_settle_retry", SYNC_HELPER_PATH)
    script_path = tmp_path / "script.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    attempts = {"count": 0}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "get_script", lambda **kwargs: (404, None))
    monkeypatch.setattr(module, "create_script", lambda **kwargs: (201, "created"))
    monkeypatch.setattr(module, "wait_for_content", lambda **kwargs: None)

    def fake_wait_for_absent(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise module.SyncError("timed out waiting for f/lv3/health/refresh_composite to disappear")

    monkeypatch.setattr(module, "wait_for_absent", fake_wait_for_absent)

    result = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec={
            "path": "f/lv3/health/refresh_composite",
            "language": "python3",
            "summary": "summary",
            "description": "desc",
            "local_file": str(script_path),
        },
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert result == {
        "path": "f/lv3/health/refresh_composite",
        "attempts": 2,
        "status": "synced",
    }


def test_sync_helper_retries_when_created_script_is_not_immediately_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("sync_helper_visibility_retry", SYNC_HELPER_PATH)
    script_path = tmp_path / "script.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    attempts = {"count": 0}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "get_script", lambda **kwargs: (404, None))
    monkeypatch.setattr(module, "wait_for_absent", lambda **kwargs: None)
    monkeypatch.setattr(module, "create_script", lambda **kwargs: (201, "created"))

    def fake_wait_for_content(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise module.SyncError("timed out waiting for f/lv3/health/refresh_composite to match expected content")

    monkeypatch.setattr(module, "wait_for_content", fake_wait_for_content)

    result = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec={
            "path": "f/lv3/health/refresh_composite",
            "language": "python3",
            "summary": "summary",
            "description": "desc",
            "local_file": str(script_path),
        },
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert result == {
        "path": "f/lv3/health/refresh_composite",
        "attempts": 2,
        "status": "synced",
    }


def test_sync_helper_retries_remote_disconnect(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module("sync_helper_retry_disconnect", SYNC_HELPER_PATH)
    spec = {
        "path": "f/lv3/sync_operators",
        "local_file": str(tmp_path / "sync-operators.py"),
        "language": "python3",
        "summary": "sync operators",
        "description": "repo-managed sync operators wrapper",
    }
    Path(spec["local_file"]).write_text("print('ok')\n", encoding="utf-8")
    attempts = {"count": 0}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "get_script", lambda **kwargs: (404, None))
    monkeypatch.setattr(module, "wait_for_absent", lambda **kwargs: None)
    monkeypatch.setattr(module, "wait_for_content", lambda **kwargs: None)
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)

    def fake_create_script(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise module.SyncTransportError(
                "POST scripts/create transport error: Remote end closed connection without response"
            )
        return 201, ""

    monkeypatch.setattr(module, "create_script", fake_create_script)

    payload = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.01,
    )

    assert payload == {"path": "f/lv3/sync_operators", "attempts": 2, "status": "synced"}


def test_sync_helper_retries_wait_for_content_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module("sync_helper_retry_wait_for_content", SYNC_HELPER_PATH)
    spec = {
        "path": "f/lv3/deploy_and_promote",
        "local_file": str(tmp_path / "deploy-and-promote.py"),
        "language": "python3",
        "summary": "deploy and promote",
        "description": "repo-managed deploy and promote wrapper",
    }
    Path(spec["local_file"]).write_text("print('ok')\n", encoding="utf-8")
    attempts = {"count": 0}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "get_script", lambda **kwargs: (404, None))
    monkeypatch.setattr(module, "wait_for_absent", lambda **kwargs: None)
    monkeypatch.setattr(module, "create_script", lambda **kwargs: (201, ""))
    monkeypatch.setattr(module.time, "sleep", lambda *_args, **_kwargs: None)

    def fake_wait_for_content(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise module.SyncError("timed out waiting for f/lv3/deploy_and_promote to match expected content")

    monkeypatch.setattr(module, "wait_for_content", fake_wait_for_content)

    payload = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.01,
    )

    assert payload == {"path": "f/lv3/deploy_and_promote", "attempts": 2, "status": "synced"}


def test_sync_helper_treats_create_conflict_as_converged_when_remote_script_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module("sync_helper_create_conflict_match", SYNC_HELPER_PATH)
    script_path = tmp_path / "script.py"
    script_path.write_text("print('ok')\n", encoding="utf-8")
    spec = {
        "path": "f/lv3/stage-smoke-suites",
        "language": "python3",
        "summary": "Stage smoke suites",
        "description": "Repo-managed sync test",
        "local_file": str(script_path),
    }
    get_calls = {"count": 0}

    monkeypatch.setattr(module, "delete_script", lambda **kwargs: None)
    monkeypatch.setattr(module, "wait_for_absent", lambda **kwargs: None)
    monkeypatch.setattr(module, "create_script", lambda **kwargs: (400, "already exists"))
    monkeypatch.setattr(module, "wait_for_content", lambda **kwargs: None)

    def fake_get_script(**kwargs):
        get_calls["count"] += 1
        if get_calls["count"] == 1:
            return 404, None
        return (
            200,
            {
                "path": "f/lv3/stage-smoke-suites",
                "content": "print('ok')\n",
                "language": "python3",
                "summary": "Stage smoke suites",
                "description": "Repo-managed sync test",
            },
        )

    monkeypatch.setattr(module, "get_script", fake_get_script)

    payload = module.sync_script(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="token",
        spec=spec,
        max_attempts=3,
        settle_interval_s=0.0,
    )

    assert payload == {"path": "f/lv3/stage-smoke-suites", "attempts": 1, "status": "synced"}


def test_sync_helper_marks_remote_disconnect_as_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_transport_error", SYNC_HELPER_PATH)

    def fake_urlopen(_request, timeout=None):
        raise http.client.RemoteDisconnected("Remote end closed connection without response")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(module.SyncTransportError, match="transport error"):
        module.request_json_or_text(
            base_url="http://windmill.internal",
            workspace="lv3",
            token="token",
            path="scripts/create",
            method="POST",
            payload={"path": "f/lv3/sync_operators"},
            expected_statuses=(201,),
        )


def test_intent_queue_wrapper_exposes_module_main(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("intent_queue_wrapper", INTENT_QUEUE_WRAPPER_PATH)
    captured: dict[str, object] = {}

    def fake_main(**kwargs):
        captured.update(kwargs)
        return {"status": "ok", "source": "impl"}

    monkeypatch.setattr(module, "_load_impl", lambda repo_root: SimpleNamespace(main=fake_main))

    payload = module.main(
        repo_root="/srv/proxmox_florin_server", resource_hints=["lane"], workflow_hints=["wf"], max_items=0
    )

    assert payload == {"status": "ok", "source": "impl"}
    assert captured == {
        "repo_root": "/srv/proxmox_florin_server",
        "resource_hints": ["lane"],
        "workflow_hints": ["wf"],
        "max_items": 0,
    }


def test_scheduler_watchdog_wrapper_exposes_module_main(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("scheduler_watchdog_wrapper", SCHEDULER_WATCHDOG_WRAPPER_PATH)

    monkeypatch.setattr(
        module,
        "_load_impl",
        lambda repo_root: SimpleNamespace(main=lambda **kwargs: {"status": "ok", "repo_path": kwargs["repo_path"]}),
    )

    payload = module.main(repo_path="/srv/proxmox_florin_server")

    assert payload == {"status": "ok", "repo_path": "/srv/proxmox_florin_server"}


def test_lane_scheduler_uses_uv_fallback_when_yaml_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module("lane_scheduler_wrapper", LANE_SCHEDULER_WRAPPER_PATH)
    repo_root = tmp_path / "repo"
    (repo_root / "config" / "windmill" / "scripts").mkdir(parents=True)
    captured: dict[str, object] = {}

    def fake_run(command, cwd, env, text, capture_output, check):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        assert text is True
        assert capture_output is True
        assert check is False
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"status": "ok", "source": "uv"}), stderr="")

    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None if name == "yaml" else object())
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root), max_dispatches=0)

    assert payload == {"status": "ok", "source": "uv"}
    assert captured["cwd"] == repo_root
    assert captured["command"] == [
        "uv",
        "run",
        "--no-project",
        "--with",
        "pyyaml",
        "python",
        str(repo_root / "config" / "windmill" / "scripts" / "lane-scheduler.py"),
        "--repo-path",
        str(repo_root),
        "--max-dispatches",
        "0",
    ]
    assert captured["env"]["PYTHONPATH"] == str(repo_root)


def test_intent_queue_dispatcher_uses_uv_fallback_when_yaml_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_module("intent_queue_dispatcher_impl", REPO_ROOT / "scripts" / "intent_queue_dispatcher.py")
    repo_root = tmp_path / "repo"
    (repo_root / "scripts").mkdir(parents=True)
    captured: dict[str, object] = {}

    def fake_run(command, cwd, env, text, capture_output, check):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        assert text is True
        assert capture_output is True
        assert check is False
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"status": "ok", "source": "uv"}), stderr="")

    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None if name == "yaml" else object())
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_root=str(repo_root), max_items=0)

    assert payload == {"status": "ok", "source": "uv"}
    assert captured["cwd"] == repo_root
    assert captured["command"] == [
        "uv",
        "run",
        "--no-project",
        "--with",
        "pyyaml",
        "python",
        str(repo_root / "scripts" / "intent_queue_dispatcher.py"),
        "--repo-root",
        str(repo_root),
        "--max-items",
        "0",
    ]
    assert captured["env"]["PYTHONPATH"] == str(repo_root)


def test_watchdog_impl_uses_uv_fallback_when_yaml_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = load_module("scheduler_watchdog_impl", WATCHDOG_IMPL_PATH)
    repo_root = tmp_path / "repo"
    (repo_root / "windmill" / "scheduler").mkdir(parents=True)
    captured: dict[str, object] = {}

    def fake_run(command, cwd, env, text, capture_output, check):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        assert text is True
        assert capture_output is True
        assert check is False
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"status": "ok", "source": "uv"}), stderr="")

    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None if name == "yaml" else object())
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.main(repo_path=str(repo_root))

    assert payload == {"status": "ok", "source": "uv"}
    assert captured["cwd"] == repo_root
    assert captured["command"] == [
        "uv",
        "run",
        "--no-project",
        "--with",
        "pyyaml",
        "python",
        str(repo_root / "windmill" / "scheduler" / "watchdog-loop.py"),
        "--repo-path",
        str(repo_root),
    ]
    assert captured["env"]["PYTHONPATH"] == str(repo_root)


def test_lane_scheduler_resolves_token_from_proc_environ(tmp_path: Path) -> None:
    module = load_module("lane_scheduler_proc_env", LANE_SCHEDULER_WRAPPER_PATH)
    proc_environ = tmp_path / "proc-1-environ"
    proc_environ.write_bytes(b"PATH=/usr/bin\0LV3_WINDMILL_TOKEN=proc-secret\0")

    assert module._read_proc_env_var("LV3_WINDMILL_TOKEN", proc_environ_path=str(proc_environ)) == "proc-secret"


def test_intent_queue_dispatcher_resolves_token_from_proc_environ(tmp_path: Path) -> None:
    module = load_module("intent_queue_proc_env", REPO_ROOT / "scripts" / "intent_queue_dispatcher.py")
    proc_environ = tmp_path / "proc-1-environ"
    proc_environ.write_bytes(b"PATH=/usr/bin\0SUPERADMIN_SECRET=proc-secret\0")

    assert (
        module._read_proc_env_var("LV3_WINDMILL_TOKEN", "SUPERADMIN_SECRET", proc_environ_path=str(proc_environ))
        == "proc-secret"
    )


def test_watchdog_impl_resolves_token_from_proc_environ(tmp_path: Path) -> None:
    module = load_module("scheduler_watchdog_proc_env", WATCHDOG_IMPL_PATH)
    proc_environ = tmp_path / "proc-1-environ"
    proc_environ.write_bytes(b"PATH=/usr/bin\0LV3_WINDMILL_TOKEN=proc-secret\0")

    assert module._read_proc_env_var("LV3_WINDMILL_TOKEN", proc_environ_path=str(proc_environ)) == "proc-secret"


def test_intent_queue_dispatcher_resolves_token_from_worker_checkout(tmp_path: Path) -> None:
    module = load_module("intent_queue_worker_secret", REPO_ROOT / "scripts" / "intent_queue_dispatcher.py")
    repo_root = tmp_path / "repo"
    secret_file = repo_root / ".local" / "windmill" / "superadmin-secret.txt"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("worker-secret\n", encoding="utf-8")

    assert module._resolve_windmill_token(repo_root) == "worker-secret"


def test_intent_queue_dispatcher_resolves_token_from_repo_relative_manifest_path(tmp_path: Path) -> None:
    module = load_module("intent_queue_relative_manifest_secret", REPO_ROOT / "scripts" / "intent_queue_dispatcher.py")
    repo_root = tmp_path / "repo"
    secret_file = repo_root / ".local" / "windmill" / "superadmin-secret.txt"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("manifest-secret\n", encoding="utf-8")
    manifest_path = repo_root / "config" / "controller-local-secrets.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "secrets": {
                    "windmill_superadmin_secret": {
                        "kind": "file",
                        "path": ".local/windmill/superadmin-secret.txt",
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert module._resolve_windmill_token(repo_root) == "manifest-secret"


def test_lane_scheduler_resolves_token_from_worker_checkout(tmp_path: Path) -> None:
    module = load_module("lane_scheduler_worker_secret", LANE_SCHEDULER_WRAPPER_PATH)
    repo_root = tmp_path / "repo"
    secret_file = repo_root / ".local" / "windmill" / "superadmin-secret.txt"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("worker-secret\n", encoding="utf-8")

    assert module._resolve_windmill_token(repo_root) == "worker-secret"


def test_watchdog_impl_resolves_token_from_worker_checkout(tmp_path: Path) -> None:
    module = load_module("scheduler_watchdog_worker_secret", WATCHDOG_IMPL_PATH)
    repo_root = tmp_path / "repo"
    secret_file = repo_root / ".local" / "windmill" / "superadmin-secret.txt"
    secret_file.parent.mkdir(parents=True)
    secret_file.write_text("worker-secret\n", encoding="utf-8")

    assert module._resolve_windmill_token(repo_root) == "worker-secret"


def test_run_wait_result_helper_requires_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_module("run_wait_result_helper", RUN_WAIT_RESULT_HELPER_PATH)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "windmill_run_wait_result.py",
            "--base-url",
            "http://windmill.internal",
            "--workspace",
            "lv3",
            "--path",
            "f/lv3/windmill_healthcheck",
        ],
    )
    monkeypatch.delenv("WINDMILL_TOKEN", raising=False)

    assert module.main() == 2
    assert "WINDMILL_TOKEN is required" in capsys.readouterr().err


def test_run_wait_result_helper_writes_polled_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_module("run_wait_result_helper_retry", RUN_WAIT_RESULT_HELPER_PATH)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "windmill_run_wait_result.py",
            "--base-url",
            "http://windmill.internal",
            "--workspace",
            "lv3",
            "--path",
            "f/lv3/windmill_healthcheck",
            "--payload-json",
            '{"probe":"manual-run"}',
            "--poll-interval",
            "0.25",
        ],
    )
    monkeypatch.setenv("WINDMILL_TOKEN", "managed-secret")
    monkeypatch.setenv("WINDMILL_BOOTSTRAP_SECRET", "bootstrap-secret")

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(
            self,
            *,
            base_url: str,
            token: str,
            workspace: str,
            bootstrap_secret: str,
            request_timeout_seconds: int,
        ) -> None:
            captured["client_init"] = {
                "base_url": base_url,
                "token": token,
                "workspace": workspace,
                "bootstrap_secret": bootstrap_secret,
                "request_timeout_seconds": request_timeout_seconds,
            }

        def run_workflow_wait_result(
            self,
            workflow_id: str,
            payload: dict[str, object],
            *,
            timeout_seconds: int | None = None,
            poll_interval_seconds: float = 1.0,
        ) -> dict[str, object]:
            captured["run"] = {
                "workflow_id": workflow_id,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
            return {"status": "ok", "probe": payload["probe"]}

    monkeypatch.setattr(module, "HttpWindmillClient", FakeClient)

    assert module.main() == 0
    assert json.loads(capsys.readouterr().out) == {"status": "ok", "probe": "manual-run"}
    assert captured == {
        "client_init": {
            "base_url": "http://windmill.internal",
            "token": "managed-secret",
            "workspace": "lv3",
            "bootstrap_secret": "bootstrap-secret",
            "request_timeout_seconds": 120,
        },
        "run": {
            "workflow_id": "f/lv3/windmill_healthcheck",
            "payload": {"probe": "manual-run"},
            "timeout_seconds": 120,
            "poll_interval_seconds": 0.25,
        },
    }


def test_run_wait_result_helper_rejects_empty_results(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_module("run_wait_result_helper_empty_result", RUN_WAIT_RESULT_HELPER_PATH)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "windmill_run_wait_result.py",
            "--base-url",
            "http://windmill.internal",
            "--workspace",
            "lv3",
            "--path",
            "f/lv3/gate-status",
        ],
    )
    monkeypatch.setenv("WINDMILL_TOKEN", "managed-secret")

    class FakeClient:
        def __init__(
            self,
            *,
            base_url: str,
            token: str,
            workspace: str,
            bootstrap_secret: str,
            request_timeout_seconds: int,
        ) -> None:
            assert base_url == "http://windmill.internal"
            assert token == "managed-secret"
            assert workspace == "lv3"
            assert bootstrap_secret == "managed-secret"
            assert request_timeout_seconds == 120

        def run_workflow_wait_result(
            self,
            workflow_id: str,
            payload: dict[str, object],
            *,
            timeout_seconds: int | None = None,
            poll_interval_seconds: float = 1.0,
        ) -> None:
            assert workflow_id == "f/lv3/gate-status"
            assert payload == {}
            assert timeout_seconds == 120
            assert poll_interval_seconds == 1.0
            return None

    monkeypatch.setattr(module, "HttpWindmillClient", FakeClient)

    assert module.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Windmill workflow f/lv3/gate-status returned an empty result" in captured.err


def test_run_wait_result_helper_reports_connection_reset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_module("run_wait_result_helper_connection_reset", RUN_WAIT_RESULT_HELPER_PATH)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "windmill_run_wait_result.py",
            "--base-url",
            "http://windmill.internal",
            "--workspace",
            "lv3",
            "--path",
            "f/lv3/gate-status",
        ],
    )
    monkeypatch.setenv("WINDMILL_TOKEN", "managed-secret")

    class FakeClient:
        def __init__(
            self,
            *,
            base_url: str,
            token: str,
            workspace: str,
            bootstrap_secret: str,
            request_timeout_seconds: int,
        ) -> None:
            assert base_url == "http://windmill.internal"
            assert token == "managed-secret"
            assert workspace == "lv3"
            assert bootstrap_secret == "managed-secret"
            assert request_timeout_seconds == 120

        def run_workflow_wait_result(
            self,
            workflow_id: str,
            payload: dict[str, object],
            *,
            timeout_seconds: int | None = None,
            poll_interval_seconds: float = 1.0,
        ) -> None:
            assert workflow_id == "f/lv3/gate-status"
            assert payload == {}
            assert timeout_seconds == 120
            assert poll_interval_seconds == 1.0
            raise ConnectionResetError(54, "Connection reset by peer")

    monkeypatch.setattr(module, "HttpWindmillClient", FakeClient)

    assert module.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Connection reset by peer" in captured.err


def test_run_wait_result_helper_polls_completed_result_for_hash_submissions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_module("run_wait_result_helper_hash_fallback", RUN_WAIT_RESULT_HELPER_PATH)
    monkeypatch.setattr(
        module.sys,
        "argv",
        [
            "windmill_run_wait_result.py",
            "--base-url",
            "http://windmill.internal",
            "--workspace",
            "lv3",
            "--path",
            "f/lv3/windmill_healthcheck",
            "--timeout",
            "30",
        ],
    )
    monkeypatch.setenv("WINDMILL_TOKEN", "session-token")
    monkeypatch.setattr(time, "sleep", lambda _: None)

    class FakeResponse:
        def __init__(self, body: str, *, status: int = 200) -> None:
            self._body = body.encode("utf-8")
            self.status = status

        def read(self) -> bytes:
            return self._body

        def close(self) -> None:
            return None

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    calls: list[str] = []
    poll_count = {"value": 0}

    def fake_urlopen(request, timeout=120):
        calls.append(request.full_url)
        if request.full_url.endswith("/api/w/lv3/scripts/get/p/f%2Flv3%2Fwindmill_healthcheck"):
            return FakeResponse('{"hash":"hash-123"}')
        if request.full_url.endswith("/api/w/lv3/jobs/run/h/hash-123"):
            return FakeResponse('"job-123"')
        if request.full_url.endswith("/api/w/lv3/jobs_u/completed/get_result_maybe/job-123?get_started=true"):
            poll_count["value"] += 1
            if poll_count["value"] == 1:
                return FakeResponse('{"completed":false,"started":false,"result":null}')
            return FakeResponse('{"completed":true,"success":true,"result":{"status":"ok"}}')
        raise AssertionError(f"unexpected request {request.full_url}")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert module.main() == 0
    assert json.loads(capsys.readouterr().out) == {"status": "ok"}
    assert calls == [
        "http://windmill.internal/api/w/lv3/scripts/get/p/f%2Flv3%2Fwindmill_healthcheck",
        "http://windmill.internal/api/w/lv3/jobs/run/h/hash-123",
        "http://windmill.internal/api/w/lv3/jobs_u/completed/get_result_maybe/job-123?get_started=true",
        "http://windmill.internal/api/w/lv3/jobs_u/completed/get_result_maybe/job-123?get_started=true",
    ]


def test_sync_helper_retries_with_bootstrap_login_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module("sync_helper_bootstrap_login", SYNC_HELPER_PATH)

    class FakeResponse:
        def __init__(self, body: str, status: int = 200) -> None:
            self._body = body.encode("utf-8")
            self.status = status

        def read(self) -> bytes:
            return self._body

        def close(self) -> None:
            return None

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    calls: list[tuple[str, str | None]] = []

    def fake_urlopen(request, timeout=None):
        auth_header = request.headers.get("Authorization")
        calls.append((request.full_url, auth_header))
        if request.full_url.endswith("/api/auth/login"):
            return FakeResponse("session-token")
        if auth_header == "Bearer managed-secret":
            raise module.urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=FakeResponse("Unauthorized"),
            )
        assert auth_header == "Bearer session-token"
        return FakeResponse("[]", status=200)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    status, body = module.request_json_or_text(
        base_url="http://windmill.internal",
        workspace="lv3",
        token="managed-secret",
        path="schedules/list",
        method="GET",
        expected_statuses=(200,),
    )

    assert (status, body) == (200, "[]")
    assert calls == [
        ("http://windmill.internal/api/w/lv3/schedules/list", "Bearer managed-secret"),
        ("http://windmill.internal/api/auth/login", None),
        ("http://windmill.internal/api/w/lv3/schedules/list", "Bearer session-token"),
    ]
