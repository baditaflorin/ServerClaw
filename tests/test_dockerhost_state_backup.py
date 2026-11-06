"""Tests for config/0docker/dockerhost-state-backup (the file-level backup of the Docker host's state to own-pbs).

Real SQLite files, real subprocesses and shell shims for `docker` and `proxmox-backup-client` (recording their argv and environment), so the
run is exercised end to end: preflight, staging of Postgres dumps and online SQLite copies, one client call, cleanup, metrics, exit code.
Standard library and pytest only.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DIR = REPO_ROOT / "config" / "0docker" / "dockerhost-state-backup"
SCRIPT = DIR / "dockerhost_state_backup.py"
SECRET = "00000000-test-secret-0000-000000000000"


def load():
    spec = importlib.util.spec_from_file_location("dockerhost_state_backup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = load()


# ----------------------------------------------------------------------------- fixtures


def write_exe(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """Archive roots, a fake docker and a fake client on PATH, a private token file, the lock and the textfile in tmp."""
    roots = {}
    for name in ("etc", "opt", "home", "srv", "root", "volumes"):
        roots[name] = tmp_path / "fs" / name
        roots[name].mkdir(parents=True)
    (roots["etc"] / "hosts").write_text("127.0.0.1 localhost\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    (state / "containers.jsonl").write_text("")
    write_exe(bin_dir / "docker", f"""#!/bin/sh
S={state}
case "$1" in
  ps) if [ "$2" = "-q" ]; then awk -F'"' '{{print $4}}' $S/containers.jsonl; else :; fi ;;
  inspect) cat $S/containers.jsonl ;;
  exec)
    shift; name="$1"; shift
    if [ "$1" = "printenv" ]; then cat "$S/user.$name" 2>/dev/null || exit 1
    elif [ "$1" = "pg_dumpall" ]; then
      if [ -f "$S/fail.$name" ]; then echo "pg_dumpall: error: connection failed" >&2; exit 1; fi
      echo "-- PostgreSQL database cluster dump of $name"; echo "$@" | sed 's/^/-- args: /'; echo "CREATE ROLE app;"; echo "SELECT 1;"
    fi ;;
  *) : ;;
esac
""")
    write_exe(bin_dir / "proxmox-backup-client", f"""#!/bin/sh
