"""Tests for the nightly Scanopy database backup pull.

The job streams a pg_dump from the 0docker hypervisor through a forced-command key, verifies it, keeps 14 and reports metrics.
A failed or truncated dump must never replace or rotate away a good one. SSH is replaced by a scripted `pull`; nothing here
touches a real host.
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

ROLE_FILES = Path(__file__).resolve().parents[1] / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-backup"
MODULE_PATH = ROLE_FILES / "scanopy_backup.py"
WRAPPER_PATH = ROLE_FILES / "scanopy_backup_hv.sh"


def dump_text(tables=("daemons", "hosts", "discovery", "api_keys", "credentials"), complete=True) -> bytes:
    body = "".join(f"CREATE TABLE public.{t} (\n    id uuid NOT NULL\n);\n" for t in tables)
    body += "".join(f"-- row {i} {i * 7919 % 10007}\n" for i in range(3000))  # varied, so it does not compress to nothing
    if complete:
        body += "--\n-- PostgreSQL database dump complete\n--\n"
    return body.encode()


@pytest.fixture()
def backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_backup_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setitem(module.CONF, "dir", str(tmp_path / "dumps"))
    monkeypatch.setitem(module.CONF, "textfile", str(tmp_path / "scanopy_backup.prom"))
    monkeypatch.setitem(module.CONF, "min_bytes", 200)
    stamps = iter(f"20261013T0{i}0000Z" for i in range(10))
    monkeypatch.setattr(module, "utcstamp", lambda: next(stamps))
    return module


def serve(backup: ModuleType, monkeypatch: pytest.MonkeyPatch, payload: bytes | None, error: str | None = None) -> None:
    def fake_pull(part: str) -> None:
        if error:
            raise RuntimeError(error)
        Path(part).write_bytes(gzip.compress(payload or b""))

    monkeypatch.setattr(backup, "pull", fake_pull)


def run(backup: ModuleType, monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(sys, "argv", ["scanopy_backup.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        backup.main()
    return int(exit_info.value.code)


def metrics(backup: ModuleType) -> dict[str, float]:
    text = Path(backup.CONF["textfile"]).read_text()
    return {line.split()[0]: float(line.split()[1]) for line in text.splitlines() if line and not line.startswith("#")}


def dumps(backup: ModuleType) -> list[str]:
    return sorted(p.name for p in Path(backup.CONF["dir"]).iterdir())


def test_a_good_dump_is_kept_with_private_permissions_and_reported(backup, monkeypatch) -> None:
    serve(backup, monkeypatch, dump_text())

    assert run(backup, monkeypatch) == 0

    assert dumps(backup) == ["scanopy-20261013T000000Z.sql.gz"]
    path = Path(backup.CONF["dir"]) / "scanopy-20261013T000000Z.sql.gz"
    assert (path.stat().st_mode & 0o777) == 0o600
    m = metrics(backup)
    assert m["scanopy_backup_last_attempt_success"] == 1 and m["scanopy_backup_files"] == 1
    assert m["scanopy_backup_last_size_bytes"] == path.stat().st_size
    assert m["scanopy_backup_last_success_timestamp_seconds"] > 1_700_000_000


def test_the_metrics_file_is_readable_by_node_exporter_even_under_a_strict_umask(backup, monkeypatch) -> None:
    # The unit runs with UMask=0077; a root-only .prom file is invisible to node_exporter and ScanopyBackupMetricsAbsent fires.
    old = os.umask(0o077)
    try:
        serve(backup, monkeypatch, dump_text())
        assert run(backup, monkeypatch) == 0
    finally:
        os.umask(old)

    assert (Path(backup.CONF["textfile"]).stat().st_mode & 0o777) == 0o644


def test_only_the_newest_files_are_kept(backup, monkeypatch) -> None:
    monkeypatch.setitem(backup.CONF, "keep", 3)
    serve(backup, monkeypatch, dump_text())

    for _ in range(5):
        assert run(backup, monkeypatch) == 0

    assert dumps(backup) == [f"scanopy-20261013T0{i}0000Z.sql.gz" for i in (2, 3, 4)]
    assert metrics(backup)["scanopy_backup_files"] == 3


@pytest.mark.parametrize(
    "payload,message",
    [
        (b"x", "bytes"),  # tiny
        (dump_text(complete=False), "truncated"),  # no completion trailer: the ssh stream was cut
        (dump_text(tables=("daemons", "hosts")), "lacks expected tables"),
    ],
)
def test_a_bad_dump_fails_the_run_and_never_replaces_or_rotates_good_ones(backup, monkeypatch, payload, message, capsys) -> None:
    monkeypatch.setitem(backup.CONF, "keep", 1)
    serve(backup, monkeypatch, dump_text())
    assert run(backup, monkeypatch) == 0
    good = metrics(backup)["scanopy_backup_last_success_timestamp_seconds"]

    serve(backup, monkeypatch, payload)
    assert run(backup, monkeypatch) == 1

    assert dumps(backup) == ["scanopy-20261013T000000Z.sql.gz"]  # no .part left behind, the good dump was not rotated away
    m = metrics(backup)
    assert m["scanopy_backup_last_attempt_success"] == 0
    assert m["scanopy_backup_last_success_timestamp_seconds"] == good  # staleness stays measurable after a failure
    assert message in capsys.readouterr().err


def test_a_table_name_that_is_only_a_prefix_does_not_count(backup, monkeypatch) -> None:
    # `daemon` must not satisfy `daemons`: the verification once matched the prefix of another table name.
    serve(backup, monkeypatch, dump_text(tables=("daemon_interfaced_subnets", "hosts", "discovery", "api_keys", "credentials")))

    assert run(backup, monkeypatch) == 1


def test_ssh_failure_is_reported_without_touching_existing_dumps(backup, monkeypatch) -> None:
    serve(backup, monkeypatch, dump_text())
    run(backup, monkeypatch)
    serve(backup, monkeypatch, None, error="ssh/pg_dump failed (rc=255): Host key verification failed")

    assert run(backup, monkeypatch) == 1

    assert dumps(backup) == ["scanopy-20261013T000000Z.sql.gz"]


def test_dry_run_keeps_nothing_and_publishes_nothing(backup, monkeypatch) -> None:
    serve(backup, monkeypatch, dump_text())

    assert run(backup, monkeypatch, "--dry-run") == 0

    assert dumps(backup) == [] and not Path(backup.CONF["textfile"]).exists()


def test_the_hypervisor_wrapper_streams_a_dump_and_refuses_everything_else(tmp_path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text("#!/bin/sh\necho \"docker $*\" >&2\necho dump-body\n")
    (fake_bin / "docker").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}

    ok = subprocess.run(["bash", str(WRAPPER_PATH)], env={**env, "SSH_ORIGINAL_COMMAND": "dump"}, capture_output=True)
    assert ok.returncode == 0 and gzip.decompress(ok.stdout) == b"dump-body\n"
    assert b"exec scanopy-postgres-1" in ok.stderr and b"pg_dump" in ok.stderr

    for forbidden in ("bash", "dump; id", "psql", "dump extra"):
        bad = subprocess.run(["bash", str(WRAPPER_PATH)], env={**env, "SSH_ORIGINAL_COMMAND": forbidden}, capture_output=True)
        assert bad.returncode == 2 and bad.stdout == b"", forbidden


def test_a_failing_pg_dump_makes_the_wrapper_fail_instead_of_streaming_an_empty_dump(tmp_path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "docker").write_text("#!/bin/sh\necho 'no such container' >&2\nexit 1\n")
    (fake_bin / "docker").chmod(0o755)

    out = subprocess.run(["bash", str(WRAPPER_PATH)], env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "SSH_ORIGINAL_COMMAND": "dump"}, capture_output=True)

    assert out.returncode != 0
