#!/usr/bin/env python3
"""scanopy_backup - pull a nightly dump of the Scanopy database to the monitoring VM.

Why: the Scanopy server, its Postgres and the hypervisor-local daemon run on the 0docker hypervisor itself, which PBS does not
back up (it backs up guests), and the only copy kept there was one dump from 2026-10-08. Losing that host would lose every daemon
key, credential assignment, tag and schedule. This job pulls a fresh dump every night to a different fleet (0mcp), through a
forced-command SSH key that can do nothing but stream the dump.

Each run: ssh <hypervisor> dump > <dir>/scanopy-<UTC>.sql.gz.part, verify (gzip integrity, size, the "dump complete" trailer
pg_dump writes, the expected tables), move it into place (0600), then keep the newest KEEP files (default 14). A failed run
leaves the older dumps untouched and publishes scanopy_backup_* metrics; alerts live in config/prometheus/rules/inventory.yml.
stdlib only. --dry-run does the dump and the checks but keeps nothing and publishes nothing.
"""
import argparse
import datetime as dt
import glob
import gzip
import os
import subprocess
import sys
import time

CONF = {
    "ssh": os.environ.get("BACKUP_SSH", "root@example.net"),
    "port": os.environ.get("BACKUP_SSH_PORT", "22"),
    "ssh_key": os.environ.get("BACKUP_SSH_KEY", "/etc/scanopy-backup/id_ed25519"),
    "known_hosts": os.environ.get("BACKUP_KNOWN_HOSTS", "/etc/scanopy-backup/known_hosts"),
    "dir": os.environ.get("BACKUP_DIR", "/var/backups/scanopy"),
    "textfile": os.environ.get("BACKUP_TEXTFILE", "/var/lib/prometheus/node-exporter/scanopy_backup.prom"),
    "keep": int(os.environ.get("BACKUP_KEEP", "14")),
    "min_bytes": int(os.environ.get("BACKUP_MIN_BYTES", "10000")),
    "timeout": int(os.environ.get("BACKUP_TIMEOUT", "600")),
}
TRAILER = b"PostgreSQL database dump complete"
EXPECTED_TABLES = tuple(b"CREATE TABLE public.%s (" % t for t in (b"daemons", b"hosts", b"discovery", b"api_keys", b"credentials"))


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def utcstamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def pull(part):
    argv = ["ssh", "-i", CONF["ssh_key"], "-p", CONF["port"], "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "ConnectTimeout=20", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={CONF['known_hosts']}",
            CONF["ssh"], "dump"]
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as out:
        p = subprocess.run(argv, stdout=out, stderr=subprocess.PIPE, timeout=CONF["timeout"])
    if p.returncode:
        raise RuntimeError(f"ssh/pg_dump failed (rc={p.returncode}): {p.stderr.decode(errors='replace').strip()[-200:]}")


def verify(path):
    """Raise unless the file is a complete, plausible pg_dump of the Scanopy database; returns its size."""
    size = os.path.getsize(path)
    if size < CONF["min_bytes"]:
        raise RuntimeError(f"dump is only {size} bytes")
    seen, carry = set(), b""
    with gzip.open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            window = carry + chunk  # a table name may straddle two chunks
            seen.update(t for t in EXPECTED_TABLES if t in window)
            carry = window[-4096:]
    if TRAILER not in carry:
        raise RuntimeError("dump is truncated (no pg_dump completion trailer)")
    missing = [t.decode() for t in EXPECTED_TABLES if t not in seen]
    if missing:
        raise RuntimeError(f"dump lacks expected tables: {missing}")
    return size


def rotate(directory, keep):
    files = sorted(glob.glob(os.path.join(directory, "scanopy-*.sql.gz")))
    removed = 0
    for old in files[:-keep] if keep > 0 else []:
        os.unlink(old)
        removed += 1
    return len(files) - removed, removed


def previous_success():
    """(timestamp, size) of the last verified dump from the metrics file, so a failed run keeps reporting it."""
    values = {}
    try:
        with open(CONF["textfile"]) as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and not line.startswith("#"):
                    values[parts[0]] = parts[1]
        return (int(values["scanopy_backup_last_success_timestamp_seconds"]),
                int(values.get("scanopy_backup_last_size_bytes", 0)))
    except (OSError, KeyError, ValueError):
        return None


def write_metrics(ok, size, count, dry_run, prev=None):
    if dry_run:
        return
    now = int(time.time())
    lines = [
        "# HELP scanopy_backup_last_success_timestamp_seconds Last verified Scanopy database dump pulled to the monitoring VM",
        "# TYPE scanopy_backup_last_success_timestamp_seconds gauge",
        f"scanopy_backup_last_attempt_timestamp_seconds {now}",
        f"scanopy_backup_last_attempt_success {1 if ok else 0}",
    ]
    if ok:
        lines += [f"scanopy_backup_last_success_timestamp_seconds {now}", f"scanopy_backup_last_size_bytes {size}"]
    elif prev:  # a failed run keeps the age of the last good dump visible instead of making the series disappear
        lines += [f"scanopy_backup_last_success_timestamp_seconds {prev[0]}", f"scanopy_backup_last_size_bytes {prev[1]}"]
    if count is not None:
        lines.append(f"scanopy_backup_files {count}")
    tmp = CONF["textfile"] + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, CONF["textfile"])
    except OSError as e:
        log(f"warning: could not write metrics: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ok, size, count = False, 0, None
    prev = previous_success()
    try:
        os.makedirs(CONF["dir"], mode=0o700, exist_ok=True)
        stamp = utcstamp()
        part = os.path.join(CONF["dir"], f"scanopy-{stamp}.sql.gz.part")
        final = os.path.join(CONF["dir"], f"scanopy-{stamp}.sql.gz")
        try:
            pull(part)
            size = verify(part)
        except BaseException:
            if os.path.exists(part):
                os.unlink(part)
            raise
        if args.dry_run:
            os.unlink(part)
            log(f"dry run: dump ok ({size} bytes), nothing kept")
        else:
            os.chmod(part, 0o600)  # the dump holds credential material, whatever created the file
            os.replace(part, final)
            count, removed = rotate(CONF["dir"], CONF["keep"])
            log(f"saved {final} ({size} bytes); {count} kept, {removed} rotated out")
        ok = True
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        log(f"FAILED: {e}")
    write_metrics(ok, size, count, args.dry_run, prev)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
