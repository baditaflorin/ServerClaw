#!/usr/bin/env python3
"""standby-ctl: start, check, rehearse and stop the DomainScope standby VM (8101) from the 0infer hypervisor.

The standby is a restored copy of the production docker VM (VM101 on 0docker) that stays OFF and SILENT: link down, onboot 0, protected, tailscaled masked (a restored copy
carries the production VM's tailnet identity), every container stopped with restart=no. This tool is the only thing that changes that, and it is reached through ONE ssh key
whose forced command (standby-ctl-ssh) allows exactly the verbs below. It runs as root on the hypervisor and talks to the guest only through the QEMU guest agent, so a
VM whose link is down can still be prepared.

  status        read-only: VM, resting-state checks, guest view if it runs, bundle applied, last runs
  rehearse      daily: the SAME path as an activation (so what is tested is what will run): start the VM with the link DOWN, silent check, current config bundle, link up,
                read-only DB probe with the production DSN, image tags, then the production api + frontend on the real ports against the STAGING database (the production
                `.env` is swapped to the staging DSN for the run and restored in the teardown; compose's RENDERED config and the running containers are checked to point at the
                staging database, and anything else is refused/stopped), a settle window for the edge path probe, teardown, power off, link down. Always ends resting.
  activate      the real thing: refuses unless the 0docker site is unreachable from here AND the control targets are reachable; start, silent check, bundle, link up, DB probe,
                image tags, production api+frontend up (rendered config and running containers verified to point at the PRODUCTION database), health. Never starts the singleton
                writer (domainscope-cron). Re-runnable: every step checks its own postcondition.
  check         read-only readiness: the VM is in its resting state (or running under an activation), and a bundle on stdin parses and would be applied; starts nothing
  start-cron    start domainscope-cron on an activated standby (needs the fence to hold again and the standby to have been active for cron_min_active_minutes)
  deactivate    stop the stack, link down, shut the VM down, verify the resting state (the failback; never automatic)

A config bundle (tar.gz of .env, docker-compose.yml, token files, graph-writer key, produced hourly on CT108) is read from STDIN when --bundle is given. It is validated again
here, the standby-specific environment overrides are applied (private primary-LAN endpoints cleared, the hypervisor's gateway added to the trusted proxies) and the result
goes into the guest through the agent's stdin channel: the plaintext never touches this host's disk.

Images: no host in the fleet keeps a registry login (deploys log in with a token they are handed and log out again), so the standby cannot pull during an outage. It runs the
tags the bundle asks for when they are on its disk (or can be pulled); otherwise it falls back to the NEWEST tags it has, says so in the result (`degraded`) and keeps going:
an older image on the current database beats no site. The weekly rehearsal reports the lag.

Output: one JSON object on stdout. Exit codes: 0 ok, 3 precheck failed, 4 refusing (primary answers / cannot tell / busy / disabled), 5 failed mid-way, 6 rehearsal skipped.
When a guest step runs out of time (exit 124) the record also carries `guest_diag`: the guest's own account of itself (systemd jobs, docker/containerd journal, blocked
processes), taken without docker so a hung docker cannot hang it.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import time

CONFIG_PATH = os.environ.get("STANDBY_CTL_CONFIG", "/etc/standby-ctl/config.json")
STATE_DIR = os.environ.get("STANDBY_CTL_STATE", "/var/lib/standby-ctl")
LOCK_PATH = os.environ.get("STANDBY_CTL_LOCK", "/run/standby-ctl.lock")
DISABLE_FILE = os.environ.get("STANDBY_CTL_DISABLE", "/etc/standby-ctl/DISABLE")
LOG_DIR = os.environ.get("STANDBY_CTL_LOG", "/var/log/standby-ctl")

DEFAULTS = {
    "vmid": 8101,
    "expect_name": "standby-docker-prod",
    "bridge": "vmbr70",
    "guest_ip": "10.70.10.50",
    "gateway_ip": "10.70.10.1",
    "primary_probes": [["203.0.113.2", 22], ["203.0.113.2", 443]],       # the 0docker host: ssh and the public edge
    "control_probes": [["203.0.113.1", 443], ["1.1.1.1", 443]],            # must answer, or "primary unreachable" means nothing (UNKNOWN never counts as DOWN)
    "guest_root": "",                                                         # prefix for every absolute path the guest scripts touch; empty in production, a temp dir in tests
    "compose_dir": "/opt/domainscope_scrapetheworld.org",
    "staging_dir": "/opt/domainscope_staging_scrapetheworld_org",
    "helpers": ["domainscope-go-proxy", "domainscope-search-duck-go"],
    "prod_services": ["api", "frontend"],
    "cron_service": "cron",
    "images": {"API_IMAGE_TAG": "ghcr.io/baditaflorin/go-url-categorizer-api", "FRONTEND_IMAGE_TAG": "ghcr.io/baditaflorin/go-url-categorizer-frontend"},
    "ports": {"frontend": 23480, "api": 23481},
    "prod_dbname": "prod_2026_domainscope_scrapetheworld_org",               # the database an activation MUST be connected to; a bundle whose .env names another one is refused
    "rehearsal_dbname": "stage_2026_domainscope_scrapetheworld_org",         # the database a rehearsal MUST be connected to (never the production one)
    "rehearse_hold_s": 20,                                                    # how long a rehearsal keeps the stack up after its health check, so the runner can probe the edge path through it
    "health_paths": {"api": "/health", "frontend": "/"},
    # dsn_host_map: since the 2026-10-18 database cutover the production DSNs name VM701 by its TAILNET address, which this VM (no tailscale, link bridged on vmbr70) cannot route to;
    # the same machine answers on its vmbr70 address. Applied to POSTGRES_DSN of the production AND the staging .env of a bundle; the credentials and every other part are kept byte for byte.
    "env_overrides": {"unset": ["FLEET_INTERNAL_HOST", "FLEET_COLOCATE_SERVICES"], "set": {}, "append_csv": {"TRUSTED_PROXIES": ["10.70.10.1"]},
                      "dsn_host_map": {"100.64.0.22": "10.70.10.10"}},
    # pg_cert: the DSN says sslmode=verify-ca with sslrootcert=/data/pg-tls/infer-pg-primary.crt, and this restored copy of VM101 has no such file in its data volume. VM701's server certificate is
    # self-signed and public (valid to 2036); a copy lives next to this tool (host/pg-tls/, installed to /etc/standby-ctl/pg-tls/), is pinned by the sha256 of its bytes and is put into the
    # volume before the database probe. Empty = feature off.
    "pg_cert": {"src": "/etc/standby-ctl/pg-tls/infer-pg-primary.crt", "sha256": "dc4a57dfb0b201d5a86f3ce5b077478c239bd66147c405423dd1021e100c3827",
                "volume": "domainscope-data", "dest": "pg-tls/infer-pg-primary.crt"},
    "min_available_mb_rehearse": 9000,
    "min_available_mb_activate": 4500,
    "min_free_disk_gb": 6,
    "cron_min_active_minutes": 30,
    "bundle_max_bytes": 900000,
    "timeouts": {"agent_s": 240, "shutdown_s": 150, "pull_s": 420, "up_s": 300, "lock_wait_s": 600, "db_probe_s": 90, "health_s": 180, "diag_s": 25},
}

# what a bundle may contain (tar member names, relative to /) and what it must contain
BUNDLE_PREFIXES = ("opt/domainscope_scrapetheworld.org/.env", "opt/domainscope_scrapetheworld.org/docker-compose.yml", "opt/domainscope_staging_scrapetheworld_org/.env", "etc/domainscope-secrets",
                   "opt/fleet-secrets/graph-writers")
BUNDLE_PARENTS = ("opt", "etc", "opt/domainscope_scrapetheworld.org", "opt/domainscope_staging_scrapetheworld_org", "opt/fleet-secrets")
BUNDLE_MAX_UNPACKED = 5_000_000
ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
LONG_TOKEN = re.compile(r"[A-Za-z0-9+/=]{32,}")
URL_CREDS = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@")
DSN_VARS = ("POSTGRES_DSN",)
# one libpq URL with ONE host: userinfo ends at the first '@' before any '/', the host is followed by an optional :port and then '/', '?', '#' or the end (a list of hosts does not match)
DSN_URL = re.compile(r"^(?P<scheme>postgres(?:ql)?://)(?P<userinfo>[^/?#@]*@)?(?P<host>[A-Za-z0-9._-]+)(?::[0-9]+)?(?=[/?#]|$)")
DSN_KV_HOST = re.compile(r"(?P<pre>(?:^|\s)host\s*=\s*)(?P<v>'(?:[^'\\]|\\.)*'|[^\s']+)")
HOST_OK = re.compile(r"[A-Za-z0-9._-]+")


# What the guest says about itself when one of the steps does not finish in time (exit 124). It must never need docker: the hang it exists for (2026-10-31: docker.service never
# finished starting, `docker ps` blocked, cloud-init's final stage never ran) is exactly the case where docker answers nothing. Every command is bounded and read-only.
GUEST_DIAG = r"""
echo "uptime: $(uptime)"
echo "--- systemd jobs still queued"; timeout 10 systemctl list-jobs --no-pager 2>&1 | head -15
echo "--- unit states"; for u in containerd docker.socket docker cloud-final multi-user.target; do echo "$u=$(timeout 5 systemctl is-active $u 2>&1 | head -1)"; done
echo "--- containerd and docker, this boot"; timeout 15 journalctl -b -u containerd -u docker --no-pager -n 30 -o short-monotonic 2>&1 | cut -c1-200
echo "--- kernel warnings"; timeout 10 dmesg --level=err,warn 2>&1 | tail -8 | cut -c1-200
echo "--- blocked processes"; ps -eo stat,pid,etime,args 2>&1 | awk '$1 ~ /^D/' | cut -c1-160 | head -8
echo "--- memory and disk"; free -m | sed -n 2p; df -h / | tail -1
"""
GUEST_DIAG_MAX = 3500


class Refusing(Exception):
    """A deliberate refusal (exit 4): the primary answers, the control targets do not, another run holds the lock, the kill switch exists."""


class StepFailed(Exception):
    pass


class Skipped(Exception):
    def __init__(self, result):
        super().__init__(result.get("note", "")); self.result = result


def scrub(text: str) -> str:
    """Nothing that looks like a key or a URL with credentials leaves this process in a note, log line or error."""
    return LONG_TOKEN.sub("<redacted>", URL_CREDS.sub(r"\1<redacted>@", text))


# ---------------------------------------------------------------------------------------------------------------------------------------------------- pure helpers
def load_config(path: str = CONFIG_PATH) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if os.path.exists(path):
        for k, v in json.load(open(path)).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def parse_kv(text: str) -> dict:
    """`qm config` output -> dict (first colon-space splits)."""
    out = {}
    for line in text.splitlines():
        if ": " in line and not line.startswith(("#", " ")):
            k, v = line.split(": ", 1)
            out[k.strip()] = v.strip()
    return out


def net0_with_link(net0: str, up: bool) -> str:
    """The same net0 string with link_down removed (up) or set (down); nothing else about the NIC changes."""
    parts = [p for p in net0.split(",") if p and not p.startswith("link_down=")]
    if not up:
        parts.append("link_down=1")
    return ",".join(parts)


def csv_add(value: str, items: list[str]) -> str:
    """Append items to a comma separated value (quotes kept), skipping those already present."""
    q = value[0] if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0] else ""
    inner = value[1:-1] if q else value
    have = [x.strip() for x in inner.split(",") if x.strip()]
    for it in items:
        if it not in have:
            have.append(it)
    return f"{q}{','.join(have)}{q}"


def map_dsn_host(value: str, mapping: dict) -> tuple[str, bool]:
    """Replace the HOST of one libpq DSN (URL or keyword/value form) when it is EXACTLY a key of `mapping`. The credentials, the port, the database and every option are kept byte for byte
    (they are never decoded or re-encoded); a DSN with a list of hosts, an IPv6 host or another host is returned as it came. Returns (value, changed)."""
    if not mapping or not value:
        return value, False
    q = value[0] if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0] else ""
    inner = value[1:-1] if q else value
    m = DSN_URL.match(inner)
    if m:
        new = mapping.get(m.group("host"))
        if new is None or not HOST_OK.fullmatch(new):
            return value, False
        return f"{q}{inner[:m.start('host')]}{new}{inner[m.end('host'):]}{q}", True
    changed = False

    def sub(mm):
        nonlocal changed
        raw = mm.group("v")
        quoted = len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'"
        new = mapping.get(raw[1:-1] if quoted else raw)
        if new is None or not HOST_OK.fullmatch(new):
            return mm.group(0)
        changed = True
        return mm.group("pre") + (f"'{new}'" if quoted else new)

    inner2 = DSN_KV_HOST.sub(sub, inner)
    return (f"{q}{inner2}{q}", True) if changed else (value, False)


def rewrite_env(text: str, overrides: dict) -> tuple[str, dict]:
    """Apply the standby overrides to a .env file. Returns (new text, report of NAMES only). Every other line is kept as it is."""
    unset = set(overrides.get("unset", [])); sets = dict(overrides.get("set", {})); app = {k: list(v) for k, v in overrides.get("append_csv", {}).items()}
    report = {"unset": [], "set": [], "appended": []}
    out, seen = [], set()
    for line in text.splitlines():
        m = ENV_LINE.match(line)
        if not m:
            out.append(line); continue
        name, val = m.group(1), m.group(2)
        seen.add(name)
        if name in unset:
            out.append(f"# standby-ctl: {name} cleared for the standby (it pointed at the primary LAN)"); report["unset"].append(name)
        elif name in sets:
            out.append(f"{name}={sets[name]}"); report["set"].append(name)
        elif name in app:
            out.append(f"{name}={csv_add(val, app[name])}"); report["appended"].append(name)
        else:
            out.append(line)
    for name, val in sets.items():
        if name not in seen:
            out.append(f"{name}={val}"); report["set"].append(name)
    for name, items in app.items():
        if name not in seen:
            out.append(f"{name}={','.join(items)}"); report["appended"].append(name)
    hmap = overrides.get("dsn_host_map") or {}
    if hmap:
        mapped = []
        for i, line in enumerate(out):
            m = ENV_LINE.match(line)
            if m and m.group(1) in DSN_VARS:
                v, changed = map_dsn_host(m.group(2), hmap)
                if changed:
                    out[i] = f"{m.group(1)}={v}"; mapped.append(m.group(1))
        if mapped:
            report["dsn_host_mapped"] = mapped
    return "\n".join(out) + "\n", report


def env_tags(text: str) -> dict:
    tags = {}
    for line in text.splitlines():
        m = ENV_LINE.match(line)
        if m and m.group(1) in ("API_IMAGE_TAG", "FRONTEND_IMAGE_TAG"):
            tags[m.group(1)] = m.group(2).strip().strip("'\"")
    return tags


def dsn_dbname(dsn: str) -> str:
    """The database name of a libpq URL or keyword/value DSN ('' when it has none). Never returns anything else of the DSN."""
    dsn = dsn.strip().strip("'\"")
    if "://" in dsn:
        from urllib.parse import urlparse
        return urlparse(dsn).path.lstrip("/")
    m = re.search(r"dbname=(\S+)", dsn)
    return m.group(1) if m else ""


def env_dsn(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("POSTGRES_DSN="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def read_bundle(raw: bytes, cfg: dict) -> dict:
    """Validate a bundle (a second time: CT108 already did). Returns {"members": [(TarInfo, bytes|None)], "env": text, "tags": {...}, "counts": {...}}. Raises StepFailed."""
    if len(raw) > cfg["bundle_max_bytes"]:
        raise StepFailed(f"bundle is {len(raw)} bytes (limit {cfg['bundle_max_bytes']})")
    try:
        tf = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz")
        infos = tf.getmembers()
    except (tarfile.TarError, EOFError, OSError) as e:
        raise StepFailed(f"bundle is not a tar.gz: {e}")
    members, total, env_text, compose, staging_env = [], 0, None, False, None
    secrets = writers = 0
    for ti in infos:
        raw_name = ti.name
        if raw_name.startswith("/") or ".." in raw_name.split("/"):
            raise StepFailed(f"bundle member with an unsafe path: {raw_name!r}")
        name = raw_name[2:] if raw_name.startswith("./") else raw_name
        name = name.rstrip("/")
        if not (ti.isfile() or ti.isdir()):
            raise StepFailed(f"bundle member that is neither file nor directory: {raw_name!r}")
        if not any(name == p or name.startswith(p + "/") for p in BUNDLE_PREFIXES) and name not in BUNDLE_PARENTS:
            raise StepFailed(f"bundle member outside the allowed paths: {raw_name!r}")
        if ti.uid > 65535 or ti.gid > 65535:
            raise StepFailed(f"bundle member with an odd owner: {raw_name!r}")
        data = tf.extractfile(ti).read() if ti.isfile() else None
        total += len(data or b"")
        if total > BUNDLE_MAX_UNPACKED:
            raise StepFailed("bundle unpacks to more than the limit")
        members.append((ti, data))
        if name == "opt/domainscope_scrapetheworld.org/.env":
            try:
                env_text = data.decode("utf-8")
            except UnicodeDecodeError:
                raise StepFailed("bundle .env is not UTF-8")
        elif name == "opt/domainscope_staging_scrapetheworld_org/.env":
            try:
                staging_env = data.decode("utf-8")
            except UnicodeDecodeError:
                raise StepFailed("bundle staging .env is not UTF-8")
        elif name == "opt/domainscope_scrapetheworld.org/docker-compose.yml":
            compose = len(data) >= 20000
        elif name.startswith("etc/domainscope-secrets/") and ti.isfile():
            secrets += 1
        elif name.startswith("opt/fleet-secrets/graph-writers/") and ti.isfile():
            writers += 1
    if env_text is None or not compose:
        raise StepFailed("bundle lacks .env or a plausible docker-compose.yml")
    nvars = sum(1 for l in env_text.splitlines() if ENV_LINE.match(l))
    tags = env_tags(env_text)
    if nvars < 300 or secrets < 20 or writers < 1 or len(tags) != 2:
        raise StepFailed(f"implausible bundle: env vars={nvars} secret files={secrets} graph-writer files={writers} tags={sorted(tags)}")
    if dsn_dbname(env_dsn(env_text)) != cfg["prod_dbname"]:
        raise StepFailed("bundle .env does not point at the production database (no POSTGRES_DSN, or another database name): refusing to apply it")
    if staging_env is not None:
        sdb = dsn_dbname(env_dsn(staging_env))
        if sdb != cfg["rehearsal_dbname"] or sdb == cfg["prod_dbname"]:
            raise StepFailed("bundle staging .env does not name the rehearsal database: refusing to apply it")
    return {"members": members, "env": env_text, "staging_env_text": staging_env, "tags": tags,
            "counts": {"env_vars": nvars, "secret_files": secrets, "graph_writer_files": writers, "staging_env": staging_env is not None}}


PROD_ENV_MEMBER = "opt/domainscope_scrapetheworld.org/.env"
STAGING_ENV_MEMBER = "opt/domainscope_staging_scrapetheworld_org/.env"


def repack_bundle(parsed: dict, new_env: str, new_staging_env: str | None = None) -> bytes:
    """The same members (owners and modes kept) with .env replaced by the overridden text, and the staging .env too when it was rewritten (its DSN host)."""
    repl = {PROD_ENV_MEMBER: new_env}
    if new_staging_env is not None:
        repl[STAGING_ENV_MEMBER] = new_staging_env
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for ti, data in parsed["members"]:
            name = ti.name.lstrip("./").rstrip("/")
            if name in repl:
                data = repl[name].encode()
                n = tarfile.TarInfo(ti.name); n.size = len(data); n.mode = ti.mode & 0o777; n.uid, n.gid = ti.uid, ti.gid; n.mtime = ti.mtime
                ti = n
            tf.addfile(ti, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


# Runs INSIDE the guest: puts the pinned public database certificate (on stdin) into the data volume. @R@ (guest root, empty in production), @VOL@, @DEST@ and @WANT@ are substituted by
# Ctl.install_pg_cert after the config values were matched against strict patterns. The hash is checked again on this side of the agent, and an identical file is left alone.
PG_CERT_GUEST = r"""
set -e
R='@R@'; vol='@VOL@'; dest='@DEST@'; want='@WANT@'
h() { python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }
mp=$(docker volume inspect "$vol" --format '{{.Mountpoint}}' 2>/dev/null) || mp=""
[ -n "$mp" ] || { echo "no-volume:$vol"; exit 3; }
t=$(mktemp "$R/var/tmp/standby-pgcert.XXXXXX"); trap 'rm -f "$t"' EXIT
cat > "$t"
[ "$(h "$t")" = "$want" ] || { echo "hash-mismatch"; exit 4; }
f="$R$mp/$dest"; d=$(dirname "$f")
if [ -f "$f" ] && [ "$(h "$f")" = "$want" ]; then echo "unchanged"; exit 0; fi
[ -d "$d" ] || install -d -m 755 "$d"
install -m 644 "$t" "$f.new" && mv -f "$f.new" "$f"
echo installed
"""

# Runs INSIDE the guest (parameters come in through the environment, never through argv). See Ctl.stack_up for why the .env is swapped for a rehearsal.
STACK_UP_PY = r"""
import json, os, re, shutil, subprocess, sys, urllib.parse
MODE = os.environ["MODE"]; EXPECT = os.environ["EXPECT_DB"]; PROD_DB = os.environ["PROD_DB"]
SERVICES = os.environ["SERVICES"].split(); WAIT_S = os.environ["WAIT_S"]
os.chdir(os.environ["COMPOSE_DIR"])

