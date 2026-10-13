#!/usr/bin/env python3
"""scanopy_sd - turn the Scanopy inventory into Prometheus file_sd targets.

Single source of truth: Scanopy (hosts, daemons, services) -> file_sd JSON for
  (a) node_exporter targets   (/etc/prometheus/file_sd/scanopy-node.json)
  (b) blackbox TCP/HTTP probes (/etc/prometheus/file_sd/scanopy-blackbox.json)
plus a node_exporter textfile with scanopy_sd_* metrics.

Safety properties
  * stdlib only; atomic writes (tmp + rename); files rewritten only on change
  * if the pull fails, or the inventory / a target class shrinks by more than
    MIN_RATIO versus the last-good state, the previous files are KEPT and
    scanopy_sd_last_success_timestamp_seconds is NOT advanced
  * only endpoints that were actually connectable from this VM (now, or earlier
    per state) are published; node_exporter identity is verified against
    node_uname_info so a mis-pointed proxy can never be scraped under the wrong
    host label (nodename must equal an inventory name, the first DNS label of one when that label is unique
    across inventory hosts, or an explicit alias from /opt/scanopy-sd/node-aliases.json)
  * the API key is read from a root-only file and never logged

Usage
  scanopy_sd.py                      # live pull from the Scanopy API
  scanopy_sd.py --snapshot FILE      # use `fleet-runner scanopy --format json` output
  scanopy_sd.py --dry-run --out-dir D --state-dir S --textfile T
"""
import argparse
import concurrent.futures as cf
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

CONF = {
    "url": os.environ.get("SCANOPY_URL", "http://10.10.10.1:60072"),
    "key_file": os.environ.get("SCANOPY_KEY_FILE", "/etc/scanopy-sd/api-key"),
    "out_dir": os.environ.get("SD_OUT_DIR", "/etc/prometheus/file_sd"),
    "state_dir": os.environ.get("SD_STATE_DIR", "/var/lib/scanopy-sd"),
    "textfile": os.environ.get("SD_TEXTFILE", "/var/lib/prometheus/node-exporter/scanopy_sd.prom"),
    "extra_file": os.environ.get("SD_EXTRA_FILE", "/opt/scanopy-sd/extra-endpoints.json"),
    # optional {"inventory-name": ["nodename", ...]} map for exporters whose nodename cannot be derived
    "alias_file": os.environ.get("SD_NODE_ALIAS_FILE", "/opt/scanopy-sd/node-aliases.json"),
    "min_ratio": float(os.environ.get("SD_MIN_RATIO", "0.8")),
    "max_age_days": float(os.environ.get("SD_MAX_AGE_DAYS", "30")),
    "sticky_days": float(os.environ.get("SD_STICKY_DAYS", "7")),
}

# fleet subnets (Proxmox host -> fleet name used as the `fleet` label)
FLEETS = [
    ("10.10.10.0/24", "0docker"),
    ("10.10.10.0/24", "0mcp"),
    ("10.50.0.0/24", "0database"),   # pve01
    ("10.60.10.0/24", "0own"),
]
FLEETS = [(ipaddress.ip_network(c), n) for c, n in FLEETS]
DAEMON_FLEET = {"0docker": "0docker", "0mcp": "0mcp", "0own": "0own", "pve01": "0database"}

# node_exporter listen ports seen on this estate (identity-checked, see below)
NODE_PORTS = (9100, 9102, 9101)
# Prometheus job names the pre-existing rule files select on (rules/*.yml)
LEGACY_HYPERVISOR_JOB = {
    "0docker": "pve_0docker_host_node_exporter_via_tailscale",
    "0mcp": "pve_0mcp_host_via_tailscale",
    "0own": "pve_0own_host_node_exporter_via_tailscale",
    "0database": "pve01_host_node_exporter_via_tailscale",
}
SERVICE_ROLE = {
    "PostgreSQL": "postgres", "Proxmox VE": "hypervisor", "Proxmox Backup Server": "backup",
    "Grafana": "monitoring", "Nomad": "runtime", "WordPress": "web", "PowerDNS": "dns",
}
PORT_NAMES = {22: "ssh", 53: "dns", 80: "http", 443: "https", 3000: "http-3000", 5432: "postgres",
              8006: "pve-ui", 8007: "pbs-ui", 4646: "nomad", 9090: "prometheus", 3100: "loki"}
