#!/usr/bin/env python3
"""scanopy_discover - start Scanopy discovery on a fixed daily schedule, from outside Scanopy.

Why: Scanopy's own scheduler is not reliable here. In five days of server logs it fired once (a schedule that had just been
saved); the weekly schedules that were already stored never fired, and the server restart on 2026-10-10 appears to drop them.
This job does not depend on that scheduler: a systemd timer runs it every 15 minutes, and it starts the discovery of every
daemon whose daily UTC slot has passed and which has not run since that slot.

Safety properties
  * only ever calls POST /api/v1/discovery/start-session for discoveries that already exist; creates, edits and deletes
    nothing in Scanopy
  * skips a target whose discovery ran since its slot (also when Scanopy's own scheduler ran it, so scans are not doubled)
    and treats HTTP 409 (a session is already running) as "skipped", not as an error
  * catch-up window: a missed slot is only made up within CATCHUP_HOURS (default 3), so a long outage does not trigger a
    burst of daytime scans; the overdue metric and its alert report that case instead
  * starts at most MAX_STARTS_PER_RUN (default 1) sessions per run, so large hosts are never scanned together
  * stdlib only; the API key is read from a root-only file and never logged
  * writes node_exporter textfile metrics scanopy_discover_*

Config (JSON, rendered from inventory): {"<daemon name>": "HH:MM", ...}, times in UTC.
Daemons that are not in the file but whose Scanopy Scheduled definition is enabled with a daily cron on a quarter hour
("0 M H * * *", UTC) are scheduled too: that is how the onboarding job (scanopy_onboard.py) hands over a new daemon, so the
inventory does not need an edit before a new guest is scanned.

It also reports daemon liveness: scanopy_daemon_last_seen_age_seconds{daemon} for every daemon Scanopy knows (a healthy
daemon polls every ~30 s), which the ScanopyDaemonDown alert reads.

Usage
  scanopy_discover.py            # start what is due
  scanopy_discover.py --dry-run  # report only, no sessions, no metrics
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

CONF = {
    "url": os.environ.get("SCANOPY_URL", "http://10.10.10.1:60072"),
    "key_file": os.environ.get("SCANOPY_KEY_FILE", "/etc/scanopy-retag/api-key"),
    "schedule_file": os.environ.get("DISCOVER_SCHEDULE_FILE", "/opt/scanopy-discover/schedule.json"),
    "textfile": os.environ.get("DISCOVER_TEXTFILE", "/var/lib/prometheus/node-exporter/scanopy_discover.prom"),
    "catchup_hours": float(os.environ.get("DISCOVER_CATCHUP_HOURS", "3")),
    "max_starts": int(os.environ.get("DISCOVER_MAX_STARTS_PER_RUN", "1")),
}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def call(key, method, path, body=None):
    req = urllib.request.Request(
        CONF["url"] + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read(16 << 20))
    if not out.get("success"):
        raise RuntimeError(f"{method} {path}: success=false")
    return out


def get_all(key, path):
    rows, offset = [], 0
    while True:
        page = call(key, "GET", f"{path}?limit=1000&offset={offset}")
        rows += page.get("data") or []
        if not page.get("meta", {}).get("pagination", {}).get("has_more"):
            return rows
        if not page.get("data"):
            raise RuntimeError(f"{path}: empty page with has_more")
        offset += 1000
        if offset > 100000:
            raise RuntimeError(f"{path}: safety cap")


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


NEVER_RAN_AGE = 10 * 365 * 86400  # reported instead of infinity so the metric stays a finite number


def parse_ts(value):
    """Scanopy timestamps look like 2026-10-12T14:27:00.369016Z (sometimes nanoseconds)."""
    if not value:
        return None
    head = value.replace("Z", "").split(".")[0]
    return dt.datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)


def last_slot(now, hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return slot if slot <= now else slot - dt.timedelta(days=1)


DAILY_CRON = re.compile(r"^0 ([0-5]?[0-9]) ([01]?[0-9]|2[0-3]) \* \* \*$")


def auto_slots(daemons, discoveries, known):
    """{daemon name: "HH:MM"} for daemons absent from the inventory schedule with an enabled daily quarter-hour cron."""
    out = {}
    for name, daemon_id in daemons.items():
        if name in known:
            continue
        disc = pick_discovery(discoveries, daemon_id)
        if disc is None or not disc["run_type"].get("enabled"):
            continue
        m = DAILY_CRON.match((disc["run_type"].get("cron_schedule") or "").strip())
        if m and int(m.group(1)) % 15 == 0:
            out[name] = f"{int(m.group(2)):02d}:{int(m.group(1)):02d}"
    return out


def liveness(daemon_rows, now):
    """[(daemon name, seconds since last_seen)]; a daemon that never checked in reports NEVER_RAN_AGE."""
    out = []
    for d in daemon_rows:
        seen = parse_ts(d.get("last_seen"))
        out.append((d["name"], (now - seen).total_seconds() if seen else NEVER_RAN_AGE))
    return sorted(out)


def pick_discovery(discoveries, daemon_id):
    """The Scheduled definition of this daemon; an enabled one wins over a disabled leftover."""
    mine = [d for d in discoveries if d["daemon_id"] == daemon_id and d["run_type"]["type"] == "Scheduled"]
    mine.sort(key=lambda d: (bool(d["run_type"].get("enabled")), d["run_type"].get("last_run") or ""), reverse=True)
    return mine[0] if mine else None


def write_metrics(ok, targets, started, due, errors, oldest_age, dry_run, alive=None, unreachable=None):
    if dry_run:
        return
    now = int(time.time())
    lines = [
        "# HELP scanopy_discover_last_attempt_success 1 if the last run finished without errors",
        "# TYPE scanopy_discover_last_attempt_success gauge",
        f"scanopy_discover_last_attempt_success {1 if ok else 0}",
        f"scanopy_discover_last_attempt_timestamp_seconds {now}",
    ]
    if ok:
        lines.append(f"scanopy_discover_last_success_timestamp_seconds {now}")
    lines += [
        f"scanopy_discover_targets {targets}",
        f"scanopy_discover_started_this_run {started}",
        f"scanopy_discover_due {due}",
        f"scanopy_discover_errors {errors}",
    ]
    if oldest_age is not None:
        lines.append(f"scanopy_discover_oldest_last_run_age_seconds {int(oldest_age)}")
    if alive is not None:
        lines += [
            "# HELP scanopy_daemon_last_seen_age_seconds Seconds since the Scanopy daemon last polled the server",
            "# TYPE scanopy_daemon_last_seen_age_seconds gauge",
        ]
        lines += [f'scanopy_daemon_last_seen_age_seconds{{daemon="{n}"}} {int(a)}' for n, a in alive]
        lines += [f"scanopy_daemons_total {len(alive)}", f"scanopy_daemons_unreachable {unreachable or 0}"]
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
    targets, started, due, errors, oldest_age, fatal = 0, 0, 0, 0, None, False
    alive, unreachable = None, None
    try:
        try:
            key = open(CONF["key_file"]).read().strip()
        except OSError as e:
            raise RuntimeError(f"no API key file ({CONF['key_file']}): {e.strerror}")
        if not key:
            raise RuntimeError("API key file is empty")
        schedule = json.load(open(CONF["schedule_file"]))
        if not isinstance(schedule, dict) or not schedule:
            raise RuntimeError(f"{CONF['schedule_file']} must be a non-empty JSON object")
        now = utcnow()
        daemon_rows = get_all(key, "/api/v1/daemons")
        alive = liveness(daemon_rows, now)
        unreachable = sum(1 for d in daemon_rows if d.get("is_unreachable"))
        daemons = {d["name"]: d["id"] for d in daemon_rows}
        discoveries = get_all(key, "/api/v1/discovery")
        schedule = {**auto_slots(daemons, discoveries, schedule), **schedule}
        targets = len(schedule)
        for name in sorted(schedule, key=lambda n: schedule[n]):
            if name not in daemons:
                log(f"ERROR {name}: no such daemon in Scanopy")
                errors += 1
                continue
            disc = pick_discovery(discoveries, daemons[name])
            if disc is None:
                log(f"ERROR {name}: no Scheduled discovery definition to start")
                errors += 1
                continue
            last_run = parse_ts(disc["run_type"].get("last_run"))
            age = (now - last_run).total_seconds() if last_run else NEVER_RAN_AGE
            if oldest_age is None or age > oldest_age:
                oldest_age = age
            slot = last_slot(now, schedule[name])
            if last_run is not None and last_run >= slot:
                continue
            if (now - slot).total_seconds() > CONF["catchup_hours"] * 3600:
                log(f"missed {name} (slot {slot:%m-%d %H:%M} UTC) and past the catch-up window; waiting for the next slot")
                continue
            due += 1
            if started >= CONF["max_starts"]:
                log(f"due {name} (slot {slot:%H:%M} UTC): deferred to the next run (max {CONF['max_starts']} per run)")
                continue
            if args.dry_run:
                log(f"would start {name} (slot {slot:%H:%M} UTC, last run {last_run})")
                started += 1
                continue
            try:
                call(key, "POST", "/api/v1/discovery/start-session", disc["id"])
                log(f"started {name} (slot {slot:%H:%M} UTC)")
                started += 1
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    log(f"skipped {name}: a session is already running")
                else:
                    log(f"ERROR {name}: start-session HTTP {e.code}")
                    errors += 1
    except (RuntimeError, urllib.error.URLError, OSError, ValueError, KeyError) as e:
        log(f"FAILED: {e}")
        fatal = True
    ok = not fatal and errors == 0
    log(f"targets={targets} due={due} started={started} errors={errors}" + (" (dry run)" if args.dry_run else ""))
    write_metrics(ok, targets, started, due, errors, oldest_age, args.dry_run, alive, unreachable)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