S={state}
printf '%s\\n' "$@" > $S/client.argv
env | grep -E '^PBS_' | sed 's/=.*//' | sort > $S/client.env.names
printf '%s' "$PBS_PASSWORD" > $S/client.password
# the staging archive must still exist while the client runs
for a in "$@"; do case "$a" in staging.pxar:*) ls "${{a#staging.pxar:}}" > $S/client.staging.ls 2>&1; find "${{a#staging.pxar:}}/sqlite" -type f > $S/client.staging.files 2>/dev/null; cp "${{a#staging.pxar:}}/MANIFEST.json" $S/client.manifest.json 2>/dev/null;; esac; done
if [ -f $S/client.fail ]; then echo "Error: simulated failure"; exit 1; fi
echo "Upload statistics: ok"
""")
    secret = tmp_path / "token.secret"
    secret.write_text(SECRET + "\n")
    secret.chmod(0o600)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setattr(mod, "LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.setattr(mod, "loadavg", lambda: (1.0, 1.0, 1.0))
    staging = tmp_path / "var-backups" / "dockerhost-state"
    cfg = json.loads((DIR / "config.json").read_text())
    cfg.update({"secret_file": str(secret), "staging_dir": str(staging), "textfile": str(tmp_path / "metrics" / "x.prom"),
                "archives": {n: str(p) for n, p in roots.items()}, "exclude": {}})
    (tmp_path / "metrics").mkdir()

    def remove_staging(path):  # the real one only deletes below /var/backups or /var/tmp: tests stage in tmp
        if os.path.isdir(path) and "dockerhost-state" in os.path.basename(path.rstrip("/")):
            import shutil
            shutil.rmtree(path, ignore_errors=True)

    monkeypatch.setattr(mod, "remove_staging", remove_staging)

    class World:
        pass

    w = World()
    w.tmp, w.roots, w.state, w.cfg, w.secret, w.staging = tmp_path, roots, state, cfg, secret, staging

    def add_container(name, image, mounts, user=None):
        with (state / "containers.jsonl").open("a") as fh:
            fh.write(json.dumps({"name": "/" + name, "image": image, "mounts": mounts}) + "\n")
        if user:
            (state / f"user.{name}").write_text(user + "\n")

    w.add_container = add_container
    return w


def args(skip=True):
    class A:
        skip_load_check = skip

    return A()


def wal_db(path: Path, rows: int = 50) -> sqlite3.Connection:
    """A WAL-mode database that is open (so -wal and -shm exist) and holds committed rows that were never checkpointed."""
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
    for i in range(rows):
        conn.execute("INSERT INTO t(v) VALUES (?)", ("row %d " % i + "x" * 200,))
    return conn


# ----------------------------------------------------------------------------- configuration


def test_the_shipped_config_is_valid_and_holds_no_secret():
    cfg = json.loads((DIR / "config.json").read_text())
    assert mod.config_problems(cfg) == []
    text = (DIR / "config.json").read_text()
    assert "password" not in text.lower() and SECRET not in text
    assert cfg["repository"].split("@")[1].startswith("pbs!"), "an API token, not a user password"
    assert cfg["secret_file"].startswith("/etc/dockerhost-state-backup/")
    assert cfg["backup_type"] == "host" and cfg["namespace"] == "0docker" and cfg["backup_id"] == "dockerhost-state"
    assert "/etc/dockerhost-state-backup/token.secret" not in "".join(cfg["archives"].values())
    assert "/dockerhost-state-backup/token.secret" in cfg["exclude"]["etc"], "the backup must not carry its own token"


@pytest.mark.parametrize("key,value,needle", [
    ("repository", "backup@pbs@100.1.1.1:own-pbs", "API token"),
    ("fingerprint", "C2:22", "fingerprint"),
    ("backup_type", "vm", "backup_type"),
    ("staging_dir", "/", "staging_dir"),
    ("staging_dir", "/var/lib/docker", "staging_dir"),
    ("archives", {"staging": "/x"}, "reserved"),
    ("archives", {"etc": "etc"}, "absolute"),
    ("exclude", {"nope": ["/a"]}, "unknown archive"),
    ("exclude", {"etc": ["relative"]}, "anchored"),
    ("limits", {"start_load5": 0}, "limits."),
])
def test_config_problems_are_named(key, value, needle):
    cfg = json.loads((DIR / "config.json").read_text())
    cfg[key] = value
    assert any(needle in p for p in mod.config_problems(cfg)), (key, mod.config_problems(cfg))


def test_the_token_file_must_be_private_and_non_empty(tmp_path):
    f = tmp_path / "s"
    f.write_text(SECRET)
    f.chmod(0o644)
    with pytest.raises(mod.BackupError, match="chmod 600"):
        mod.read_secret(str(f))
    f.chmod(0o600)
    assert mod.read_secret(str(f)) == SECRET
    f.write_text("\n")
    with pytest.raises(mod.BackupError, match="empty"):
        mod.read_secret(str(f))


# ----------------------------------------------------------------------------- patterns


def test_patterns_are_anchored_escaped_and_belong_to_the_longest_matching_root():
    assert mod.escape_pattern("/a[b]/c*?\\d") == "/a\\[b\\]/c\\*\\?\\\\d"
    assert mod.relative_pattern("/root", "/root/embcache") == "/embcache"
    assert mod.relative_pattern("/root", "/rootx/a") is None and mod.relative_pattern("/root", "/root") is None
    assert mod.relative_pattern("/", "/etc/x") == "/etc/x"
    archives = {"volumes": "/var/lib/docker/volumes", "var": "/var/lib"}
    assert mod.owning_archive(archives, "/var/lib/docker/volumes/v/_data") == ("volumes", "/v/_data")
    assert mod.owning_archive(archives, "/elsewhere") == (None, None)


def test_a_pattern_that_names_a_path_of_another_archive_is_refused(tmp_path):
    (tmp_path / "a" / "cache").mkdir(parents=True)
    (tmp_path / "b" / "cache").mkdir(parents=True)
    (tmp_path / "b" / "other").mkdir()
    archives = {"a": str(tmp_path / "a"), "b": str(tmp_path / "b")}
    assert mod.collisions(archives, {"a": ["/cache"], "b": []})  # /cache also exists in b: it would silently drop b's cache too
    assert mod.collisions(archives, {"b": ["/other"], "a": []}) == []
    assert mod.collisions(archives, {"a": ["/gl*b"], "b": []}) == []  # a glob cannot be checked by name


# ----------------------------------------------------------------------------- containers and the plan


def test_postgres_and_rebuildable_data_dirs_are_left_out_of_the_archive_that_holds_them(world):
    vol = world.roots["volumes"]
    (vol / "pgvol" / "_data").mkdir(parents=True)
    (vol / "esvol" / "_data").mkdir(parents=True)
    world.add_container("db1", "postgres:16-alpine", [{"Type": "volume", "Source": str(vol / "pgvol" / "_data"), "Destination": "/var/lib/postgresql/data"}], user="app")
    world.add_container("es", "elasticsearch:7.17.27", [{"Type": "volume", "Source": str(vol / "esvol" / "_data"), "Destination": "/usr/share/elasticsearch/data"}])
    world.add_container("cache", "redis:7-alpine", [{"Type": "volume", "Source": "/x", "Destination": "/data"}])
    cs = mod.containers()
    assert [c["name"] for c in cs] == ["db1", "es", "cache"]
    cls = mod.classify(cs)
    assert [c["name"] for c in cls["postgres"]] == ["db1"] and [c["name"] for c in cls["rebuildable"]] == ["es"] and [c["name"] for c in cls["raw_engines"]] == ["cache"]
    plan = mod.build_plan(world.cfg, cs, time.time(), discover=False)
    assert plan["excludes"]["volumes"] == ["/pgvol/_data", "/esvol/_data"]
    assert any("db1" in n and "dumped" in n for n in plan["notes"]) and any("cache" in n and "crash-consistent" in n for n in plan["notes"])
    assert plan["problems"] == []


def test_a_postgres_data_dir_outside_every_archive_is_a_warning_not_a_silent_loss(world):
    world.add_container("db2", "postgres:17", [{"Type": "bind", "Source": "/mnt/elsewhere/pg", "Destination": "/var/lib/postgresql/data"}])
    plan = mod.build_plan(world.cfg, mod.containers(), time.time(), discover=False)
    assert any(n.startswith("WARNING /mnt/elsewhere/pg is outside every archive") for n in plan["notes"])


# ----------------------------------------------------------------------------- sqlite


def test_a_wal_database_that_is_open_is_copied_online_with_its_uncheckpointed_rows(world):
    src = world.roots["opt"] / "app" / "data.db"
    src.parent.mkdir()
    conn = wal_db(src, rows=40)
    try:
        assert os.path.getsize(str(src) + "-wal") > 0 and os.path.exists(str(src) + "-shm")
        before = sorted(p.name for p in src.parent.iterdir())
        dst = world.tmp / "copy.db"
        mod.sqlite_backup(str(src), str(dst), wal=True)
        assert sorted(p.name for p in src.parent.iterdir()) == before, "the read-only open must not create or change files next to the live database"
        c2 = sqlite3.connect(str(dst))
        assert c2.execute("SELECT count(*) FROM t").fetchone()[0] == 40
        assert c2.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # a raw copy of the main file alone would have lost them: this is why the file copy is not enough
        raw = world.tmp / "raw.db"
        raw.write_bytes(src.read_bytes())
        assert sqlite3.connect(str(raw)).execute("SELECT count(*) FROM sqlite_master WHERE name='t'").fetchone()[0] == 0
    finally:
        conn.close()


def test_the_child_entry_point_copies_and_reports_failure(world):
    src = world.roots["opt"] / "d.db"
    conn = wal_db(src, rows=5)
    try:
        dst = world.tmp / "c.db"
        ok = subprocess.run([sys.executable, str(SCRIPT), "_sqlite", str(src), str(dst), "1"], capture_output=True, text=True)
        assert ok.returncode == 0 and sqlite3.connect(str(dst)).execute("SELECT count(*) FROM t").fetchone()[0] == 5
        bad = subprocess.run([sys.executable, str(SCRIPT), "_sqlite", str(world.tmp / "missing.db"), str(world.tmp / "m.db"), "1"], capture_output=True, text=True)
        assert bad.returncode == 1 and bad.stderr.strip()
    finally:
        conn.close()


def test_live_and_quiet_databases_are_told_apart(world):
    live = world.roots["opt"] / "live.db"
    conn = wal_db(live)
    quiet = world.roots["opt"] / "quiet.db"
    q = sqlite3.connect(str(quiet))
    q.execute("CREATE TABLE t(x)")
    q.commit()
    q.close()
    old = time.time() - 86400
    os.utime(quiet, (old, old))
    junk = world.roots["opt"] / "notes.db"
    junk.write_bytes(b"not a database" * 1000)
    try:
        found = {p: (s, m) for p, s, m in mod.sqlite_candidates([str(world.roots["opt"])], [])}
        assert str(live) in found and str(quiet) in found and str(junk) not in found
        now = time.time()
        assert mod.is_live(str(live), found[str(live)][1], now) is True
        assert mod.is_live(str(quiet), found[str(quiet)][1], now) is False
    finally:
        conn.close()


def test_a_rollback_journal_database_is_live_when_it_has_a_hot_journal_or_was_just_written(world):
    db = world.roots["opt"] / "old-style.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE t(x)")
    c.execute("INSERT INTO t VALUES (1)")
    c.commit()
    c.close()
    assert mod.journal_mode_wal(str(db)) is False
    now = time.time()
    old = now - 86400
    os.utime(db, (old, old))
    assert mod.is_live(str(db), old, now) is False  # quiet for a day, no journal: a plain copy is consistent
    assert mod.is_live(str(db), now - 60, now) is True  # written a minute ago
    dst = world.tmp / "c2.db"
    mod.sqlite_backup(str(db), str(dst), wal=False)  # the stepwise path for rollback-journal databases
    assert sqlite3.connect(str(dst)).execute("SELECT x FROM t").fetchone()[0] == 1
    (world.roots["opt"] / "old-style.db-journal").write_bytes(b"x")
    assert mod.is_live(str(db), old, now) is True  # a hot journal: someone is in the middle of a write


def corrupt_interior_page(db: Path) -> None:
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
    c.executemany("INSERT INTO t(v) VALUES (?)", [("x" * 500,) for _ in range(400)])
    c.commit()
    c.close()
    data = bytearray(db.read_bytes())
    data[3 * 4096: 3 * 4096 + 300] = b"\xff" * 300  # an interior page: the backup API copies pages without parsing them
    db.write_bytes(bytes(data))


def test_a_corrupt_source_is_copied_and_then_reported_by_the_separate_check(world):
    db = world.roots["opt"] / "bad.db"
    corrupt_interior_page(db)
    dst = world.tmp / "bad-copy.db"
    copy = subprocess.run([sys.executable, str(SCRIPT), "_sqlite", str(db), str(dst), "0"], capture_output=True, text=True)
    assert copy.returncode == 0 and dst.exists(), "the copy itself does not judge the content"
    check = subprocess.run([sys.executable, str(SCRIPT), "_check", str(dst), str(db)], capture_output=True, text=True)
    assert check.returncode == 1 and check.stderr.strip(), "the check must fail for a damaged database"
    ok = world.roots["opt"] / "fine.db"
    c = sqlite3.connect(str(ok))
    c.execute("CREATE TABLE t(x)")
    c.commit()
    c.close()
    fine = world.tmp / "fine-copy.db"
    assert subprocess.run([sys.executable, str(SCRIPT), "_sqlite", str(ok), str(fine), "0"]).returncode == 0
    assert subprocess.run([sys.executable, str(SCRIPT), "_check", str(fine), str(ok)]).returncode == 0
    assert subprocess.run([sys.executable, str(SCRIPT), "_check", str(world.tmp / "missing.db"), str(ok)], capture_output=True).returncode == 1



def test_the_staged_copy_of_a_wal_database_stands_alone_without_wal_or_shm(world):
    src = world.roots["opt"] / "app" / "w.db"
    src.parent.mkdir()
    conn = wal_db(src, rows=30)
    try:
        dst = world.tmp / "stage" / "w.db"
        dst.parent.mkdir()
        mod.sqlite_backup(str(src), str(dst), wal=True)
        assert sorted(p.name for p in dst.parent.iterdir()) == ["w.db"], "no -wal/-shm may be left next to a staged copy: they would be archived and restored"
        assert mod.journal_mode_wal(str(dst)) is False
        assert sqlite3.connect(str(dst)).execute("SELECT count(*) FROM t").fetchone()[0] == 30
    finally:
        conn.close()


def test_a_database_with_a_virtual_table_this_sqlite_cannot_open_is_copied_not_failed():
    """2026-10-21: hermes' state.db has messages_fts_trigram; quick_check raised 'vtable constructor failed' and the whole copy was reported failed."""
    class Conn:
        def __init__(self, exc=None, row=("ok",)):
            self.exc, self.row = exc, row

        def execute(self, sql):
            if self.exc:
                raise self.exc
            return self

        def fetchone(self):
            return self.row

    mod.check_copy(Conn(sqlite3.OperationalError("vtable constructor failed: messages_fts_trigram")), "/x.db")
    with pytest.raises(sqlite3.DatabaseError):
        mod.check_copy(Conn(sqlite3.DatabaseError("database disk image is malformed")), "/x.db")
    with pytest.raises(mod.BackupError, match="quick_check"):
        mod.check_copy(Conn(row=("*** in database main ***",)), "/x.db")
    mod.check_copy(Conn(), "/x.db")


