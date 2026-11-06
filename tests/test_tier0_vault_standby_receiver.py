"""Tier-0 vault standby receiver (config/0infer/tier0-vault-standby/vault-standby-receive): the refuse-while-the-standby-runs guard.

The receiver only runs on infer-tier0 as the courier's forced command. Here its host paths point into tmp_path, `sqlite3` is a small stub
(real sqlite3 module, no CLI needed) and `stat` a stub, and the standby's ports are probed on loopback: a real TCP listener on one of them
stands for "the standby is running".
"""

from __future__ import annotations

import gzip
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDBY = REPO_ROOT / "config" / "0infer" / "tier0-vault-standby"
RECEIVER = STANDBY / "vault-standby-receive"
LOG, DATA, PORTS = "/home/vsync/receive.log", "/opt/tier0/vault-standby/data", 'STANDBY_PORTS="18021 18140"'

# sqlite3 stub: `sqlite3 FILE SQL` prints the first column of every row. With PAUSE_AT_INTEGRITY it parks on the integrity check until the
# test creates $FAKE_STATE/go, which lets the test start the "standby" while an upload is in flight.
SQLITE3_PY = """import os, sqlite3, sys, time
db, sql = sys.argv[1], sys.argv[2]
state = os.environ.get("FAKE_STATE", "")
if "integrity_check" in sql and os.environ.get("PAUSE_AT_INTEGRITY"):
    open(os.path.join(state, "at_integrity"), "w").close()
    deadline = time.time() + 30
    while not os.path.exists(os.path.join(state, "go")) and time.time() < deadline:
        time.sleep(0.05)
for row in sqlite3.connect(db).execute(sql):
    print(row[0])
"""


def _db(path: Path, tables: int) -> bytes:
    con = sqlite3.connect(path)
    for n in range(tables):
        con.execute(f"create table t{n} (v text)")
        con.execute(f"insert into t{n} values ('x')")
    con.commit()
    con.close()
    return path.read_bytes()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _listen(port: int) -> socket.socket:
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(5)
    return s


