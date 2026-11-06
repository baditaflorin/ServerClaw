"""Tests for the Scanopy warm standby job.

The job restores the newest hourly dump into a persistent Postgres container, and boot-tests the standby server against it.
Two properties matter most: a failover server must never be touched by the sync or by a boot test, and a failed run must not
make the standby look fresh. Docker, HTTP and time are replaced by fakes; nothing here starts a container.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-standby/scanopy_standby.py"
)
TABLES = ("daemons", "hosts", "discovery", "api_keys", "credentials")


@pytest.fixture()
def standby(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_standby_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    (tmp_path / "dumps").mkdir()
    (tmp_path / "key").write_text("job-key\n")
    for key, value in (("dir", tmp_path / "dumps"), ("state", tmp_path / "state" / "state.json"),
                       ("textfile", tmp_path / "standby.prom"), ("key_file", tmp_path / "key"), ("compose", tmp_path / "compose.yml")):
        monkeypatch.setitem(module.CONF, key, str(value))
    monkeypatch.setitem(module.CONF, "ready_seconds", 20)
    monkeypatch.setitem(module.CONF, "boot_seconds", 30)
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(module, "now_ts", lambda: clock["t"])
    monkeypatch.setattr(module, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    return module


class FakeDocker:
    """Scripted docker: container state, compose commands, psql answers."""

    def __init__(self, counts=None, server_running=False, up_rc=0) -> None:
        self.counts = counts if counts is not None else {t: 5 for t in TABLES}
        self.server_running = server_running
        self.up_rc = up_rc
        self.calls: list[list[str]] = []
        self.compose_env: list[dict] = []

    def __call__(self, args, stdin=None, timeout=120, env=None):
        self.calls.append(list(args))
        if args[0] == "inspect":
            return 0, "true\n" if self.server_running else "false\n", ""
        if args[0] == "compose":
            self.compose_env.append(env or {})
            if "up" in args and "server" in args:
                self.server_running = self.up_rc == 0
                return self.up_rc, "", "no such image" if self.up_rc else ""
            if "rm" in args and "server" in args:
                self.server_running = False
            return 0, "", ""
        if args[0] == "exec":
            if "pg_isready" in args:
                return 0, "", ""
            sql = args[-1]
            if sql.startswith("select count(*) from "):
                return 0, f"{self.counts[sql.rsplit(' ', 1)[1]]}\n", ""
            return 0, "", ""  # DROP / CREATE DATABASE
        raise AssertionError(args)


class FakePopen:
    returncode = 0
    stderr_text = b""
    last: "FakePopen | None" = None

    def __init__(self, argv, stdin=None, stdout=None, stderr=None) -> None:
        FakePopen.last = self
        self.received = b""
        self.stdin = self

    def write(self, data: bytes) -> int:
        self.received += data
        return len(data)

    def close(self) -> None:
        pass

    def communicate(self, timeout=None):
        return b"", FakePopen.stderr_text

    def kill(self) -> None:
        pass


def write_dump(standby: ModuleType, name: str = "scanopy-20261013T000000Z.sql.gz") -> Path:
    path = Path(standby.CONF["dir"]) / name
    path.write_bytes(gzip.compress(b"select 1;\n"))
    return path


def run(standby: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: FakeDocker, *argv: str, restore_rc: int = 0) -> int:
    monkeypatch.setattr(standby, "docker", fake)
    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    FakePopen.returncode = restore_rc
    monkeypatch.setattr(sys, "argv", ["scanopy_standby.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        standby.main()
    return int(exit_info.value.code)


def metrics(standby: ModuleType) -> dict[str, float]:
    text = Path(standby.CONF["textfile"]).read_text()
    return {line.split()[0]: float(line.split()[1]) for line in text.splitlines() if line and not line.startswith("#")}


def healthy_http(standby: ModuleType, monkeypatch: pytest.MonkeyPatch, daemons: int = 5, health_after: int = 0) -> list[str]:
    seen: list[str] = []
    state = {"n": 0}

    def fake_get(url, key=None, timeout=10):
        seen.append(url)
        if url.endswith("/api/health"):
            state["n"] += 1
            if state["n"] <= health_after:
                raise urllib.error.URLError("connection refused")
            return 200, b"ok"
        assert key == "job-key"
        return 200, json.dumps({"data": [{"id": i} for i in range(daemons)]}).encode()

    monkeypatch.setattr(standby, "http_get", fake_get)
    return seen


def test_sync_restores_the_newest_dump_and_reports_fresh_metrics(standby, monkeypatch) -> None:
    write_dump(standby, "scanopy-20261012T000000Z.sql.gz")
    newest = write_dump(standby)
    fake = FakeDocker()

    assert run(standby, monkeypatch, fake, "sync") == 0

    assert FakePopen.last is not None and FakePopen.last.received == b"select 1;\n"
    assert json.loads(Path(standby.CONF["state"]).read_text())["restored"] == newest.name
    m = metrics(standby)
    assert m["scanopy_standby_last_attempt_success"] == 1 and m["scanopy_standby_failover_active"] == 0
    assert m["scanopy_standby_last_success_timestamp_seconds"] == int(standby.now_ts())
    assert m['scanopy_standby_rows{table="daemons"}'] == 5
    assert (Path(standby.CONF["textfile"]).stat().st_mode & 0o777) == 0o644


def test_sync_skips_the_restore_when_that_dump_is_already_in_the_standby(standby, monkeypatch) -> None:
    write_dump(standby)
    assert run(standby, monkeypatch, FakeDocker(), "sync") == 0
    first = metrics(standby)["scanopy_standby_last_success_timestamp_seconds"]
    standby.sleep(3600)
    FakePopen.last = None

    assert run(standby, monkeypatch, FakeDocker(), "sync") == 0

    assert FakePopen.last is None  # nothing was restored again
    assert metrics(standby)["scanopy_standby_last_success_timestamp_seconds"] == first  # staleness keeps counting from the real refresh


def test_sync_never_touches_the_database_while_the_standby_server_runs(standby, monkeypatch) -> None:
    write_dump(standby)
    fake = FakeDocker(server_running=True)

    assert run(standby, monkeypatch, fake, "sync") == 0

    assert FakePopen.last is None or FakePopen.last.received == b""
    assert not any(c[0] == "exec" for c in fake.calls)  # no DROP/CREATE, no psql at all
    assert metrics(standby)["scanopy_standby_failover_active"] == 1


def test_a_failed_restore_fails_the_run_and_keeps_the_previous_success_time(standby, monkeypatch) -> None:
    write_dump(standby, "scanopy-20261013T000000Z.sql.gz")
    assert run(standby, monkeypatch, FakeDocker(), "sync") == 0
    good = metrics(standby)["scanopy_standby_last_success_timestamp_seconds"]
    standby.sleep(3600)
    write_dump(standby, "scanopy-20261013T010000Z.sql.gz")

    assert run(standby, monkeypatch, FakeDocker(), "sync", restore_rc=3) == 1

    m = metrics(standby)
    assert m["scanopy_standby_last_attempt_success"] == 0 and m["scanopy_standby_last_success_timestamp_seconds"] == good
    assert json.loads(Path(standby.CONF["state"]).read_text())["restored"] == "scanopy-20261013T000000Z.sql.gz"


def test_empty_tables_after_a_restore_are_a_failure(standby, monkeypatch) -> None:
    write_dump(standby)

    assert run(standby, monkeypatch, FakeDocker(counts={**{t: 5 for t in TABLES}, "hosts": 0}), "sync") == 1

    assert not Path(standby.CONF["state"]).exists()  # an unverified restore is not recorded as done


def test_no_dump_at_all_is_a_failure(standby, monkeypatch) -> None:
    assert run(standby, monkeypatch, FakeDocker(), "sync") == 1


def test_boot_test_starts_the_server_on_localhost_checks_the_api_and_stops_it(standby, monkeypatch) -> None:
    write_dump(standby)
    run(standby, monkeypatch, FakeDocker(), "sync")
    fake = FakeDocker()
    seen = healthy_http(standby, monkeypatch, daemons=5, health_after=2)

    assert run(standby, monkeypatch, fake, "boot-test") == 0

    up = next(env for env, call in zip(fake.compose_env, [c for c in fake.calls if c[0] == "compose"]) if "up" in call and "server" in call)
    assert up == {"STANDBY_BIND": "127.0.0.1", "STANDBY_PORT": standby.CONF["boot_port"]}  # never published beyond localhost
    assert any(u.endswith("/api/v1/daemons?limit=1000") for u in seen)
    assert not fake.server_running  # stopped again
    m = metrics(standby)
    assert m["scanopy_standby_boot_test_last_success_timestamp_seconds"] == int(standby.now_ts()) or m["scanopy_standby_boot_test_last_success_timestamp_seconds"] > 0
    assert m["scanopy_standby_last_success_timestamp_seconds"] > 0  # the boot test keeps the sync's success time


def test_boot_test_refuses_while_a_failover_server_runs_and_never_stops_it(standby, monkeypatch) -> None:
    write_dump(standby)
    fake = FakeDocker(server_running=True)
    healthy_http(standby, monkeypatch)

    assert run(standby, monkeypatch, fake, "boot-test") == 1

    assert fake.server_running  # the real failover server is still up
    assert not any("rm" in c for c in fake.calls if c[0] == "compose")


def test_boot_test_cleans_up_a_server_it_started_when_the_check_fails(standby, monkeypatch) -> None:
    write_dump(standby)
    run(standby, monkeypatch, FakeDocker(), "sync")
    fake = FakeDocker()
    healthy_http(standby, monkeypatch, daemons=3)  # the API shows 3 daemons, the database has 5

    assert run(standby, monkeypatch, fake, "boot-test") == 1

    assert not fake.server_running
    assert metrics(standby)["scanopy_standby_last_attempt_success"] == 0


def test_boot_test_fails_when_the_server_never_becomes_healthy(standby, monkeypatch) -> None:
    write_dump(standby)
    fake = FakeDocker()
    healthy_http(standby, monkeypatch, health_after=10_000)

    assert run(standby, monkeypatch, fake, "boot-test") == 1

    assert not fake.server_running


def test_unknown_subcommands_are_refused(standby, monkeypatch) -> None:
    assert run(standby, monkeypatch, FakeDocker(), "restore-everything") == 2