def test_files_listed_in_raw_sqlite_are_never_staged_never_excluded_and_never_warned_about(world):
    keep = world.roots["srv"] / "backups"
    keep.mkdir()
    db = keep / "state-corrupt.db"
    conn = wal_db(db)  # a static copy that still has its -shm from the day it was made
    conn.close()
    (keep / "state-corrupt.db-shm").write_bytes(b"x" * 32768)
    live = world.roots["srv"] / "live.db"
    conn2 = wal_db(live)
    try:
        world.cfg["raw_sqlite"] = [str(world.roots["srv"] / "backups") + "/*"]
        plan = mod.build_plan(world.cfg, [], time.time())
        assert [x["path"] for x in plan["live_sqlite"]] == [str(live)]
        assert not [e for e in plan["excludes"]["srv"] if "backups" in e], "a raw file stays in the file archive"
        assert any("state-corrupt.db" in n and "raw_sqlite" in n for n in plan["notes"])
    finally:
        conn2.close()


def test_raw_sqlite_must_be_absolute_patterns_and_the_shipped_config_lists_the_known_static_copies():
    cfg = json.loads((DIR / "config.json").read_text())
    assert mod.config_problems(cfg) == []
    bad = dict(cfg, raw_sqlite=["relative/*"])
    assert any("raw_sqlite" in p for p in mod.config_problems(bad))
    assert "/srv/hermes-offsite/backups/*" in cfg["raw_sqlite"] and "/srv/hermes-offsite/recovery-work-*" in cfg["raw_sqlite"]
    assert not any("graph.db" in g or "chaos.db" in g or "keys.db" in g.split("/")[-1] for g in cfg["raw_sqlite"]), "the databases that matter are never exempted"


