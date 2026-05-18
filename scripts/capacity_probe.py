"""Capacity probe — ADR 0482 (single-deployment, post-ADR 0488).

Read-only probe of the Proxmox host. Emits a structured `.local/capacity.yml`
describing what RAM / CPU / disk / network the host actually has.

The resolver (scripts/resolve_topology.py) consumes this file alongside
config/sizing-policy.yml and `.local/profile.yml` to compute per-VM
allocations that fit the host.

Probe transport: SSH using the `proxmox_host_ssh` block in `.local/identity.yml`.
Falls back to an explicit `--from-stdin` mode for operator-authored capacity
(cold provisioning before the host is reachable).

Expected `.local/identity.yml` shape (ADR 0385 + ADR 0488):

    platform_domain: example.com
    platform_operator_email: op@example.com
    platform_operator_name: "Op Name"
    proxmox_host_ssh:
      addr: 203.0.113.10        # public IP or DNS of the Proxmox host
      port: 22                  # SSH port (default 22)
      user: root                # SSH user (default root)
      key: bootstrap.id_ed25519 # filename under .local/ssh/, or absolute path

Usage:

    uv run --with pyyaml --with jsonschema python scripts/capacity_probe.py --write

    # Dry-run (print what would be written):
    uv run --with pyyaml --with jsonschema python scripts/capacity_probe.py

    # Operator-authored fallback (read from stdin):
    uv run ... python scripts/capacity_probe.py --from-stdin --write < capacity.yml

Exit codes: 0 = success, 2 = bad input, 3 = SSH/probe failed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

CODE_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ROOT = CODE_ROOT / ".local"
IDENTITY_PATH = LOCAL_ROOT / "identity.yml"
CAPACITY_PATH = LOCAL_ROOT / "capacity.yml"
SCHEMA_PATH = CODE_ROOT / "config" / "contracts" / "deployment-v1" / "capacity.schema.json"

PROBE_SCRIPT = r"""
set -eu
ram_total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
ram_total_mb=$(( ram_total_kb / 1024 ))
cores=$(nproc --all)
threads=$(nproc)
echo "ram_total_mb=${ram_total_mb}"
echo "cores=${cores}"
echo "threads=${threads}"
# storage (Proxmox local pools)
if command -v pvesm >/dev/null 2>&1; then
  pvesm status 2>/dev/null | awk 'NR>1 {printf "storage=%s|%s|%s|%s\n", $1, $2, int($4/1024/1024), int($5/1024/1024)}'
