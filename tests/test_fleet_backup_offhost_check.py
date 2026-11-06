"""config/0docker/fleet-backup-offhost-check: the independent check of the off-host copy of the small encrypted backup archives (2026-10-22).

The sidecar fleet-backup-sync copies the newest secrets-db / keystore-db / broker-db-snapshot archive to a private GitHub repository (payload/<source>.age or numbered parts, and
payload/state.tsv). Nothing watched that copy: the keystore-db archive was about to pass the sidecar's size cap and GitHub's 100 MB file limit and the copy would have gone stale
silently. These tests run the tool against a real local git repository (a file:// remote with partial clone enabled, like GitHub's): freshness, parts, sizes, a missing part, a
stray file, an unreadable repository (previous values kept, last success not moved), the daily deep check (sha256 of the rebuilt archive, age header, size) and that the 30-minute
check never downloads the payload files.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DIR = REPO / "config" / "0docker" / "fleet-backup-offhost-check"
spec = importlib.util.spec_from_file_location("offhost", DIR / "fleet_backup_offhost_check.py")
offhost = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offhost)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
AGE = b"age-encryption.org/v1\n"
NOW = 1_792_700_000
SIDECAR_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(*args: str, cwd: Path | None = None) -> str:
    env = dict(os.environ, **SIDECAR_ENV)
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)
    return r.stdout


def _archive(n: int) -> bytes:
    return AGE + bytes((i * 7 + 3) % 251 for i in range(n - len(AGE)))


class Remote:
    """A bare repository that behaves like GitHub for partial clones, plus a working copy to publish into it."""

    def __init__(self, root: Path):
        self.bare = root / "remote.git"
        self.work = root / "work"
        _git("init", "-q", "--bare", "-b", "main", str(self.bare))
        _git("config", "uploadpack.allowFilter", "true", cwd=self.bare)
        _git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=self.bare)
        _git("init", "-q", "-b", "main", str(self.work))
        _git("remote", "add", "origin", str(self.bare), cwd=self.work)

    def publish(self, files: dict[str, bytes], state: str | None) -> None:
        pay = self.work / "payload"
        shutil.rmtree(pay, ignore_errors=True)
        pay.mkdir(parents=True)
        for name, data in files.items():
            (pay / name).write_bytes(data)
        if state is not None:
            (pay / "state.tsv").write_text(state, encoding="utf-8")
        (self.work / "README.md").write_text("x", encoding="utf-8")
        _git("add", "-A", cwd=self.work)
        _git("commit", "-q", "--allow-empty", "-m", "state", cwd=self.work)
        _git("push", "-q", "-f", "origin", "HEAD:refs/heads/main", cwd=self.work)

    @property
    def url(self) -> str:
        return "file://" + str(self.bare)


def _state_line(src: str, name: str, data: bytes, epoch: int, parts: int, size: int | None = None) -> str:
    cols = [src, name, hashlib.sha256(data).hexdigest(), str(epoch), str(parts)]
    if size is not None:
        cols.append(str(size))
    return "\t".join(cols) + "\n"


@pytest.fixture()
def world(tmp_path: Path):
    r = Remote(tmp_path)
    big = _archive(250)
    small = _archive(60)
    files = {"secrets-db.age": small, "keystore-db.age.part-000": big[:100], "keystore-db.age.part-001": big[100:200], "keystore-db.age.part-002": big[200:],
             "broker-db-snapshot.age": _archive(40)}
    state = (_state_line("broker-db-snapshot", "2026-10-22T02:15:02Z.age", files["broker-db-snapshot.age"], NOW - 3600, 0, 40)
             + _state_line("keystore-db", "2026-10-22T02:15:02Z.age", big, NOW - 7200, 3, 250)
             + _state_line("secrets-db", "2026-10-22T02:15:02Z.age", small, NOW - 7000, 0, 60))
    r.publish(files, state)
    cfg = {"repo": r.url, "branch": "main", "sources": ["secrets-db", "keystore-db", "broker-db-snapshot"], "textfile": str(tmp_path / "out" / "offhost.prom"),
           "tmpdir": str(tmp_path), "fetch_timeout_s": 60}
    cfgfile = tmp_path / "config.json"
    cfgfile.write_text(json.dumps(cfg), encoding="utf-8")
    return {"remote": r, "cfg": cfg, "cfgfile": str(cfgfile), "big": big, "small": small, "files": files, "state": state, "tmp": tmp_path}


def _metrics(path: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            k, v = line.rsplit(" ", 1)
            out[k] = float(v)
    return out


def _run(world, mode: str, now: int = NOW, monkeypatch=None) -> int:
    os.environ["OFFHOST_CHECK_NOW"] = str(now)
    try:
        return offhost.main([mode, "--config", world["cfgfile"]])
    finally:
        os.environ.pop("OFFHOST_CHECK_NOW", None)


def _deep_path(world) -> str:
    return str(Path(world["cfg"]["textfile"]).with_name("offhost_deep.prom"))


# --- parsing -------------------------------------------------------------------------------------------------------------------------

def test_state_lines_with_four_five_and_six_columns_are_read() -> None:
    s = offhost.parse_state("a\tn1\tsha1\t100\n" "b\tn2\tsha2\t200\t3\n" "c\tn3\tsha3\t300\t0\t999\n" "garbage\n" "d\tn4\tsha4\tnotanumber\n")
    assert s["a"] == {"name": "n1", "sha": "sha1", "epoch": 100, "parts": 0, "size": None}
    assert s["b"]["parts"] == 3 and s["b"]["size"] is None
    assert s["c"]["size"] == 999 and s["c"]["parts"] == 0
    assert "garbage" not in s and "d" not in s


def test_archive_time_comes_from_the_archive_name() -> None:
    assert offhost.archive_epoch("2026-10-22T02:15:02Z.age") == 1792635302
    assert offhost.archive_epoch("20261022T021502Z.age") == 1792635302
    assert offhost.archive_epoch("whatever.age") is None


def test_the_expected_files_of_a_split_and_of_a_single_archive() -> None:
    assert offhost.expected_files("k", {"parts": 3}) == ["payload/k.age.part-000", "payload/k.age.part-001", "payload/k.age.part-002"]
    assert offhost.expected_files("k", {"parts": 0}) == ["payload/k.age"]
    assert offhost.structure_problems("k", {"parts": 2}, {"payload/k.age.part-000", "payload/k.age.part-001"}) == []
    assert offhost.structure_problems("k", {"parts": 2}, {"payload/k.age.part-000"}) == ["missing payload/k.age.part-001"]
    p = offhost.structure_problems("k", {"parts": 1}, {"payload/k.age.part-000", "payload/k.age", "payload/k.age.part-001", "payload/other.age"})
    assert p == ["unexpected payload/k.age", "unexpected payload/k.age.part-001"], p


def test_a_source_name_that_is_not_a_plain_name_is_refused_in_the_config(tmp_path: Path) -> None:
    for bad in (["../etc"], ["a/b"], [], "keystore-db"):
        f = tmp_path / "c.json"
        f.write_text(json.dumps({"repo": "x", "branch": "main", "sources": bad, "textfile": "y"}), encoding="utf-8")
        with pytest.raises(SystemExit):
            offhost.load_config(str(f))


# --- the 30-minute check ---------------------------------------------------------------------------------------------------------------

def test_the_light_check_publishes_age_parts_size_and_presence_of_every_source(world) -> None:
    assert _run(world, "check") == 0
    m = _metrics(world["cfg"]["textfile"])
    assert m["fleet_backup_offhost_check_ok"] == 1
    assert m["fleet_backup_offhost_check_last_success_timestamp_seconds"] == NOW
    assert m['fleet_backup_offhost_copy_timestamp_seconds{archive="keystore-db"}'] == NOW - 7200
    assert m['fleet_backup_offhost_copy_timestamp_seconds{archive="secrets-db"}'] == NOW - 7000
    assert m['fleet_backup_offhost_copy_parts{archive="keystore-db"}'] == 3
    assert m['fleet_backup_offhost_copy_parts{archive="secrets-db"}'] == 0
    assert m['fleet_backup_offhost_copy_bytes{archive="keystore-db"}'] == 250
    assert m['fleet_backup_offhost_copy_archive_timestamp_seconds{archive="keystore-db"}'] == 1792635302
    assert all(m[f'fleet_backup_offhost_copy_present{{archive="{s}"}}'] == 1 for s in ("secrets-db", "keystore-db", "broker-db-snapshot"))
    assert m["fleet_backup_offhost_commit_timestamp_seconds"] > 1_700_000_000
    text = Path(world["cfg"]["textfile"]).read_text(encoding="utf-8")
    for fam in ("fleet_backup_offhost_check_ok", "fleet_backup_offhost_copy_timestamp_seconds", "fleet_backup_offhost_copy_present"):
        assert f"# HELP {fam} " in text and f"# TYPE {fam} gauge" in text


def test_the_light_check_never_downloads_the_payload_files(world, monkeypatch) -> None:
    calls: list[list[str]] = []
    real = offhost.git

    def spy(args, cwd, env, timeout, binary=False):
        calls.append(list(args))
        return real(args, cwd, env, timeout, binary)

    monkeypatch.setattr(offhost, "git", spy)
    assert _run(world, "check") == 0
    clone = next(c for c in calls if c[0] == "clone")
    assert "--filter=blob:none" in clone and "--depth" in clone
    assert not any(c[0] in ("checkout", "archive", "archive", "pull", "fetch") for c in calls), calls
    cat = [c for c in calls if c[0] == "cat-file"]
    assert cat == [["cat-file", "blob", "HEAD:payload/state.tsv"]], "only the one small state file may be read"


def test_a_missing_part_makes_the_copy_not_present_and_the_run_fail(world) -> None:
    files = dict(world["files"])
    del files["keystore-db.age.part-001"]
    world["remote"].publish(files, world["state"])
    assert _run(world, "check") == 2
    m = _metrics(world["cfg"]["textfile"])
    assert m['fleet_backup_offhost_copy_present{archive="keystore-db"}'] == 0
    assert m['fleet_backup_offhost_copy_present{archive="secrets-db"}'] == 1


def test_a_stray_old_file_next_to_the_copy_is_reported(world) -> None:
    files = dict(world["files"])
    files["keystore-db.age"] = b"old single file left behind"
    world["remote"].publish(files, world["state"])
    assert _run(world, "check") == 2
    assert _metrics(world["cfg"]["textfile"])['fleet_backup_offhost_copy_present{archive="keystore-db"}'] == 0


def test_a_source_without_a_state_line_is_reported_missing_and_has_no_timestamp(world) -> None:
    state = "".join(line for line in world["state"].splitlines(keepends=True) if not line.startswith("secrets-db"))
    world["remote"].publish(world["files"], state)
    assert _run(world, "check") == 2
    m = _metrics(world["cfg"]["textfile"])
    assert m['fleet_backup_offhost_copy_present{archive="secrets-db"}'] == 0
    assert 'fleet_backup_offhost_copy_timestamp_seconds{archive="secrets-db"}' not in m
    assert m['fleet_backup_offhost_copy_present{archive="keystore-db"}'] == 1


def test_a_repository_without_a_state_file_reports_every_source_missing(world) -> None:
    world["remote"].publish(world["files"], None)
    assert _run(world, "check") == 2
    m = _metrics(world["cfg"]["textfile"])
    assert all(m[f'fleet_backup_offhost_copy_present{{archive="{s}"}}'] == 0 for s in world["cfg"]["sources"])
    assert m["fleet_backup_offhost_check_ok"] == 1


def test_an_unreadable_repository_keeps_the_previous_values_and_does_not_move_the_last_success(world) -> None:
    assert _run(world, "check", now=NOW) == 0
    cfg = dict(world["cfg"], repo="file://" + str(world["tmp"] / "does-not-exist.git"))
    Path(world["cfgfile"]).write_text(json.dumps(cfg), encoding="utf-8")
    assert _run(world, "check", now=NOW + 4000) == 1
    m = _metrics(world["cfg"]["textfile"])
    assert m["fleet_backup_offhost_check_ok"] == 0
    assert m["fleet_backup_offhost_check_last_attempt_timestamp_seconds"] == NOW + 4000
    assert m["fleet_backup_offhost_check_last_success_timestamp_seconds"] == NOW, "a failed run must not look like a success"
    assert m['fleet_backup_offhost_copy_timestamp_seconds{archive="keystore-db"}'] == NOW - 7200, "the absolute copy time is carried over so time() - x keeps growing"


def test_a_first_run_that_cannot_read_the_repository_has_no_last_success_at_all(world) -> None:
    cfg = dict(world["cfg"], repo="file://" + str(world["tmp"] / "does-not-exist.git"))
    Path(world["cfgfile"]).write_text(json.dumps(cfg), encoding="utf-8")
    assert _run(world, "check") == 1
    m = _metrics(world["cfg"]["textfile"])
    assert m["fleet_backup_offhost_check_ok"] == 0 and "fleet_backup_offhost_check_last_success_timestamp_seconds" not in m


def test_no_temporary_clone_is_left_behind(world) -> None:
    _run(world, "check")
    assert not [p for p in world["tmp"].iterdir() if p.name.startswith("offhost-check-")]


# --- the daily deep check ----------------------------------------------------------------------------------------------------------------

def test_the_deep_check_rebuilds_the_split_archive_and_accepts_an_intact_copy(world) -> None:
    assert _run(world, "deep") == 0
    m = _metrics(_deep_path(world))
    for s, n in (("secrets-db", 60), ("keystore-db", 250), ("broker-db-snapshot", 40)):
        assert m[f'fleet_backup_offhost_deep_source_ok{{archive="{s}"}}'] == 1, s
        assert m[f'fleet_backup_offhost_deep_source_bytes{{archive="{s}"}}'] == n, s
    assert m["fleet_backup_offhost_deep_last_success_timestamp_seconds"] == NOW
    assert m["fleet_backup_offhost_deep_readable"] == 1


def test_the_deep_check_catches_one_flipped_byte_in_one_part(world) -> None:
    assert _run(world, "deep", now=NOW) == 0
    files = dict(world["files"])
    p = bytearray(files["keystore-db.age.part-001"])
    p[10] ^= 0xFF
    files["keystore-db.age.part-001"] = bytes(p)
    world["remote"].publish(files, world["state"])
    assert _run(world, "deep", now=NOW + 86400) == 2
    m = _metrics(_deep_path(world))
    assert m['fleet_backup_offhost_deep_source_ok{archive="keystore-db"}'] == 0
    assert m['fleet_backup_offhost_deep_source_ok{archive="secrets-db"}'] == 1
    assert m["fleet_backup_offhost_deep_last_success_timestamp_seconds"] == NOW, "a damaged copy must not move the deep last-success time"


def test_the_deep_check_catches_content_that_is_not_an_age_file(world) -> None:
    junk = bytes(range(200))[:60]
    files = dict(world["files"], **{"secrets-db.age": junk})
    state = world["state"].replace(hashlib.sha256(world["small"]).hexdigest(), hashlib.sha256(junk).hexdigest())
    world["remote"].publish(files, state)
    assert _run(world, "deep") == 2
    assert _metrics(_deep_path(world))['fleet_backup_offhost_deep_source_ok{archive="secrets-db"}'] == 0


def test_the_deep_check_catches_a_size_that_does_not_match_the_state(world) -> None:
    state = world["state"].replace("\t3\t250\n", "\t3\t251\n")
    assert state != world["state"]
    world["remote"].publish(world["files"], state)
    assert _run(world, "deep") == 2
    assert _metrics(_deep_path(world))['fleet_backup_offhost_deep_source_ok{archive="keystore-db"}'] == 0


def test_the_deep_check_catches_a_missing_part(world) -> None:
    files = dict(world["files"])
    del files["keystore-db.age.part-002"]
    world["remote"].publish(files, world["state"])
    assert _run(world, "deep") == 2
    assert _metrics(_deep_path(world))['fleet_backup_offhost_deep_source_ok{archive="keystore-db"}'] == 0


def test_an_unreadable_repository_in_the_deep_check_keeps_the_previous_result(world) -> None:
    assert _run(world, "deep", now=NOW) == 0
    cfg = dict(world["cfg"], repo="file://" + str(world["tmp"] / "does-not-exist.git"))
    Path(world["cfgfile"]).write_text(json.dumps(cfg), encoding="utf-8")
    assert _run(world, "deep", now=NOW + 5000) == 1
    m = _metrics(_deep_path(world))
    assert m["fleet_backup_offhost_deep_readable"] == 0
    assert m["fleet_backup_offhost_deep_last_success_timestamp_seconds"] == NOW
    assert m['fleet_backup_offhost_deep_source_ok{archive="keystore-db"}'] == 1, "the last known per-source result is carried over"


def test_a_four_column_line_from_before_the_size_column_is_still_checked(world) -> None:
    state = "".join(f"{l.split(chr(9))[0]}\t{l.split(chr(9))[1]}\t{l.split(chr(9))[2]}\t{l.split(chr(9))[3]}\n" if l.startswith("secrets-db") else l
                    for l in world["state"].splitlines(keepends=True))
    world["remote"].publish(world["files"], state)
    assert _run(world, "check") == 0
    assert 'fleet_backup_offhost_copy_bytes{archive="secrets-db"}' not in _metrics(world["cfg"]["textfile"])
    assert _run(world, "deep") == 0


# --- the units and the config shipped in the repository ------------------------------------------------------------------------------------

def test_the_shipped_config_names_the_three_sources_and_the_sidecars_key_files() -> None:
    cfg = json.loads((DIR / "config.json").read_text(encoding="utf-8"))
    assert cfg["sources"] == ["secrets-db", "keystore-db", "broker-db-snapshot"]
    assert cfg["deploy_key"] == "/opt/services/fleet-backup-sync/github_deploy_key" and cfg["known_hosts"] == "/opt/services/fleet-backup-sync/github_known_hosts"
    assert cfg["textfile"] == "/var/lib/prometheus/node-exporter/fleet_backup_offhost.prom"
    assert "token" not in json.dumps(cfg).lower() and "password" not in json.dumps(cfg).lower()


def test_the_units_run_the_two_modes_at_the_lowest_priority_and_the_timers_are_off_the_backup_minutes() -> None:
    svc = (DIR / "fleet-backup-offhost-check.service").read_text(encoding="utf-8")
    deep = (DIR / "fleet-backup-offhost-deep.service").read_text(encoding="utf-8")
    assert "ExecStart=/usr/local/sbin/fleet-backup-offhost-check check" in svc and "ExecStart=/usr/local/sbin/fleet-backup-offhost-check deep" in deep
    for u in (svc, deep):
        assert "Nice=19" in u and "IOSchedulingClass=idle" in u and "Type=oneshot" in u and "NoNewPrivileges=yes" in u
        assert "ReadWritePaths=" in u and "ProtectSystem=strict" in u
    t = (DIR / "fleet-backup-offhost-check.timer").read_text(encoding="utf-8")
    d = (DIR / "fleet-backup-offhost-deep.timer").read_text(encoding="utf-8")
    assert "OnCalendar=*:12,42" in t and "OnCalendar=*-*-* 12:20:00 UTC" in d


def test_the_installer_backs_up_validates_and_can_undo() -> None:
    sh = (DIR / "install.sh").read_text(encoding="utf-8")
    assert sh.startswith("#!/bin/bash")
    for needle in ("--undo", ".pre-", "daemon-reload", "python3 -c", "systemctl enable --now fleet-backup-offhost-check.timer", "fleet-backup-offhost-deep.timer"):
        assert needle in sh, needle
