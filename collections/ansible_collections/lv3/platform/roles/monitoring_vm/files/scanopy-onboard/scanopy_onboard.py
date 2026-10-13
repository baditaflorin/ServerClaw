#!/usr/bin/env python3
"""scanopy_onboard - put a Scanopy daemon on every Proxmox guest that has none, without anyone touching the guest.

Every run (systemd timer, 15 minutes):
  1. asks each hypervisor in fleets.json for its running guests through the forced-command key
     (scanopy_onboard_hv.py `list`) and asks Scanopy which hosts already have a daemon;
  2. a guest counts as covered when a daemon is named after it, or one of its MAC addresses, or an IPv4 address that belongs
     to exactly one daemon host, is known to Scanopy;
  3. a guest that is uncovered in two consecutive runs (so a guest still being provisioned is left alone) is onboarded:
     a daemon record and 1:1 API key are provisioned (POST /api/v1/daemons/provision), the hypervisor installs the daemon
     in the guest (`install`), the job waits for the daemon to check in, gives its discovery a free daily quarter-hour slot
     (scanopy_discover.py then scans it every day without an inventory edit) and attaches the Docker credential to hosts
     that run Docker;
  4. publishes scanopy_onboard_* metrics; alerts live in config/prometheus/rules/inventory.yml.

Safety: at most MAX_INSTALLS guests per run; a failing guest backs off (30 min, doubling, up to 24 h) instead of being retried
every run; it never touches a guest that already runs an active scanopy-daemon service; --dry-run changes nothing. Guests listed
under `exclude` ("<fleet>:<vm|ct>:<id>") are ignored on purpose. stdlib only; the Scanopy key is read from a root-only file
and never logged; the daemon key goes to the hypervisor on stdin only.

Config: fleets.json  {"site_id":..., "docker_credential_id":..., "exclude":[...], "fleets":[{"name":"0mcp",
"ssh":"root@10.10.10.1","port":22,"relay_url":"http://10.10.10.1:60072"}, ...]}
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

CONF = {
    "url": os.environ.get("SCANOPY_URL", "http://10.10.10.1:60072"),
    "key_file": os.environ.get("SCANOPY_KEY_FILE", "/etc/scanopy-retag/api-key"),
    "fleets_file": os.environ.get("ONBOARD_FLEETS_FILE", "/opt/scanopy-onboard/fleets.json"),
    "schedule_file": os.environ.get("DISCOVER_SCHEDULE_FILE", "/opt/scanopy-discover/schedule.json"),
    "ssh_key": os.environ.get("ONBOARD_SSH_KEY", "/etc/scanopy-onboard/id_ed25519"),
    "known_hosts": os.environ.get("ONBOARD_KNOWN_HOSTS", "/etc/scanopy-onboard/known_hosts"),
    "state_file": os.environ.get("ONBOARD_STATE_FILE", "/var/lib/scanopy-onboard/state.json"),
    "textfile": os.environ.get("ONBOARD_TEXTFILE", "/var/lib/prometheus/node-exporter/scanopy_onboard.prom"),
    "max_installs": int(os.environ.get("ONBOARD_MAX_INSTALLS_PER_RUN", "2")),
    "min_runs": int(os.environ.get("ONBOARD_MIN_UNCOVERED_RUNS", "2")),
    "slot_from": os.environ.get("ONBOARD_SLOT_FROM", "12:00"),
    "wait_seconds": int(os.environ.get("ONBOARD_WAIT_SECONDS", "150")),
    "ssh_timeout": int(os.environ.get("ONBOARD_SSH_TIMEOUT", "40")),
    "install_timeout": int(os.environ.get("ONBOARD_INSTALL_TIMEOUT", "480")),
}
BACKOFF_FIRST = 1800
BACKOFF_MAX = 86400
DAILY_CRON = re.compile(r"^0 ([0-5]?[0-9]) ([01]?[0-9]|2[0-3]) \* \* \*$")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def call(key, method, path, body=None):
    req = urllib.request.Request(
        CONF["url"] + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json", "Content-Type": "application/json"})
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
        if not page.get("data") or offset > 100000:
            raise RuntimeError(f"{path}: pagination did not terminate")
        offset += 1000


def now_ts():
    return time.time()


def sleep(seconds):
    time.sleep(seconds)


def ssh(fleet, remote_cmd, stdin=None, timeout=None):
    """Run one forced-command request on the fleet's hypervisor; returns (rc, stdout, stderr)."""
    argv = ["ssh", "-i", CONF["ssh_key"], "-p", str(fleet.get("port", 22)),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
            "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={CONF['known_hosts']}",
            fleet["ssh"], remote_cmd]
    p = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout or CONF["ssh_timeout"])
    return p.returncode, p.stdout, p.stderr


