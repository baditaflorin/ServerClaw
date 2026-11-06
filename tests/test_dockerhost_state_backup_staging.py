"""Tests for the staging-peak part of config/0docker/dockerhost-state-backup: the large SQLite copies are staged one at a time, compressed with zstd,
proven to decompress to the same bytes, and only then is the raw copy deleted and its disk blocks trimmed.

Reuses the world fixture of test_dockerhost_state_backup.py (real SQLite files, real subprocesses, shell shims for `docker` and
`proxmox-backup-client`). `zstd` is replaced by a shim built on Python's gzip, so the pipeline is exercised on any host; one more test runs the real
zstd when it is installed. Standard library and pytest only.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import types
from pathlib import Path

import pytest

from tests.test_dockerhost_state_backup import DIR, args, mod, wal_db, world  # noqa: F401 - world is a fixture

REAL_ZSTD = shutil.which("zstd")
REAL_FILE_EXTENTS, REAL_TRIM_RANGES = mod.file_extents, mod.trim_ranges
MIB = 1 << 20


@pytest.fixture(autouse=True)
def no_real_trim(monkeypatch):
    """The tests never issue FIEMAP or FITRIM against the filesystem of the test host: here a trim always works (the tests that look at trimming replace these)."""
    monkeypatch.setattr(mod, "file_extents", lambda p: [(0, os.path.getsize(p))] if os.path.exists(p) else [])
    monkeypatch.setattr(mod, "trim_ranges", lambda d, r: sum(length for _start, length in r))


def fake_zstd(world, mode: str = "ok") -> None:
    """A `zstd` on PATH that speaks gzip. Used the way the script uses it: compress stdin to stdout, or `-d -q -c FILE` to stdout.
    mode: ok, fail (exits 3 without reading its input), garbage (decompresses to other bytes)."""
    (world.state / "zstd.mode").write_text(mode)
    path = world.tmp / "bin" / "zstd"
    path.write_text(
        f"""#!{sys.executable}
import gzip, sys
args = sys.argv[1:]
mode = open("{world.state}/zstd.mode").read().strip()
open("{world.state}/zstd.calls", "a").write(" ".join(args) + "\\n")
if "-d" in args:
    data = gzip.open(args[-1], "rb").read()
    sys.stdout.buffer.write(b"garbage" if mode == "garbage" else data)
else:
    if mode == "fail":
        sys.exit(3)
    sys.stdout.buffer.write(gzip.compress(sys.stdin.buffer.read(), 1))
"""
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def big_db(path: Path, rows: int) -> sqlite3.Connection:
    """A WAL database that is open and whose main file holds its rows (checkpointed), so the discovery sees its real size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = wal_db(path, rows=rows)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return conn


def client_files(world) -> list:
    return sorted((world.state / "client.staging.files").read_text().split())


def manifest(world) -> dict:
    return json.loads((world.state / "client.manifest.json").read_text())


def three_databases(world):
    vol = world.roots["volumes"] / "v" / "_data"
    paths = {"small": vol / "a-small.db", "big": vol / "b-big.db", "mid": vol / "c-mid.db"}
    conns = [big_db(paths["small"], 5), big_db(paths["big"], 4000), big_db(paths["mid"], 1500)]
    world.cfg["limits"]["compress_min_bytes"] = 50_000  # between the middle and the small one
    return paths, conns


def gunzip_to(src: str, dst: Path) -> None:
    dst.write_bytes(gzip.open(src, "rb").read())


# ----------------------------------------------------------------------------- configuration


def test_the_shipped_config_compresses_big_copies_and_trims_what_it_frees():
    cfg = json.loads((DIR / "config.json").read_text())
    assert mod.config_problems(cfg) == []
    lim = cfg["limits"]
    assert lim["compress_min_bytes"] == mod.COMPRESS_MIN_BYTES_DEFAULT == 64 * MIB, (
        "an installed config without the key behaves like the shipped one"
    )
    assert lim["compress_timeout_s"] == mod.COMPRESS_TIMEOUT_DEFAULT and lim["trim_wait_s"] == mod.TRIM_WAIT_DEFAULT
    assert lim["compress_min_bytes"] < lim["check_max_bytes"], (
        "a copy that is compressed must be small enough to have been checked, or be above the check cap"
    )
    assert cfg["trim_staging"] is True and mod.ZSTD_LEVEL == 1


@pytest.mark.parametrize(
    "mutate,needle",
    [
        (lambda c: c["limits"].update(compress_min_bytes=-1), "compress_min_bytes"),
        (lambda c: c["limits"].update(compress_min_bytes="big"), "compress_min_bytes"),
        (lambda c: c["limits"].update(compress_timeout_s=0), "compress_timeout_s"),
        (lambda c: c["limits"].update(trim_wait_s=-5), "trim_wait_s"),
        (lambda c: c.update(trim_staging="yes"), "trim_staging"),
        (lambda c: c.update(trim_staging=False), "trim_staging false needs limits.compress_min_bytes 0"),
    ],
)
def test_staging_config_problems_are_named(mutate, needle):
    cfg = json.loads((DIR / "config.json").read_text())
    mutate(cfg)
    assert any(needle in p for p in mod.config_problems(cfg))
    off = json.loads((DIR / "config.json").read_text())
    off["limits"]["compress_min_bytes"] = 0
    assert mod.config_problems(off) == [], "0 is how the compression is turned off"
    off["trim_staging"] = False
    assert mod.config_problems(off) == [], "without compression there is nothing to trim between copies"


