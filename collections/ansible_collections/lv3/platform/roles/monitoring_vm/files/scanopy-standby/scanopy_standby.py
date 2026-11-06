#!/usr/bin/env python3
"""scanopy_standby - keep a warm standby of the Scanopy server on this VM (another fleet than the primary on 0docker).

The primary is a Scanopy server plus Postgres on the 0docker hypervisor; its only state is the database (the server's data
directory is empty). scanopy-backup pulls an hourly dump to this VM. This job turns the dump into a standby:

  sync       restore the newest dump into a persistent Postgres container (scanopy-standby-postgres) whenever a newer dump exists;
             check that the core tables have rows. Does nothing, and says so in the metrics, while the standby server runs
             (failover active), so a failover never has its data overwritten.
  boot-test  start the standby SERVER (compose profile `failover`) on 127.0.0.1:60099 against the restored data, wait for its
             health check, list the daemons through the API with the key of the retag/discover/onboard jobs (it is stored in the
             database, so it must work on the copy), then stop the server again. Proves the standby really is a working Scanopy.

Failover itself (start the server on the tailnet address, repoint the relays) is described in docs/runbooks/scanopy-service-discovery.md.
Metrics scanopy_standby_* in the node_exporter textfile directory (last success is kept across failed runs); alerts live in
config/prometheus/rules/inventory.yml. stdlib only.
"""
import glob
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

CONF = {
    "dir": os.environ.get("BACKUP_DIR", "/var/backups/scanopy"),
    "compose": os.environ.get("STANDBY_COMPOSE", "/opt/scanopy-standby/docker-compose.yml"),
    "state": os.environ.get("STANDBY_STATE", "/var/lib/scanopy-standby/state.json"),
    "textfile": os.environ.get("STANDBY_TEXTFILE", "/var/lib/prometheus/node-exporter/scanopy_standby.prom"),
    "key_file": os.environ.get("SCANOPY_KEY_FILE", "/etc/scanopy-retag/api-key"),
    "boot_port": os.environ.get("STANDBY_BOOT_PORT", "60099"),
    "db_container": "scanopy-standby-postgres",
    "server_container": "scanopy-standby-server",
    "ready_seconds": int(os.environ.get("STANDBY_READY_SECONDS", "90")),
    "boot_seconds": int(os.environ.get("STANDBY_BOOT_SECONDS", "150")),
    "restore_seconds": int(os.environ.get("STANDBY_RESTORE_SECONDS", "600")),
}
TABLES = ("daemons", "hosts", "discovery", "api_keys", "credentials")
USER = "postgres"
DB = "scanopy"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def docker(args, stdin=None, timeout=120, env=None):
    p = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **(env or {})})
    return p.returncode, p.stdout, p.stderr


def compose(args, env=None, timeout=180):
    return docker(["compose", "-f", CONF["compose"], *args], env=env, timeout=timeout)


def now_ts():
    return time.time()


def sleep(seconds):
    time.sleep(seconds)


def http_get(url, key=None, timeout=10):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key} if key else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(16 << 20)


def server_running():
    rc, out, _ = docker(["inspect", "-f", "{{.State.Running}}", CONF["server_container"]], timeout=30)
    return rc == 0 and out.strip() == "true"


def newest_dump():
    files = sorted(glob.glob(os.path.join(CONF["dir"], "scanopy-*.sql.gz")))
    if not files:
        raise RuntimeError(f"no dump in {CONF['dir']}")
    return files[-1]


def load_state():
    try:
        with open(CONF["state"]) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(CONF["state"]), exist_ok=True)
    tmp = CONF["state"] + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, CONF["state"])