def guest_key(fleet, g):
    return f"{fleet['name']}:{g['kind']}:{g['id']}"


def daemon_name(fleet, g):
    clean = re.sub(r"[^A-Za-z0-9._-]", "-", g["name"]).strip("-.") or "guest"
    return f"{g['kind']}-{fleet['name']}-{g['id']}-{clean}"[:80]


def coverage_index(daemons, hosts):
    """(daemon names, MACs of daemon hosts, IPv4s that belong to exactly one daemon host)."""
    host_by_id = {h["id"]: h for h in hosts}
    # A record that never checked in (provisioned, install failed) is not coverage: it has no host and nothing polls for it.
    names = {d["name"] for d in daemons if d.get("host_id")}
    macs, ip_owner = set(), {}
    for d in daemons:
        h = host_by_id.get(d.get("host_id"))
        if not h:
            continue
        for ip in h.get("ip_addresses") or []:
            if ip.get("mac_address"):
                macs.add(ip["mac_address"].lower())
            ip_owner.setdefault(ip.get("ip_address"), set()).add(h["id"])
    return names, macs, {ip for ip, owners in ip_owner.items() if ip and len(owners) == 1}


def is_covered(fleet, g, names, macs, unique_ips):
    if daemon_name(fleet, g) in names:
        return True
    suffix = f"-{g['name']}"
    infix = f"-{fleet['name']}-{g['id']}-"
    base = re.sub(r"(-lv3)$", "", g["name"])
    if any(n.endswith(suffix) or infix in n or (fleet["name"] in n.split("-") and n.endswith(f"-{base}"))
           for n in names):
        return True
    if any(m.lower() in macs for m in g.get("macs", [])):
        return True
    return any(ip in unique_ips for ip in g.get("ips", []))


def daemon_version(daemons):
    seen = {}
    for d in daemons:
        v = d.get("version")
        if v and re.match(r"^\d+\.\d+\.\d+$", v):
            seen[v] = seen.get(v, 0) + 1
    return max(seen, key=seen.get) if seen else "latest"


def parse_cron_slot(cron):
    m = DAILY_CRON.match((cron or "").strip())
    if not m or int(m.group(1)) % 15:
        return None
    return int(m.group(2)) * 60 + int(m.group(1))


def free_slot(taken, start="12:00"):
    """First free quarter-hour from `start` (wrapping at midnight); the least-used one when every slot is taken."""
    first = int(start[:2]) * 60 + int(start[3:])
    order = [(first + 15 * i) % 1440 for i in range(96)]
    load = {m: taken.get(m, 0) for m in order}
    pick = min(order, key=lambda m: (load[m], order.index(m)))
    return f"{pick // 60:02d}:{pick % 60:02d}"


def taken_slots(schedule, discoveries):
    taken = {}
    for hhmm in schedule.values():
        minute = int(hhmm[:2]) * 60 + int(hhmm[3:])
        taken[minute] = taken.get(minute, 0) + 1
    for d in discoveries:
        rt = d["run_type"]
        if rt.get("type") == "Scheduled" and rt.get("enabled"):
            minute = parse_cron_slot(rt.get("cron_schedule"))
            if minute is not None:
                taken[minute] = taken.get(minute, 0) + 1
    return taken


def provision_key(key, name, site_id, daemons):
    existing = [d for d in daemons if d["name"] == name]
    body = {"daemon_id": existing[0]["id"]} if existing else {"name": name, "site_id": site_id, "mode": "daemon_poll"}
    out = call(key, "POST", "/api/v1/daemons/provision", body)["data"]
    k = out.get("daemon_api_key")
    plaintext = k.get("key") if isinstance(k, dict) else k
    if not plaintext:
        raise RuntimeError("provision response carried no plaintext key")
    return plaintext


def wait_for_daemon(key, name):
    deadline = now_ts() + CONF["wait_seconds"]
    while now_ts() < deadline:
        for d in get_all(key, "/api/v1/daemons"):
            if d["name"] == name and d.get("host_id") and d.get("last_seen"):
                return d
        sleep(10)
    return None