# ----------------------------------------------------------------------------- the pipeline


def test_big_copies_are_staged_one_at_a_time_largest_first_and_only_the_compressed_ones_reach_the_client(
    world, monkeypatch
):
    fake_zstd(world)
    paths, conns = three_databases(world)
    real = mod.run
    seen = []

    def run(cmd, **kw):
        if "_sqlite" in cmd:
            raw = [p.name for p in (world.staging / "sqlite").rglob("*") if p.is_file() and not p.name.endswith(".zst")]
            seen.append((cmd[cmd.index("_sqlite") + 1], raw))
        return real(cmd, **kw)

    monkeypatch.setattr(mod, "run", run)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        for c in conns:
            c.close()
    assert [p for p, _ in seen] == [str(paths["big"]), str(paths["mid"]), str(paths["small"])], "largest first"
    assert all(raw == [] for _, raw in seen), "no raw copy is left on disk when the next copy starts: %s" % seen
    names = [Path(f).name for f in client_files(world)]
    assert names == ["a-small.db", "b-big.db.zst", "c-mid.db.zst"], (
        "the client sees the compressed big ones and the raw small one"
    )
    m = manifest(world)
    by_path = {x["path"]: x for x in m["sqlite"]}
    assert list(by_path) == [str(paths["small"]), str(paths["big"]), str(paths["mid"])], (
        "the manifest keeps the plan's order"
    )
    big = by_path[str(paths["big"])]
    assert (
        big["codec"] == "zstd"
        and big["level"] == 1
        and big["staged"].endswith("b-big.db.zst")
        and big["staged_bytes"] < big["copy_bytes"]
    )
    assert "codec" not in by_path[str(paths["small"])] and by_path[str(paths["small"])]["staged"].endswith("a-small.db")
    assert m["warnings"] == []
    raw_total = sum(x["copy_bytes"] for x in by_path.values())
    assert m["staging_peak_bytes"] < raw_total, (
        "the peak is below the sum of the raw copies (the old behaviour staged all of them at once)"
    )
    assert m["staging_peak_bytes"] >= big["copy_bytes"] + big["staged_bytes"], (
        "the directory is fullest when the raw copy and its compressed file both exist"
    )
    prom = Path(world.cfg["textfile"]).read_text()
    assert (
        "dockerhost_state_backup_staging_peak_bytes %d" % m["staging_peak_bytes"] in prom
        and "dockerhost_state_backup_last_status 1" in prom
    )


def run_keeping_the_staging(world, monkeypatch, tmp_path) -> Path:
    """do_run, but the staging directory is copied aside just before it is deleted: what the client saw, for the restore recipe."""
    kept = tmp_path / "kept"
    delete = mod.remove_staging

    def remove_staging(path):
        if os.path.isdir(path):
            shutil.copytree(path, kept, dirs_exist_ok=True)
        delete(path)

    monkeypatch.setattr(mod, "remove_staging", remove_staging)
    paths, conns = three_databases(world)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        for c in conns:
            c.close()
    return kept


def check_restore_recipe(kept: Path, decompress, tmp_path: Path) -> None:
    """The README's recipe: decompress the staged .zst to the original place, compare with the manifest's sha256, open the database."""
    m = json.loads((kept / "MANIFEST.json").read_text())
    big = next(x for x in m["sqlite"] if x["path"].endswith("b-big.db"))
    staged = kept / big["staged"]
    assert staged.name == "b-big.db.zst" and staged.stat().st_size == big["staged_bytes"] < big["copy_bytes"]
    restored = tmp_path / "restored" / "big.db"
    restored.parent.mkdir()
    decompress(staged, restored)
    assert hashlib.sha256(restored.read_bytes()).hexdigest() == big["sha256"], (
        "the manifest's sha256 is of the raw copy"
    )
    assert restored.stat().st_size == big["copy_bytes"]
    db = sqlite3.connect(str(restored))
    assert (
        db.execute("SELECT count(*) FROM t").fetchone()[0] == 4000
        and db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    )
    assert not list(kept.rglob("*.part")), "no partial file travels"


def test_a_compressed_copy_restores_to_the_same_database_and_matches_its_manifest_hash(world, monkeypatch, tmp_path):
    fake_zstd(world)
    kept = run_keeping_the_staging(world, monkeypatch, tmp_path)
    check_restore_recipe(kept, lambda src, dst: gunzip_to(str(src), dst), tmp_path)