fi
# capabilities
if lspci 2>/dev/null | grep -qiE 'NVIDIA|3D controller'; then echo "cap=gpu"; fi
if ls /dev/nvme* >/dev/null 2>&1; then echo "cap=nvme"; fi
# public IPv4 (first non-private)
public_ipv4=$(ip -4 -j addr 2>/dev/null | python3 -c 'import json,sys
data=json.load(sys.stdin)
for ifc in data:
  for a in ifc.get("addr_info",[]):
    ip=a.get("local","")
    if ip.startswith(("10.","127.","172.16.","172.17.","172.18.","172.19.","172.20.","172.21.","172.22.","172.23.","172.24.","172.25.","172.26.","172.27.","172.28.","172.29.","172.30.","172.31.","192.168.","169.254.")): continue
    if a.get("family")=="inet":
      print(ip); raise SystemExit' 2>/dev/null || true)
echo "public_ipv4=${public_ipv4:-}"
"""


CONNECTION_PATH = LOCAL_ROOT / "connection.yml"


def _load_connection() -> dict[str, Any]:
    """Read .local/connection.yml — the ADR 0448 schema for how to reach the host.

    Falls back to legacy .local/identity.yml's `proxmox_host_ssh:` block
    (ADR 0385 era) when connection.yml is absent, so existing deployments
    keep working through the migration window.
    """
    if CONNECTION_PATH.is_file():
        with CONNECTION_PATH.open() as f:
            data = yaml.safe_load(f) or {}
        host = data.get("proxmox_host") or {}
        if not host.get("addr"):
            sys.exit(
                "ERROR: .local/connection.yml has no `proxmox_host.addr`. "
                "Re-run `make derive-deployment-files` from a manifest with "
                "`provider.host`, or hand-author the file (see "
                "config/contracts/deployment-v1/connection.schema.json)."
            )
        return host
    if IDENTITY_PATH.is_file():
        with IDENTITY_PATH.open() as f:
            identity = yaml.safe_load(f) or {}
        legacy = identity.get("proxmox_host_ssh") or {}
        if legacy.get("addr"):
            return legacy
    sys.exit(
        f"ERROR: neither {CONNECTION_PATH} nor a legacy identity.yml "
        "proxmox_host_ssh block found.\n"
        "Run `make derive-deployment-files` after authoring "
        ".local/manifest.yml (see config/contracts/deployment-v1/)."
    )


def _ssh_argv(host: dict[str, Any]) -> list[str]:
    """Build the ssh command from a `proxmox_host`-shaped dict."""
    addr = host["addr"]
    port = int(host.get("port", 22))
    user = host.get("user", "root")
    key = host.get("key", "")
    key_path = (LOCAL_ROOT / "ssh" / key) if key and not key.startswith("/") else Path(key)
    args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-p", str(port)]
    if key:
        args += ["-i", str(key_path), "-o", "IdentitiesOnly=yes"]
    args.append(f"{user}@{addr}")
    return args


def probe_via_ssh() -> dict[str, Any]:
    host = _load_connection()
    argv = _ssh_argv(host)
    cmd = argv + ["bash", "-s"]
    try:
        out = subprocess.run(cmd, input=PROBE_SCRIPT, text=True, capture_output=True, timeout=45, check=True).stdout
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"probe failed (rc={e.returncode}):\n{e.stderr}\n")
        sys.exit(3)
    except subprocess.TimeoutExpired:
        sys.stderr.write("probe timed out after 45s\n")
        sys.exit(3)
    return _parse_probe_output(out)


def _parse_probe_output(raw: str) -> dict[str, Any]:
    host: dict[str, Any] = {"storage": [], "capabilities": [], "networks": {}}
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k == "ram_total_mb":
            host["ram_total_mb"] = int(v)
        elif k == "cores":
            host["cores"] = int(v)
        elif k == "threads":
            host["threads"] = int(v)
        elif k == "storage":
            parts = v.split("|")
            if len(parts) >= 4:
                host["storage"].append(
                    {
                        "name": parts[0],
                        "type": parts[1] if parts[1] in {"zfs", "lvm", "dir", "btrfs", "ceph"} else "other",
                        "total_gb": int(parts[2]),
                        "free_gb": int(parts[3]),
                    }
                )
        elif k == "cap":
            host["capabilities"].append(v)
        elif k == "public_ipv4" and v:
            host["networks"]["public_ipv4"] = v
    host.setdefault("ram_reserved_mb", 4096)
    return {
        "schema_version": 1,
        "probed_at": _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "probed_via": "ssh",
        "host": host,
    }


def validate(capacity: dict[str, Any]) -> list[str]:
    """Validate against the JSON schema if jsonschema is available."""
    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except ImportError:
        errs = []
        if capacity.get("schema_version") != 1:
            errs.append("schema_version must be 1")
        if not isinstance(capacity.get("host", {}).get("ram_total_mb"), int):
            errs.append("host.ram_total_mb missing or not int")
        return errs
    if not SCHEMA_PATH.is_file():
        return []
    schema = json.loads(SCHEMA_PATH.read_text())
    v = Draft202012Validator(schema)
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in v.iter_errors(capacity)]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write", action="store_true", help="Write to .local/capacity.yml")
    p.add_argument(
        "--from-stdin", action="store_true", help="Read operator-authored capacity from stdin instead of probing"
    )
    args = p.parse_args()

    if args.from_stdin:
        capacity = yaml.safe_load(sys.stdin) or {}
        capacity.setdefault("probed_via", "operator")
    else:
        capacity = probe_via_ssh()

    errs = validate(capacity)
    if errs:
        sys.stderr.write("capacity validation errors:\n  " + "\n  ".join(errs) + "\n")
        return 2

    out_yaml = yaml.dump(capacity, sort_keys=False, default_flow_style=False)
    if args.write:
        CAPACITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        CAPACITY_PATH.write_text(out_yaml)
        print(f"wrote {CAPACITY_PATH}")
    else:
        sys.stdout.write(out_yaml)
    return 0


if __name__ == "__main__":
    sys.exit(main())