def dsn_of(path):
    try:
        for line in open(path):
            if line.startswith("POSTGRES_DSN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""

def dbname(dsn):
    if "://" in dsn:
        return urllib.parse.urlparse(dsn).path.lstrip("/")
    m = re.search(r"dbname=(\S+)", dsn)
    return m.group(1) if m else ""

def sh(*a):
    return subprocess.run(list(a), capture_output=True, text=True)

def restore():
    if os.path.exists(".env.pre-rehearsal"):
        os.replace(".env.pre-rehearsal", ".env")

def rendered():
    r = sh("docker", "compose", "config", "--format", "json")
    if r.returncode != 0:
        return None
    svcs = json.loads(r.stdout).get("services", {})
    out = {}
    for s in SERVICES:
        env = svcs.get(s, {}).get("environment") or {}
        v = env.get("POSTGRES_DSN") or env.get("DATABASE_URL")
        if v:
            out[s] = dbname(v)
    return out

if MODE == "activate" and os.path.exists(".env.pre-rehearsal"):
    # a rehearsal that died before its cleanup: if .env still names the rehearsal database restore the production one, otherwise (a fresh bundle replaced it) drop the stale copy
    if dbname(dsn_of(".env")) != EXPECT:
        restore()
    else:
        os.remove(".env.pre-rehearsal")
if MODE == "rehearse":
    stg = dsn_of(os.environ["STAGING_ENV"])
    if not stg or dbname(stg) != EXPECT or EXPECT == PROD_DB:
        print("REFUSED: no usable rehearsal database (missing, unparsable, or the production one)"); sys.exit(8)
    shutil.copy2(".env", ".env.pre-rehearsal")
    lines = [("POSTGRES_DSN=" + stg) if l.startswith("POSTGRES_DSN=") else l for l in open(".env").read().splitlines()]
    open(".env.new", "w").write("\n".join(lines) + "\n"); os.chmod(".env.new", 0o600); os.replace(".env.new", ".env")
found = rendered()
if not found or any(v != EXPECT for v in found.values()):
    if MODE == "rehearse":
        restore()
    print("REFUSED: compose would connect %s to %s, expected %s" % (sorted(found or {}), sorted(set((found or {}).values())), EXPECT)); sys.exit(9)
r = sh("docker", "compose", "up", "-d", "--no-deps", "--pull", "never", "--wait", "--wait-timeout", WAIT_S, *SERVICES)
print("up_rc=%d" % r.returncode)
bad = []
for s in SERVICES:
    cid = sh("docker", "compose", "ps", "-q", s).stdout.strip()
    if not cid:
        continue
    for l in sh("docker", "inspect", cid, "--format", "{{range .Config.Env}}{{println .}}{{end}}").stdout.splitlines():
        if l.startswith("POSTGRES_DSN=") and dbname(l.split("=", 1)[1].strip().strip("'\"")) != EXPECT:
            bad.append(s)
if bad:
    sh("docker", "compose", "stop", *SERVICES)
    print("DB-MISMATCH after start: " + ",".join(bad)); sys.exit(10)
print(sh("docker", "compose", "ps", "--format", "{{.Service}}={{.State}}/{{.Health}}", *SERVICES).stdout)
"""


# ---------------------------------------------------------------------------------------------------------------------------------------------------- the machine
class Machine:
    """Everything that touches the outside world. Tests replace it; this is the real one."""

    def run(self, argv: list[str], timeout: float = 120, stdin: bytes | None = None) -> tuple[int, str, str]:
        try:
            p = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout)
            return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            return 124, "", f"timeout after {timeout}s"

    def tcp(self, host: str, port: int, timeout: float = 4) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def http_status(self, url: str, timeout: float = 8) -> int:
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 0

    def now(self) -> float:
        return time.time()

    def sleep(self, s: float) -> None:
        time.sleep(s)

    def mem_available_mb(self) -> int:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
        return 0

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def read_bytes(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def read_json(self, path: str, default):
        try:
            return json.load(open(path))
        except (OSError, ValueError):
            return default

    def write_json(self, path: str, obj) -> None:
        os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)

    def lock(self, wait_s: float):
        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        fh = open(LOCK_PATH, "w")
        end = time.time() + wait_s
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fh
            except OSError:
                if time.time() >= end:
                    raise Refusing(f"another standby-ctl run holds the lock (waited {int(wait_s)} s)")
                time.sleep(2)


class Ctl:
    def __init__(self, cfg: dict, m: Machine | None = None, log=None):
        self.cfg, self.m = cfg, m or Machine()
        self.vm = str(cfg["vmid"]); self.steps: list[dict] = []; self.degraded: list[str] = []; self.chosen: dict = {}; self.guest_diag = ""
        self.log = log or (lambda s: print(s, file=sys.stderr, flush=True))        # callers scrub what they log
        self.state_path = os.path.join(STATE_DIR, "state.json")

    # ---- plumbing -------------------------------------------------------------------------------------------------------------------------------------
    def step(self, name: str, fn, *a, soft: bool = False, **kw):
        t = self.m.now()
        try:
            r = fn(*a, **kw)
            self.steps.append({"step": name, "ok": True, "note": scrub(r) if isinstance(r, str) else "", "secs": round(self.m.now() - t, 1)})
            self.log(scrub(f"ok   {name} {r if isinstance(r, str) else ''}"))
            return r
        except (StepFailed, Refusing) as e:
            self.steps.append({"step": name, "ok": False, "note": scrub(str(e)), "secs": round(self.m.now() - t, 1), "soft": soft})
            self.log(scrub(f"FAIL {name}: {e}"))
            if soft:
                return None
            raise

    def qm(self, *args, timeout: float = 120, stdin: bytes | None = None):
        return self.m.run(["qm", *args], timeout=timeout, stdin=stdin)

    def vm_status(self) -> str:
        rc, out, _ = self.qm("status", self.vm)
        return out.split(":", 1)[1].strip() if rc == 0 and ":" in out else "unknown"

    def vm_config(self) -> dict:
        rc, out, err = self.qm("config", self.vm)
        if rc != 0:
            raise StepFailed(f"qm config {self.vm} failed: {err.strip()[:120]}")
        return parse_kv(out)

    def agent_up(self) -> bool:
        return self.qm("agent", self.vm, "ping", timeout=15)[0] == 0

    def guest(self, name: str, script: str, timeout: float = 60, stdin: bytes | None = None) -> tuple[int, str, str]:
        """Run a shell script inside the VM through the guest agent. The first line tags the script (the test double dispatches on it); `timeout` bounds the wait."""
        argv = ["guest", "exec", self.vm, "--timeout", str(int(timeout))]
        if stdin is not None:
            argv += ["--pass-stdin", "1"]
        argv += ["--", "/bin/bash", "-c", f"# standby-ctl:{name}\nset -o pipefail\n{script}"]
        rc, out, err = self.qm(*argv, timeout=timeout + 30, stdin=stdin)
        if rc != 0:
            return 125, "", f"qm guest exec failed: {(err or out).strip()[:200]}"
        try:
            j = json.loads(out)
        except ValueError:
            return 125, "", f"unparseable agent reply: {out[:120]!r}"
        if "exitcode" not in j:
            return 124, j.get("out-data", ""), "guest command did not finish in time"
        return int(j["exitcode"]), j.get("out-data", ""), j.get("err-data", "")

    def g(self, name: str, script: str, timeout: float = 60, ok_rc=(0,), stdin: bytes | None = None) -> str:
        rc, out, err = self.guest(name, script, timeout, stdin)
        if rc not in ok_rc:
            if rc == 124:
                self.capture_guest_diag(name)
            raise StepFailed(f"{name}: guest exit {rc}: {(err or out).strip()[-300:]}")
        return out

    def capture_guest_diag(self, step: str) -> None:
        """A guest step that ran out of time leaves the guest's own account of itself in the run record (`guest_diag`), once per run, taken before the teardown can
        add its own wait. Never raises: when the agent is wedged too, that is what gets recorded."""
        if self.guest_diag:
            return
        try:
            rc, out, err = self.guest("diag", GUEST_DIAG, self.cfg["timeouts"]["diag_s"])
            text = out if rc == 0 else f"unavailable: guest exit {rc}: {(err or out).strip()[-200:]}"
        except Exception as e:                       # a diagnostic must never replace the failure it explains
            text = f"unavailable: {type(e).__name__}"
        self.guest_diag = scrub(f"after step {step}:\n{text.strip()}")[-GUEST_DIAG_MAX:]
        self.log(self.guest_diag)

    def save(self, **kw) -> None:
        s = self.m.read_json(self.state_path, {})
        s.update(kw); self.m.write_json(self.state_path, s)

    # ---- host side checks ------------------------------------------------------------------------------------------------------------------------------
    def check_config(self) -> str:
        c = self.vm_config(); problems = []
        if c.get("name") != self.cfg["expect_name"]:
            problems.append(f"name is {c.get('name')!r}, expected {self.cfg['expect_name']!r}")
        if c.get("protection") != "1":
            problems.append("protection is not 1")
        if c.get("onboot", "0") != "0":
            problems.append("onboot is not 0")
        net0 = c.get("net0", "")
        if f"bridge={self.cfg['bridge']}" not in net0:
            problems.append(f"net0 is not on {self.cfg['bridge']}")
        if problems:
            raise StepFailed("standby VM config is not as expected: " + "; ".join(problems))
        return "link " + ("DOWN" if "link_down=1" in net0 else "UP")

    def fence(self) -> str:
        """The 0docker site must be unreachable from here while the control targets are reachable. UNKNOWN (control targets silent too) never counts as DOWN."""
        if self.m.exists(DISABLE_FILE):
            raise Refusing(f"{DISABLE_FILE} exists (host-side kill switch)")
        ctl = [f"{h}:{p}" for h, p in self.cfg["control_probes"] if self.m.tcp(h, p)]
        if not ctl:
            raise Refusing("no control target answers from this host: cannot tell whether the primary is down")
        up = [f"{h}:{p}" for h, p in self.cfg["primary_probes"] if self.m.tcp(h, p)]
        if up:
            raise Refusing("the primary answers from here (" + ", ".join(up) + "): two stacks on one database is the one thing this must never do")
        return f"primary silent on {len(self.cfg['primary_probes'])} probes, {len(ctl)} control targets answer"

    def check_memory(self, minimum: int) -> str:
        have = self.m.mem_available_mb()
        if have < minimum:
            raise StepFailed(f"host MemAvailable {have} MB < {minimum} MB")
        return f"{have} MB available"

    # ---- VM lifecycle ----------------------------------------------------------------------------------------------------------------------------------
    def set_link(self, up: bool) -> str:
        net0 = self.vm_config().get("net0", "")
        want = net0_with_link(net0, up)
        if want != net0:
            rc, _, err = self.qm("set", self.vm, "--net0", want)
            if rc != 0:
                raise StepFailed(f"qm set net0 failed: {err.strip()[:160]}")
        got = self.vm_config().get("net0", "")
        if ("link_down=1" in got) == up:
            raise StepFailed(f"link did not change: net0 is {got}")
        return "link " + ("UP" if up else "DOWN")

    def start_vm(self) -> str:
        if self.vm_status() != "running":
            if "link_down=1" not in self.vm_config().get("net0", ""):
                self.set_link(False)          # a stopped VM always boots with its link DOWN, whatever an earlier aborted run left behind
            rc, _, err = self.qm("start", self.vm, timeout=120)
            if rc != 0:
                raise StepFailed(f"qm start failed: {err.strip()[:160]}")
        end = self.m.now() + self.cfg["timeouts"]["agent_s"]
        while self.m.now() < end:
            if self.agent_up():
                return "running, agent answers"
            self.m.sleep(3)
        raise StepFailed(f"guest agent did not answer within {self.cfg['timeouts']['agent_s']} s")

    def stop_vm(self) -> str:
        if self.vm_status() == "stopped":
            return "already stopped"
        self.qm("shutdown", self.vm, "--timeout", str(self.cfg["timeouts"]["shutdown_s"]), timeout=self.cfg["timeouts"]["shutdown_s"] + 30)
        end = self.m.now() + 20
        while self.m.now() < end and self.vm_status() != "stopped":
            self.m.sleep(2)
        if self.vm_status() != "stopped":
            self.qm("stop", self.vm, timeout=60)
            self.m.sleep(2)
        if self.vm_status() != "stopped":
            raise StepFailed("the VM did not stop")
        return "stopped"

    # ---- guest checks and actions ----------------------------------------------------------------------------------------------------------------------
    def check_silent(self) -> str:
        out = self.g("silent", r"""
echo "tailscaled enabled=$(systemctl is-enabled tailscaled 2>&1 | head -1) active=$(systemctl is-active tailscaled 2>&1 | head -1)"
for u in scanopy-daemon fleet-hairpin-nat; do echo "$u enabled=$(systemctl is-enabled $u 2>&1 | head -1)"; done
echo "containers_running=$(docker ps -q | wc -l | tr -d " ")"
""", 45)
        problems = []
        ts = re.search(r"tailscaled enabled=(\S+) active=(\S+)", out)
        if not ts or ts.group(1) != "masked" or ts.group(2) == "active":
            problems.append(f"tailscaled is {ts.groups() if ts else 'unknown'}: a restored copy carries the production VM's tailnet identity")
        for u in ("scanopy-daemon", "fleet-hairpin-nat"):
            m = re.search(rf"{u} enabled=(\S+)", out)
            if m and m.group(1) == "enabled":
                problems.append(f"{u} is enabled")
        running = re.search(r"containers_running=(\d+)", out)
        if not running or running.group(1) != "0":
            problems.append(f"{running.group(1) if running else '?'} containers running at boot")
        if problems:
            raise StepFailed("the standby does not boot silent: " + "; ".join(problems))
        return "tailscaled masked, nothing running"

    def check_network(self) -> str:
        out = self.g("network", f"""
ip -4 -br addr show | awk '$1!="lo"{{print "addr="$3}}' | head -1
ping -c1 -W2 {self.cfg['gateway_ip']} >/dev/null 2>&1 && echo gw=ok || echo gw=FAIL
getent hosts ghcr.io >/dev/null 2>&1 && echo dns=ok || echo dns=FAIL
""", 40)
        if f"addr={self.cfg['guest_ip']}/" not in out or "gw=ok" not in out or "dns=ok" not in out:
            raise StepFailed("guest network is not usable: " + " ".join(out.split()))
        return f"{self.cfg['guest_ip']} reaches its gateway and resolves names"

    def db_probe(self) -> str:
        script = f"""
cd {self.cfg['compose_dir']}
python3 - <<'PY'
import os, subprocess, sys
dsn = ""
for line in open(".env"):
    if line.startswith("POSTGRES_DSN="):
        dsn = line.split("=", 1)[1].strip().strip("'\\"")
        break
if not dsn:
    print("no POSTGRES_DSN"); sys.exit(2)
sql = "select current_user, current_database(), (select ssl from pg_stat_ssl where pid=pg_backend_pid()), (select count(*) from information_schema.tables where table_schema='public'), pg_is_in_recovery()"
cmd = ["docker", "run", "--rm", "-i", "--network", "host", "-e", "PGCONN", "-v", "domainscope-data:/data:ro", "postgres:16-alpine", "sh", "-c", 'psql "$PGCONN" -At -F "|"']
r = subprocess.run(cmd, input=sql, env=dict(os.environ, PGCONN=dsn), capture_output=True, text=True, timeout=75)
if r.returncode == 0:
    print("probe=" + (r.stdout.strip().splitlines() or ["none"])[-1]); sys.exit(0)
print("probe-failed: " + ((r.stderr.strip().splitlines() or ["?"])[-1][-160:]).replace(dsn, "<dsn>")); sys.exit(3)
PY
"""
        out = self.g("db_probe", script, self.cfg["timeouts"]["db_probe_s"])
        m = re.search(r"probe=([^|]*)\|([^|]*)\|([^|]*)\|(\d+)\|(\w)", out)
        if not m:
            raise StepFailed("database probe gave no answer: " + out.strip()[-160:])
        user, db, tls, tables, rec = m.groups()
        if tls != "t" or rec != "f" or int(tables) < 100:
            raise StepFailed(f"database probe is not what production looks like: user={user} tls={tls} tables={tables} replica={rec}")
        return f"{user}@{db} tls on, {tables} tables, primary"

    def pg_cert_source(self):
        """The pinned database certificate kept on this host: (its config, its bytes), or (None, None) when the feature is off. Every value that reaches a guest script is checked here,
        and the bytes must hash to the recorded sha256 and be exactly one public certificate: nothing else is ever sent into the guest."""
        c = self.cfg.get("pg_cert") or {}
        if not c:
            return None, None
        for key, pat in (("src", r"/[A-Za-z0-9._/-]+"), ("volume", r"[A-Za-z0-9_.-]+"), ("dest", r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*"), ("sha256", r"[0-9a-f]{64}")):
            if not re.fullmatch(pat, str(c.get(key, ""))):
                raise StepFailed(f"unsafe or missing value in pg_cert.{key}")
        if ".." in c["dest"].split("/"):
            raise StepFailed("unsafe value in pg_cert.dest")
        try:
            data = self.m.read_bytes(c["src"])
        except OSError as e:
            raise StepFailed(f"the database certificate {c['src']} cannot be read: {e.strerror or e}")
        if hashlib.sha256(data).hexdigest() != c["sha256"]:
            raise StepFailed(f"the database certificate on this host is not the pinned one (sha256 differs from the recorded {c['sha256'][:12]}...): refusing to install it")
        if data.count(b"-----BEGIN CERTIFICATE-----") != 1 or b"PRIVATE KEY" in data:
            raise StepFailed("the database certificate file is not exactly one public certificate")
        return c, data

    def check_pg_cert_source(self) -> str:
        c, _ = self.pg_cert_source()
        return "not configured" if c is None else f"{c['src']} matches its pin ({c['sha256'][:12]}...)"

    def install_pg_cert(self) -> str:
        """Put the pinned certificate where the DSN's sslrootcert (/data/pg-tls/...) points: the guest's data volume. Idempotent; runs before the database probe."""
        c, data = self.pg_cert_source()
        if c is None:
            return "not configured"
        script = (PG_CERT_GUEST.replace("@R@", self.cfg["guest_root"]).replace("@VOL@", c["volume"]).replace("@DEST@", c["dest"]).replace("@WANT@", c["sha256"]))
        out = self.g("pgcert", script, 60, stdin=data)
        word = out.strip().splitlines()[-1] if out.strip() else ""
        if word not in ("installed", "unchanged"):
            raise StepFailed("database certificate was not installed in the guest: " + out.strip()[-160:])
        return f"{c['dest']} {word} in volume {c['volume']}"

    def apply_bundle(self, raw: bytes) -> str:
        parsed = read_bundle(raw, self.cfg)
        new_env, report = rewrite_env(parsed["env"], self.cfg["env_overrides"])
        new_staging = None
        hmap = self.cfg["env_overrides"].get("dsn_host_map") or {}
        if hmap and parsed.get("staging_env_text") is not None:
            staging_text, srep = rewrite_env(parsed["staging_env_text"], {"dsn_host_map": hmap})
            if srep.get("dsn_host_mapped"):                      # the staging .env is rewritten only when its DSN host is mapped: otherwise it goes in byte for byte
                new_staging = staging_text; report["staging_dsn_host_mapped"] = srep["dsn_host_mapped"]
        payload = repack_bundle(parsed, new_env, new_staging)
        cd, sd = self.cfg["compose_dir"], self.cfg["staging_dir"]
        R = self.cfg["guest_root"]
        out = self.g("bundle", f"""
set -e
R='{R}'
d=$(mktemp -d "$R/var/tmp/standby-bundle.XXXXXX"); trap 'rm -rf "$d"' EXIT
if [ "$(id -u)" = 0 ]; then tar -xzf - -C "$d" --same-owner; else tar -xzf - -C "$d"; fi          # root in the guest (the agent): owners restored; the non-root branch exists for the tests
ts=$(date -u +%Y%m%dT%H%M%SZ); b="$R/var/lib/standby-bundle/backup-$ts"; mkdir -p "$b"
cp -a "$R{cd}"/.env "$R{cd}"/.release.env "$R{cd}"/docker-compose.yml "$b"/ 2>/dev/null || true
for f in .env docker-compose.yml; do cp -a "$d{cd}/$f" "$R{cd}/$f.new" && mv -f "$R{cd}/$f.new" "$R{cd}/$f"; done
if [ -f "$d{sd}/.env" ]; then cp -a "$R{sd}"/.env "$b"/staging.env 2>/dev/null || true; cp -a "$d{sd}/.env" "$R{sd}/.env.new" && mv -f "$R{sd}/.env.new" "$R{sd}/.env"; fi
install -d -m 700 "$R/etc/domainscope-secrets"; cp -a "$d/etc/domainscope-secrets/." "$R/etc/domainscope-secrets/"
install -d -m 755 "$R/opt/fleet-secrets/graph-writers"; cp -a "$d/opt/fleet-secrets/graph-writers/." "$R/opt/fleet-secrets/graph-writers/"
if ! (cd "$R{cd}" && docker compose config -q 2>"$d/compose-check.txt"); then
  cp -a "$b"/.env "$b"/docker-compose.yml "$R{cd}"/ 2>/dev/null || true; echo "compose-invalid: $(head -c 300 "$d/compose-check.txt")"; exit 7
fi
ls -1dt "$R"/var/lib/standby-bundle/backup-* | tail -n +4 | xargs -r rm -rf
echo applied
""", 90, stdin=payload)
        if "applied" not in out:
            raise StepFailed("bundle was not applied: " + out.strip()[-200:])
        tags = parsed["tags"]
        self.save(bundle={"applied_ts": int(self.m.now()), "tags": tags, "counts": parsed["counts"], "overrides": report})
        return f"{parsed['counts']['env_vars']} vars, {parsed['counts']['secret_files']} token files, tags {tags.get('API_IMAGE_TAG')}/{tags.get('FRONTEND_IMAGE_TAG')}; overrides {json.dumps(report)}"

    def ensure_disk(self) -> str:
        need = self.cfg["min_free_disk_gb"]
        out = self.g("disk", f"""
free() {{ df -BG --output=avail / | tail -1 | tr -dc 0-9; }}
if [ "$(free)" -lt {need} ]; then docker image prune -f >/dev/null 2>&1; fi
if [ "$(free)" -lt {need} ]; then docker image prune -af >/dev/null 2>&1; docker builder prune -af >/dev/null 2>&1; fi
echo "free_after=$(free)"
""", 240)
        m = re.search(r"free_after=(\d+)", out)
        if not m or int(m.group(1)) < need:
            raise StepFailed(f"guest disk has {m.group(1) if m else '?'} GB free after pruning (need {need})")
        return f"{m.group(1)} GB free"

    def resolve_images(self, write_back: bool) -> str:
        """For every image variable: the wanted tag if it is on disk or can be pulled; else the NEWEST tag on disk (recorded as degraded). With write_back the choice goes
        into .env and .release.env so compose runs exactly what was resolved."""
        spec = json.dumps(self.cfg["images"])
        cd = self.cfg["compose_dir"]
        out = self.g("images", f"""
cd {cd}
SPEC='{spec}' WRITE={1 if write_back else 0} python3 - <<'PY'
import json, os, re, subprocess, sys
spec = json.loads(os.environ["SPEC"]); write = os.environ["WRITE"] == "1"
env = open(".env").read().splitlines()
want = {{}}
for l in env:
    m = re.match(r"^(\\w+)=(.*)$", l)
    if m and m.group(1) in spec:
        want[m.group(1)] = m.group(2).strip().strip("'\\"")
def sh(*a, t=400):
    return subprocess.run(a, capture_output=True, text=True, timeout=t)
chosen = {{}}
for var, repo in spec.items():
    tag = want.get(var, "")
    local = sh("docker", "image", "inspect", f"{{repo}}:{{tag}}").returncode == 0 if tag else False
    status = "have"
    if not local and tag:
        status = "pulled" if sh("docker", "pull", "-q", f"{{repo}}:{{tag}}").returncode == 0 else "pull-failed"
    if status == "pull-failed" or not tag:
        rows = [l.split("|") for l in sh("docker", "image", "ls", repo, "--format", "{{{{.Tag}}}}|{{{{.CreatedAt}}}}").stdout.splitlines() if l and not l.startswith("<none>")]
        rows = [r for r in rows if len(r) == 2 and r[0] != "<none>"]
        rows.sort(key=lambda r: r[1], reverse=True)
        if not rows:
            print(f"NOIMAGE {{var}}"); sys.exit(4)
        status = f"fallback:{{tag}}"; tag = rows[0][0]
    chosen[var] = tag
    print(f"IMG {{var}}={{tag}} {{status}}")
if write:
    out = []
    for l in env:
        m = re.match(r"^(\\w+)=", l)
        out.append(f"{{m.group(1)}}={{chosen[m.group(1)]}}" if m and m.group(1) in chosen else l)
    open(".env.new", "w").write("\\n".join(out) + "\\n"); os.chmod(".env.new", 0o600); os.replace(".env.new", ".env")
    open(".release.env.new", "w").write("".join(f"{{k}}={{v}}\\n" for k, v in chosen.items())); os.chmod(".release.env.new", 0o600); os.replace(".release.env.new", ".release.env")
PY
""", self.cfg["timeouts"]["pull_s"], ok_rc=(0, 4))
        if "NOIMAGE" in out:
            raise StepFailed("no image at all for " + re.search(r"NOIMAGE (\S+)", out).group(1) + " on the standby (and none can be pulled)")
        notes = []; self.chosen = {}
        for var, tag, status in re.findall(r"IMG (\w+)=(\S+) (\S+)", out):
            self.chosen[var] = tag
            if status.startswith("fallback:"):
                self.degraded.append(f"{var}: wanted {status.split(':', 1)[1] or '(none)'}, running {tag}")
                notes.append(f"{var}={tag} (FALLBACK from {status.split(':', 1)[1]})")
            else:
                notes.append(f"{var}={tag} ({status})")
        return "; ".join(notes)

    def helpers_up(self) -> str:
        h = ' '.join(self.cfg['helpers'])
        # restart=no is the resting state; while the standby is up the helpers must come back with the VM like the stack does (the teardown makes everything silent again)
        self.g("helpers", f"docker update --restart=unless-stopped {h} >/dev/null && docker start {h} >/dev/null && echo started", 90)
        return "helpers started"

    def stack_up(self, mode: str) -> str:
        """Production api + frontend on the real ports. mode 'activate': against the production database. mode 'rehearse': against the STAGING database, by swapping POSTGRES_DSN in
        the production .env (the compose file reads it through `env_file`, so a shell variable would be silently ignored) and restoring it in the teardown. Either way the RENDERED
        compose config is checked before anything starts and the running containers after: a mismatch refuses to start, or stops what started."""
        cfg = self.cfg; t = cfg["timeouts"]["up_s"]
        expect = cfg["prod_dbname"] if mode == "activate" else cfg["rehearsal_dbname"]
        for v in (expect, cfg["prod_dbname"], cfg["compose_dir"], cfg["staging_dir"], *cfg["prod_services"]):
            if not re.fullmatch(r"[A-Za-z0-9._/-]+", v):
                raise StepFailed(f"unsafe value in the configuration: {v!r}")
        if mode == "rehearse" and expect == cfg["prod_dbname"]:
            raise StepFailed("the rehearsal database is configured to be the production database")
        script = f"""
MODE={mode} EXPECT_DB={expect} PROD_DB={cfg['prod_dbname']} COMPOSE_DIR={cfg['compose_dir']} STAGING_ENV={cfg['staging_dir']}/.env SERVICES='{' '.join(cfg['prod_services'])}' WAIT_S={t - 40} python3 - <<'PY'
{STACK_UP_PY}
PY
"""
        out = self.g("stack_up", script, t)
        states = dict(re.findall(r"^(\w+)=(\S+)$", out, re.M))
        bad = [f"{s}={states.get(s, 'missing')}" for s in cfg["prod_services"] if not states.get(s, "").startswith("running")]
        if bad:
            raise StepFailed("stack_up: not running: " + ", ".join(bad))
        return ", ".join(f"{s} {states[s]}" for s in cfg["prod_services"]) + f" on {expect}"

    def health(self) -> str:
        p = self.cfg["ports"]; ip = self.cfg["guest_ip"]
        end = self.m.now() + self.cfg["timeouts"]["health_s"]; last = {}
        while True:
            last = {"api": self.m.http_status(f"http://{ip}:{p['api']}{self.cfg['health_paths']['api']}"), "frontend": self.m.http_status(f"http://{ip}:{p['frontend']}{self.cfg['health_paths']['frontend']}")}
            if all(v == 200 for v in last.values()):
                return f"api {last['api']}, frontend {last['frontend']} (from the hypervisor, over {self.cfg['bridge']})"
            if self.m.now() >= end:
                raise StepFailed(f"health not 200 within {self.cfg['timeouts']['health_s']} s: {last}")
            self.m.sleep(5)

    def hold(self) -> str:
        self.m.sleep(self.cfg["rehearse_hold_s"])
        return f"stack kept up {self.cfg['rehearse_hold_s']} s for the edge path probe"

    def teardown_guest(self) -> str:
        """Stop everything the guest runs and make the restart policies silent again. Idempotent; used by rehearse (always) and deactivate."""
        cd = self.cfg["compose_dir"]
        out = self.g("teardown", f"""
(cd {cd} && docker compose stop >/dev/null 2>&1 || true)
docker stop {' '.join(self.cfg['helpers'])} >/dev/null 2>&1 || true
docker ps -aq | xargs -r docker update --restart=no >/dev/null 2>&1 || true
docker ps -q | xargs -r docker stop >/dev/null 2>&1 || true
echo "containers_running=$(docker ps -q | wc -l | tr -d " ")"
COMPOSE_DIR={cd} python3 - <<'PY'
import os, re, urllib.parse
d = os.environ["COMPOSE_DIR"]
if os.path.exists(d + "/.env.pre-rehearsal"):
    os.replace(d + "/.env.pre-rehearsal", d + "/.env")          # a rehearsal swapped the DSN: the production .env comes back
dsn = ""
for l in open(d + "/.env"):
    if l.startswith("POSTGRES_DSN="):
        dsn = l.split("=", 1)[1].strip().strip("'\\"")
db = urllib.parse.urlparse(dsn).path.lstrip("/") if "://" in dsn else (re.search(r"dbname=(\\S+)", dsn) or [None, ""])[1]
print("env_db=" + db)
PY
""", 240)
        if "containers_running=0" not in out:
            raise StepFailed("containers still running after the teardown: " + out.strip()[-120:])
        m = re.search(r"env_db=(\S*)", out)
        if not m or m.group(1) != self.cfg["prod_dbname"]:
            raise StepFailed(f"the standby's .env does not point at the production database after the teardown (database {m.group(1) if m else '?'})")
        return "all containers stopped, restart=no, .env points at production"

    def check_resting(self) -> str:
        c = self.vm_config(); problems = []
        if self.vm_status() != "stopped":
            problems.append("VM is not stopped")
        if "link_down=1" not in c.get("net0", ""):
            problems.append("link is not down")
        if c.get("onboot", "0") != "0":
            problems.append("onboot is not 0")
        if c.get("protection") != "1":
            problems.append("protection is not 1")
        if problems:
            raise StepFailed("not in the resting state: " + "; ".join(problems))
        return "stopped, link down, onboot 0, protected"

    def stack_running(self) -> bool:
        """Is the production stack already up (a re-run of activate)? Its containers would fail the silent check, which is right for a fresh boot only."""
        if self.vm_status() != "running" or not self.agent_up():
            return False
        rc, out, _ = self.guest("probe_stack", "docker ps --format '{{.Names}}' | grep -c '^domainscope-api$'", 30)
        return rc == 0 and out.strip() == "1"

    # ---- verbs -----------------------------------------------------------------------------------------------------------------------------------------
    def verb_status(self) -> dict:
        info = {"vm": self.vm_status(), "state": self.m.read_json(self.state_path, {})}
        try:
            c = self.vm_config()
            info["config"] = {k: c.get(k) for k in ("name", "protection", "onboot", "memory", "balloon")}
            info["link"] = "down" if "link_down=1" in c.get("net0", "") else "up"
        except StepFailed as e:
            info["config_error"] = str(e)
        info["disabled"] = self.m.exists(DISABLE_FILE); info["mem_available_mb"] = self.m.mem_available_mb()
        if info["vm"] == "running" and self.agent_up():
            rc, out, _ = self.guest("status", "echo containers=$(docker ps --format '{{.Names}}' | tr '\\n' ' ')", 40)
            info["guest_containers"] = out.split("containers=", 1)[-1].strip() if rc == 0 else "unknown"
        return info

    def verb_check(self, bundle: bytes | None) -> dict:
        result = {"verb": "check", "ok": False}
        self.step("config", self.check_config)
        if self.vm_status() == "stopped":
            self.step("resting state", self.check_resting)
        else:
            self.step("VM state", lambda: f"VM is {self.vm_status()} (phase {self.m.read_json(self.state_path, {}).get('phase', '?')}): not in the resting state, which is expected only during an activation")
        if bundle:
            def summary():
                parsed = read_bundle(bundle, self.cfg)
                _, rep = rewrite_env(parsed["env"], self.cfg["env_overrides"])
                result["bundle"] = {"counts": parsed["counts"], "tags": parsed["tags"], "overrides": rep}
                return f"{parsed['counts']['env_vars']} vars, {parsed['counts']['secret_files']} token files, tags {parsed['tags'].get('API_IMAGE_TAG')}/{parsed['tags'].get('FRONTEND_IMAGE_TAG')}"
            self.step("bundle parses", summary)
        self.step("database certificate (this host's copy)", self.check_pg_cert_source)
        result["ok"] = True
        return result

    def verb_rehearse(self, bundle: bytes | None) -> dict:
        t0 = self.m.now(); result = {"verb": "rehearse", "ok": False}
        self.step("config", self.check_config)
        if self.vm_status() != "stopped":
            raise Skipped({"verb": "rehearse", "ok": True, "skipped": True, "note": f"VM is {self.vm_status()}: not touching it (an activation or a manual session owns it)"})
        try:
            self.step("memory", self.check_memory, self.cfg["min_available_mb_rehearse"])
        except StepFailed as e:
            raise Skipped({"verb": "rehearse", "ok": True, "skipped": True, "note": f"not rehearsing: {e}"})
        self.save(phase="REHEARSING", since=int(t0))
        try:
            self.step("start (link down)", self.start_vm)
            self.step("silent", self.check_silent)
            if bundle:
                self.step("bundle", self.apply_bundle, bundle)
            self.step("database certificate", self.install_pg_cert)
            self.step("link up", self.set_link, True)
            self.step("network", self.check_network)
            self.step("database (read-only)", self.db_probe)
            self.step("disk", self.ensure_disk)
            self.step("image tags", self.resolve_images, True)
            self.step("helpers", self.helpers_up)
            self.step("production stack on the rehearsal database", self.stack_up, "rehearse")
            self.step("health", self.health)
            self.step("settle", self.hold)
            result["ok"] = True
        except (StepFailed, Refusing) as e:
            result["error"] = scrub(str(e))
        finally:
            if self.agent_up():
                self.step("teardown", self.teardown_guest, soft=True)
            self.step("link down", self.set_link, False, soft=True)
            self.step("power off", self.stop_vm, soft=True)
            try:
                self.step("resting state", self.check_resting)
            except StepFailed as e:
                result["ok"] = False; result["cleanup_failed"] = True; result.setdefault("error", scrub(str(e)))
        if result["ok"]:
            result["ok"] = not any(not s["ok"] and not s.get("soft") for s in self.steps)
        if self.degraded:
            result["degraded"] = self.degraded
        if self.guest_diag:
            result["guest_diag"] = self.guest_diag
        result["seconds"] = round(self.m.now() - t0, 1)
        self.save(phase="FAILED" if result.get("cleanup_failed") else "RESTING",
                  last_rehearsal={"ts": int(self.m.now()), "ok": result["ok"], "seconds": result["seconds"], "error": result.get("error", ""), "degraded": self.degraded})
        return result

    def verb_activate(self, bundle: bytes | None) -> dict:
        t0 = self.m.now(); result = {"verb": "activate", "ok": False}
        self.step("config", self.check_config)
        self.step("fence", self.fence)
        self.step("memory", self.check_memory, self.cfg["min_available_mb_activate"])
        self.save(phase="ACTIVATING", since=int(t0))
        try:
            self.step("start (link down until checked)", self.start_vm)
            if not self.stack_running():
                self.step("silent", self.check_silent)
            if bundle:
                if self.step("bundle", self.apply_bundle, bundle, soft=True) is None:
                    result["bundle_applied"] = False            # an unusable bundle must not stop the failover: the standby runs on its own (older) config and says so
                else:
                    result["bundle_applied"] = True
            self.step("database certificate", self.install_pg_cert, soft=True)       # a failure here must not stop a failover by itself: the database probe that follows decides
            self.step("link up", self.set_link, True)
            self.step("network", self.check_network)
            self.step("database (read-only)", self.db_probe)
            self.step("disk", self.ensure_disk)
            self.step("image tags", self.resolve_images, True)
            self.step("helpers", self.helpers_up)
            self.step("production api + frontend", self.stack_up, "activate")
            self.step("health", self.health)
            result["ok"] = True
        except (StepFailed, Refusing) as e:
            result["error"] = scrub(str(e))
        if self.degraded:
            result["degraded"] = self.degraded
        if self.guest_diag:
            result["guest_diag"] = self.guest_diag
        result["seconds"] = round(self.m.now() - t0, 1)
        self.save(phase="ACTIVE" if result["ok"] else "ACTIVATION_FAILED", **({"active_since": int(self.m.now())} if result["ok"] else {}),
                  last_activation={"ts": int(self.m.now()), "ok": result["ok"], "seconds": result["seconds"], "error": result.get("error", ""), "degraded": self.degraded})
        return result

    def verb_start_cron(self) -> dict:
        st = self.m.read_json(self.state_path, {})
        if st.get("phase") != "ACTIVE":
            raise Refusing(f"the standby is not ACTIVE (phase {st.get('phase')!r})")
        mins = (self.m.now() - st.get("active_since", self.m.now())) / 60
        if mins < self.cfg["cron_min_active_minutes"]:
            raise Refusing(f"active for {mins:.0f} min, cron needs {self.cfg['cron_min_active_minutes']}: the primary may still come back")
        self.step("fence", self.fence)

        def start():
            self.g("cron", f"cd {self.cfg['compose_dir']} && docker compose up -d --no-deps --pull never {self.cfg['cron_service']} && echo started", 120)
            return "cron started"
        self.step("cron", start)
        self.save(cron_started=int(self.m.now()))
        return {"verb": "start-cron", "ok": True}

    def verb_deactivate(self) -> dict:
        result = {"verb": "deactivate", "ok": False}
        self.step("config", self.check_config)
        try:
            if self.agent_up():
                self.step("teardown", self.teardown_guest)
            self.step("link down", self.set_link, False)
            self.step("power off", self.stop_vm)
            self.step("resting state", self.check_resting)
            result["ok"] = True
        except (StepFailed, Refusing) as e:
            result["error"] = scrub(str(e))
        self.save(phase="RESTING" if result["ok"] else "DEACTIVATION_FAILED", cron_started=None, active_since=None)
        return result


# ---------------------------------------------------------------------------------------------------------------------------------------------------- CLI
def main(argv=None, machine: Machine | None = None, config: dict | None = None, stdin=None) -> int:
    ap = argparse.ArgumentParser(description="DomainScope standby VM controller (see the module docstring)")
    ap.add_argument("verb", choices=["status", "check", "rehearse", "activate", "start-cron", "deactivate"])
    ap.add_argument("--bundle", action="store_true", help="a config bundle (tar.gz) follows on stdin")
    args = ap.parse_args(argv)
    cfg = config or load_config()
    m = machine or Machine()
    bundle = (stdin or sys.stdin.buffer).read(cfg["bundle_max_bytes"] + 1) if args.bundle else None
    ctl = Ctl(cfg, m)
    code, result = 0, {"verb": args.verb, "ok": False}
    try:
        if args.verb not in ("status", "check"):
            _lock = m.lock(cfg["timeouts"]["lock_wait_s"] if args.verb == "activate" else 5)   # held until the process exits
        if args.verb == "status":
            result = {"verb": "status", "ok": True, **ctl.verb_status()}
        elif args.verb == "check":
            result = ctl.verb_check(bundle); code = 0 if result["ok"] else 3
        elif args.verb == "rehearse":
            result = ctl.verb_rehearse(bundle); code = 0 if result["ok"] else 5
        elif args.verb == "activate":
            result = ctl.verb_activate(bundle); code = 0 if result["ok"] else 5
        elif args.verb == "start-cron":
            result = ctl.verb_start_cron()
        elif args.verb == "deactivate":
            result = ctl.verb_deactivate(); code = 0 if result["ok"] else 5
    except Skipped as e:
        result, code = e.result, 6
    except Refusing as e:
        result, code = {"verb": args.verb, "ok": False, "refusing": scrub(str(e))}, 4
    except StepFailed as e:
        result, code = {"verb": args.verb, "ok": False, "error": scrub(str(e))}, 3
    result["steps"] = ctl.steps
    result["exit_code"] = code
    text = json.dumps(result, indent=1)
    if args.verb != "status":
        try:
            os.makedirs(LOG_DIR, mode=0o750, exist_ok=True)
            with open(os.path.join(LOG_DIR, time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(m.now())) + f"-{args.verb}.json"), "w") as f:
                f.write(text)                                          # already scrubbed: notes and errors never carry values
        except OSError:
            pass
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
