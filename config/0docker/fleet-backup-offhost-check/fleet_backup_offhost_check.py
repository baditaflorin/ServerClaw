#!/usr/bin/env python3
"""Independent check of the OFF-HOST copy of the small encrypted backup archives (runs as root on VM 100, publishes node_exporter textfile metrics).

Background: the sidecar `fleet-backup-sync` (go-fleet-backup, ops/fleet-backup-sync) copies the newest age-encrypted archive of secrets-db, keystore-db and
broker-db-snapshot to a private GitHub repository (payload/<source>.age, or payload/<source>.age.part-000, -001, ... for archives above 45 MiB, and
payload/state.tsv: source, archive name, sha256 of the whole archive, copy time, parts, size). It is the only copy outside both hypervisors' providers. Nothing
watched it: on 2026-10-22 the keystore-db archive was about to pass the sidecar's 90 MiB cap and GitHub's 100 MB file limit and the copy would have gone stale
without a single alert (the daily report that would have noticed ran on the operator's Mac, which was asleep for three days).

  check   (every 30 min)  fetch the branch head WITHOUT file contents (partial clone) and the one small state.tsv, list the payload tree by name, and publish how old
                          each copy is, how many parts it has, its size and whether its files are all there (fleet_backup_offhost.prom)
  deep    (daily)         fetch everything, rebuild every archive from its parts, compare the SHA-256 with state.tsv, check the age header and the size, and publish
                          the result (fleet_backup_offhost_deep.prom). It cannot decrypt (no key here): it proves the copy on GitHub is the archive the sidecar meant to
                          publish, byte for byte.

It only READS the repository, with the sidecar's deploy key (same host, same root). Exit codes: 0 ok, 1 the repository could not be read, 2 the copy is damaged or
incomplete. A failed run keeps the previous per-source values (timestamps are absolute, so the alerts' `time() - ...` keeps growing) and does not move the last-success time.
Config: /etc/fleet-backup-offhost-check/config.json (see README.md).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

AGE_MAGIC = b"age-encryption.org/v1\n"
NAME_TS = re.compile(r"^(\d{4})-?(\d\d)-?(\d\d)T(\d\d):?(\d\d):?(\d\d)Z\.age$")
PART = re.compile(r"\.age\.part-(\d{3,})$")
CHECK_PREFIXES = ("fleet_backup_offhost_copy_", "fleet_backup_offhost_commit_")
DEEP_PREFIXES = ("fleet_backup_offhost_deep_source_",)


class Unreadable(Exception):
    """The repository could not be read (network, key, missing branch or state file)."""


def now_epoch() -> int:
    v = os.environ.get("OFFHOST_CHECK_NOW")
    return int(v) if v else int(time.time())


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for k in ("repo", "branch", "sources", "textfile"):
        if k not in cfg:
            raise SystemExit(f"config {path}: missing '{k}'")
    if not isinstance(cfg["sources"], list) or not cfg["sources"] or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", s) for s in cfg["sources"]):
        raise SystemExit(f"config {path}: 'sources' must be a non-empty list of plain names")
    return cfg


def git_env(cfg: dict) -> dict:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    key, kh = cfg.get("deploy_key"), cfg.get("known_hosts")
    if key:  # a file:// repository (the tests) needs neither
        env["GIT_SSH_COMMAND"] = (f"ssh -i {key} -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes "
                                  f"-o UserKnownHostsFile={kh}")
    return env


def git(args: list[str], cwd: str, env: dict, timeout: int, binary: bool = False):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        raise Unreadable(f"git {args[0]} timed out after {timeout}s") from e
    if r.returncode != 0:
        raise Unreadable(f"git {args[0]} failed: {r.stderr.decode(errors='replace').strip()[-300:]}")
    return r.stdout if binary else r.stdout.decode(errors="replace")


def clone(cfg: dict, dest: str, full: bool) -> str:
    env = git_env(cfg)
    timeout = int(cfg.get("fetch_timeout_s", 900))
    args = ["clone", "-q", "--depth", "1", "--no-checkout", "--branch", cfg["branch"]]
    if not full:
        args += ["--filter=blob:none"]
    git(args + [cfg["repo"], dest], cwd=os.path.dirname(dest), env=env, timeout=timeout)
    return dest


def parse_state(text: str) -> dict:
    """source -> dict(name, sha, epoch, parts, size). Lines written before 2026-10-22 have four columns (one file, unknown size)."""
    out = {}
    for line in text.splitlines():
        f = line.split("\t")
        if len(f) < 4 or not f[3].isdigit():
            continue
        out[f[0]] = {
            "name": f[1],
            "sha": f[2],
            "epoch": int(f[3]),
            "parts": int(f[4]) if len(f) > 4 and f[4].isdigit() else 0,
            "size": int(f[5]) if len(f) > 5 and f[5].isdigit() else None,
        }
    return out


def archive_epoch(name: str):
    m = NAME_TS.match(name)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    return int(datetime.datetime(y, mo, d, h, mi, s, tzinfo=datetime.timezone.utc).timestamp())


def expected_files(src: str, entry: dict) -> list[str]:
    if entry["parts"] > 0:
        return [f"payload/{src}.age.part-{i:03d}" for i in range(entry["parts"])]
    return [f"payload/{src}.age"]


def structure_problems(src: str, entry: dict, names: set[str]) -> list[str]:
    """What is wrong with the files of one source in the payload tree (empty list = intact)."""
    want = expected_files(src, entry)
    problems = [f"missing {w}" for w in want if w not in names]
    mine = {n for n in names if n == f"payload/{src}.age" or n.startswith(f"payload/{src}.age.part-")}
    problems += [f"unexpected {n}" for n in sorted(mine - set(want))]
    return problems


def read_previous(path: str, prefixes: tuple[str, ...], last_success_name: str):
    """Lines of the previous textfile to carry over when a run fails, and its last-success value."""
    keep, last = [], None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                if line.startswith(last_success_name + " "):
                    last = line.split()[-1]
                elif line.startswith(prefixes):
                    keep.append(line.rstrip("\n"))
    except OSError:
        pass
    return keep, last


def write_textfile(path: str, lines: list[str]) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".offhost.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def gauge(name: str, help_: str, samples: list[tuple[str, float]]) -> list[str]:
    out = [f"# HELP {name} {help_}", f"# TYPE {name} gauge"]
    for labels, value in samples:
        out.append(f"{name}{labels} {value:g}" if isinstance(value, float) else f"{name}{labels} {value}")
    return out


def run_check(cfg: dict, dry_run: bool = False) -> int:
    t = now_epoch()
    path = cfg["textfile"]
    prev_lines, prev_success = read_previous(path, CHECK_PREFIXES, "fleet_backup_offhost_check_last_success_timestamp_seconds")
    work = tempfile.mkdtemp(prefix="offhost-check-", dir=cfg.get("tmpdir", "/var/tmp"))
    try:
        repo = clone(cfg, os.path.join(work, "r"), full=False)
        env = git_env(cfg)
        to = int(cfg.get("fetch_timeout_s", 900))
        commit_ts = int(git(["log", "-1", "--format=%ct", "HEAD"], cwd=repo, env=env, timeout=to).strip())
        names = set(git(["ls-tree", "-r", "--name-only", "HEAD", "payload"], cwd=repo, env=env, timeout=to).split("\n")) - {""}
        state_text = ""
        if "payload/state.tsv" in names:
            state_text = git(["cat-file", "blob", "HEAD:payload/state.tsv"], cwd=repo, env=env, timeout=to)
        else:  # readable repository without a state file: every configured source is reported missing (present 0, exit 2)
            print("offhost-check: payload/state.tsv is not in the repository", file=sys.stderr)
    except Unreadable as e:
        lines = (gauge("fleet_backup_offhost_check_ok", "1 when the last run could read the off-host repository.", [("", 0)])
                 + gauge("fleet_backup_offhost_check_last_attempt_timestamp_seconds", "Unix time of the last run.", [("", t)]))
        if prev_success is not None:
            lines += gauge("fleet_backup_offhost_check_last_success_timestamp_seconds", "Unix time of the last run that read the repository.", [("", prev_success)])
        lines += prev_lines
        print(f"offhost-check: {e}", file=sys.stderr)
        if not dry_run:
            write_textfile(path, lines)
        else:
            print("\n".join(lines))
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    state = parse_state(state_text)
    ts, parts, size, present, archive_ts, problems_out = [], [], [], [], [], []
    rc = 0
    for src in cfg["sources"]:
        lab = f'{{archive="{src}"}}'
        entry = state.get(src)
        if entry is None:
            present.append((lab, 0))
            problems_out.append(f"{src}: no line in payload/state.tsv")
            rc = 2
            continue
        probs = structure_problems(src, entry, names)
        present.append((lab, 0 if probs else 1))
        ts.append((lab, entry["epoch"]))
        parts.append((lab, entry["parts"]))
        if entry["size"] is not None:
            size.append((lab, entry["size"]))
        a = archive_epoch(entry["name"])
        if a is not None:
            archive_ts.append((lab, a))
        if probs:
            rc = 2
            problems_out.append(f"{src}: " + "; ".join(probs))
    lines = (gauge("fleet_backup_offhost_check_ok", "1 when the last run could read the off-host repository.", [("", 1)])
             + gauge("fleet_backup_offhost_check_last_attempt_timestamp_seconds", "Unix time of the last run.", [("", t)])
             + gauge("fleet_backup_offhost_check_last_success_timestamp_seconds", "Unix time of the last run that read the repository.", [("", t)])
             + gauge("fleet_backup_offhost_commit_timestamp_seconds", "Commit time of the branch head in the off-host repository.", [("", commit_ts)])
             + gauge("fleet_backup_offhost_copy_timestamp_seconds", "When the sidecar last copied this source's archive to the off-host repository (state.tsv).", ts)
             + gauge("fleet_backup_offhost_copy_archive_timestamp_seconds", "Time in the name of the archive that is currently copied off-host.", archive_ts)
             + gauge("fleet_backup_offhost_copy_parts", "Number of parts of the off-host copy (0 = one file).", parts)
             + gauge("fleet_backup_offhost_copy_bytes", "Size in bytes of the archive copied off-host (state.tsv, absent for old lines).", size)
             + gauge("fleet_backup_offhost_copy_present", "1 when every file of the off-host copy is in the repository tree and nothing stray is.", present))
    if dry_run:
        print("\n".join(lines))
    else:
        write_textfile(path, lines)
    for p in problems_out:
        print(f"offhost-check: {p}", file=sys.stderr)
    return rc


def sha_of_files(files: list[str]):
    h = hashlib.sha256()
    total = 0
    header = b""
    for i, fn in enumerate(files):
        with open(fn, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                if i == 0 and len(header) < len(AGE_MAGIC):
                    header += b[: len(AGE_MAGIC) - len(header)]
                h.update(b)
                total += len(b)
    return h.hexdigest(), total, header


def run_deep(cfg: dict, dry_run: bool = False) -> int:
    t = now_epoch()
    path = cfg["textfile"]
    prev_lines, prev_success = read_previous(path, DEEP_PREFIXES, "fleet_backup_offhost_deep_last_success_timestamp_seconds")
    work = tempfile.mkdtemp(prefix="offhost-deep-", dir=cfg.get("tmpdir", "/var/tmp"))
    started = time.time()
    try:
        repo = clone(cfg, os.path.join(work, "r"), full=True)
        env = git_env(cfg)
        to = int(cfg.get("fetch_timeout_s", 900))
        git(["checkout", "-q", "HEAD", "--", "payload"], cwd=repo, env=env, timeout=to)
        with open(os.path.join(repo, "payload", "state.tsv"), encoding="utf-8") as f:
            state = parse_state(f.read())
        names = {os.path.relpath(os.path.join(dp, fn), repo) for dp, _d, fns in os.walk(os.path.join(repo, "payload")) for fn in fns}
        ok, nbytes, problems_out = [], [], []
        rc = 0
        for src in cfg["sources"]:
            lab = f'{{archive="{src}"}}'
            entry = state.get(src)
            if entry is None:
                ok.append((lab, 0))
                problems_out.append(f"{src}: no line in payload/state.tsv")
                rc = 2
                continue
            probs = structure_problems(src, entry, names)
            good = not probs
            total = 0
            if good:
                sha, total, header = sha_of_files([os.path.join(repo, w) for w in expected_files(src, entry)])
                if sha != entry["sha"]:
                    good = False
                    probs.append(f"sha256 {sha[:12]} does not match state.tsv {entry['sha'][:12]}")
                if not header.startswith(AGE_MAGIC):
                    good = False
                    probs.append("the reassembled file does not start with the age header")
                if entry["size"] is not None and total != entry["size"]:
                    good = False
                    probs.append(f"size {total} does not match state.tsv {entry['size']}")
            ok.append((lab, 1 if good else 0))
            nbytes.append((lab, total))
            if not good:
                rc = 2
                problems_out.append(f"{src}: " + "; ".join(probs))
    except (Unreadable, OSError) as e:
        lines = (gauge("fleet_backup_offhost_deep_last_attempt_timestamp_seconds", "Unix time of the last deep check.", [("", t)])
                 + gauge("fleet_backup_offhost_deep_readable", "1 when the last deep check could read the repository.", [("", 0)]))
        if prev_success is not None:
            lines += gauge("fleet_backup_offhost_deep_last_success_timestamp_seconds", "Unix time of the last deep check in which every source was intact.", [("", prev_success)])
        lines += prev_lines
        print(f"offhost-deep: {e}", file=sys.stderr)
        if not dry_run:
            write_textfile(path, lines)
        else:
            print("\n".join(lines))
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    lines = (gauge("fleet_backup_offhost_deep_last_attempt_timestamp_seconds", "Unix time of the last deep check.", [("", t)])
             + gauge("fleet_backup_offhost_deep_readable", "1 when the last deep check could read the repository.", [("", 1)])
             + gauge("fleet_backup_offhost_deep_duration_seconds", "Wall time of the last deep check.", [("", round(time.time() - started, 1))])
             + gauge("fleet_backup_offhost_deep_source_ok", "1 when the copy rebuilt from GitHub matches state.tsv (sha256, age header, size).", ok)
             + gauge("fleet_backup_offhost_deep_source_bytes", "Bytes of the archive rebuilt from the off-host copy.", nbytes))
    if rc == 0:
        lines += gauge("fleet_backup_offhost_deep_last_success_timestamp_seconds", "Unix time of the last deep check in which every source was intact.", [("", t)])
    elif prev_success is not None:
        lines += gauge("fleet_backup_offhost_deep_last_success_timestamp_seconds", "Unix time of the last deep check in which every source was intact.", [("", prev_success)])
    if dry_run:
        print("\n".join(lines))
    else:
        write_textfile(path, lines)
    for p in problems_out:
        print(f"offhost-deep: {p}", file=sys.stderr)
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=("check", "deep"))
    ap.add_argument("--config", default="/etc/fleet-backup-offhost-check/config.json")
    ap.add_argument("--dry-run", action="store_true", help="print the metrics instead of writing the textfile")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.mode == "deep":
        cfg = dict(cfg, textfile=cfg.get("deep_textfile") or re.sub(r"\.prom$", "_deep.prom", cfg["textfile"]))
        return run_deep(cfg, args.dry_run)
    return run_check(cfg, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