def schedule_daemon(key, daemon, schedule):
    """Give the daemon's Scheduled discovery a free daily slot; returns the HH:MM it got (None when no definition appeared)."""
    deadline = now_ts() + 90
    disc = None
    while now_ts() < deadline and disc is None:
        mine = [d for d in get_all(key, "/api/v1/discovery")
                if d["daemon_id"] == daemon["id"] and d["run_type"].get("type") == "Scheduled"]
        disc = mine[0] if mine else None
        if disc is None:
            sleep(10)
    if disc is None:
        return None
    slot = free_slot(taken_slots(schedule, get_all(key, "/api/v1/discovery")), CONF["slot_from"])
    disc["run_type"].update({"enabled": True, "cron_schedule": f"0 {int(slot[3:])} {int(slot[:2])} * * *", "timezone": None})
    call(key, "PUT", f"/api/v1/discovery/{disc['id']}", disc)
    return slot


def attach_docker(key, host_id, credential_id):
    host = call(key, "GET", f"/api/v1/hosts/{host_id}")["data"]
    assigned = host.get("credential_assignments") or []
    if any(a["credential_id"] == credential_id for a in assigned):
        return False
    assigned.append({"credential_id": credential_id, "ip_address_ids": None})
    call(key, "PUT", f"/api/v1/hosts/{host_id}", {
        "id": host["id"], "name": host["name"], "hidden": host["hidden"], "tags": host["tags"],
        "credential_assignments": assigned, "expected_updated_at": host["updated_at"]})
    return True


def onboard(key, fleet, g, cfg, daemons, version, schedule, dry_run):
    """Install the daemon in one guest and finish its Scanopy setup. Returns (ok, detail)."""
    name = daemon_name(fleet, g)
    if dry_run:
        return True, f"would onboard as {name} (daemon {version})"
    plaintext = provision_key(key, name, cfg["site_id"], daemons)
    rc, out, err = ssh(fleet, f"install {g['kind']} {g['id']} {fleet['relay_url']} {name} {version}",
                       stdin=plaintext + "\n", timeout=CONF["install_timeout"])
    result = re.search(r"^RESULT (.*)$", out, re.M)
    if rc or not result:
        tail = (out.strip().splitlines() or err.strip().splitlines() or ["no output"])[-1]
        return False, f"install failed (rc={rc}): {tail[:200]}"
    fields = dict(kv.split("=", 1) for kv in result.group(1).split() if "=" in kv)
    if fields.get("skipped"):
        return False, f"daemon service already active in the guest but unknown to Scanopy ({fields['skipped']})"
    if fields.get("active") != "yes":
        return False, "daemon service did not become active"
    daemon = wait_for_daemon(key, name)
    if daemon is None:
        return False, f"daemon installed but did not check in within {CONF['wait_seconds']} s (relay/firewall?)"
    detail = [f"daemon {name} checked in"]
    slot = schedule_daemon(key, daemon, schedule)
    detail.append(f"daily scan {slot} UTC" if slot else "no discovery definition appeared (scan slot not set)")
    if fields.get("docker") == "yes" and cfg.get("docker_credential_id"):
        if attach_docker(key, daemon["host_id"], cfg["docker_credential_id"]):
            detail.append("Docker credential attached")
    return True, ", ".join(detail)


def load_state():
    try:
        with open(CONF["state_file"]) as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(CONF["state_file"]), exist_ok=True)
    tmp = CONF["state_file"] + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, CONF["state_file"])