GENERIC_NAMES = {"Scanopy Daemon", "Scanopy Server", "scanopy-daemon", "Docker", "Proxmox VE"}
PROBE_PORT_DENY = {60073, 60074}     # scanopy daemon internal ports
CONNECT_TIMEOUT = 2.5


def now():
    return time.time()


def parse_ts(s):
    if not s:
        return 0.0
    try:
        s = s.replace("Z", "+00:00")
        from datetime import datetime
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- inventory
def load_snapshot(path):
    d = json.load(open(path))
    inv = {"hosts": [], "services": [], "daemons": [], "subnets": []}
    for m in d.get("matches", []):
        if m.get("resource") in inv:
            inv[m["resource"]].append(m["fields"])
    return inv, "snapshot"


def api_get(base, key, resource):
    rows, offset = [], 0
    while True:
        req = urllib.request.Request(
            f"{base}/api/v1/{resource}?limit=1000&offset={offset}",
            headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            page = json.loads(r.read(16 << 20))
        if not page.get("success"):
            raise RuntimeError(f"{resource}: success=false")
        rows += page.get("data") or []
        if not (page.get("meta", {}).get("pagination", {}).get("has_more")):
            break
        if not page.get("data"):
            raise RuntimeError(f"{resource}: empty page with has_more")
        offset += 1000
        if offset > 100000:
            raise RuntimeError(f"{resource}: safety cap")
    return rows


def load_api():
    try:
        key = open(CONF["key_file"]).read().strip()
    except OSError as e:
        raise RuntimeError(f"no API key file ({CONF['key_file']}): {e.strerror}")
    if not key:
        raise RuntimeError("API key file is empty")
    inv = {r: api_get(CONF["url"], key, r) for r in ("hosts", "services", "daemons", "subnets")}
    return inv, "api"


# --------------------------------------------------------------------------- model
def fleet_of_ip(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for net, name in FLEETS:
        if a in net:
            return name
    return None


def norm(s):
    return (s or "").strip().lower()


def first_label(name):
    """First DNS label of a dotted inventory name ('a.example.org' -> 'a'); None for bare names and IP literals."""
    name = norm(name)
    if "." not in name:
        return None
    try:
        ipaddress.ip_address(name)
        return None
    except ValueError:
        pass
    label = name.split(".", 1)[0]
    return label or None


def load_aliases(path):
    """Optional explicit identity aliases: {"inventory name": ["nodename", ...]} (a missing/invalid file means none)."""
    try:
        raw = json.load(open(path))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        vals = [v] if isinstance(v, str) else v if isinstance(v, list) else []
        out[norm(k)] = {norm(x) for x in vals if isinstance(x, str) and norm(x)}
    return out


def assign_node_names(hosts, aliases=None):
    """Set rec["node_names"]: the nodenames node_uname_info may legitimately report for each host.

    Always the inventory names. Additionally the first DNS label of an inventory name (scrapetheworld.org ->
    scrapetheworld, the hostname the machine itself reports), but only when that label belongs to exactly one inventory
    host: a label shared by several hosts could verify the wrong machine, so it is never accepted. Explicit aliases
    always apply to the host whose inventory name they are keyed by.
    """
    aliases = aliases or {}
    owners = {}
    for rec in hosts:
        labels = {first_label(n) for n in rec["names"]} | {n for n in rec["names"] if "." not in n}
        for lab in labels - {None}:
            owners.setdefault(lab, set()).add(rec["id"])
    for rec in hosts:
        accepted = set(rec["names"])
        for n in rec["names"]:
            lab = first_label(n)
            if lab and owners.get(lab) == {rec["id"]}:
                accepted.add(lab)
            accepted |= aliases.get(n, set())
        rec["node_names"] = accepted
    return hosts


def build_hosts(inv):
    """Return list of host dicts (deduplicated machines with a fleet IP)."""
    daemons = inv["daemons"]
    svc_by_host = {}
    for s in inv["services"]:
        svc_by_host.setdefault(s.get("host_id"), set()).add(s.get("name"))
    hyp_ids = {}   # host_id -> fleet   (daemon named pve-<fleet>)
    hyp_label = {}  # host_id -> daemon name (stable label for hypervisors)
    guest_daemons = []  # (fleet, vmid, suffix)
    for d in daemons:
        n = d.get("name") or ""
        m = re.match(r"^pve-(.+)$", n)
        if m and m.group(1) in DAEMON_FLEET:
            hyp_ids[d.get("host_id")] = DAEMON_FLEET[m.group(1)]
            hyp_label[d.get("host_id")] = n
            continue
        m = re.match(r"^vm-(0docker|0mcp|0own|pve01)-(?:(\d+)-)?(.+)$", n)
        if m:
            guest_daemons.append((DAEMON_FLEET[m.group(1)], m.group(2) or "", norm(m.group(3))))
    cutoff = now() - CONF["max_age_days"] * 86400
    stats = {"too_old": 0, "non_fleet": 0, "dup": 0}
    by_key = {}
    newest_seen = 0.0
    for h in inv["hosts"]:
        seen = parse_ts(h.get("last_seen_at"))
        newest_seen = max(newest_seen, seen)
        ips = [i.get("ip_address") for i in (h.get("ip_addresses") or []) if isinstance(i, dict)]
        fleet_ips = [(ip, fleet_of_ip(ip)) for ip in ips if fleet_of_ip(ip)]
        hid = h.get("id")
        is_hyp = hid in hyp_ids
        if not fleet_ips and not is_hyp:
            stats["non_fleet"] += 1
            continue
        if seen and seen < cutoff:
            stats["too_old"] += 1
            continue
        names = {n for n in (norm(h.get("hostname")), norm(h.get("name"))) if n}
        host_fleets = [f for _, f in fleet_ips]
        fleet, vmid = hyp_ids.get(hid), ""
        if not fleet:
            for f, vm, suf in guest_daemons:
                if f in host_fleets and suf in names:
                    fleet, vmid = f, vm
                    break
        if not fleet:
            fleet = host_fleets[0]
        # prefer the IP that lies in this host's own fleet subnet
        own = [ip for ip, f in fleet_ips if f == fleet] or [ip for ip, _ in fleet_ips]
        key = norm(h.get("hostname")) or norm(h.get("name"))
        ports = sorted({p.get("number") for p in (h.get("ports") or [])
                        if isinstance(p, dict) and str(p.get("protocol", "Tcp")).lower() == "tcp"
                        and isinstance(p.get("number"), int)})
        gname = h.get("name") or ""
        if is_hyp:
            label = hyp_label[hid]
        elif gname in GENERIC_NAMES or not gname:
            label = h.get("hostname") or gname or key
        else:
            label = gname
        rec = {"id": hid, "name": label, "rawname": gname,
               "hostname": h.get("hostname") or "", "fleet": fleet, "ips": own, "ports": ports,
               "seen": seen, "hyp": is_hyp, "vmid": vmid, "services": sorted(x for x in svc_by_host.get(hid, []) if x)}
        if key in by_key:        # same machine seen under several Scanopy records
            stats["dup"] += 1
            old = by_key[key]
            better = (rec["hyp"] and not old["hyp"]) or (not old["hyp"] and rec["vmid"] and not old["vmid"])
            merged_ports = sorted(set(rec["ports"]) | set(old["ports"]))
            if better:
                rec["ports"] = merged_ports
                rec["ips"] = rec["ips"] + [i for i in old["ips"] if i not in rec["ips"]]
                rec["seen"] = max(rec["seen"], old["seen"])
                by_key[key] = rec
            else:
                old["ports"] = merged_ports
                old["ips"] = old["ips"] + [i for i in rec["ips"] if i not in old["ips"]]
                old["seen"] = max(old["seen"], rec["seen"])
            continue
        by_key[key] = rec
    hosts = list(by_key.values())
    for rec in hosts:
        names = {norm(rec["rawname"]), norm(rec["name"]), norm(rec["hostname"])}
        role = "hypervisor" if rec["hyp"] else "guest"
        if not rec["hyp"]:
            for s in rec["services"]:
                if s in SERVICE_ROLE and SERVICE_ROLE[s] != "hypervisor":
                    role = SERVICE_ROLE[s]
                    break
        rec["role"] = role
        rec["names"] = {n for n in names if n}
    assign_node_names(hosts, load_aliases(CONF["alias_file"]))
    hosts.sort(key=lambda r: (r["fleet"], tuple(int(x) for x in r["ips"][0].split(".")) if r["ips"] else (0,), r["name"]))
    return hosts, stats, newest_seen


def tailscale_peers():
    """hostname(lower) -> [ips] from the local tailscaled (best effort)."""
    try:
        out = subprocess.run(["tailscale", "status", "--json"], capture_output=True, timeout=10, check=True).stdout
        d = json.loads(out)
    except Exception as e:
        log(f"tailscale status unavailable: {e}")
        return {}
    peers = {}
    for p in list((d.get("Peer") or {}).values()) + [d.get("Self") or {}]:
        hn = norm(p.get("HostName"))
        ips = [i for i in (p.get("TailscaleIPs") or []) if ":" not in i]
        if hn and ips:
            peers[hn] = ips
    return peers


# --------------------------------------------------------------------------- probing
def tcp_state(ip, port):
    """'open' | 'refused' (host reachable) | 'timeout' (no route / filtered / down)."""
    s = socket.socket()
    s.settimeout(CONNECT_TIMEOUT)
    try:
        s.connect((ip, port))
        return "open"
    except ConnectionRefusedError:
        return "refused"
    except Exception:
        return "timeout"
    finally:
        s.close()


def nodename_of(ip, port):
    """node_uname_info nodename from the exporter, or None."""
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/metrics", timeout=6) as r:
            buf = b""
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                buf += chunk
                m = re.search(rb'node_uname_info\{[^}]*nodename="([^"]+)"', buf)
                if m:
                    return m.group(1).decode()
                if len(buf) > 4 << 20:
                    break
    except Exception:
        return None
    return None


def resolve_node(host, peers, state):
    """Find a working, identity-verified node_exporter endpoint for a host."""
    cands = []
    for ip in host["ips"]:
        cands += [(ip, p, "lan") for p in NODE_PORTS]
    for n in host["names"]:
        for tip in peers.get(n, []) + peers.get(n + "-metrics", []):
            cands += [(tip, p, "tailscale") for p in NODE_PORTS]
    seen, uniq = set(), []
    for c in cands:
        if c[:2] not in seen:
            seen.add(c[:2])
            uniq.append(c)
    reachable = False
    mismatch = None
    ident_cache = state.setdefault("ident", {})
    for ip, port, via in uniq:
        st = tcp_state(ip, port)
        if st == "refused":
            reachable = True
            continue
        if st != "open":
            continue
        reachable = True
        k = f"{ip}:{port}"
        c = ident_cache.get(k)
        if c and now() - c["ts"] < 3600 and c.get("host") == host["name"]:
            nodename = c["nodename"]
        else:
            nodename = nodename_of(ip, port)
        if nodename is None:
            return {"addr": k, "via": via, "identity": "unverified"}, reachable, None
        if norm(nodename) in host.get("node_names", host["names"]):
            ident_cache[k] = {"ts": now(), "nodename": nodename, "host": host["name"]}
            return {"addr": k, "via": via, "identity": "verified"}, reachable, None
        mismatch = nodename
    return None, reachable, mismatch


def probe_all(hosts, peers, state, extras):
    with cf.ThreadPoolExecutor(24) as ex:
        node_futs = {h["id"]: ex.submit(resolve_node, h, peers, state) for h in hosts}
        bb = []
        for h in hosts:
            for port in h["ports"]:
                if port in PROBE_PORT_DENY or not h["ips"]:
                    continue
                bb.append((h, h["ips"][0], port))
        bb_futs = [(h, ip, port, ex.submit(tcp_state, ip, port)) for h, ip, port in bb]
        ex_futs = []
        for e in extras:
            m = re.match(r"^(?:\w+://)?([^/:]+):(\d+)", e["target"]) or re.match(r"^(?:\w+://)?([^/:]+)()", e["target"])
            host, port = m.group(1), int(m.group(2) or (443 if e["target"].startswith("https") else 80))
            ex_futs.append((e, ex.submit(tcp_state, host, port)))
        node_res = {k: f.result() for k, f in node_futs.items()}
        bb_res = [(h, ip, port, f.result()) for h, ip, port, f in bb_futs]
        ex_res = [(e, f.result()) for e, f in ex_futs]
    return node_res, bb_res, ex_res


# --------------------------------------------------------------------------- outputs
def write_atomic(path, data, mode=0o644, group="prometheus"):
    d = os.path.dirname(path)
    tmp = os.path.join(d, "." + os.path.basename(path) + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, mode)
    try:
        import grp
        os.chown(tmp, 0, grp.getgrnam(group).gr_gid)
    except Exception:
        pass
    os.replace(tmp, path)


def write_if_changed(path, data):
    try:
        if open(path, "rb").read() == data:
            return False
    except OSError:
        pass
    write_atomic(path, data)
    return True


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def metrics_text(m):
    lines = []

    def add(name, help_, typ, series):
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} {typ}")
        for labels, val in series:
            lab = ",".join(f'{k}="{esc(v)}"' for k, v in labels.items())
            lines.append(f"{name}{{{lab}}} {val}" if lab else f"{name} {val}")
    add("scanopy_sd_last_success_timestamp_seconds", "Last run that pulled Scanopy and published targets.", "gauge",
        [({}, int(m["last_success"]))])
    add("scanopy_sd_last_attempt_timestamp_seconds", "Last run attempt.", "gauge", [({}, int(m["attempt"]))])
    add("scanopy_sd_last_attempt_success", "1 if the last attempt succeeded, 0 if last-good files were kept.", "gauge",
        [({}, 1 if m["ok"] else 0)])
    add("scanopy_sd_source_info", "Where the inventory of the last successful run came from.", "gauge",
        [({"inventory_source": m["source"]}, 1)])
    add("scanopy_sd_targets", "Targets currently published in the file_sd files.", "gauge",
        [({"kind": k}, v) for k, v in sorted(m["targets"].items())])
    add("scanopy_sd_candidate_targets", "Targets the latest pull would publish.", "gauge",
        [({"kind": k}, v) for k, v in sorted(m["candidates"].items())])
    add("scanopy_sd_guard_tripped", "1 when the shrink guard kept last-good files for this kind.", "gauge",
        [({"kind": k}, v) for k, v in sorted(m["guard"].items())])
    add("scanopy_sd_inventory_entities", "Entities in the Scanopy inventory.", "gauge",
        [({"kind": k}, v) for k, v in sorted(m["inventory"].items())])
    add("scanopy_sd_inventory_newest_seen_timestamp_seconds",
        "Newest last_seen_at over all Scanopy host records (discovery freshness).", "gauge",
        [({}, int(m["newest_seen"]))])
    add("scanopy_sd_hosts_uncovered", "Inventory hosts without a verified node_exporter, by reason.", "gauge",
        [({"reason": k}, v) for k, v in sorted(m["uncovered"].items())])
    add("scanopy_sd_blackbox_endpoints_unreachable", "Scanopy-listed endpoints never connectable from this VM (not probed).", "gauge",
        [({}, m.get("bb_unreachable", 0))])
    add("scanopy_sd_host_info", "One series per inventory host; expected_node_exporter=1 means it must be scraped.", "gauge",
        [({("inv_" + k if k in ("fleet", "host", "vmid", "role", "address") else k): v for k, v in h.items()}, 1)
         for h in m["host_info"]])
    return ("\n".join(lines) + "\n").encode()


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir")
    ap.add_argument("--state-dir")
    ap.add_argument("--textfile")
    a = ap.parse_args()
    if a.out_dir:
        CONF["out_dir"] = a.out_dir
    if a.state_dir:
        CONF["state_dir"] = a.state_dir
    if a.textfile:
        CONF["textfile"] = a.textfile
    os.makedirs(CONF["state_dir"], exist_ok=True)
    st_path = os.path.join(CONF["state_dir"], "state.json")
    try:
        state = json.load(open(st_path))
    except Exception:
        state = {}
    t0 = now()
    prev = state.get("last_good", {})
    mx = {
        "last_success": state.get("last_success", 0), "attempt": t0, "ok": False,
        "source": state.get("source", "none"),
        "targets": dict(prev.get("targets", {"node": 0, "blackbox": 0})),
        "candidates": {"node": 0, "blackbox": 0}, "guard": {"node": 0, "blackbox": 0},
        "inventory": dict(prev.get("inventory", {})), "newest_seen": state.get("newest_seen", 0),
        "uncovered": dict(state.get("uncovered", {})), "host_info": state.get("host_info", []),
        "bb_unreachable": state.get("bb_unreachable", 0),
    }

    def finish(rc, note):
        state["last_attempt"] = t0
        if True:
            write_atomic(st_path, json.dumps(state, indent=1, sort_keys=True).encode(), 0o600, "root")
            write_atomic(CONF["textfile"], metrics_text(mx), 0o644, "root")
        log(note)
        return rc

    # ---- pull
    try:
        inv, source = load_snapshot(a.snapshot) if a.snapshot else load_api()
        if not inv["hosts"] or not inv["daemons"]:
            raise RuntimeError("inventory has no hosts/daemons")
    except Exception as e:
        return finish(0 if prev else 1, f"PULL FAILED, keeping last-good files: {e}")
    inv_counts = {k: len(v) for k, v in inv.items()}
    prev_inv = prev.get("inventory", {})
    if prev_inv.get("hosts", 0) >= 10 and inv_counts["hosts"] < CONF["min_ratio"] * prev_inv["hosts"] \
            and not os.path.exists(os.path.join(CONF["state_dir"], "accept-shrink")):
        mx["guard"] = {"node": 1, "blackbox": 1}
        mx["inventory"] = inv_counts
        return finish(0, f"GUARD: inventory hosts {prev_inv['hosts']} -> {inv_counts['hosts']}, keeping last-good files")

    # ---- derive
    hosts, hstats, newest_seen = build_hosts(inv)
    peers = tailscale_peers()
    try:
        extras = json.load(open(CONF["extra_file"]))
    except Exception:
        extras = []
    node_res, bb_res, ex_res = probe_all(hosts, peers, state, extras)
    sticky_cut = t0 - CONF["sticky_days"] * 86400
    node_seen = state.setdefault("node_last_ok", {})
    bb_seen = state.setdefault("bb_last_ok", {})

    node_targets, host_info, uncovered = [], [], {}
    for h in hosts:
        res, reachable, mismatch = node_res[h["id"]]
        lab = {"fleet": h["fleet"], "host": h["name"], "vmid": h["vmid"], "role": h["role"],
               "source": "scanopy_node", "scanopy_id": h["id"]}
        if h["hyp"]:
            lab["scanopy_job"] = LEGACY_HYPERVISOR_JOB[h["fleet"]]
        info = dict(fleet=h["fleet"], host=h["name"], vmid=h["vmid"], role=h["role"],
                    address=h["ips"][0] if h["ips"] else "")
        if res:
            lab["via"] = res["via"]
            lab["identity"] = res["identity"]
            node_targets.append({"targets": [res["addr"]], "labels": lab})
            node_seen[h["id"]] = {"addr": res["addr"], "ts": t0, "via": res["via"]}
            info.update(expected_node_exporter="1", reason="ok", via=res["via"])
        else:
            last = node_seen.get(h["id"])
            if last and last["ts"] >= sticky_cut:
                # was scrapeable recently: keep publishing so up==0 is visible and alerts
                lab["via"] = last["via"]
                lab["identity"] = "stale"
                node_targets.append({"targets": [last["addr"]], "labels": lab})
                info.update(expected_node_exporter="1", reason="down_after_ok", via=last["via"])
            elif mismatch:
                info.update(expected_node_exporter="1", reason="identity_mismatch", via="")
            elif reachable:
                info.update(expected_node_exporter="1", reason="exporter_not_listening", via="")
            else:
                info.update(expected_node_exporter="0", reason="unreachable", via="")
        if info["reason"] != "ok":
            uncovered[info["reason"]] = uncovered.get(info["reason"], 0) + 1
        host_info.append(info)

    bb_targets, bb_nr = [], 0
    for h, ip, port, stt in bb_res:
        k = f"{ip}:{port}"
        if stt == "open":
            bb_seen[k] = t0
        elif not (k in bb_seen and bb_seen[k] >= sticky_cut):
            bb_nr += 1
            continue
        bb_targets.append({"targets": [k], "labels": {
            "fleet": h["fleet"], "host": h["name"], "vmid": h["vmid"], "role": h["role"],
            "service": PORT_NAMES.get(port, f"tcp-{port}"), "port": str(port),
            "probe_module": "tcp_connect", "source": "scanopy_blackbox"}})
    have = {t["targets"][0] for t in bb_targets}
    for e, stt in ex_res:
        k = e["target"]
        if stt == "open":
            bb_seen[k] = t0
        elif not (k in bb_seen and bb_seen[k] >= sticky_cut):
            bb_nr += 1
            continue
        hostrec = next((h for h in hosts if h["name"] == e.get("host")), None)
        bb_targets.append({"targets": [k], "labels": {
            "fleet": hostrec["fleet"] if hostrec else e.get("fleet", ""), "host": e.get("host", ""),
            "vmid": hostrec["vmid"] if hostrec else "", "role": hostrec["role"] if hostrec else "",
            "service": e.get("service", ""), "probe_module": e.get("module", "http_2xx"),
            "source": "scanopy_blackbox", "origin": "extra-endpoints"}})
    mx["candidates"] = {"node": len(node_targets), "blackbox": len(bb_targets)}
    mx["bb_unreachable"] = bb_nr

    # ---- shrink guard (per kind)
    out = {"node": ("scanopy-node.json", node_targets), "blackbox": ("scanopy-blackbox.json", bb_targets)}
    accept = os.path.exists(os.path.join(CONF["state_dir"], "accept-shrink"))
    published = dict(mx["targets"])
    for kind, (fname, tl) in out.items():
        last = prev.get("targets", {}).get(kind, 0)
        if last >= 5 and len(tl) < CONF["min_ratio"] * last and not accept:
            mx["guard"][kind] = 1
            log(f"GUARD: {kind} targets {last} -> {len(tl)} (<{CONF['min_ratio']:.0%}); keeping last-good file")
            continue
        data = (json.dumps(tl, indent=1, sort_keys=True) + "\n").encode()
        if not a.dry_run:
            if write_if_changed(os.path.join(CONF["out_dir"], fname), data):
                log(f"wrote {fname}: {len(tl)} targets")
        else:
            write_atomic(os.path.join(CONF["out_dir"], fname), data)
        published[kind] = len(tl)
    if accept and not a.dry_run:
        try:
            os.remove(os.path.join(CONF["state_dir"], "accept-shrink"))
        except OSError:
            pass

    mx.update(ok=not any(mx["guard"].values()), source=source, targets=published, inventory=inv_counts, newest_seen=newest_seen,
              uncovered=uncovered, host_info=host_info)
    if not any(mx["guard"].values()):
        mx["last_success"] = t0
        state["last_success"] = t0
    state.update(bb_unreachable=bb_nr, source=source, newest_seen=newest_seen, uncovered=uncovered, host_info=host_info,
                 last_good={"targets": published, "inventory": inv_counts})
    # drop stale ident cache / stickiness entries
    state["bb_last_ok"] = {k: v for k, v in bb_seen.items() if v >= sticky_cut}
    state["node_last_ok"] = {k: v for k, v in node_seen.items() if v["ts"] >= sticky_cut}
    return finish(0, f"ok source={source} hosts={len(hosts)} (skipped {hstats}) node={published['node']} "
                     f"blackbox={published['blackbox']} uncovered={uncovered}")


if __name__ == "__main__":
    sys.exit(main())