def test_discovery_skips_excluded_trees_and_symlinks(world):
    (world.roots["opt"] / "skipme").mkdir()
    db = world.roots["opt"] / "skipme" / "a.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE t(x)")
    c.commit()
    c.close()
    link = world.roots["opt"] / "link.db"
    link.symlink_to(db)
    assert mod.sqlite_candidates([str(world.roots["opt"])], [str(world.roots["opt"] / "skipme")]) == []
    assert [p for p, _s, _m in mod.sqlite_candidates([str(world.roots["opt"])], [])] == [str(db)]


def test_live_sqlite_files_and_their_sidecars_are_excluded_from_the_file_archive(world):
    db = world.roots["volumes"] / "v" / "_data" / "graph.db"
    db.parent.mkdir(parents=True)
    conn = wal_db(db)
    try:
        plan = mod.build_plan(world.cfg, [], time.time())
        assert [x["path"] for x in plan["live_sqlite"]] == [str(db)] and plan["live_sqlite"][0]["wal"] is True
        assert plan["excludes"]["volumes"] == ["/v/_data/graph.db", "/v/_data/graph.db-wal", "/v/_data/graph.db-shm", "/v/_data/graph.db-journal"]
    finally:
        conn.close()


# ----------------------------------------------------------------------------- dumps