class Setup:
    """An installed receiver in tmp_path with an existing, older secrets.db and a courier upload ready."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.state, bin_dir = tmp_path / "state", tmp_path / "bin"
        for directory in (self.state, bin_dir):
            directory.mkdir()
        (tmp_path / "sqlite3_stub.py").write_text(SQLITE3_PY, encoding="utf-8")
        (bin_dir / "sqlite3").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{tmp_path / "sqlite3_stub.py"}" "$@"\n', encoding="utf-8")
        (bin_dir / "stat").write_text("#!/bin/sh\necho 4096\n", encoding="utf-8")
        for stub in ("sqlite3", "stat"):
            (bin_dir / stub).chmod(0o755)
        self.ports = (_free_port(), _free_port())
        script = RECEIVER.read_text(encoding="utf-8")
        for host_path in (LOG, DATA, PORTS):
            assert host_path in script, host_path
        script = script.replace(LOG, str(tmp_path / "receive.log")).replace(DATA, str(tmp_path / "data"))
        script = script.replace(PORTS, f'STANDBY_PORTS="{self.ports[0]} {self.ports[1]}"')
        self.script = tmp_path / "receive.sh"
        self.script.write_text(script, encoding="utf-8")
        self.dir = tmp_path / "data" / "vault"
        self.dir.mkdir(parents=True)
        self.old = _db(self.dir / "secrets.db", tables=1)
        (self.dir / ".last_sync").write_text("100\n", encoding="utf-8")
        self.upload = gzip.compress(_db(tmp_path / "new.db", tables=3))
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_STATE": str(self.state),
            "SSH_ORIGINAL_COMMAND": "put secrets",
        }

    def run(self, payload: bytes | None = None, command: str | None = None) -> subprocess.CompletedProcess[bytes]:
        env = {**self.env, **({"SSH_ORIGINAL_COMMAND": command} if command is not None else {})}
        return subprocess.run(["bash", str(self.script)], input=self.upload if payload is None else payload, env=env, capture_output=True, timeout=60, check=False)

    def untouched(self) -> None:
        assert (self.dir / "secrets.db").read_bytes() == self.old
        assert (self.dir / ".last_sync").read_text(encoding="utf-8") == "100\n"
        assert not list(self.dir.glob(".incoming.*"))
        assert not list((self.dir / "history").glob("*")) if (self.dir / "history").exists() else True


def test_an_upload_is_swapped_in_while_the_standby_is_stopped(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    result = s.run()
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().startswith("ok secrets.db")
    con = sqlite3.connect(s.dir / "secrets.db")
    assert con.execute("select count(*) from sqlite_master where type='table'").fetchone()[0] == 3
    con.close()
    assert int((s.dir / ".last_sync").read_text(encoding="utf-8")) > 100
    assert [p.read_bytes() for p in (s.dir / "history").glob("secrets.db.*")] == [s.old]
    assert "start cmd=[put secrets]" in (tmp_path / "receive.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("which", [0, 1], ids=["keystore-port", "vault-port"])
def test_a_running_standby_is_refused_with_the_upload_drained_and_nothing_touched(tmp_path: Path, which: int) -> None:
    s = Setup(tmp_path)
    listener = _listen(s.ports[which])
    try:
        # A 5 MB upload through a pipe: the producer only exits 0 if the receiver read all of it (141 = SIGPIPE, the leaked-snapshot case).
        result = subprocess.run(
            ["bash", "-c", 'head -c 5000000 /dev/zero | bash "$0"; echo "producer=${PIPESTATUS[0]} receiver=${PIPESTATUS[1]}"', str(s.script)],
            env=s.env,
            capture_output=True,
            timeout=60,
            check=False,
        )
    finally:
        listener.close()
    assert "producer=0 receiver=5" in result.stdout.decode(), (result.stdout, result.stderr)
    assert "refused: the standby is running" in result.stderr.decode()
    s.untouched()
    assert not (s.dir / "history").exists()  # refused before anything was created


def test_a_standby_that_starts_during_the_upload_is_refused_before_the_swap(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    (tmp_path / "upload.gz").write_bytes(s.upload)
    with (tmp_path / "upload.gz").open("rb") as upload:
        proc = subprocess.Popen(
            ["bash", str(s.script)],
            stdin=upload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**s.env, "PAUSE_AT_INTEGRITY": "1"},
        )
        deadline = time.time() + 30
        while not (s.state / "at_integrity").exists() and time.time() < deadline:
            time.sleep(0.05)
        assert (s.state / "at_integrity").exists(), "the receiver never reached the integrity check"
        listener = _listen(s.ports[1])  # the standby comes up while the upload is being verified
        try:
            (s.state / "go").touch()
            out, err = proc.communicate(timeout=30)
        finally:
            listener.close()
    assert proc.returncode == 5, (out, err)
    assert "refused: the standby is running" in err.decode()
    s.untouched()


def test_unknown_commands_are_still_denied(tmp_path: Path) -> None:
    s = Setup(tmp_path)
    for command in ("put other", "get secrets", ""):
        result = s.run(command=command)
        assert result.returncode == 2 and b"denied" in result.stderr
    s.untouched()


def test_the_guard_watches_the_ports_the_standby_publishes_and_the_script_parses() -> None:
    subprocess.run(["bash", "-n", str(RECEIVER)], check=True)
    compose = (STANDBY / "compose.yml").read_text(encoding="utf-8")
    published = set(re.findall(r'"127\.0\.0\.1:(\d+):\d+"', compose))
    assert published == {"18021", "18140"}
    assert set(re.search(r'STANDBY_PORTS="([^"]+)"', RECEIVER.read_text(encoding="utf-8")).group(1).split()) == published  # type: ignore[union-attr]
