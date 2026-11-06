#!/usr/bin/env python3
"""hostconf: host-local OS configuration kept in git, with a drift check and a reload-only apply.

Some configuration lives on one host and nowhere else: the systemd drop-in that makes nginx restart after an OOM kill, the sysctl file that
raises the thread limit of a VM whose memory is hot-plugged, a Postgres conf.d file. Nobody can review it, a rebuilt VM loses it, and a
hand edit changes it without a trace. config/hostconf/hostconf.yaml lists, per host, the files that must exist (destination, source file in
config/hostconf/files/, owner and mode, why it exists) and the effective setting each one must produce (`systemctl show`, `sysctl -n`,
Postgres `SHOW`). This tool compares the live hosts with that file and, on request, writes the files.

  hostconf.py check                                    offline: the manifest and the files are valid (CI runs this)
  hostconf.py drift [--host H ... | --all] [--diff]    live files and settings against the repo, read-only (--all also lists the guests of every hypervisor)
                    [--inventory]
                    [--file ID ...] [--textfile-dir D] [--jobs N]
  hostconf.py apply --host H ... [--file ID ...] [--yes]   plan; with --yes write, reload, verify, roll back if a setting is not in effect
  hostconf.py adopt --host H --file ID                 copy the live file into config/hostconf/files byte for byte (the first import)

The manifest also carries a fleet-wide `baseline`: floors that every host listed in it must meet (today kernel.threads-max >= 131072, the limit
whose boot-time default is about 7000 on VMs with hot-plugged memory). `drift` checks it on every host, including those that carry no file (a host that
is already above the floor needs none: a fixed file would lower it), and says which catalog file fixes a host that is below.

Every machine belongs in the manifest. `inventory` names the hypervisors; `drift --all` lists their VMs and containers and flags any that is neither a host
(`vm: {hypervisor, id}`) nor exempt with a reason, so a machine created by hand is noticed. A VM no operator can ssh into (a host with `vm` and no `ssh`) is reached through its
hypervisor's guest agent (`qm guest exec`), the same way.

What it can touch is fixed in the code, not in the manifest: systemd drop-ins (/etc/systemd/system/<unit>.d/*.conf, then `systemctl
daemon-reload`), sysctl files (/etc/sysctl.d/NN-*.conf, then `sysctl -p`) and Postgres conf.d files (then `pg_ctlcluster reload`). It never
restarts or stops anything, never touches a file outside those patterns, and refuses a file that looks like it holds a credential.
A file that differs on the host is kept as <file>.bak-hostconf-<UTC time> before it is replaced; `apply` shows the difference first and
changes nothing without --yes.

Exit codes: 0 in sync / ok, 1 check findings or an apply refused before any change, 2 drift (or a setting not in effect after the apply),
3 a host could not be looked at, 4 an apply failed AND its rollback could not be verified (a human must look now), 5 an apply failed and was
rolled back and verified. Python 3 standard library plus PyYAML.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import difflib
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

try:
    import yaml
except ImportError:  # pragma: no cover - the CI step installs it
    yaml = None

REPO = Path(__file__).resolve().parents[1]
HOSTCONF_DIR = REPO / "config" / "hostconf"
MANIFEST = HOSTCONF_DIR / "hostconf.yaml"
FILES_DIR = HOSTCONF_DIR / "files"
DEFAULT_TEXTFILE_DIR = "/var/lib/prometheus-node-exporter/textfile"
MAX_FILE_BYTES = 16 * 1024
MODES = ("0644", "0640", "0600")
UNIT_TYPES = "service|socket|timer|path|mount|automount|swap|slice|scope|target|device"

# The only places this tool writes. Checked here (offline) and again by the script that runs on the host.
KIND_PATTERNS: dict[str, str] = {
    "systemd_dropin": rf"^/etc/systemd/system/[A-Za-z0-9@_.:\\-]+\.(?:{UNIT_TYPES})\.d/[A-Za-z0-9_.-]+\.conf$",
    "sysctl": r"^/etc/sysctl\.d/[0-9]{2}-[A-Za-z0-9_.-]+\.conf$",
    "pg_conf_d": r"^/etc/postgresql/[0-9]+/[A-Za-z0-9_.-]+/conf\.d/[0-9]{2}-[A-Za-z0-9_.-]+\.conf$",
}
EXPECT_KIND = {"systemd_dropin": "systemd", "sysctl": "sysctl", "pg_conf_d": "pg_setting"}

# A file that looks like it carries a credential is refused, in the repo and on the host. False positives are cheap (reword the comment).
# LoadCredential= / ImportCredential= name a file, not the secret, and are allowed; SetCredential= carries the value and is not.
SECRET_RE = (
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|bearer|private[ _-]?key|(?<!load)(?<!import)credential)s?\s*[=:]\s*\S"
    r"|[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
    r"|BEGIN [A-Z ]*PRIVATE KEY"
    r"|\b(?:tskey-[A-Za-z0-9-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})"
)
SECTION_RE = re.compile(r"^\[(Unit|Service|Install|Socket|Timer|Path|Mount|Automount|Swap|Slice|Scope)\]$")
SYSTEMD_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)=")
SYSCTL_LINE_RE = re.compile(r"^([a-z0-9_]+(?:\.[a-z0-9_*/-]+)+)\s*=\s*(\S.*)$")
PG_LINE_RE = re.compile(r"^([a-z_][a-z0-9_.]*)\s*=\s*(\S.*)$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
SSH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@:-]*$")
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ManifestError(Exception):
    """The manifest, a file it names, or a live reading is not usable."""


# ───────────────────────────── files and kinds ─────────────────────────────


def kind_of(dest: str) -> str | None:
    """The kind of a destination path, or None when this tool must not write there."""
    if dest != str(Path(dest)) or ".." in dest.split("/"):
        return None
    for kind, pattern in KIND_PATTERNS.items():
        if re.match(pattern, dest):
            return kind
    return None


def _data_lines(text: str) -> list[tuple[int, str]]:
    return [(n, line) for n, line in enumerate(text.splitlines(), 1) if line.strip() and not line.lstrip().startswith(("#", ";"))]


def parse_settings(kind: str, text: str) -> dict[str, str]:
    """key -> value of the settings in a sysctl or Postgres file (the last one wins, as in the real parsers)."""
    rx = SYSCTL_LINE_RE if kind == "sysctl" else PG_LINE_RE
    out: dict[str, str] = {}
    for _, line in _data_lines(text):
        m = rx.match(line.strip())
        if m:
            out[m.group(1)] = re.sub(r"\s+#.*$", "", m.group(2)).strip().strip("'\"") if kind == "pg_conf_d" else " ".join(m.group(2).split())
    return out


def content_problems(kind: str, data: bytes) -> list[str]:
    """Why this content must not be written: encoding, size, a credential, or a shape the target would not parse."""
    if len(data) > MAX_FILE_BYTES:
        return [f"larger than {MAX_FILE_BYTES} bytes"]
    if b"\x00" in data or b"\r" in data:
        return ["contains NUL or CR bytes"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["not UTF-8"]
    problems: list[str] = []
    if not text.endswith("\n"):
        problems.append("does not end with a newline")
    if re.search(SECRET_RE, text):
        problems.append("looks like it holds a credential (a password, token, key or URL with a password)")
    if problems:
        return problems
    lines = _data_lines(text)
    if not lines:
        return ["has no setting, only comments"]
    if kind == "systemd_dropin":
        section = False
        continuation = False
        for n, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if continuation:
                continuation = raw.rstrip().endswith("\\")
                continue
            if not line or line.startswith(("#", ";")):
                continue
            if SECTION_RE.match(line):
                section = True
            elif not section:
                problems.append(f"line {n}: a setting before any [Section]")
            elif not SYSTEMD_KEY_RE.match(line):
                problems.append(f"line {n}: not a Key=Value line or a [Section]")
            continuation = raw.rstrip().endswith("\\")
        if not any(SYSTEMD_KEY_RE.match(line.strip()) for _, line in lines):
            problems.append("has no Key=Value setting")
    else:
        rx = SYSCTL_LINE_RE if kind == "sysctl" else PG_LINE_RE
        seen: set[str] = set()
        for n, line in lines:
            m = rx.match(line.strip())
            if not m:
                problems.append(f"line {n}: not a 'name = value' line")
            elif m.group(1) in seen:
                problems.append(f"line {n}: {m.group(1)} is set twice in one file")
            else:
                seen.add(m.group(1))
    return problems


def systemd_unit_of(dest: str) -> str:
    return dest.split("/")[-2][: -len(".d")]


def pg_cluster_of(dest: str) -> str:
    parts = dest.split("/")
    return f"{parts[3]}/{parts[4]}"


# ───────────────────────────── manifest ─────────────────────────────


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    if yaml is None:
        raise ManifestError("PyYAML is not installed")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: the top level must be a mapping")
    return data


def _expect_problems(fid: str, kind: str, dest: str, expect: Any, content: str) -> list[str]:
    if not isinstance(expect, list) or not expect:
        return [f"{fid}: `expect` must list at least one setting that proves the file is in effect"]
    out: list[str] = []
    settings = parse_settings(kind, content) if kind in ("sysctl", "pg_conf_d") else {}
    for i, x in enumerate(expect):
        where = f"{fid}: expect[{i}]"
        if not isinstance(x, dict):
            out.append(f"{where} must be a mapping")
            continue
        typ = [k for k in ("systemd", "sysctl", "pg_setting") if k in x]
        if len(typ) != 1:
            out.append(f"{where} needs exactly one of systemd, sysctl, pg_setting")
            continue
        typ = typ[0]
        if typ != EXPECT_KIND[kind]:
            out.append(f"{where}: a {kind} file is proven by a {EXPECT_KIND[kind]} setting, not {typ}")
            continue
        allowed = {typ, "value", "contains"} | ({"property"} if typ == "systemd" else {"cluster"} if typ == "pg_setting" else set())
        extra = set(x) - allowed
        if extra:
            out.append(f"{where}: unknown keys {sorted(extra)}")
        if ("value" in x) == ("contains" in x):
            out.append(f"{where} needs exactly one of value, contains")
            continue
        if "contains" in x and typ != "systemd":
            out.append(f"{where}: contains is only for systemd list properties")
        for key in ("value", "contains"):
            if key in x and not (isinstance(x[key], str) and x[key] != ""):
                out.append(f"{where}: {key} must be a non-empty string (quote numbers: \"131072\")")
        name = x.get(typ)
        if typ == "systemd":
            if not (isinstance(name, str) and re.match(rf"^[A-Za-z0-9@_.:\\-]+\.(?:{UNIT_TYPES})$", name)):
                out.append(f"{where}: systemd must be a unit name such as nginx.service")
            elif name.split("@")[0].split(".")[0] != systemd_unit_of(dest).split("@")[0].split(".")[0]:
                out.append(f"{where}: unit {name} is not the unit of {dest}")
            if not (isinstance(x.get("property"), str) and re.match(r"^[A-Za-z][A-Za-z0-9]*$", x["property"])):
                out.append(f"{where}: property must be a systemd property name")
        elif typ == "sysctl":
            if name not in settings:
                out.append(f"{where}: {name} is not set by the file")
            elif x.get("value") is not None and settings[name] != " ".join(str(x["value"]).split()):
                out.append(f"{where}: the file sets {name} = {settings[name]} but the expectation is {x['value']}")
        else:
            if not (isinstance(x.get("cluster"), str) and re.match(r"^[0-9]+/[A-Za-z0-9_.-]+$", x["cluster"])):
                out.append(f"{where}: cluster must be like 18/main")
            elif x["cluster"] != pg_cluster_of(dest):
                out.append(f"{where}: cluster {x['cluster']} is not the cluster of {dest}")
            if name not in settings:
                out.append(f"{where}: {name} is not set by the file")
            elif x.get("value") is not None and settings[name] != x["value"]:
                out.append(f"{where}: the file sets {name} = {settings[name]} but the expectation is {x['value']}")
    return out


def _inventory_problems(manifest: dict[str, Any]) -> list[str]:
    """`vm: {hypervisor, id}` of the hosts, the hypervisors to list, and the guests deliberately left out (each with a reason)."""
    hosts = manifest.get("hosts") or {}
    out: list[str] = []
    managed: dict[tuple[str, int], str] = {}
    for hid, h in hosts.items():
        vm = h.get("vm") if isinstance(h, dict) else None
        if vm is None:
            continue
        if not (isinstance(vm, dict) and set(vm) == {"hypervisor", "id"} and isinstance(vm["hypervisor"], str) and isinstance(vm["id"], int) and not isinstance(vm["id"], bool) and vm["id"] > 0):
            out.append(f"host {hid}: vm must be {{hypervisor: <hypervisor host id>, id: <vmid or ctid>}}")
            continue
        key = (vm["hypervisor"], vm["id"])
        if key in managed:
            out.append(f"host {hid}: vm {vm['id']} on {vm['hypervisor']} is already host {managed[key]}")
        managed[key] = hid
    inv = manifest.get("inventory")
    if inv is None:
        if managed:
            out.append("hosts have `vm` but there is no `inventory` section naming the hypervisors")
        return out
    if not isinstance(inv, dict) or set(inv) - {"hypervisors", "exempt"}:
        return out + ["inventory takes only `hypervisors` and `exempt`"]
    hv = inv.get("hypervisors")
    if not (isinstance(hv, list) and hv and all(isinstance(x, str) for x in hv) and len(set(hv)) == len(hv)):
        return out + ["inventory.hypervisors must list host ids, once each"]
    for x in hv:
        if x not in hosts:
            out.append(f"inventory.hypervisors: unknown host {x}")
        elif "ssh" not in hosts[x]:
            out.append(f"inventory.hypervisors: {x} needs an ssh alias (a hypervisor is reached directly)")
    for (on, _), hid in managed.items():
        if on not in hv:
            out.append(f"host {hid}: vm.hypervisor {on} is not in inventory.hypervisors")
    exempt = inv.get("exempt") or []
    if not isinstance(exempt, list):
        return out + ["inventory.exempt must be a list"]
    seen: set[tuple[str, int]] = set()
    for i, e in enumerate(exempt):
        where = f"inventory.exempt[{i}]"
        if not (isinstance(e, dict) and set(e) == {"hypervisor", "id", "why"} and isinstance(e["hypervisor"], str) and isinstance(e["id"], int) and not isinstance(e["id"], bool)):
            out.append(f"{where} needs hypervisor, id and why")
            continue
        if e["hypervisor"] not in hv:
            out.append(f"{where}: {e['hypervisor']} is not in inventory.hypervisors")
        if not (isinstance(e["why"], str) and len(e["why"].strip()) >= 20):
            out.append(f"{where}: why must say why this guest is not managed (at least 20 characters)")
        key = (e["hypervisor"], e["id"])
        if key in managed:
            out.append(f"{where}: {e['hypervisor']} {e['id']} is the managed host {managed[key]}; it cannot also be exempt")
        if key in seen:
            out.append(f"{where}: {e['hypervisor']} {e['id']} is exempt twice")
        seen.add(key)
    return out


SYSCTL_KEY_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_*/-]+)+$")


def _baseline_problems(baseline: Any, files: dict[str, Any], files_dir: Path) -> list[str]:
    """The fleet-wide floors: each names a sysctl key, the lowest acceptable value and the catalog file that raises a host that is below it."""
    if not isinstance(baseline, list):
        return ["baseline must be a list"]
    out: list[str] = []
    for i, b in enumerate(baseline):
        where = f"baseline[{i}]"
        if not isinstance(b, dict) or set(b) != {"sysctl_min", "value", "fix"}:
            out.append(f"{where} needs exactly sysctl_min, value and fix")
            continue
        key, value, fix = b["sysctl_min"], b["value"], b["fix"]
        if not (isinstance(key, str) and SYSCTL_KEY_RE.match(key)):
            out.append(f"{where}: sysctl_min must be a sysctl key such as kernel.threads-max")
            continue
        if not (isinstance(value, str) and value.isdigit()):
            out.append(f"{where}: value must be a quoted whole number")
            continue
        f = files.get(fix) if isinstance(fix, str) else None
        if not isinstance(f, dict) or not isinstance(f.get("dest"), str) or kind_of(f["dest"]) != "sysctl":
            out.append(f"{where}: fix must be the id of a sysctl catalog file")
            continue
        src = files_dir / str(f.get("src", ""))
        if not src.is_file():
            continue  # the catalog entry reports the missing file
        got = parse_settings("sysctl", src.read_text(encoding="utf-8")).get(key, "")
        if not (got.isdigit() and int(got) >= int(value)):
            out.append(f"{where}: {fix} sets {key} to {got or 'nothing'}, which does not meet the floor {value}")
    return out


def manifest_problems(manifest: dict[str, Any], files_dir: Path | None = None) -> list[str]:
    """Every reason this manifest must not be used, in one list (empty = valid). Offline: no host is contacted."""
    files_dir = files_dir or FILES_DIR
    out: list[str] = []
    if manifest.get("version") != 1:
        out.append("version must be 1")
    extra_top = set(manifest) - {"version", "files", "hosts", "baseline", "inventory"}
    if extra_top:
        out.append(f"unknown top-level keys {sorted(extra_top)}")
    files = manifest.get("files")
    hosts = manifest.get("hosts")
    if not isinstance(files, dict) or not files:
        return out + ["`files` must be a non-empty mapping"]
    if not isinstance(hosts, dict) or not hosts:
        return out + ["`hosts` must be a non-empty mapping"]
    used_src: set[str] = set()
    for fid, f in files.items():
        if not (isinstance(fid, str) and ID_RE.match(fid)):
            out.append(f"file id {fid!r}: use lowercase letters, digits, dots and dashes")
            continue
        if not isinstance(f, dict):
            out.append(f"{fid}: must be a mapping")
            continue
        extra = set(f) - {"dest", "src", "purpose", "mode", "owner", "group", "expect"}
        if extra:
            out.append(f"{fid}: unknown keys {sorted(extra)}")
        dest, src = f.get("dest"), f.get("src")
        kind = kind_of(dest) if isinstance(dest, str) else None
        if kind is None:
            out.append(f"{fid}: dest {dest!r} is not a path this tool may write (systemd drop-in, /etc/sysctl.d/NN-*.conf, Postgres conf.d/NN-*.conf)")
        if not (isinstance(f.get("purpose"), str) and len(f["purpose"].strip()) >= 20):
            out.append(f"{fid}: purpose must say why the file exists (at least 20 characters)")
        mode = f.get("mode", "0644")
        if mode not in MODES:
            out.append(f"{fid}: mode must be one of {list(MODES)} (quoted)")
        for key in ("owner", "group"):
            if not re.match(r"^[a-z_][a-z0-9_-]*$", str(f.get(key, "root"))):
                out.append(f"{fid}: {key} must be a user/group name")
        if not (isinstance(src, str) and src and not src.startswith("/") and ".." not in src.split("/")):
            out.append(f"{fid}: src must be a relative path under config/hostconf/files")
            continue
        used_src.add(src)
        path = files_dir / src
        if not path.is_file():
            out.append(f"{fid}: src {src} does not exist")
            continue
        data = path.read_bytes()
        if kind:
            bad = content_problems(kind, data)
            out.extend(f"{fid} ({src}): {p}" for p in bad)
            if not bad:
                out.extend(_expect_problems(fid, kind, dest, f.get("expect"), data.decode("utf-8")))
    if files_dir.is_dir():
        for p in sorted(files_dir.rglob("*")):
            if p.is_file() and str(p.relative_to(files_dir)) not in used_src:
                out.append(f"{p.relative_to(files_dir)}: a file that no catalog entry uses")
    baseline = manifest.get("baseline") or []
    out.extend(_baseline_problems(baseline, files, files_dir))
    used_ids: set[str] = set()
    aliases: dict[str, str] = {}
    for hid, h in hosts.items():
        if not (isinstance(hid, str) and ID_RE.match(hid)):
            out.append(f"host id {hid!r}: use lowercase letters, digits, dots and dashes")
            continue
        if not isinstance(h, dict):
            out.append(f"host {hid}: must be a mapping")
            continue
        extra = set(h) - {"ssh", "hostname", "note", "files", "sudo", "vm"}
        if extra:
            out.append(f"host {hid}: unknown keys {sorted(extra)}")
        if "sudo" in h and not isinstance(h["sudo"], bool):
            out.append(f"host {hid}: sudo must be true or false (false = the ssh user is root and there is no sudo)")
        if "sudo" in h and "ssh" not in h:
            out.append(f"host {hid}: sudo only applies to an ssh login (this host is reached through its hypervisor's guest agent)")
        if "ssh" not in h:
            if "vm" not in h:
                out.append(f"host {hid}: needs ssh (an alias) or vm (a guest reached through its hypervisor's agent)")
        elif not (isinstance(h["ssh"], str) and SSH_RE.match(h["ssh"])):
            out.append(f"host {hid}: ssh must be an ssh alias or user@host (no leading dash)")
        elif h["ssh"] in aliases:
            out.append(f"host {hid}: ssh alias {h['ssh']} is already used by {aliases[h['ssh']]}")
        else:
            aliases[h["ssh"]] = hid
        if not (isinstance(h.get("hostname"), str) and HOSTNAME_RE.match(h["hostname"])):
            out.append(f"host {hid}: hostname must be what `hostname` prints on the machine (the tool refuses to write to another one)")
        listed = h.get("files", [])
        if not isinstance(listed, list):
            out.append(f"host {hid}: files must be a list of catalog ids")
            continue
        if not listed and not baseline:
            out.append(f"host {hid}: no files and the manifest has no baseline, so nothing would be checked there")
        dests: dict[str, str] = {}
        for fid in listed:
            if fid not in files or not isinstance(files[fid], dict):
                out.append(f"host {hid}: unknown file id {fid!r}")
                continue
            used_ids.add(fid)
            d = files[fid].get("dest")
            if d in dests:
                out.append(f"host {hid}: {fid} and {dests[d]} both write {d}")
            dests[d] = fid
        if len(set(listed)) != len(listed):
            out.append(f"host {hid}: a file is listed twice")
    for fid in files:
        if fid not in used_ids:
            out.append(f"file {fid} is in the catalog but no host uses it")
    out.extend(_inventory_problems(manifest))
    return out


def select_hosts(manifest: dict[str, Any], names: list[str] | None, everything: bool) -> list[str]:
    hosts = list(manifest["hosts"])
    if everything:
        return hosts
    if not names:
        raise ManifestError("name at least one --host (or use --all)")
    unknown = [n for n in names if n not in manifest["hosts"]]
    if unknown:
        raise ManifestError(f"unknown host(s) {unknown}; known: {hosts}")
    return names


def host_files(manifest: dict[str, Any], host: str, only: list[str] | None = None, lean: bool = False) -> list[dict[str, Any]]:
    """The files of one host as the remote script wants them: destination, kind, expected bytes (base64) and settings.

    `lean` (adopt) skips the repo content and the expectations: the file may not exist in the repo yet."""
    out = []
    for fid in manifest["hosts"][host].get("files", []):
        if only is not None and fid not in only:
            continue
        f = manifest["files"][fid]
        data = b"" if lean else (FILES_DIR / f["src"]).read_bytes()
        out.append({
            "id": fid, "dest": f["dest"], "kind": kind_of(f["dest"]), "mode": f.get("mode", "0644"),
            "owner": f.get("owner", "root"), "group": f.get("group", "root"),
            "sha256": hashlib.sha256(data).hexdigest(), "b64": base64.b64encode(data).decode(),
            "expect": [] if lean else [_expect_for_remote(fid, x) for x in f["expect"]],
        })
    return out


def _expect_for_remote(fid: str, x: dict[str, Any]) -> dict[str, Any]:
    typ = next(k for k in ("systemd", "sysctl", "pg_setting") if k in x)
    out = {"file": fid, "type": typ, "name": x[typ]}
    out.update({k: v for k, v in x.items() if k != typ})
    return out


# ───────────────────────────── the script that runs on the host ─────────────────────────────

REMOTE_SCRIPT = r'''
import base64, fcntl, grp, hashlib, json, os, pwd, re, socket, stat, subprocess, sys, time

SPEC = json.loads(base64.b64decode("@@SPEC@@").decode())
ROOT = os.environ.get("HOSTCONF_ROOT", "")  # tests only: every absolute path below is looked up under this directory
TEST = bool(ROOT)
SECRET = re.compile(SPEC["secret_re"])
KINDS = {k: re.compile(v) for k, v in SPEC["kinds"].items()}
MAX_BYTES = SPEC["max_bytes"]
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def real(path):
    return ROOT + path


def emit(obj, code=0):
    print("HOSTCONF_RESULT " + json.dumps(obj))
    sys.stdout.flush()
    sys.exit(code)


def run(argv, timeout=60):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd="/")
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


def names(uid, gid):
    if TEST and uid == os.geteuid() and gid == os.getegid():
        return "root", "root"  # tests only: the user running the tests stands in for root
    try:
        user = pwd.getpwuid(uid).pw_name
    except KeyError:
        user = str(uid)
    try:
        group = grp.getgrgid(gid).gr_name
    except KeyError:
        group = str(gid)
    return user, group


def look(f):
    dest = f["dest"]
    entry = {"id": f["id"], "dest": dest, "exists": False}
    try:
        st = os.lstat(real(dest))
    except FileNotFoundError:
        return entry
    except OSError as exc:
        entry["error"] = str(exc)
        return entry
    entry["exists"] = True
    if stat.S_ISLNK(st.st_mode):
        entry["symlink"] = True
        return entry
    if not stat.S_ISREG(st.st_mode):
        entry["notregular"] = True
        return entry
    with open(real(dest), "rb") as fh:
        data = fh.read(MAX_BYTES + 1)
    entry["sha256"] = hashlib.sha256(data).hexdigest()
    entry["size"] = st.st_size
    entry["mode"] = "%04o" % (st.st_mode & 0o7777)
    entry["owner"], entry["group"] = names(st.st_uid, st.st_gid)
    if len(data) > MAX_BYTES:
        entry["toobig"] = True
    else:
        text = data.decode("utf-8", "replace")
        if SECRET.search(text):
            entry["secretish"] = True
        elif SPEC.get("want_content"):
            entry["b64"] = base64.b64encode(data).decode()
    return entry


def pg_port(cluster):
    version, name = cluster.split("/")
    rc, out, _ = run(["pg_lsclusters", "-h"])
    if rc != 0:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == version and parts[1] == name:
            return parts[2]
    return None


def evaluate(x):
    typ = x["type"]
    actual = None
    if typ == "systemd":
        rc, out, _ = run(["systemctl", "show", x["name"], "--property=" + x["property"], "--value"])
        actual = out.strip() if rc == 0 else None
    elif typ == "sysctl":
        rc, out, _ = run(["sysctl", "-n", x["name"]])
        actual = " ".join(out.split()) if rc == 0 else None
    elif typ == "pg_setting":
        port = pg_port(x["cluster"])
        if port:
            rc, out, _ = run(["runuser", "-u", "postgres", "--", "psql", "-X", "-A", "-t", "-q", "-p", port, "-c", "SHOW " + x["name"]])
            actual = out.strip() if rc == 0 else None
    if "value" in x:
        ok = actual is not None and actual == x["value"]
        want = x["value"]
    else:
        ok = actual is not None and x["contains"] in actual.split()
        want = "contains " + x["contains"]
    return {"file": x["file"], "type": typ, "name": x["name"], "property": x.get("property"), "actual": actual, "want": want, "ok": ok}


def evaluate_baseline(b):
    rc, out, _ = run(["sysctl", "-n", b["name"]])
    actual = " ".join(out.split()) if rc == 0 else None
    try:
        ok = actual is not None and int(actual) >= int(b["value"])
    except ValueError:
        ok = False
    return {"file": "<baseline>", "type": "sysctl_min", "name": b["name"], "property": None, "actual": actual, "want": ">= " + b["value"], "ok": ok, "fix": b["fix"]}


def expectations():
    return [evaluate(x) for f in SPEC["files"] for x in f["expect"]] + [evaluate_baseline(b) for b in SPEC.get("baseline", [])]


def check_host():
    want = SPEC.get("hostname")
    have = socket.gethostname()
    if want and have != want:
        emit({"mode": SPEC["mode"], "refused": "this is host %r, the manifest says %r" % (have, want), "hostname": have}, 1)
    return have


def write_atomic(path, data, mode, uid, gid):
    os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
    tmp = path + ".hostconf-new"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, mode)
    if not TEST:
        os.chown(tmp, uid, gid)
    os.replace(tmp, path)


def reload_actions(changed):
    """Reload what the changed files need. Never a restart. Returns (done, failures)."""
    done, bad = [], []
    kinds = {c["kind"] for c in changed}

    def step(label, argv):
        rc, out, err = run(argv)
        (done if rc == 0 else bad).append(label if rc == 0 else "%s (exit %s: %s)" % (label, rc, (err or out).strip()[:200]))

    if "systemd_dropin" in kinds:
        step("systemctl daemon-reload", ["systemctl", "daemon-reload"])
    for c in changed:
        if c["kind"] == "sysctl":
            step("sysctl -p " + c["dest"], ["sysctl", "-p", real(c["dest"])])
        elif c["kind"] == "pg_conf_d":
            version, name = c["dest"].split("/")[3:5]
            step("pg_ctlcluster %s %s reload" % (version, name), ["pg_ctlcluster", version, name, "reload"])
    return done, bad


def sysctl_runtime(files):
    out = {}
    for f in files:
        if f["kind"] != "sysctl":
            continue
        for line in base64.b64decode(f["b64"]).decode().splitlines():
            m = re.match(r"^\s*([a-z0-9_.*/-]+)\s*=", line)
            if m and not line.lstrip().startswith(("#", ";")):
                rc, val, _ = run(["sysctl", "-n", m.group(1)])
                if rc == 0:
                    out[m.group(1)] = val.strip()
    return out


def mode_of(f):
    return int(f["mode"], 8)


def ids_of(f):
    if TEST:
        return os.geteuid(), os.getegid()
    return pwd.getpwnam(f["owner"]).pw_uid, grp.getgrnam(f["group"]).gr_gid


def observe():
    have = check_host()
    files = [look(f) for f in SPEC["files"]]
    emit({"mode": "observe", "hostname": have, "files": files, "expects": expectations()}, 0)


def apply():
    have = check_host()
    os.makedirs(real("/run/lock"), exist_ok=True)
    lock = open(real("/run/lock/hostconf.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        emit({"mode": "apply", "hostname": have, "refused": "another hostconf apply is running on this host"}, 1)
    plan = []
    for f in SPEC["files"]:
        data = base64.b64decode(f["b64"])
        if f["kind"] not in KINDS or not KINDS[f["kind"]].match(f["dest"]) or os.path.normpath(f["dest"]) != f["dest"] or ".." in f["dest"].split("/"):
            emit({"mode": "apply", "hostname": have, "refused": "%s is not a path hostconf may write" % f["dest"]}, 1)
        if hashlib.sha256(data).hexdigest() != f["sha256"] or len(data) > MAX_BYTES or SECRET.search(data.decode("utf-8", "replace")):
            emit({"mode": "apply", "hostname": have, "refused": "the content of %s failed its integrity or credential check" % f["dest"]}, 1)
        try:
            uid, gid = ids_of(f)
        except KeyError as exc:
            emit({"mode": "apply", "hostname": have, "refused": "owner or group %s does not exist here" % exc}, 1)
        path = real(f["dest"])
        old = None
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                emit({"mode": "apply", "hostname": have, "refused": "%s exists and is not a regular file" % f["dest"]}, 1)
            with open(path, "rb") as fh:
                old = (fh.read(), st.st_mode & 0o7777, st.st_uid, st.st_gid)
        except FileNotFoundError:
            pass
        same = old is not None and old[0] == data and old[1] == mode_of(f) and (old[2], old[3]) == (uid, gid)
        plan.append({"f": f, "data": data, "uid": uid, "gid": gid, "old": old, "same": same})
    changed = [p for p in plan if not p["same"]]
    result = {"mode": "apply", "hostname": have, "changed": [p["f"]["dest"] for p in changed], "backups": {}, "reloaded": [], "pending_restart": []}
    runtime_before = sysctl_runtime([p["f"] for p in changed])

    def restore():
        for p in changed:
            path = real(p["f"]["dest"])
            try:
                if p["old"] is None:
                    if os.path.lexists(path):
                        os.unlink(path)
                else:
                    write_atomic(path, p["old"][0], p["old"][1], p["old"][2], p["old"][3])
            except OSError as exc:
                result.setdefault("rollback_errors", []).append("%s: %s" % (p["f"]["dest"], exc))
        reload_actions([p["f"] for p in changed])
        for key, val in runtime_before.items():
            run(["sysctl", "-w", "%s=%s" % (key, val)])
        verified = True
        for p in changed:
            path = real(p["f"]["dest"])
            try:
                now = open(path, "rb").read() if os.path.exists(path) else None
            except OSError:
                now = None
            if now != (p["old"][0] if p["old"] else None):
                verified = False
        return verified

    def fail(reason):
        result["error"] = reason
        ok = restore()
        result["status"] = "rolled_back" if ok else "rollback_unverified"
        emit(result, 5 if ok else 4)

    for p in changed:
        path = real(p["f"]["dest"])
        try:
            if p["old"] is not None:
                backup = path + ".bak-hostconf-" + STAMP
                write_atomic(backup, p["old"][0], p["old"][1], p["old"][2], p["old"][3])
                result["backups"][p["f"]["dest"]] = p["f"]["dest"] + ".bak-hostconf-" + STAMP
            write_atomic(path, p["data"], mode_of(p["f"]), p["uid"], p["gid"])
        except OSError as exc:
            fail("writing %s failed: %s" % (p["f"]["dest"], exc))
    changed_ids = set(p["f"]["id"] for p in changed)
    if changed:
        done, bad = reload_actions([p["f"] for p in changed])
        result["reloaded"] = done
        if bad:
            fail("reload failed: " + "; ".join(bad))
    exp = expectations()
    stale = [f for f in SPEC["files"] if f["id"] not in changed_ids and any(e["file"] == f["id"] and not e["ok"] for e in exp)]
    if stale:
        # a file that is already as wanted but is not in effect (written by hand, never reloaded): reload what it needs once and look again
        done, bad = reload_actions(stale)
        result["reloaded"] = result["reloaded"] + done
        exp = expectations()
    result["expects"] = exp
    broken = [e for e in exp if e["file"] in changed_ids and not e["ok"]]
    if broken:
        fail("a setting is not in effect after the change: " + ", ".join("%s %s (live %s, wanted %s)" % (e["type"], e["name"], e["actual"], e["want"]) for e in broken))
    for p in plan:
        if p["f"]["kind"] == "pg_conf_d" and changed:
            version, name = p["f"]["dest"].split("/")[3:5]
            port = pg_port("%s/%s" % (version, name))
            if port:
                rc, out, _ = run(["runuser", "-u", "postgres", "--", "psql", "-X", "-A", "-t", "-q", "-p", port, "-c", "SELECT name FROM pg_settings WHERE pending_restart"])
                result["pending_restart"] += [l for l in out.split() if l]
    unmet = [e for e in exp if not e["ok"]]
    result["status"] = "not_in_effect" if unmet else ("applied" if changed else "unchanged")
    emit(result, 2 if unmet else 0)


def inventory():
    """The guests of this hypervisor. One `pvesh get /cluster/resources` call when it answers (it reads the state pvestatd already holds, so it stays quick while a vzdump
    keeps the host at a load of 30); `qm list`, `pct list` and one `qm config` per VM otherwise (each of those took 20-60 s on 0own during its nightly backup)."""
    have = check_host()
    guests = []
    rc, out, _ = run(["pvesh", "get", "/cluster/resources", "--type", "vm", "--output-format", "json"], 180)
    if rc == 0:
        try:
            rows = json.loads(out)
            for r in rows:
                if r.get("type") in ("qemu", "lxc") and isinstance(r.get("vmid"), int):
                    guests.append({"id": r["vmid"], "name": r.get("name", ""), "status": r.get("status", "?"), "kind": "VM" if r["type"] == "qemu" else "CT", "template": bool(r.get("template"))})
            emit({"mode": "inventory", "hostname": have, "guests": guests, "via": "pvesh"}, 0)
        except (ValueError, AttributeError, TypeError):
            guests = []
    rc, out, err = run(["qm", "list"], 240)
    if rc != 0:
        emit({"mode": "inventory", "hostname": have, "error": "qm list failed: " + (err or out).strip()[:200]}, 1)
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        vmid = int(parts[0])
        _, cfg, _ = run(["qm", "config", str(vmid)], 90)
        guests.append({"id": vmid, "name": parts[1], "status": parts[2], "kind": "VM", "template": any(l.strip() == "template: 1" for l in cfg.splitlines())})
    rc, out, _ = run(["pct", "list"], 120)
    if rc == 0:
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                guests.append({"id": int(parts[0]), "name": parts[-1], "status": parts[1], "kind": "CT", "template": False})
    emit({"mode": "inventory", "hostname": have, "guests": guests, "via": "qm"}, 0)


{"observe": observe, "adopt": observe, "apply": apply, "inventory": inventory}[SPEC["mode"]]()
'''


def build_script(mode: str, host: dict[str, Any], files: list[dict[str, Any]], want_content: bool = False, baseline: list[dict[str, Any]] | None = None) -> str:
    spec = {
        "mode": mode, "hostname": host["hostname"], "files": files, "want_content": want_content, "baseline": baseline or [],
        "secret_re": SECRET_RE, "kinds": KIND_PATTERNS, "max_bytes": MAX_FILE_BYTES,
    }
    blob = base64.b64encode(json.dumps(spec).encode()).decode()
    return REMOTE_SCRIPT.replace("@@SPEC@@", blob)


Runner = Callable[..., "tuple[int, str, str]"]  # (alias, script, timeout, sudo, via) -> (exit code, stdout, stderr)


def _unwrap_guest_exec(rc: int, stdout: str, stderr: str) -> tuple[int, str, str]:
    """`qm guest exec` answers with JSON ({exitcode, exited, out-data, err-data}); hand back what the guest's command printed."""
    try:
        d = json.loads(stdout)
    except ValueError:
        return (rc or 1), stdout, stderr
    if not isinstance(d, dict):
        return (rc or 1), stdout, stderr
    if d.get("exited") != 1:
        return 124, d.get("out-data", ""), (d.get("err-data", "") + " the guest command did not finish in time").strip()
    return int(d.get("exitcode", 1)), d.get("out-data", ""), (d.get("err-data", "") + stderr).strip()