def test_pg_dumpall_runs_as_the_containers_own_user_and_is_compressed(world, tmp_path):
    world.add_container("db1", "postgres:16", [{"Type": "volume", "Source": "/s", "Destination": "/var/lib/postgresql/data"}], user="geocode")
    c = mod.containers()[0]
    path = mod.dump_postgres(c, str(tmp_path), 30)
    text = gzip.open(path, "rt").read()
    assert path.endswith("db1.sql.gz") and "CREATE ROLE app;" in text
    assert "-U geocode --clean --if-exists" in text


def test_a_failing_dump_raises_with_the_reason(world, tmp_path):
    world.add_container("db1", "postgres:16", [{"Type": "volume", "Source": "/s", "Destination": "/var/lib/postgresql/data"}])
    (world.state / "fail.db1").write_text("x")
    with pytest.raises(mod.BackupError, match="connection failed"):
        mod.dump_postgres(mod.containers()[0], str(tmp_path), 30)


# ----------------------------------------------------------------------------- the run


def test_a_run_makes_one_snapshot_with_every_archive_keeps_the_secret_off_the_command_line_and_cleans_up(world, capsys):
    vol = world.roots["volumes"]
    (vol / "pgvol" / "_data").mkdir(parents=True)
    world.add_container("db1", "postgres:16-alpine", [{"Type": "volume", "Source": str(vol / "pgvol" / "_data"), "Destination": "/var/lib/postgresql/data"}], user="app")
    db = vol / "g" / "_data" / "graph.db"
    db.parent.mkdir(parents=True)
    conn = wal_db(db, rows=20)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        conn.close()
    argv = (world.state / "client.argv").read_text().split("\n")
    assert argv[:2] == ["backup", ""] or argv[0] == "backup", argv[:3]
    named = [a.split(":")[0] for a in argv if ".pxar:" in a]
    assert named == ["etc.pxar", "opt.pxar", "home.pxar", "srv.pxar", "root.pxar", "volumes.pxar", "staging.pxar"]
    pairs = dict(zip(argv, argv[1:]))
    assert pairs["--ns"] == "0docker" and pairs["--backup-type"] == "host" and pairs["--backup-id"] == "dockerhost-state"
    assert pairs["--crypt-mode"] == "none" and pairs["--change-detection-mode"] == "metadata" and pairs["--repository"] == world.cfg["repository"]
    excludes = [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"]
    assert "/pgvol/_data" in excludes and "/g/_data/graph.db" in excludes and "/g/_data/graph.db-wal" in excludes
    assert SECRET not in "\n".join(argv) and SECRET not in capsys.readouterr().out, "the secret must never appear on a command line or in the log"
    assert (world.state / "client.password").read_text() == SECRET
    assert (world.state / "client.env.names").read_text().split() == ["PBS_FINGERPRINT", "PBS_PASSWORD"]
    staging_ls = (world.state / "client.staging.ls").read_text().split()
    assert {"MANIFEST.json", "inventory", "pg", "sqlite"} <= set(staging_ls)
    manifest = json.loads((world.state / "client.manifest.json").read_text())
    assert manifest["postgres"] == ["db1"] and [x["path"] for x in manifest["sqlite"]] == [str(db)] and manifest["warnings"] == []
    assert not world.staging.exists(), "staging is removed after the run"
    prom = Path(world.cfg["textfile"]).read_text()
    assert "dockerhost_state_backup_last_status 1" in prom and "dockerhost_state_backup_warnings 0" in prom
    assert oct(Path(world.cfg["textfile"]).stat().st_mode & 0o777) == "0o644"


def test_a_failed_dump_copies_the_data_dir_as_it_is_and_the_run_still_ends_failed(world):
    vol = world.roots["volumes"]
    (vol / "pgvol" / "_data").mkdir(parents=True)
    world.add_container("db1", "postgres:16-alpine", [{"Type": "volume", "Source": str(vol / "pgvol" / "_data"), "Destination": "/var/lib/postgresql/data"}])
    (world.state / "fail.db1").write_text("x")
    assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    argv = (world.state / "client.argv").read_text().split("\n")
    assert "/pgvol/_data" not in [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"], "no usable dump: the raw data dir is better than nothing"
    prom = Path(world.cfg["textfile"]).read_text()
    assert "dockerhost_state_backup_last_status 0" in prom and "dockerhost_state_backup_warnings 1" in prom
    assert "dockerhost_state_backup_last_success_timestamp_seconds 0" in prom


def test_a_database_that_cannot_be_copied_online_is_then_copied_as_it_is_not_dropped(world):
    db = world.roots["volumes"] / "v" / "_data" / "s.db"
    db.parent.mkdir(parents=True)
    conn = wal_db(db, rows=5)
    bad = world.roots["volumes"] / "v" / "_data" / "bad.db"
    c = sqlite3.connect(str(bad))
    c.execute("CREATE TABLE t(x)")
    c.commit()
    c.close()
    data = bytearray(bad.read_bytes())
    data[16:18] = b"\x00\x03"  # an impossible page size: the magic still matches, but sqlite cannot open it for the copy
    bad.write_bytes(bytes(data))
    (world.roots["volumes"] / "v" / "_data" / "bad.db-journal").write_bytes(b"")  # makes it look open
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    finally:
        conn.close()
    argv = (world.state / "client.argv").read_text().split("\n")
    excludes = [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"]
    assert "/v/_data/s.db" in excludes, "the good database goes through its staged copy"
    assert "/v/_data/bad.db" not in excludes, "the one that could not be copied online stays in the file archive instead of vanishing"
    manifest = json.loads((world.state / "client.manifest.json").read_text())
    assert any("bad.db" in w and "online copy" in w for w in manifest["warnings"])


def test_a_damaged_source_keeps_its_staged_copy_and_the_run_ends_failed(world):
    db = world.roots["volumes"] / "v" / "_data" / "dmg.db"
    db.parent.mkdir(parents=True)
    corrupt_interior_page(db)
    (db.parent / "dmg.db-journal").write_bytes(b"")  # looks open
    assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    argv = (world.state / "client.argv").read_text().split("\n")
    excludes = [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"]
    assert "/v/_data/dmg.db" in excludes, "the copy is complete: it goes in through staging, the damaged original is not archived twice"
    manifest = json.loads((world.state / "client.manifest.json").read_text())
    assert any("dmg.db" in w and "source database is damaged" in w and "copy is kept" in w for w in manifest["warnings"])


def test_a_check_that_runs_out_of_time_never_throws_away_a_finished_copy(world, monkeypatch):
    """2026-10-21: chaos.db (8.7 GB) took over an hour on the starved host and the 3600 s limit discarded a complete copy; copy and check now have their own limits."""
    db = world.roots["volumes"] / "v" / "_data" / "slow.db"
    db.parent.mkdir(parents=True)
    conn = wal_db(db, rows=10)
    real = mod.run
    limits_seen = {}

    def run(cmd, **kw):
        for kind in ("_sqlite", "_check"):
            if kind in cmd:
                limits_seen[kind] = kw.get("timeout")
        if "_check" in cmd:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))
        return real(cmd, **kw)

    monkeypatch.setattr(mod, "run", run)
    world.cfg["limits"]["check_timeout_s"] = 5
    world.cfg["limits"]["sqlite_timeout_s"] = 777
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK, "an unfinished check is a note, not a failure"
    finally:
        conn.close()
    assert limits_seen == {"_sqlite": 777, "_check": 5}, "the copy and the check have their own limits"
    argv = (world.state / "client.argv").read_text().split("\n")
    assert "/v/_data/slow.db" in [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"]
    manifest = json.loads((world.state / "client.manifest.json").read_text())
    assert manifest["warnings"] == []


def test_a_database_above_check_max_bytes_is_copied_and_never_checked(world, monkeypatch):
    """2026-10-22: the check of kuma.db (2.5 GB) took 51 min and those of graph.db and chaos.db ran into their 1 h limit on the CPU-starved host, so a night took 3 h 44 min for a 24 min upload."""
    big = world.roots["volumes"] / "v" / "_data" / "big.db"
    big.parent.mkdir(parents=True)
    conn = wal_db(big, rows=2000)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # the main file only grows at a checkpoint: the discovery sees its size, not the WAL's
    small = world.roots["volumes"] / "v" / "_data" / "small.db"
    c2 = wal_db(small, rows=3)
    c2.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    real = mod.run
    checked = []

    def run(cmd, **kw):
        if "_check" in cmd:
            checked.append(cmd[cmd.index("_check") + 2])
        return real(cmd, **kw)

    monkeypatch.setattr(mod, "run", run)
    world.cfg["limits"]["check_max_bytes"] = 100_000  # between the two sizes
    try:
        assert os.path.getsize(big) > world.cfg["limits"]["check_max_bytes"] > os.path.getsize(small), (os.path.getsize(big), os.path.getsize(small))
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        conn.close()
        c2.close()
    assert checked == [str(small)], "only the small one is checked"
    argv = (world.state / "client.argv").read_text().split("\n")
    excludes = [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"]
    assert "/v/_data/big.db" in excludes and "/v/_data/small.db" in excludes, "both still go through their staged copies"
    staged = (world.state / "client.staging.files").read_text().split()
    assert any(f.endswith("/v/_data/big.db") for f in staged) and any(f.endswith("/v/_data/small.db") for f in staged), "skipping the check must not skip or discard the copy"
    manifest = json.loads((world.state / "client.manifest.json").read_text())
    assert manifest["warnings"] == [] and [x["path"] for x in manifest["sqlite"]] == [str(big), str(small)]


def test_check_timeout_must_be_a_positive_number_and_the_shipped_limits_give_the_copy_more_time_than_the_check():
    cfg = json.loads((DIR / "config.json").read_text())
    assert mod.config_problems(cfg) == []
    assert any("check_timeout_s" in p for p in mod.config_problems(dict(cfg, limits=dict(cfg["limits"], check_timeout_s=0))))
    assert any("check_max_bytes" in p for p in mod.config_problems(dict(cfg, limits=dict(cfg["limits"], check_max_bytes=-1))))
    assert cfg["limits"]["check_max_bytes"] < 2 * 2**30, "kuma.db (2.5 GB), graph.db and chaos.db must fall above the cap"
    assert mod.CHECK_MAX_BYTES_DEFAULT == 512 * 2**20 == cfg["limits"]["check_max_bytes"], "an installed config without the key behaves like the shipped one"
    assert cfg["limits"]["sqlite_timeout_s"] >= 3 * cfg["limits"]["check_timeout_s"] and cfg["limits"]["sqlite_timeout_s"] < cfg["limits"]["deadline_s"]


def test_a_client_failure_fails_the_run_keeps_the_last_success_and_still_removes_staging(world):
    Path(world.cfg["textfile"]).write_text("dockerhost_state_backup_last_success_timestamp_seconds 1234567\n")
    (world.state / "client.fail").write_text("x")
    assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    assert not world.staging.exists()
    prom = Path(world.cfg["textfile"]).read_text()
    assert "dockerhost_state_backup_last_status 0" in prom and "dockerhost_state_backup_last_success_timestamp_seconds 1234567" in prom


def test_a_pattern_collision_stops_the_run_before_anything_is_uploaded(world):
    (world.roots["root"] / "cache").mkdir()
    (world.roots["opt"] / "cache").mkdir()
    world.cfg["exclude"] = {"root": ["/cache"]}
    assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    assert not (world.state / "client.argv").exists()


def test_a_busy_host_skips_the_run_and_says_so(world, monkeypatch):
    monkeypatch.setattr(mod, "loadavg", lambda: (90.0, 90.0, 90.0))
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    world.cfg["limits"]["start_wait_s"] = 0.01
    assert mod.do_run(world.cfg, args(skip=False)) == mod.EXIT_SKIPPED
    assert not (world.state / "client.argv").exists()
    assert "dockerhost_state_backup_last_status 0" in Path(world.cfg["textfile"]).read_text()


def test_a_second_run_does_not_start_while_the_lock_is_held(world):
    import fcntl
    held = open(mod.LOCK_PATH, "w")
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_BUSY
    finally:
        held.close()


def test_a_missing_client_or_token_ends_the_run_failed_with_a_metric(world, monkeypatch):
    world.secret.chmod(0o644)
    assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    assert "dockerhost_state_backup_last_status 0" in Path(world.cfg["textfile"]).read_text()


# ----------------------------------------------------------------------------- load guard and cleanup


def test_the_watchdog_stops_the_client_when_the_load_stays_high_and_leaves_a_calm_one_alone():
    lim = {"abort_load1": 100, "deadline_s": 3600}
    proc = subprocess.Popen(["sleep", "30"])
    dog = mod.Watchdog(proc, lim, loadavg_fn=lambda: (500.0, 100.0, 100.0), period=0.02)
    dog.start()
    proc.wait(10)
    dog.join(5)
    assert proc.returncode is not None and "load1 stayed above 100" in dog.reason
    calm = subprocess.Popen(["sleep", "1"])
    dog2 = mod.Watchdog(calm, lim, loadavg_fn=lambda: (5.0, 5.0, 5.0), period=0.02)
    dog2.start()
    assert calm.wait(10) == 0 and dog2.reason == ""
    dog2.stop()


def test_the_watchdog_enforces_the_deadline():
    proc = subprocess.Popen(["sleep", "30"])
    dog = mod.Watchdog(proc, {"abort_load1": 1000, "deadline_s": 0.05}, loadavg_fn=lambda: (1.0, 1.0, 1.0), period=0.02)
    dog.start()
    proc.wait(10)
    assert "deadline" in dog.reason


def test_remove_staging_only_touches_the_staging_directory(tmp_path):
    real = mod.remove_staging
    keep = tmp_path / "something"
    keep.mkdir()
    (keep / "f").write_text("x")
    real(str(keep))  # not under /var/backups or /var/tmp and not named dockerhost-state: left alone
    assert (keep / "f").exists()
    real("/")  # never
    assert os.path.isdir("/")


def test_metrics_keep_the_previous_success_when_a_run_fails(tmp_path):
    p = tmp_path / "m.prom"
    mod.write_metrics(str(p), True, 100.0, 160.0, 0, 5, None)
    assert mod.previous_success(str(p)) == 160
    mod.write_metrics(str(p), False, 200.0, 230.0, 2, 0, 160)
    text = p.read_text()
    assert "dockerhost_state_backup_last_success_timestamp_seconds 160" in text and "dockerhost_state_backup_last_status 0" in text
    assert "dockerhost_state_backup_duration_seconds 30" in text and "dockerhost_state_backup_warnings 2" in text
    assert not (tmp_path / "m.prom.tmp").exists()


# ----------------------------------------------------------------------------- shipped units


def test_the_units_run_at_idle_priority_at_the_quiet_hour_and_the_service_runs_the_installed_script():
    service = (DIR / "dockerhost-state-backup.service").read_text()
    timer = (DIR / "dockerhost-state-backup.timer").read_text()
    assert "ExecStart=/usr/local/sbin/dockerhost-state-backup run" in service and "Type=oneshot" in service
    assert "Nice=19" in service and "IOSchedulingClass=idle" in service and "MemoryMax=" in service
    assert "OnCalendar=*-*-* 17:30:00 UTC" in timer and "Persistent=false" in timer and "WantedBy=timers.target" in timer
    readme = (DIR / "README.md").read_text()
    for needle in ("proxmox-backup-client restore", "pg_dumpall", "undo", "17:30"):
        assert needle.lower() in readme.lower(), needle