def write_metrics(m, dry_run):
    if dry_run:
        return
    ts = int(now_ts())
    lines = [
        "# HELP scanopy_onboard_last_success_timestamp_seconds Last run that listed every fleet and finished without a fatal error",
        "# TYPE scanopy_onboard_last_success_timestamp_seconds gauge",
        f"scanopy_onboard_last_attempt_timestamp_seconds {ts}",
    ]
    if m["ok"]:
        lines.append(f"scanopy_onboard_last_success_timestamp_seconds {ts}")
    # not a `fleet` label: Prometheus' own target label of that name would turn it into `exported_fleet`
    for fleet, vals in sorted(m["fleets"].items()):
        lines.append(f'scanopy_onboard_fleet_list_ok{{hypervisor="{fleet}"}} {vals["list_ok"]}')
        lines.append(f'scanopy_onboard_guests_running{{hypervisor="{fleet}"}} {vals["running"]}')
    lines += [
        "# HELP scanopy_onboard_guests_uncovered Running guests without a Scanopy daemon (after the grace runs)",
        "# TYPE scanopy_onboard_guests_uncovered gauge",
        f"scanopy_onboard_guests_uncovered {m['uncovered']}",
        f"scanopy_onboard_guests_unmanageable {m['unmanageable']}",
        f"scanopy_onboard_installs_this_run {m['installs']}",
        f"scanopy_onboard_install_failures {m['failures']}",
    ]
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
    m = {"ok": False, "fleets": {}, "uncovered": 0, "unmanageable": 0, "installs": 0, "failures": 0}
    fatal = False
    try:
        key = open(CONF["key_file"]).read().strip()
        if not key:
            raise RuntimeError("API key file is empty")
        cfg = json.load(open(CONF["fleets_file"]))
        schedule = {}
        try:
            schedule = json.load(open(CONF["schedule_file"]))
        except (OSError, ValueError):
            log("warning: no discover schedule file; slots are chosen from Scanopy alone")
        excluded = set(cfg.get("exclude", []))
        daemons = get_all(key, "/api/v1/daemons")
        hosts = get_all(key, "/api/v1/hosts")
        names, macs, unique_ips = coverage_index(daemons, hosts)
        version = daemon_version(daemons)
        state = load_state()
        seen = {}
        all_listed = True
        for fleet in cfg["fleets"]:
            vals = m["fleets"].setdefault(fleet["name"], {"list_ok": 0, "running": 0})
            listing, err = None, ""
            for attempt in (1, 2):  # one retry: a single SSH timeout must not fail the whole run
                try:
                    rc, out, err = ssh(fleet, "list")
                    listing = json.loads(out) if rc == 0 else None
                except (subprocess.TimeoutExpired, ValueError, OSError) as e:
                    listing, err = None, str(e)
                if listing is not None:
                    break
                log(f"warning: {fleet['name']}: listing attempt {attempt} failed: {(err or '').strip()[:120]}")
            if listing is None:
                log(f"ERROR {fleet['name']}: could not list guests: {(err or '').strip()[:200]}")
                all_listed = False
                continue
            vals["list_ok"] = 1
            vals["running"] = len(listing["guests"])
            for g in listing["guests"]:
                gk = guest_key(fleet, g)
                if gk in excluded:
                    continue
                if is_covered(fleet, g, names, macs, unique_ips):
                    continue
                seen[gk] = (fleet, g)
        # forget guests that are covered again (or gone) so their backoff does not outlive the problem
        listed_fleets = {f for f, v in m["fleets"].items() if v["list_ok"]}
        for gk in list(state):
            if gk.split(":")[0] in listed_fleets and gk not in seen:
                del state[gk]
        for gk, (fleet, g) in seen.items():
            st = state.setdefault(gk, {"runs": 0, "fails": 0, "next_try": 0})
            st["runs"] += 1
            if not g.get("manageable", True):
                m["unmanageable"] += 1
                st["last_error"] = "guest not manageable (QEMU guest agent does not answer)"
                log(f"UNMANAGEABLE {gk} {g['name']}: {st['last_error']}")
                continue
            m["uncovered"] += 1
            if st["runs"] < CONF["min_runs"]:
                log(f"uncovered {gk} {g['name']}: first sighting, waiting one more run")
                continue
            if now_ts() < st["next_try"]:
                log(f"uncovered {gk} {g['name']}: backing off until {dt.datetime.fromtimestamp(st['next_try'], dt.timezone.utc):%H:%M} UTC ({st.get('last_error', '')})")
                continue
            if m["installs"] >= CONF["max_installs"]:
                log(f"uncovered {gk} {g['name']}: deferred (max {CONF['max_installs']} installs per run)")
                continue
            m["installs"] += 1
            try:
                ok, detail = onboard(key, fleet, g, cfg, daemons, version, schedule, args.dry_run)
            except (RuntimeError, OSError, ValueError, KeyError, urllib.error.URLError, subprocess.TimeoutExpired) as e:
                ok, detail = False, f"{type(e).__name__}: {e}"[:200]
            log(("ONBOARDED " if ok else "FAILED ") + f"{gk} {g['name']}: {detail}")
            if ok and not args.dry_run:
                state.pop(gk, None)
                m["uncovered"] -= 1
            elif not ok:
                st["fails"] += 1
                st["last_error"] = detail
                st["next_try"] = now_ts() + min(BACKOFF_MAX, BACKOFF_FIRST * 2 ** (st["fails"] - 1))
        m["failures"] = sum(1 for s in state.values() if s.get("fails"))
        if not args.dry_run:
            save_state(state)
        m["ok"] = all_listed
    except (RuntimeError, OSError, ValueError, KeyError, urllib.error.URLError) as e:
        log(f"FAILED: {e}")
        fatal = True
    log(f"uncovered={m['uncovered']} unmanageable={m['unmanageable']} installs={m['installs']} failures={m['failures']}"
        + (" (dry run)" if args.dry_run else ""))
    write_metrics(m, args.dry_run)
    sys.exit(0 if (m["ok"] and not fatal) else 1)


if __name__ == "__main__":
    main()