def ssh_run(alias: str, script: str, timeout: int = 180, sudo: bool = True, via: int | None = None) -> tuple[int, str, str]:
    """Run a python script on a host as root over ssh (the script is the stdin of `sudo -n python3 -`; `sudo: false` hosts log in as root).

    `via` is a VMID: the host is a guest of the hypervisor `alias`, and the script is piped through `qm guest exec <vmid> --pass-stdin` (the guest agent)."""
    remote = ["python3", "-"] if via is None else ["qm", "guest", "exec", str(via), "--pass-stdin", "1", "--timeout", str(max(30, min(timeout, 300))), "--", "python3", "-"]
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3", alias, *(["sudo", "-n"] if sudo else []), *remote]
    try:
        r = subprocess.run(argv, input=script, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 255, "", str(exc)
    if via is not None:
        return _unwrap_guest_exec(r.returncode, r.stdout, r.stderr)
    return r.returncode, r.stdout, r.stderr


def ids_for(manifest: dict[str, Any], host: str, only: list[str] | None) -> list[str]:
    """The catalog ids of one host, narrowed to --file when given."""
    return [i for i in manifest["hosts"][host].get("files", []) if not only or i in only]


def run_on_host(manifest: dict[str, Any], host: str, mode: str, only: list[str] | None, runner: Runner, want_content: bool = False,
                lean: bool = False, timeout: int = 180) -> dict[str, Any]:
    """One round trip. Returns the host's JSON answer, or {'unreachable': why} when there is none."""
    h = manifest["hosts"][host]
    baseline = [] if lean else [{"type": "sysctl_min", "name": b["sysctl_min"], "value": b["value"], "fix": b["fix"]} for b in manifest.get("baseline") or []]
    script = build_script(mode, h, host_files(manifest, host, only, lean), want_content, baseline)
    if "ssh" in h:
        rc, out, err = runner(h["ssh"], script, timeout, h.get("sudo", True))
    else:
        hv = manifest["hosts"][h["vm"]["hypervisor"]]
        rc, out, err = runner(hv["ssh"], script, timeout, hv.get("sudo", True), h["vm"]["id"])
    for line in out.splitlines():
        if line.startswith("HOSTCONF_RESULT "):
            try:
                res = json.loads(line[len("HOSTCONF_RESULT "):])
            except ValueError:
                break
            res["exit"] = rc
            return res
    return {"unreachable": (err.strip() or out.strip() or f"no answer (ssh exit {rc})")[:300], "exit": rc}


# ───────────────────────────── comparing ─────────────────────────────


def compare(manifest: dict[str, Any], host: str, answer: dict[str, Any], only: list[str] | None = None) -> dict[str, Any]:
    """Per file: ok / missing / differs / mode / symlink / notregular / secretish / toobig; per setting: ok or not."""
    result: dict[str, Any] = {"host": host, "files": [], "expects": answer.get("expects", [])}
    if "unreachable" in answer:
        result["unreachable"] = answer["unreachable"]
        return result
    if "refused" in answer:
        result["unreachable"] = "wrong host: " + answer["refused"]
        return result
    want = {f["id"]: f for f in host_files(manifest, host, only)}
    for live in answer.get("files", []):
        w = want[live["id"]]
        entry = {"id": live["id"], "dest": live["dest"], "state": "ok"}
        if not live["exists"]:
            entry["state"] = "missing"
        elif live.get("symlink") or live.get("notregular") or live.get("error"):
            entry["state"] = "symlink" if live.get("symlink") else "notregular" if live.get("notregular") else "unreadable"
        elif live.get("secretish"):
            entry["state"] = "secretish"
        elif live.get("toobig") or live["sha256"] != w["sha256"]:
            entry["state"] = "differs"
            if "b64" in live:
                entry["live"] = base64.b64decode(live["b64"]).decode("utf-8", "replace")
        elif (live["mode"], live["owner"], live["group"]) != (w["mode"], w["owner"], w["group"]):
            entry["state"] = "mode"
            entry["detail"] = f"live {live['mode']} {live['owner']}:{live['group']}, wanted {w['mode']} {w['owner']}:{w['group']}"
        result["files"].append(entry)
    return result


def drift_count(res: dict[str, Any]) -> int:
    return sum(1 for f in res["files"] if f["state"] != "ok") + sum(1 for e in res["expects"] if not e["ok"])


def render_host(manifest: dict[str, Any], res: dict[str, Any], show_diff: bool = False) -> str:
    h = manifest["hosts"][res["host"]]
    way = f"ssh {h['ssh']}" if "ssh" in h else f"guest agent of {h['vm']['hypervisor']}, vm {h['vm']['id']}"
    head = f"{res['host']} ({h['hostname']}, {way})"
    if "unreachable" in res:
        return f"{head}: COULD NOT LOOK: {res['unreachable']}"
    lines = [f"{head}: " + ("in sync" if drift_count(res) == 0 else f"{drift_count(res)} difference(s)")]
    for f in res["files"]:
        if f["state"] == "ok":
            lines.append(f"  ok       {f['dest']}")
        else:
            extra = f" ({f['detail']})" if f.get("detail") else ""
            lines.append(f"  {f['state'].upper():8} {f['dest']}{extra}")
            if show_diff and f["state"] == "differs" and "live" in f:
                want = (FILES_DIR / manifest["files"][f["id"]]["src"]).read_text(encoding="utf-8")
                lines.extend("    " + d.rstrip("\n") for d in difflib.unified_diff(f["live"].splitlines(True), want.splitlines(True), "live", "repo"))
    for e in res["expects"]:
        if e["ok"]:
            continue
        if e["type"] == "sysctl_min":
            has_fix = e["fix"] in manifest["hosts"][res["host"]].get("files", [])
            hint = f"{e['fix']} is listed for this host but the setting is not in effect" if has_fix else f"add {e['fix']} to this host's files in config/hostconf/hostconf.yaml"
            lines.append(f"  BELOW BASELINE  sysctl {e['name']}: live {e['actual']!r}, wanted {e['want']}; {hint}")
        else:
            lines.append(f"  NOT IN EFFECT  {e['type']} {e['name']}{('.' + e['property']) if e.get('property') else ''}: live {e['actual']!r}, wanted {e['want']!r}")
    return "\n".join(lines)


def _label(value: str) -> str:
    """A Prometheus label value: backslash, double quote and newline are the only characters the text format escapes."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def below_baseline(res: dict[str, Any]) -> bool:
    return any(e.get("file") == "<baseline>" and not e["ok"] for e in res["expects"])


def metrics_text(manifest: dict[str, Any], results: list[dict[str, Any]], now: float | None = None, inventory: dict[str, dict[str, Any]] | None = None) -> str:
    # The label is `machine`, not `host`: the monitoring Prometheus gives every target a `host` label of its own and would rename a scraped `host`
    # to `exported_host`, so alerts and queries could not name the machine.
    out = [
        "# HELP fleet_hostconf_files_total Managed files per machine.", "# TYPE fleet_hostconf_files_total gauge",
        "# HELP fleet_hostconf_drift_files Files that differ from the repo, plus settings not in effect (the fleet baseline included).", "# TYPE fleet_hostconf_drift_files gauge",
        "# HELP fleet_hostconf_below_baseline 1 when a fleet baseline floor is not met (kernel.threads-max under 131072).", "# TYPE fleet_hostconf_below_baseline gauge",
        "# HELP fleet_hostconf_unreachable 1 when the machine could not be looked at.", "# TYPE fleet_hostconf_unreachable gauge",
    ]
    for res in results:
        h = _label(res["host"])
        out.append(f'fleet_hostconf_files_total{{machine="{h}"}} {len(manifest["hosts"][res["host"]].get("files", []))}')
        out.append(f'fleet_hostconf_unreachable{{machine="{h}"}} {1 if "unreachable" in res else 0}')
        if "unreachable" not in res:
            out.append(f'fleet_hostconf_drift_files{{machine="{h}"}} {drift_count(res)}')
            out.append(f'fleet_hostconf_below_baseline{{machine="{h}"}} {1 if below_baseline(res) else 0}')
    if inventory:
        out += ["# HELP fleet_hostconf_inventory_findings Guests of a hypervisor that the manifest does not know (or hosts that are gone).", "# TYPE fleet_hostconf_inventory_findings gauge",
                "# HELP fleet_hostconf_inventory_unreachable 1 when a hypervisor could not be listed.", "# TYPE fleet_hostconf_inventory_unreachable gauge"]
        for hv, r in inventory.items():
            out.append(f'fleet_hostconf_inventory_unreachable{{hypervisor="{_label(hv)}"}} {1 if r["unreachable"] else 0}')
            if not r["unreachable"]:
                out.append(f'fleet_hostconf_inventory_findings{{hypervisor="{_label(hv)}"}} {len(r["findings"])}')
    out += ["# HELP fleet_hostconf_last_run_timestamp_seconds When the last drift check finished.", "# TYPE fleet_hostconf_last_run_timestamp_seconds gauge",
            f"fleet_hostconf_last_run_timestamp_seconds {int(now if now is not None else time.time())}"]
    return "\n".join(out) + "\n"


def _write_textfile(directory: str, text: str) -> None:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".fleet_hostconf.prom.tmp"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(d / "fleet_hostconf.prom")


# ───────────────────────────── inventory ─────────────────────────────


def inventory_findings(manifest: dict[str, Any], hv: str, answer: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    """What the hypervisor `hv` runs against what the manifest knows: unmanaged guests, managed hosts that are gone, exemptions that no longer apply."""
    inv = manifest["inventory"]
    managed = {h["vm"]["id"]: hid for hid, h in manifest["hosts"].items() if (h.get("vm") or {}).get("hypervisor") == hv}
    exempt = {e["id"] for e in inv.get("exempt") or [] if e["hypervisor"] == hv}
    live = {g["id"]: g for g in answer["guests"]}
    counts = {"guests": len(live), "templates": sum(1 for g in live.values() if g["template"]), "managed": 0, "exempt": 0}
    findings: list[str] = []
    for gid, g in sorted(live.items()):
        if g["template"]:
            continue
        if gid in managed:
            counts["managed"] += 1
        elif gid in exempt:
            counts["exempt"] += 1
        else:
            findings.append(f"UNMANAGED  {g['kind']} {gid} {g['name']} ({g['status']}): not in hostconf.yaml; add it under hosts with `vm: {{hypervisor: {hv}, id: {gid}}}` "
                            "(and an ssh alias, or none to go through the guest agent), or list it under inventory.exempt with a reason")
    for gid, hid in sorted(managed.items()):
        if gid not in live:
            findings.append(f"GONE  host {hid} is guest {gid} of {hv}, which no longer exists there: update or delete the host")
    for gid in sorted(exempt):
        if gid not in live:
            findings.append(f"STALE EXEMPTION  {hv} {gid} no longer exists: delete it from inventory.exempt")
    return findings, counts


def run_inventory(manifest: dict[str, Any], jobs: int, runner: Runner) -> dict[str, dict[str, Any]]:
    """Ask every hypervisor of `inventory.hypervisors` for its guests (read-only) and compare with the manifest."""
    def one(hv: str) -> dict[str, Any]:
        ans = run_on_host(manifest, hv, "inventory", [], runner, lean=True, timeout=900)
        if "unreachable" in ans or "refused" in ans:
            return {"unreachable": ans.get("unreachable") or "wrong host: " + ans["refused"], "findings": [], "counts": {}}
        if "error" in ans:
            return {"unreachable": ans["error"], "findings": [], "counts": {}}
        findings, counts = inventory_findings(manifest, hv, ans)
        return {"unreachable": None, "findings": findings, "counts": counts}

    hypervisors = manifest["inventory"]["hypervisors"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return dict(zip(hypervisors, pool.map(one, hypervisors)))


def render_inventory(manifest: dict[str, Any], hv: str, res: dict[str, Any]) -> str:
    h = manifest["hosts"][hv]
    head = f"inventory {hv} ({h['hostname']}, ssh {h['ssh']})"
    if res["unreachable"]:
        return f"{head}: COULD NOT LIST: {res['unreachable']}"
    c = res["counts"]
    lines = [f"{head}: {c['guests']} guests, {c['managed']} managed, {c['exempt']} exempt, {c['templates']} template(s) skipped" + ("" if not res["findings"] else f", {len(res['findings'])} finding(s)")]
    lines.extend("  " + f for f in res["findings"])
    return "\n".join(lines)


# ───────────────────────────── commands ─────────────────────────────

BLOCKED = ("secretish", "symlink", "notregular", "unreadable")


def valid_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest = load_manifest(path or MANIFEST)
    problems = manifest_problems(manifest)
    if problems:
        raise ManifestError("the manifest is not valid:\n  " + "\n  ".join(problems))
    return manifest


def cmd_drift(manifest: dict[str, Any], hosts: list[str], only: list[str] | None, show_diff: bool, jobs: int, runner: Runner,
              textfile_dir: str | None, with_inventory: bool = False) -> int:
    hosts = [h for h in hosts if not only or ids_for(manifest, h, only)]
    if not hosts and not with_inventory:
        print("no selected host uses the named file(s)", file=sys.stderr)
        return 1

    def one(host: str) -> dict[str, Any]:
        ids = ids_for(manifest, host, only)
        return compare(manifest, host, run_on_host(manifest, host, "observe", ids, runner, want_content=show_diff), ids)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(one, hosts))
    inv = run_inventory(manifest, jobs, runner) if with_inventory else {}
    for res in results:
        print(render_host(manifest, res, show_diff))
    for hv, r in inv.items():
        print(render_inventory(manifest, hv, r))
    if textfile_dir:
        _write_textfile(textfile_dir, metrics_text(manifest, results, inventory=inv))
    unreachable = sum(1 for r in results if "unreachable" in r) + sum(1 for r in inv.values() if r["unreachable"])
    drifted = sum(1 for r in results if "unreachable" not in r and drift_count(r)) + sum(1 for r in inv.values() if r["findings"])
    if results:
        bad_hosts = sum(1 for r in results if "unreachable" in r or drift_count(r))
        print(f"{len(results)} host(s): {len(results) - bad_hosts} in sync, {sum(1 for r in results if 'unreachable' not in r and drift_count(r))} with differences, {sum(1 for r in results if 'unreachable' in r)} not reachable")
    if inv:
        print(f"{len(inv)} hypervisor(s) listed: {sum(len(r['findings']) for r in inv.values())} finding(s), {sum(1 for r in inv.values() if r['unreachable'])} could not be listed")
    return 3 if unreachable else 2 if drifted else 0


def cmd_apply(manifest: dict[str, Any], hosts: list[str], only: list[str] | None, yes: bool, runner: Runner) -> int:
    hosts = [h for h in hosts if not only or ids_for(manifest, h, only)]
    if not hosts:
        print("no selected host uses the named file(s)", file=sys.stderr)
        return 1
    worst = 0
    for host in hosts:
        ids = ids_for(manifest, host, only)
        look = compare(manifest, host, run_on_host(manifest, host, "observe", ids, runner, want_content=True), ids)
        print(render_host(manifest, look, show_diff=True))
        if "unreachable" in look:
            return 3
        todo = [f for f in look["files"] if f["state"] != "ok"]
        blocked = [f for f in todo if f["state"] in BLOCKED]
        if blocked:
            print(f"  refusing: {', '.join(f['dest'] for f in blocked)} cannot be replaced safely; look at it by hand")
            return 1
        if not todo and all(e["ok"] for e in look["expects"]):
            continue
        if not yes:
            print(f"  plan: {len(todo)} file(s) would be written on {host}; nothing changed (add --yes)")
            continue
        ans = run_on_host(manifest, host, "apply", ids, runner)
        if "unreachable" in ans:
            print(f"  apply on {host}: COULD NOT RUN: {ans['unreachable']}")
            return 3
        if "refused" in ans:
            print(f"  apply on {host}: REFUSED: {ans['refused']}")
            return 1
        status = ans.get("status", "?")
        print(f"  apply on {host}: {status}; changed {ans.get('changed', [])}; reloaded {ans.get('reloaded', [])}")
        for dest, backup in (ans.get("backups") or {}).items():
            print(f"    previous {dest} kept as {backup}")
        for e in ans.get("expects", []):
            print(f"    {'ok' if e['ok'] else 'NOT IN EFFECT'}: {e['type']} {e['name']}{('.' + e['property']) if e.get('property') else ''} = {e['actual']!r}")
        if ans.get("pending_restart"):
            print(f"    needs a restart to take effect (not done here): {', '.join(ans['pending_restart'])}")
        if ans.get("error"):
            print(f"    error: {ans['error']}")
        code = {"applied": 0, "unchanged": 0, "not_in_effect": 2, "rolled_back": 5, "rollback_unverified": 4}.get(status, 2)
        if code in (4, 5):
            return code
        worst = max(worst, code)
    return worst


def cmd_adopt(manifest: dict[str, Any], host: str, fid: str, runner: Runner) -> int:
    """Fetch the live file and write it into config/hostconf/files/<src> byte for byte (refused when it looks like a credential)."""
    f = manifest["files"][fid]
    ans = run_on_host(manifest, host, "adopt", [fid], runner, want_content=True, lean=True)
    if "unreachable" in ans or "refused" in ans:
        print(f"could not look: {ans.get('unreachable') or ans.get('refused')}", file=sys.stderr)
        return 3
    live = ans["files"][0]
    if not live["exists"]:
        print(f"{f['dest']} does not exist on {host}", file=sys.stderr)
        return 1
    if "b64" not in live:
        why = "looks like it holds a credential" if live.get("secretish") else "is too big or not a plain file"
        print(f"{f['dest']} on {host} is not adoptable: it {why}", file=sys.stderr)
        return 1
    data = base64.b64decode(live["b64"])
    problems = content_problems(kind_of(f["dest"]) or "", data)
    if problems:
        print(f"{f['dest']} on {host} is not adoptable: {'; '.join(problems)}", file=sys.stderr)
        return 1
    target = FILES_DIR / f["src"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    try:
        shown = str(target.relative_to(REPO))
    except ValueError:
        shown = str(target)
    print(f"adopted {f['dest']} from {host}: {len(data)} bytes -> {shown} (live mode {live['mode']} {live['owner']}:{live['group']})")
    return 0


def main(argv: list[str] | None = None, runner: Runner = ssh_run) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=None, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    for name in ("drift", "apply", "adopt"):
        p = sub.add_parser(name)
        p.add_argument("--host", action="append")
        p.add_argument("--file", action="append")
        if name in ("drift", "apply"):
            p.add_argument("--all", action="store_true")
        if name == "drift":
            p.add_argument("--diff", action="store_true")
            p.add_argument("--inventory", action="store_true", help="also (--all does) list the guests of every hypervisor; alone, only that")
            p.add_argument("--jobs", type=int, default=8)
            p.add_argument("--textfile-dir", nargs="?", const=DEFAULT_TEXTFILE_DIR)
        if name == "apply":
            p.add_argument("--yes", action="store_true", help="really apply (without it only the plan is printed)")
    a = ap.parse_args(argv)
    path = Path(a.manifest) if a.manifest else MANIFEST
    try:
        if a.cmd == "check":
            manifest = load_manifest(path)
            problems = manifest_problems(manifest)
            for p in problems:
                print(f"PROBLEM {p}")
            print(f"{len(manifest.get('hosts') or {})} host(s), {len(manifest.get('files') or {})} file(s): " + ("valid" if not problems else f"{len(problems)} problem(s)"))
            return 1 if problems else 0
        if a.cmd == "adopt":
            manifest = load_manifest(path)
            if len(a.host or []) != 1 or len(a.file or []) != 1:
                raise ManifestError("adopt takes one --host and one --file")
            if a.host[0] not in (manifest.get("hosts") or {}) or a.file[0] not in (manifest.get("files") or {}) or a.file[0] not in manifest["hosts"][a.host[0]].get("files", []):
                raise ManifestError(f"{a.file[0]} must be listed in the manifest for host {a.host[0]} first (its src file may be missing: adopt creates it)")
            return cmd_adopt(manifest, a.host[0], a.file[0], runner)
        manifest = valid_manifest(path)
        unknown = [f for f in a.file or [] if f not in manifest["files"]]
        if unknown:
            raise ManifestError(f"unknown file id(s) {unknown}")
        if a.cmd == "drift" and a.inventory and not (a.all or a.host):
            hosts = []
        else:
            hosts = select_hosts(manifest, a.host, a.all)
        if a.cmd == "drift":
            if a.inventory and not manifest.get("inventory"):
                raise ManifestError("the manifest has no inventory section")
            return cmd_drift(manifest, hosts, a.file, a.diff, a.jobs, runner, a.textfile_dir, with_inventory=bool(manifest.get("inventory")) and (a.all or a.inventory))
        return cmd_apply(manifest, hosts, a.file, a.yes, runner)
    except ManifestError as exc:
        print(f"hostconf: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