def test_a_copy_staged_with_the_real_zstd_restores_with_the_real_zstd(world, monkeypatch, tmp_path):
    if not REAL_ZSTD:
        pytest.skip("zstd is not installed here")
    kept = run_keeping_the_staging(world, monkeypatch, tmp_path)
    check_restore_recipe(
        kept,
        lambda src, dst: dst.write_bytes(
            subprocess.run([REAL_ZSTD, "-d", "-q", "-c", str(src)], capture_output=True, check=True).stdout
        ),
        tmp_path,
    )


def test_compression_off_stages_every_copy_raw_all_at_once_like_before(world):
    paths, conns = three_databases(world)
    world.cfg["limits"]["compress_min_bytes"] = 0
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        for c in conns:
            c.close()
    assert [Path(f).name for f in client_files(world)] == ["a-small.db", "b-big.db", "c-mid.db"]
    assert manifest(world)["staging_peak_bytes"] == sum(x["copy_bytes"] for x in manifest(world)["sqlite"])


def test_a_failing_zstd_keeps_the_raw_copy_leaves_no_partial_file_and_ends_failed(world):
    fake_zstd(world, "fail")
    paths, conns = three_databases(world)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    finally:
        for c in conns:
            c.close()
    assert [Path(f).name for f in client_files(world)] == ["a-small.db", "b-big.db", "c-mid.db"], (
        "the raw copies are staged instead, nothing is lost and no .part is left"
    )
    assert any(
        "compressing the copy of" in w and "raw copy is staged instead" in w for w in manifest(world)["warnings"]
    )
    assert (world.state / "client.argv").exists(), "the backup itself is still made"
    assert "dockerhost_state_backup_last_status 0" in Path(world.cfg["textfile"]).read_text()


def test_a_compressed_copy_that_does_not_decompress_to_the_same_bytes_is_never_kept(world):
    fake_zstd(world, "garbage")
    paths, conns = three_databases(world)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    finally:
        for c in conns:
            c.close()
    assert [Path(f).name for f in client_files(world)] == ["a-small.db", "b-big.db", "c-mid.db"]
    assert any("does not decompress to the same bytes" in w for w in manifest(world)["warnings"])


def test_a_compression_that_runs_out_of_time_keeps_the_raw_copy(world, monkeypatch):
    fake_zstd(world)
    paths, conns = three_databases(world)
    real = mod.run
    limits = {}

    def run(cmd, **kw):
        if "_compress" in cmd:
            limits["compress"] = kw.get("timeout")
            Path(cmd[-1] + ".part").write_bytes(b"half")  # what a child killed by the timeout leaves behind
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 0))
        return real(cmd, **kw)

    monkeypatch.setattr(mod, "run", run)
    world.cfg["limits"]["compress_timeout_s"] = 123
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    finally:
        for c in conns:
            c.close()
    assert limits["compress"] == 123
    assert [Path(f).name for f in client_files(world)] == ["a-small.db", "b-big.db", "c-mid.db"]


def test_without_zstd_the_copies_are_staged_raw_and_the_run_says_why(world, monkeypatch):
    paths, conns = three_databases(world)
    monkeypatch.setattr(mod, "zstd_binary", lambda: None)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    finally:
        for c in conns:
            c.close()
    assert [Path(f).name for f in client_files(world)] == ["a-small.db", "b-big.db", "c-mid.db"]
    assert any("zstd is not installed" in w for w in manifest(world)["warnings"])


def test_a_staging_disk_that_cannot_hold_one_raw_copy_stops_the_run_before_anything_is_copied(world, monkeypatch):
    fake_zstd(world)
    paths, conns = three_databases(world)
    monkeypatch.setattr(
        mod.shutil, "disk_usage", lambda p: types.SimpleNamespace(total=10 << 30, used=10 << 30, free=1 << 20)
    )
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    finally:
        for c in conns:
            c.close()
    assert not (world.state / "client.argv").exists()