def psql(sql, database="postgres", timeout=60):
    rc, out, err = docker(["exec", CONF["db_container"], "psql", "-U", USER, "-d", database, "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
                          timeout=timeout)
    if rc:
        raise RuntimeError(f"psql failed: {err.strip()[-200:]}")
    return out.strip()


def ensure_db_up():
    rc, _, err = compose(["up", "-d", "postgres"])
    if rc:
        raise RuntimeError(f"cannot start the standby postgres: {err.strip()[-200:]}")
    deadline = now_ts() + CONF["ready_seconds"]
    while now_ts() < deadline:
        rc, _, _ = docker(["exec", CONF["db_container"], "pg_isready", "-U", USER, "-d", "postgres"], timeout=20)
        if rc == 0:
            return
        sleep(3)
    raise RuntimeError("the standby postgres did not become ready")


def restore(dump):
    psql(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
    psql(f"CREATE DATABASE {DB}")
    proc = subprocess.Popen(["docker", "exec", "-i", CONF["db_container"], "psql", "-U", USER, "-d", DB, "-v", "ON_ERROR_STOP=1", "-q"],
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


def count_rows():
    counts = {t: int(psql(f"select count(*) from {t}", DB)) for t in TABLES}
    empty = [t for t, n in counts.items() if n == 0]
    if empty:
        raise RuntimeError(f"restored tables are empty: {empty}")
    return counts


def read_metric(name):
    try:
        with open(CONF["textfile"]) as f:
            for line in f:
                if line.startswith(name + " "):
                    return float(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def write_metrics(m):
    lines = [
        "# HELP scanopy_standby_last_success_timestamp_seconds Last time the standby database was refreshed from a verified dump",
        "# TYPE scanopy_standby_last_success_timestamp_seconds gauge",
        f"scanopy_standby_last_attempt_timestamp_seconds {int(now_ts())}",
        f"scanopy_standby_last_attempt_success {1 if m['ok'] else 0}",
        f"scanopy_standby_failover_active {1 if m.get('failover') else 0}",
    ]
    for key, name in (("sync_ts", "scanopy_standby_last_success_timestamp_seconds"),
                      ("boot_ts", "scanopy_standby_boot_test_last_success_timestamp_seconds")):
        value = m.get(key)
        if value is None:
            value = read_metric(name)  # keep the last good value across failed runs and across the other subcommand
        if value is not None:
            lines.append(f"{name} {int(value)}")
    if m.get("dump_age") is not None:
        lines.append(f"scanopy_standby_dump_age_seconds {int(m['dump_age'])}")
    if m.get("boot_seconds") is not None:
        lines.append(f"scanopy_standby_boot_test_seconds {int(m['boot_seconds'])}")
    for table, n in sorted((m.get("rows") or {}).items()):
        lines.append(f'scanopy_standby_rows{{table="{table}"}} {n}')
    tmp = CONF["textfile"] + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(tmp, 0o644)  # node_exporter is not root
        os.replace(tmp, CONF["textfile"])
    except OSError as e:
        log(f"warning: could not write metrics: {e}")


def cmd_sync(force):
    m = {"ok": False}
    try:
        if server_running():
            log("failover active: the standby server is running, the standby database is left alone")
            m.update(ok=True, failover=True)
            return m
        dump = newest_dump()
        name = os.path.basename(dump)
        m["dump_age"] = now_ts() - os.path.getmtime(dump)
        state = load_state()
        if state.get("restored") == name and not force:
            log(f"standby already restored from {name}")
            m.update(ok=True, sync_ts=state.get("restored_at"), rows=state.get("rows"))
            return m
        ensure_db_up()
        restore(dump)
        rows = count_rows()
        save_state({"restored": name, "restored_at": now_ts(), "rows": rows})
        m.update(ok=True, sync_ts=now_ts(), rows=rows)
        log(f"standby restored from {name}: rows {rows}")
    except Exception as e:  # any failure must still reach the metrics
        log(f"FAILED: {type(e).__name__}: {e}")
    return m


def cmd_boot_test():
    m = {"ok": False}
    started = now_ts()
    env = {"STANDBY_BIND": "127.0.0.1", "STANDBY_PORT": CONF["boot_port"]}
    we_started = False  # cleanup only ever removes a server this test started, never a running failover server
    try:
        if server_running():
            raise RuntimeError("the standby server is already running (failover active): not starting a second one")
        ensure_db_up()
        we_started = True
        rc, _, err = compose(["--profile", "failover", "up", "-d", "server"], env=env)
        if rc:
            raise RuntimeError(f"cannot start the standby server: {err.strip()[-200:]}")
        base = f"http://127.0.0.1:{CONF['boot_port']}"
        deadline = now_ts() + CONF["boot_seconds"]
        healthy = False
        while now_ts() < deadline and not healthy:
            try:
                healthy = http_get(base + "/api/health")[0] == 200
            except (urllib.error.URLError, OSError):
                sleep(5)
        if not healthy:
            raise RuntimeError("the standby server did not become healthy")
        key = open(CONF["key_file"]).read().strip()
        status, body = http_get(base + "/api/v1/daemons?limit=1000", key=key)
        daemons = len(json.loads(body).get("data") or [])
        expected = int(psql("select count(*) from daemons", DB))
        if status != 200 or daemons == 0 or daemons != expected:
            raise RuntimeError(f"the standby API listed {daemons} daemons, the standby database has {expected}")
        m.update(ok=True, boot_ts=now_ts())
        log(f"boot test ok: standby server healthy, {daemons} daemons through the API with the job key")
    except Exception as e:
        log(f"FAILED: {type(e).__name__}: {e}")
    finally:
        if we_started:
            compose(["--profile", "failover", "rm", "-sf", "server"], env=env, timeout=120)
    m["boot_seconds"] = now_ts() - started
    return m


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("sync", "boot-test"):
        print("usage: scanopy_standby.py sync [--force] | boot-test", file=sys.stderr)
        sys.exit(2)
    m = cmd_sync("--force" in args) if args[0] == "sync" else cmd_boot_test()
    write_metrics(m)
    sys.exit(0 if m["ok"] else 1)


if __name__ == "__main__":
    main()
