"""Tests for the weekly Scanopy backup restore drill.

The drill restores the newest dump into a throwaway Postgres container and counts the core tables. Docker is replaced by a
scripted fake; nothing here starts a container or touches a real host.
"""

from __future__ import annotations

import gzip
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-backup/scanopy_backup_drill.py"
)


@pytest.fixture()
def drill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_backup_drill_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    (tmp_path / "dumps").mkdir()
    monkeypatch.setitem(module.CONF, "dir", str(tmp_path / "dumps"))
    monkeypatch.setitem(module.CONF, "textfile", str(tmp_path / "drill.prom"))
    monkeypatch.setitem(module.CONF, "ready_seconds", 20)
    clock = {"t": 1_800_000_000.0}
    monkeypatch.setattr(module, "now_ts", lambda: clock["t"])
    monkeypatch.setattr(module, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    return module


class FakeDocker:
    """Scripted `docker`: container lifecycle, readiness, and per-table row counts."""

    def __init__(self, counts=None, ready_after=2, run_rc=0) -> None:
        self.counts = counts if counts is not None else {t: 5 for t in ("daemons", "hosts", "discovery", "api_keys", "credentials")}
        self.ready_after = ready_after
        self.run_rc = run_rc
        self.calls: list[list[str]] = []
        self.ready_checks = 0
        self.removed = False

    def __call__(self, args, stdin=None, timeout=60):
        self.calls.append(list(args))
        if args[0] == "run":
            return self.run_rc, "id\n", "" if self.run_rc == 0 else "pull access denied"
        if args[0] == "rm":
            self.removed = True
            return 0, "", ""
        if "pg_isready" in args:
            self.ready_checks += 1
            return (0 if self.ready_checks > self.ready_after else 2), "", ""
        if "-c" in args:
            table = args[-1].split()[-1]
            return 0, f"{self.counts[table]}\n", ""
        raise AssertionError(args)


def write_dump(drill: ModuleType, name: str = "scanopy-20261013T000000Z.sql.gz", mtime: float | None = None) -> Path:
    path = Path(drill.CONF["dir"]) / name
    path.write_bytes(gzip.compress(b"select 1;\n"))
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


class FakePopen:
    last: "FakePopen | None" = None
    returncode = 0
    stderr_text = b""

    def __init__(self, argv, stdin=None, stdout=None, stderr=None) -> None:
        FakePopen.last = self
        self.argv = argv
        self.received = b""
        self.stdin = self  # the code writes to and closes proc.stdin
        self.killed = False

    def write(self, data: bytes) -> int:
        self.received += data
        return len(data)

    def close(self) -> None:
        pass

    def communicate(self, timeout=None):
        return b"", FakePopen.stderr_text

    def kill(self) -> None:
        self.killed = True


def run(drill: ModuleType, monkeypatch: pytest.MonkeyPatch, fake: FakeDocker, restore_rc: int = 0, restore_err: bytes = b"") -> int:
    monkeypatch.setattr(drill, "docker", fake)
    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    FakePopen.returncode, FakePopen.stderr_text = restore_rc, restore_err
    with pytest.raises(SystemExit) as exit_info:
        drill.main()
    return int(exit_info.value.code)


def metrics(drill: ModuleType) -> dict[str, float]:
    text = Path(drill.CONF["textfile"]).read_text()
    return {line.split()[0]: float(line.split()[1]) for line in text.splitlines() if line and not line.startswith("#")}


def test_a_good_restore_is_reported_with_row_counts_and_the_container_is_removed(drill, monkeypatch) -> None:
    write_dump(drill)
    fake = FakeDocker()

    assert run(drill, monkeypatch, fake) == 0

    assert fake.removed and fake.ready_checks >= 2
    run_args = next(c for c in fake.calls if c[0] == "run")
    assert "--network" in run_args and run_args[run_args.index("--network") + 1] == "none"  # nothing can leave the container
    assert "--memory" in run_args and "--rm" in run_args
    assert FakePopen.last is not None and FakePopen.last.received == b"select 1;\n"  # the decompressed dump went to psql
    m = metrics(drill)
    assert m["scanopy_backup_drill_last_attempt_success"] == 1
    assert m["scanopy_backup_drill_last_success_timestamp_seconds"] == m["scanopy_backup_drill_last_attempt_timestamp_seconds"]
    assert m['scanopy_backup_drill_rows{table="daemons"}'] == 5


def test_the_newest_dump_is_the_one_restored(drill, monkeypatch) -> None:
    write_dump(drill, "scanopy-20261012T000000Z.sql.gz")
    newest = write_dump(drill, "scanopy-20261013T000000Z.sql.gz")
    seen = []
    monkeypatch.setattr(drill, "restore", lambda name, dump: seen.append(dump))

    run(drill, monkeypatch, FakeDocker())

    assert seen == [str(newest)]


def test_an_empty_restored_table_fails_the_drill_and_keeps_the_previous_success_time(drill, monkeypatch) -> None:
    write_dump(drill)
    assert run(drill, monkeypatch, FakeDocker()) == 0
    good = metrics(drill)["scanopy_backup_drill_last_success_timestamp_seconds"]
    counts = {t: 5 for t in ("daemons", "hosts", "discovery", "api_keys", "credentials")} | {"hosts": 0}
    fake = FakeDocker(counts=counts)

    assert run(drill, monkeypatch, fake) == 1

    assert fake.removed
    m = metrics(drill)
    assert m["scanopy_backup_drill_last_attempt_success"] == 0
    assert m["scanopy_backup_drill_last_success_timestamp_seconds"] == good  # its age keeps growing for the alert


def test_a_psql_error_during_restore_fails_the_drill(drill, monkeypatch, capsys) -> None:
    write_dump(drill)
    fake = FakeDocker()

    assert run(drill, monkeypatch, fake, restore_rc=3, restore_err=b'ERROR:  relation "x" already exists') == 1

    assert "restore failed" in capsys.readouterr().err and fake.removed


def test_no_dump_or_no_container_is_a_failure_that_still_cleans_up(drill, monkeypatch) -> None:
    fake = FakeDocker()
    assert run(drill, monkeypatch, fake) == 1  # no dump at all
    write_dump(drill)
    fake = FakeDocker(run_rc=125)
    assert run(drill, monkeypatch, fake) == 1 and fake.removed


def test_a_postgres_that_never_gets_ready_fails_instead_of_hanging(drill, monkeypatch) -> None:
    write_dump(drill)
    fake = FakeDocker(ready_after=10_000)

    assert run(drill, monkeypatch, fake) == 1

    assert fake.removed and metrics(drill)["scanopy_backup_drill_last_attempt_success"] == 0


def test_the_metrics_file_is_readable_by_node_exporter_under_a_strict_umask(drill, monkeypatch) -> None:
    write_dump(drill)
    old = os.umask(0o077)
    try:
        run(drill, monkeypatch, FakeDocker())
    finally:
        os.umask(old)

    assert (Path(drill.CONF["textfile"]).stat().st_mode & 0o777) == 0o644