def test_compress_file_with_the_real_zstd_round_trips(tmp_path):
    if not REAL_ZSTD:
        pytest.skip("zstd is not installed here")
    src = tmp_path / "raw.db"
    conn = sqlite3.connect(str(src))
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t(v) VALUES (?)", [("row %d " % i + "x" * 100,) for i in range(5000)])
    conn.commit()
    conn.close()
    info = mod.compress_file(str(src), str(tmp_path / "raw.db.zst"))
    assert info["bytes"] == src.stat().st_size and info["compressed"] < info["bytes"] / 3
    assert (
        not (tmp_path / "raw.db.zst.part").exists() and oct((tmp_path / "raw.db.zst").stat().st_mode & 0o777) == "0o600"
    )
    out = subprocess.run(
        [REAL_ZSTD, "-d", "-q", "-c", str(tmp_path / "raw.db.zst")], capture_output=True, check=True
    ).stdout
    assert hashlib.sha256(out).hexdigest() == info["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()


def test_compress_file_removes_its_partial_output_when_zstd_fails(world, tmp_path):
    fake_zstd(world, "fail")
    work = tmp_path / "work"
    work.mkdir()
    src = work / "raw.db"
    src.write_bytes(os.urandom(300_000))
    with pytest.raises(mod.BackupError, match="zstd exited with 3"):
        mod.compress_file(str(src), str(work / "raw.db.zst"))
    assert sorted(p.name for p in work.iterdir()) == ["raw.db"]


def test_the_compress_child_prints_one_json_line_and_fails_with_a_reason(world, tmp_path):
    fake_zstd(world)
    src = tmp_path / "raw.bin"
    src.write_bytes(b"a" * 100_000)
    ok = subprocess.run(
        [sys.executable, str(mod.__file__), "_compress", str(src), str(tmp_path / "raw.bin.zst")],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0 and json.loads(ok.stdout.strip().splitlines()[-1])["bytes"] == 100_000
    bad = subprocess.run(
        [sys.executable, str(mod.__file__), "_compress", str(tmp_path / "missing"), str(tmp_path / "x.zst")],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1 and bad.stderr.strip()


def test_plan_names_the_staging_mode(world, capsys):
    fake_zstd(world)
    assert mod.do_plan(world.cfg) == mod.EXIT_OK
    out = capsys.readouterr().out
    assert (
        "staging: SQLite copies one at a time, largest first; those of 64 MiB and more are compressed with zstd -1 (zstd found)"
        in out
    )
    world.cfg["limits"]["compress_min_bytes"] = 0
    mod.do_plan(world.cfg)
    assert "staged uncompressed, all at once" in capsys.readouterr().out


# ----------------------------------------------------------------------------- trimming what was freed


def fiemap_answer(extents, last=True):
    """The bytes the kernel writes back for FS_IOC_FIEMAP: header (32 bytes) then 56 bytes per extent; extents = [(logical, physical, length, flags)]."""
    buf = bytearray(32 + 56 * 64)
    struct.pack_into("=QQLLLL", buf, 0, 0, 0xFFFFFFFFFFFFFFFF, 0, len(extents), 64, 0)
    for i, (logical, physical, length, flags) in enumerate(extents):
        struct.pack_into(
            "=QQQQQL",
            buf,
            32 + 56 * i,
            logical,
            physical,
            length,
            0,
            0,
            flags | (mod.FIEMAP_EXTENT_LAST if last and i == len(extents) - 1 else 0),
        )
    return buf


def test_file_extents_reads_the_physical_ranges_and_skips_extents_without_blocks(tmp_path, monkeypatch):
    f = tmp_path / "f"
    f.write_bytes(b"x")
    answers = [
        fiemap_answer(
            [
                (0, 4096 * 100, 4096 * 10, 0),
                (4096 * 10, 4096 * 999, 4096 * 5, 0x4),
                (4096 * 15, 4096 * 500, 4096 * 2, 0x800),
            ]
        )
    ]
    calls = []

    def ioctl(fd, request, buf, mutate=True):
        calls.append(request)
        buf[:] = answers.pop(0)
        return 0

    monkeypatch.setattr(mod.fcntl, "ioctl", ioctl)
    assert REAL_FILE_EXTENTS(str(f)) == [(4096 * 100, 4096 * 10), (4096 * 500, 4096 * 2)], (
        "DELALLOC holds no blocks; UNWRITTEN (preallocated) does"
    )
    assert calls == [mod.FS_IOC_FIEMAP] and mod.FS_IOC_FIEMAP == 0xC020660B


def test_file_extents_pages_through_a_fragmented_file_and_gives_up_quietly(tmp_path, monkeypatch):
    f = tmp_path / "f"
    f.write_bytes(b"x")
    answers = [fiemap_answer([(0, 8192, 4096, 0)], last=False), fiemap_answer([(4096, 40960, 4096, 0)], last=True)]
    monkeypatch.setattr(
        mod.fcntl, "ioctl", lambda fd, req, buf, mutate=True: buf.__setitem__(slice(None), answers.pop(0)) or 0
    )
    assert REAL_FILE_EXTENTS(str(f)) == [(8192, 4096), (40960, 4096)]

    def broken(fd, req, buf, mutate=True):
        raise OSError(25, "Inappropriate ioctl for device")

    monkeypatch.setattr(mod.fcntl, "ioctl", broken)
    assert REAL_FILE_EXTENTS(str(f)) == [], "a filesystem without FIEMAP just means nothing is trimmed"
    assert REAL_FILE_EXTENTS(str(tmp_path / "missing")) == []


def test_extents_that_are_close_are_joined_into_one_trim_range():
    assert mod.merge_ranges([(100, 10), (300, 10), (5000, 10)], gap=1000) == [(100, 210), (5000, 10)]
    assert mod.merge_ranges([(100, 10), (300, 10), (5000, 10)], gap=5000) == [(100, 4910)]
    assert mod.merge_ranges([(0, 4096), (1 << 30, 4096)], gap=1 << 20) == [(0, 4096), (1 << 30, 4096)]
    assert mod.merge_ranges([(50, 10), (0, 100)], gap=0) == [(0, 100)], "overlapping extents never shrink the range"
    assert mod.merge_ranges([]) == []


def test_trim_ranges_issues_fitrim_for_each_range_and_adds_up_what_was_discarded(tmp_path, monkeypatch):
    seen = []

    def ioctl(fd, request, buf, mutate=True):
        start, length, minlen = struct.unpack("=QQQ", bytes(buf))
        seen.append((request, start, length, minlen))
        struct.pack_into("=QQQ", buf, 0, start, length // 2, minlen)  # the kernel reports the bytes it discarded in len
        return 0

    monkeypatch.setattr(mod.fcntl, "ioctl", ioctl)
    assert REAL_TRIM_RANGES(str(tmp_path), [(4096, 8192), (1 << 20, 4 << 20)]) == 4096 + (2 << 20)
    assert seen == [(0xC0185879, 4096, 8192, 0), (0xC0185879, 1 << 20, 4 << 20, 0)] and mod.FITRIM == 0xC0185879


def test_a_deleted_staged_file_is_trimmed_only_after_the_directory_change_is_committed(tmp_path, monkeypatch):
    """ext4 offers a freed block to FITRIM only after the journal transaction of the delete has committed (a trim straight after the unlink returned
    0 MiB of 183 MiB on the bench), so the worker fsyncs the changed directory first."""
    events = []
    monkeypatch.setattr(mod, "file_extents", lambda p: [(4096 * 7, 4096 * 3)])
    monkeypatch.setattr(mod, "trim_ranges", lambda d, r: events.append(("trim", d, r)) or 8192)
    real_fsync = os.fsync
    monkeypatch.setattr(mod.os, "fsync", lambda fd: events.append(("fsync", os.fstat(fd).st_ino)) or real_fsync(fd))
    f = tmp_path / "sqlite" / "x.db"
    f.parent.mkdir()
    f.write_bytes(b"x")
    trimmer = mod.TrimWorker(str(tmp_path))
    mod.release(str(f), trimmer)
    trimmer.close(30)
    assert not f.exists()
    assert events == [("fsync", f.parent.stat().st_ino), ("trim", str(tmp_path), [(4096 * 7, 4096 * 3)])]
    assert trimmer.trimmed == 8192


def test_a_trim_that_fails_is_a_note_and_never_stops_the_worker(tmp_path, monkeypatch, capsys):
    calls = []

    def trim(d, r):
        calls.append(r)
        if len(calls) == 1:
            raise OSError(95, "Operation not supported")
        return 4096

    monkeypatch.setattr(mod, "trim_ranges", trim)
    trimmer = mod.TrimWorker(str(tmp_path))
    trimmer.submit([(0, 4096)])
    trimmer.submit([(8192, 4096)])
    trimmer.close(30)
    assert len(calls) == 2 and trimmer.trimmed == 4096
    assert "note: trimming freed staging blocks failed (OSError)" in capsys.readouterr().out


def test_a_run_trims_each_raw_copy_it_deletes_and_what_is_left_of_the_staging(world, monkeypatch):
    fake_zstd(world)
    paths, conns = three_databases(world)
    trims, submitted = [], []
    monkeypatch.setattr(
        mod, "file_extents", lambda p: [(abs(hash(p)) % 1000 * 4096, os.path.getsize(p) if os.path.exists(p) else 4096)]
    )
    monkeypatch.setattr(mod, "trim_ranges", lambda d, r: trims.append((d, r)) or sum(length for _start, length in r))
    real_submit = mod.TrimWorker.submit

    def submit(self, extents, changed_dir=""):
        submitted.append((world.staging.exists(), changed_dir))  # a delete must be done before its trim is handed over
        return real_submit(self, extents, changed_dir)

    monkeypatch.setattr(mod.TrimWorker, "submit", submit)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        for c in conns:
            c.close()
    assert [exists for exists, _ in submitted] == [True, True, False], (
        "the last trim is handed over after the staging directory is gone"
    )
    assert submitted[-1][1] == str(world.staging.parent) and submitted[0][1].endswith("/_data")
    assert len(trims) == 4, (
        "the self-test first, then one trim for each of the two raw copies that were compressed away, then one for the rest of the staging after it was removed"
    )
    assert trims[0][0] == str(world.staging), "the self-test runs in the staging directory, before the first copy"
    assert {d for d, _ in trims[1:]} == {str(world.staging.parent)}, (
        "the trims go to the filesystem that holds the staging directory"
    )
    assert not world.staging.exists()


def test_trimming_can_be_turned_off(world, monkeypatch):
    fake_zstd(world)
    paths, conns = three_databases(world)
    world.cfg["trim_staging"] = False
    world.cfg["limits"]["compress_min_bytes"] = 0
    monkeypatch.setattr(mod, "trim_ranges", lambda d, r: pytest.fail("trim was turned off"))
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        for c in conns:
            c.close()


def test_the_trim_selftest_passes_when_a_freed_file_gives_its_blocks_back(tmp_path):
    assert mod.trim_selftest(str(tmp_path), size=2 << 20) == ""
    assert sorted(p.name for p in tmp_path.iterdir()) == [], "the test file is gone"


def test_the_trim_selftest_names_why_trimming_does_not_work(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "file_extents", lambda p: [])
    assert "no extents" in mod.trim_selftest(str(tmp_path), size=2 << 20)
    monkeypatch.setattr(mod, "file_extents", lambda p: [(0, 2 << 20)])
    monkeypatch.setattr(mod, "trim_ranges", lambda d, r: 4096)
    assert "discarded only 0 MiB" in mod.trim_selftest(str(tmp_path), size=2 << 20)

    def unsupported(d, r):
        raise OSError(95, "Operation not supported")

    monkeypatch.setattr(mod, "trim_ranges", unsupported)
    assert mod.trim_selftest(str(tmp_path), size=2 << 20).startswith("OSError: ")
    assert [p.name for p in tmp_path.iterdir()] == [], "the test file is removed on every path"


def test_when_trimming_does_not_work_the_copies_are_staged_as_before_and_the_run_says_so(world, monkeypatch):
    """Staging one at a time without the trim made the disk file of the bench bigger than the old script did (21.9 against 18.2 GiB)."""
    fake_zstd(world)
    paths, conns = three_databases(world)
    monkeypatch.setattr(mod, "trim_ranges", lambda d, r: 0)
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_FAILED
    finally:
        for c in conns:
            c.close()
    assert [Path(f).name for f in client_files(world)] == ["a-small.db", "b-big.db", "c-mid.db"], (
        "nothing was compressed"
    )
    m = manifest(world)
    assert any("does not work here" in w and "staged as before, all at once" in w for w in m["warnings"])
    assert m["staging_peak_bytes"] == sum(x["copy_bytes"] for x in m["sqlite"])
    assert not (world.state / "zstd.calls").exists(), "zstd was never started"


def test_nothing_is_checked_or_warned_about_when_no_copy_is_big_enough_to_compress(world, monkeypatch):
    """A host without zstd, or a filesystem that cannot trim, only matters once there is something to compress."""
    db = world.roots["volumes"] / "v" / "_data" / "tiny.db"
    conn = big_db(db, 20)
    monkeypatch.setattr(mod, "zstd_binary", lambda: None)
    monkeypatch.setattr(
        mod, "trim_ranges", lambda d, r: pytest.fail("no trim without a compressed copy... except the final one")
    )
    monkeypatch.setattr(mod, "trim_selftest", lambda d, size=0: pytest.fail("no selftest when nothing qualifies"))
    world.cfg["trim_staging"] = False
    world.cfg["limits"]["compress_min_bytes"] = 0
    try:
        assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    finally:
        conn.close()
    assert manifest(world)["warnings"] == []


# ----------------------------------------------------------------------------- documentation


def test_the_readme_tells_how_to_restore_a_compressed_copy_and_where_the_numbers_come_from():
    readme = (DIR / "README.md").read_text()
    for needle in ("zstd -d", ".zst", "sha256", "Staging peak", "one at a time", "trim", "quick_check"):
        assert needle.lower() in readme.lower(), needle


# ----------------------------------------------------------------------------- what VM 100 ran before this directory said so (added 2026-10-29)
# On 2026-10-29 someone added 12 inventory entries to the installed script and 6 archives to the installed config by hand. Git has them since 2026-10-30,
# as they run. These tests pin them (so a later install from git cannot drop them unnoticed), and keep what is known about their secrets next to the entries.

LIVE_ARCHIVES = {
    "etc": "/etc",
    "opt": "/opt",
    "home": "/home",
    "srv": "/srv",
    "root": "/root",
    "volumes": "/var/lib/docker/volumes",
    "usr_local": "/usr/local",
    "tailscale": "/var/lib/tailscale",
    "dockernet": "/var/lib/docker/network",
    "systemd_state": "/var/lib/systemd",
    "url_categorizer_state": "/var/lib/url-categorizer",
    "fleet_container_audit": "/var/lib/fleet-container-audit",
}
INVENTORY_BEFORE_2026_10_29 = [
    "docker-ps-a.txt",
    "docker-images.txt",
    "docker-volumes.json",
    "docker-networks.txt",
    "dpkg-selections.txt",
    "systemd-enabled-units.txt",
    "crontab-root.txt",
    "df.txt",
    "lsblk.json",
    "ip-addr.txt",
    "uname.txt",
]
INVENTORY_ADDED_2026_10_29 = [
    ("os-release.txt", ["cat", "/etc/os-release"]),
    ("docker-version.txt", ["sh", "-c", "docker version; docker compose version"]),
    (
        "docker-images-digests.txt",
        ["docker", "images", "--digests", "--format", "{{.Repository}}:{{.Tag}}\t{{.Digest}}\t{{.ID}}"],
    ),
    ("docker-networks-inspect.json", ["sh", "-c", "docker network ls -q | xargs -r docker network inspect"]),
    ("docker-compose-ls.txt", ["docker", "compose", "ls", "-a"]),
    (
        "docker-noncompose-containers.json",
        [
            "sh",
            "-c",
            "docker ps -aq | xargs -r docker inspect --format '{{.Id}} {{index .Config.Labels \"com.docker.compose.project\"}}'"
            " | awk 'NF==1{print $1}' | xargs -r docker inspect",
        ],
    ),
    ("nft-ruleset.txt", ["nft", "list", "ruleset"]),
    ("iptables-save.txt", ["iptables-save"]),
    ("ip-route.txt", ["ip", "route"]),
    ("hostnamectl.txt", ["hostnamectl"]),
    ("tailscale-status.txt", ["tailscale", "status"]),
    ("systemd-timers.txt", ["systemctl", "list-timers", "--all", "--no-pager"]),
]


def test_the_shipped_config_lists_the_twelve_archives_vm100_runs_in_the_order_it_runs_them():
    cfg = json.loads((DIR / "config.json").read_text())
    assert mod.config_problems(cfg) == []
    assert list(cfg["archives"].items()) == list(LIVE_ARCHIVES.items()), (
        "the order is the order of the client's arguments"
    )
    assert set(cfg["exclude"]) == {"etc", "root", "volumes", "usr_local"}
    assert cfg["exclude"]["usr_local"] == ["/bin/cosign"], (
        "the 135 MB release binary of cosign is downloaded again when needed"
    )
    assert "/var/spool/cron" not in cfg["archives"].values(), (
        "tried on 2026-10-29 and removed: the directory does not exist on VM 100 and the client stopped with exit 255"
    )


def test_no_archive_lies_inside_another_one():
    roots = [r.rstrip("/") for r in json.loads((DIR / "config.json").read_text())["archives"].values()]
    assert len(set(roots)) == len(roots)
    for a in roots:
        for b in roots:
            assert a == b or not b.startswith(a + "/"), f"{b} lies inside {a}: it would be backed up twice"


def test_the_client_call_has_one_pxar_per_archive_in_config_order_then_staging_and_one_cosign_exclude():
    cfg = json.loads((DIR / "config.json").read_text())
    plan = {"archives": cfg["archives"], "excludes": {name: list(pats) for name, pats in cfg["exclude"].items()}}
    cmd = mod.client_command(cfg, plan, "/var/backups/dockerhost-state")
    named = [a for a in cmd if ".pxar:" in a]
    assert named == [f"{name}.pxar:{root}" for name, root in LIVE_ARCHIVES.items()] + [
        "staging.pxar:/var/backups/dockerhost-state"
    ]
    excludes = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--exclude"]
    assert excludes.count("/bin/cosign") == 1 and "/dockerhost-state-backup/token.secret" in excludes


def test_a_run_with_the_twelve_shipped_archives_uploads_them_in_order_and_stages_all_inventory_files(
    world, monkeypatch
):
    for name in LIVE_ARCHIVES:
        world.roots[name] = world.tmp / "fs" / name
        world.roots[name].mkdir(parents=True, exist_ok=True)
    (world.roots["usr_local"] / "bin").mkdir()
    (world.roots["usr_local"] / "bin" / "cosign").write_bytes(b"x" * 100)
    (world.roots["tailscale"] / "tailscaled.state").write_text("{}")
    world.cfg["archives"] = {name: str(world.roots[name]) for name in LIVE_ARCHIVES}
    world.cfg["exclude"] = {"usr_local": ["/bin/cosign"]}
    seen = {}
    real_stage_inventory = mod.stage_inventory

    def spy(dest):
        real_stage_inventory(dest)
        seen["files"] = sorted(os.listdir(dest))

    monkeypatch.setattr(mod, "stage_inventory", spy)
    assert mod.do_run(world.cfg, args()) == mod.EXIT_OK
    argv = (world.state / "client.argv").read_text().split("\n")
    assert [a.split(":")[0] for a in argv if ".pxar:" in a] == [f"{n}.pxar" for n in LIVE_ARCHIVES] + ["staging.pxar"]
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "--exclude"] == ["/bin/cosign"]
    assert seen["files"] == sorted(INVENTORY_BEFORE_2026_10_29 + [name for name, _cmd in INVENTORY_ADDED_2026_10_29])
    assert manifest(world)["warnings"] == []


def test_the_inventory_is_what_vm100_runs():
    names = [name for name, _cmd in mod.INVENTORY]
    assert names == INVENTORY_BEFORE_2026_10_29 + [name for name, _cmd in INVENTORY_ADDED_2026_10_29]
    assert [(name, list(cmd)) for name, cmd in mod.INVENTORY][
        len(INVENTORY_BEFORE_2026_10_29) :
    ] == INVENTORY_ADDED_2026_10_29
    assert len(names) == len(set(names)) == 23


# a program that changes the host has no business in an inventory that runs as root every night
MUTATING_WORDS = {
    "rm", "mv", "cp", "tee", "dd", "kill", "pkill", "start", "stop", "restart", "reload", "enable", "disable", "prune",
    "rmi", "create", "delete", "flush", "restore", "apply", "exec", "pull", "push", "down", "up", "install", "remove",
    "purge", "truncate", "chmod", "chown", "sed", "mount", "umount", "add", "del", "replace", "load", "rename",
}  # fmt: skip


def test_every_inventory_command_only_reads():
    for name, cmd in mod.INVENTORY:
        text = " ".join(cmd)
        assert not MUTATING_WORDS & set(re.findall(r"[A-Za-z0-9_.-]+", text)), (name, text)
        assert ">" not in text.replace("->", ""), (
            name,
            "an inventory command writes only to its own file, through the script",
        )
        assert name.endswith((".txt", ".json")) and "/" not in name


def test_a_missing_or_failing_inventory_command_is_noted_in_its_own_file_and_the_others_still_run(
    tmp_path, monkeypatch
):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == "nft":
            raise FileNotFoundError(2, "No such file or directory: 'nft'")
        if cmd[0] == "hostnamectl":
            raise subprocess.TimeoutExpired(cmd, 120)
        if cmd[0] == "tailscale":
            return subprocess.CompletedProcess(cmd, 1, "", "failed to connect to local tailscaled")
        return subprocess.CompletedProcess(cmd, 0, "out of " + cmd[0] + "\n", "")

    monkeypatch.setattr(mod, "run", fake_run)
    dest = tmp_path / "inventory"
    mod.stage_inventory(str(dest))
    files = {p.name: p.read_text() for p in dest.iterdir()}
    assert sorted(files) == sorted(name for name, _cmd in mod.INVENTORY) and len(calls) == len(mod.INVENTORY) == 23
    assert files["nft-ruleset.txt"].startswith("# FileNotFoundError")
    assert files["hostnamectl.txt"].startswith("# TimeoutExpired")
    assert files["tailscale-status.txt"] == "# command failed (1): failed to connect to local tailscaled\n"
    assert files["os-release.txt"] == "out of cat\n" and files["iptables-save.txt"] == "out of iptables-save\n"


def run_noncompose_entry(tmp_path, what_docker_prints_for_a_missing_label):
    """The entry's real shell pipeline against a `docker` that knows two containers: one in the compose project `shop`, one without a compose label."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "docker"
    shim.write_text(
        """#!/bin/sh
case "$1" in
  ps) printf 'aaa111\\nbbb222\\n' ;;
  inspect)
    if [ "$2" = "--format" ]; then
      shift 3
      for id in "$@"; do
        case "$id" in
          aaa111) echo "aaa111 shop" ;;
          *) echo "$id $MISSING_LABEL" ;;
        esac
      done
    else
      for id in "$@"; do echo "{\\"Id\\": \\"$id\\"}"; done
    fi ;;
