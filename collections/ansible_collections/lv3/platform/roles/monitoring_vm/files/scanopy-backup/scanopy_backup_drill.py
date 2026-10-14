#!/usr/bin/env python3
"""scanopy_backup_drill - prove the newest Scanopy dump actually restores.

A dump that verifies (gzip, trailer, tables) can still fail to restore (version drift, a broken statement). Every week this job
restores the newest dump from /var/backups/scanopy into a throwaway Postgres container (no network, 512 MB, removed afterwards)
and checks that the core tables came back with rows. Nothing touches the real Scanopy database or the hypervisor.

Steps: docker run postgres -> wait until ready (twice, initdb restarts the server once) -> `gzip -dc dump | psql -v ON_ERROR_STOP=1`
-> row counts of daemons/hosts/discovery/api_keys/credentials must all be > 0 -> docker rm -f (always). Metrics
scanopy_backup_drill_* (the last success timestamp is kept across failed runs); alerts live in config/prometheus/rules/inventory.yml.
stdlib only. Exit 0 on a good drill, 1 otherwise.
"""
import glob
import gzip
import os
import shutil
import subprocess
import sys
import time

CONF = {
    "dir": os.environ.get("BACKUP_DIR", "/var/backups/scanopy"),
    "image": os.environ.get("DRILL_IMAGE", "postgres:17-alpine"),
    "textfile": os.environ.get("DRILL_TEXTFILE", "/var/lib/prometheus/node-exporter/scanopy_backup_drill.prom"),
    "ready_seconds": int(os.environ.get("DRILL_READY_SECONDS", "90")),
    "restore_seconds": int(os.environ.get("DRILL_RESTORE_SECONDS", "600")),
}
TABLES = ("daemons", "hosts", "discovery", "api_keys", "credentials")
USER = DB = "scanopy"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def docker(args, stdin=None, timeout=60):
    p = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def now_ts():
    return time.time()


def sleep(seconds):
    time.sleep(seconds)


def newest_dump():
    files = sorted(glob.glob(os.path.join(CONF["dir"], "scanopy-*.sql.gz")))
    if not files:
        raise RuntimeError(f"no dump in {CONF['dir']}")
    return files[-1]


def wait_ready(name):
    """Two successful readiness checks 3 s apart: the official image starts a temporary server during initdb, then restarts."""
    deadline = now_ts() + CONF["ready_seconds"]
    good = 0
    while now_ts() < deadline:
        rc, _, _ = docker(["exec", name, "pg_isready", "-U", USER, "-d", DB])
        good = good + 1 if rc == 0 else 0
        if good >= 2:
            return
        sleep(3)
    raise RuntimeError("throwaway postgres did not become ready")


def restore(name, dump):
    """Feed the decompressed dump to psql inside the container; returns when psql has finished."""
    proc = subprocess.Popen(["docker", "exec", "-i", name, "psql", "-U", USER, "-d", DB, "-v", "ON_ERROR_STOP=1", "-q"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with gzip.open(dump, "rb") as f:
            shutil.copyfileobj(f, proc.stdin, 1 << 20)
        proc.stdin.close()
        proc.stdin = None  # communicate() would otherwise try to flush the closed pipe
        _, err = proc.communicate(timeout=CONF["restore_seconds"])
    except BaseException:
        proc.kill()
        raise
    if proc.returncode:
        raise RuntimeError(f"restore failed (rc={proc.returncode}): {err.decode(errors='replace').strip()[-300:]}")


def count_rows(name):
    counts = {}
    for table in TABLES:
        rc, out, err = docker(["exec", name, "psql", "-U", USER, "-d", DB, "-At", "-c", f"select count(*) from {table}"])
        if rc:
            raise RuntimeError(f"cannot count {table}: {err.strip()[-150:]}")
        counts[table] = int(out.strip())
    empty = [t for t, n in counts.items() if n == 0]
    if empty:
        raise RuntimeError(f"restored tables are empty: {empty}")
    return counts


def previous_success():
    try:
        with open(CONF["textfile"]) as f:
            for line in f:
                if line.startswith("scanopy_backup_drill_last_success_timestamp_seconds "):
                    return int(float(line.split()[1]))
    except (OSError, ValueError, IndexError):
        pass
    return None


def write_metrics(ok, counts, seconds, dump_age, prev):
    now = int(now_ts())
    lines = [
        "# HELP scanopy_backup_drill_last_success_timestamp_seconds Last time the newest Scanopy dump restored into a throwaway Postgres",
        "# TYPE scanopy_backup_drill_last_success_timestamp_seconds gauge",
        f"scanopy_backup_drill_last_attempt_timestamp_seconds {now}",
        f"scanopy_backup_drill_last_attempt_success {1 if ok else 0}",
    ]
    last = now if ok else prev
    if last is not None:
        lines.append(f"scanopy_backup_drill_last_success_timestamp_seconds {last}")
    if seconds is not None:
        lines.append(f"scanopy_backup_drill_duration_seconds {int(seconds)}")
    if dump_age is not None:
        lines.append(f"scanopy_backup_drill_dump_age_seconds {int(dump_age)}")
    for table, n in sorted((counts or {}).items()):
        lines.append(f'scanopy_backup_drill_rows{{table="{table}"}} {n}')
    tmp = CONF["textfile"] + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(tmp, 0o644)  # node_exporter is not root
        os.replace(tmp, CONF["textfile"])
    except OSError as e:
        log(f"warning: could not write metrics: {e}")


def main():
    started = now_ts()
    prev = previous_success()
    ok, counts, dump_age = False, None, None
    name = f"scanopy-restore-drill-{os.getpid()}"
    try:
        dump = newest_dump()
        dump_age = now_ts() - os.path.getmtime(dump)
        rc, _, err = docker(["run", "-d", "--rm", "--name", name, "--network", "none", "--memory", "512m",
                             "-e", f"POSTGRES_USER={USER}", "-e", f"POSTGRES_DB={DB}", "-e", "POSTGRES_PASSWORD=drill",
                             CONF["image"]], timeout=180)
        if rc:
            raise RuntimeError(f"cannot start the throwaway postgres: {err.strip()[-200:]}")
        wait_ready(name)
        restore(name, dump)
        counts = count_rows(name)
        ok = True
        log(f"drill ok: {os.path.basename(dump)} restored, rows {counts}")
    except Exception as e:  # any failure must still reach the metrics, never escape as a traceback
        log(f"FAILED: {type(e).__name__}: {e}")
    finally:
        docker(["rm", "-f", name], timeout=60)
    write_metrics(ok, counts, now_ts() - started, dump_age, prev)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