esac
"""
    )
    shim.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MISSING_LABEL=what_docker_prints_for_a_missing_label)
    return subprocess.run(
        dict(mod.INVENTORY)["docker-noncompose-containers.json"], capture_output=True, text=True, env=env, timeout=60
    )


def test_the_non_compose_entry_selects_nothing_today_because_docker_prints_no_value(tmp_path):
    """Found on VM 100 on 2026-10-30: for a container without the compose label `docker inspect --format '{{index .Config.Labels ...}}'` prints
    `<no value>`, so its line is `<id> <no value>` (three fields) and `awk 'NF==1'` drops it. docker-noncompose-containers.json was empty although 5 of
    the 458 containers (buildx_buildkit_remote0, bwa-live, bwa-hr-live, bwa-storyline, veld-moodboard) have no label.

    This test pins what runs today. When it fails because the entry was fixed: the fixed entry writes the FULL `docker inspect` of those containers, and that
    carries Config.Env (bwa-live: 36 variables, 11 with secret-looking names, among them a Supabase service-role key and a Replicate token). The script's rule is
    that the snapshot holds no container environment (see containers() and the README). Redact the values or encrypt the snapshot first, then update this test."""
    today = run_noncompose_entry(tmp_path, "<no value>")
    assert today.returncode == 0 and today.stdout == "", today
    control = run_noncompose_entry(
        tmp_path, ""
    )  # a docker that printed an empty string would make the filter work as intended
    assert '"bbb222"' in control.stdout and "aaa111" not in control.stdout, control


def test_the_readme_says_what_the_additions_hold_which_of_them_are_secret_and_who_can_read_the_snapshot():
    readme = (DIR / "README.md").read_text()
    for needle in (
        *list(LIVE_ARCHIVES)[6:],
        *[name for name, _cmd in INVENTORY_ADDED_2026_10_29],
        "/var/spool/cron",
        "tailscaled.state",
        "credential.secret",
        "random-seed",
        "<no value>",
        "--crypt-mode none",
        "pbs-sync-0infer@pbs",
        "byte-identical",
        "Compare before every install",
    ):
        assert needle in readme, needle
