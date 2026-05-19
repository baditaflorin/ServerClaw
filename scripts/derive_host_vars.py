"""Probe the Proxmox host's network config and write .local/host_vars/proxmox-host.yml.

ADR 0488 step 2.5 — fills in the per-host networking variables the playbooks
need without requiring the operator to author them by hand. Reads:

    .local/connection.yml   - how to SSH to the host
    .local/identity.yml     - apex domain (used to form a hostname slug)
    .local/topology.yml     - resolved proxmox_guests for inventory overlay

Probes (over SSH):

    - default IPv4 gateway and CIDR
    - active link-local IPv6 / global IPv6 / IPv6 gateway
    - primary interface name
    - hostname

Writes `.local/host_vars/proxmox-host.yml` with the operator-specific
overrides. Static defaults (bridge names, port assignments) stay in the
committed `inventory/host_vars/proxmox-host.yml`.

Usage:
    uv run --with pyyaml python scripts/derive_host_vars.py [--write]

Without --write: dry-run, prints to stdout.
"""

from __future__ import annotations

import argparse
import ipaddress
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ROOT = REPO_ROOT / ".local"
SSH_DIR = LOCAL_ROOT / "ssh"
CONNECTION_PATH = LOCAL_ROOT / "connection.yml"
IDENTITY_PATH = LOCAL_ROOT / "identity.yml"
TOPOLOGY_PATH = LOCAL_ROOT / "topology.yml"
OUT_PATH = LOCAL_ROOT / "host_vars" / "proxmox-host.yml"

PROBE_SCRIPT = r"""
set -eu
default_route=$(ip -4 -o route show default | head -1)
gateway4=$(echo "$default_route" | awk '{for (i=1;i<NF;i++) if ($i=="via") print $(i+1)}')
iface=$(echo "$default_route" | awk '{for (i=1;i<NF;i++) if ($i=="dev") print $(i+1)}')
ipv4_with_cidr=$(ip -4 -o addr show dev "$iface" | awk '$3=="inet" {print $4; exit}')
ipv4=${ipv4_with_cidr%/*}
ipv4_cidr=${ipv4_with_cidr#*/}
hostname=$(hostname)
ipv6_with_cidr=$(ip -6 -o addr show dev "$iface" scope global 2>/dev/null | awk '$3=="inet6" {print $4; exit}')
ipv6=${ipv6_with_cidr%/*}
ipv6_cidr=${ipv6_with_cidr#*/}
# IPv6 default route — Hetzner default gateway is fe80::1 in most setups.
gateway6=$(ip -6 -o route show default 2>/dev/null | awk '{for (i=1;i<NF;i++) if ($i=="via") print $(i+1); exit}')
echo "iface=$iface"
echo "ipv4=$ipv4"
echo "ipv4_cidr=$ipv4_cidr"
echo "gateway4=$gateway4"
echo "ipv6=${ipv6:-}"
echo "ipv6_cidr=${ipv6_cidr:-}"
echo "gateway6=${gateway6:-fe80::1}"
echo "hostname=$hostname"
"""


def _ssh_argv(host: dict[str, Any]) -> list[str]:
    addr = host["addr"]
    port = int(host.get("port", 22))
    user = host.get("user", "root")
    key = host.get("key", "")
    key_path = (SSH_DIR / key) if key and not key.startswith("/") else Path(key)
    return [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-p", str(port),
        "-i", str(key_path), "-o", "IdentitiesOnly=yes",
        f"{user}@{addr}",
    ]


def probe_remote(host: dict[str, Any]) -> dict[str, str]:
    argv = _ssh_argv(host)
    result = subprocess.run(argv + ["bash", "-s"], input=PROBE_SCRIPT, text=True,
                            capture_output=True, timeout=30, check=True)
    facts: dict[str, str] = {}
    for line in result.stdout.strip().splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        facts[k.strip()] = v.strip()
    return facts


def build_host_vars(facts: dict[str, str], identity: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    apex_slug = (identity.get("platform_domain") or "").split(".")[0]
    cidr_int = int(facts["ipv4_cidr"])
    network = ipaddress.IPv4Network(f"{facts['ipv4']}/{cidr_int}", strict=False)
    out: dict[str, Any] = {
        "host_public_hostname": f"{apex_slug}-proxmox" if apex_slug else facts.get("hostname", ""),
        "proxmox_node_name": f"{apex_slug}-proxmox" if apex_slug else facts.get("hostname", ""),
        "management_interface": facts["iface"],
        "management_ipv4": facts["ipv4"],
        "management_ipv4_cidr": cidr_int,
        "management_gateway4": facts["gateway4"],
        "hetzner_ipv4_route_network": str(network.network_address),
        "hetzner_ipv4_route_netmask": str(network.netmask),
    }
    if facts.get("ipv6"):
        out["management_ipv6"] = facts["ipv6"]
        out["management_ipv6_cidr"] = int(facts["ipv6_cidr"])
        out["management_gateway6"] = facts.get("gateway6", "fe80::1")
    # NOTE: we intentionally do NOT emit `proxmox_guests` in the overlay.
    # The committed inventory/host_vars/proxmox-host.yml carries the full
    # `<vm>-lv3` guest catalog (17 entries today) and downstream scripts
    # like generate_platform_vars.build_service_topology look up IPs by
    # owning_vm in that catalog — if our overlay replaced the list with
    # only the 5 currently-deployed VMs, references to the other 12 would
    # KeyError. As long as the resolver's vmid + ipv4 + name choices align
    # with the committed catalog (they do: 110/10.10.10.10/nginx-lv3 etc.),
    # the committed list works for our deployment too.
    # Generate-inventory still needs to know which guests exist for the
    # current deployment — that comes from the topology, not host_vars.
    guests = topology.get("proxmox_guests") or []
    if False:  # disabled per the comment above
        out["proxmox_guests"] = guests
        # Each guest needs a `network_policy.guests.<name>` entry — without
        # it `linux_guest_firewall` asserts and the role fails. Generate a
        # minimal management-SSH-only policy per guest as a sane default;
        # operators tighten or widen via inventory/host_vars/proxmox-host.yml
        # for production rules. Generic — keyed by the guest's resolver name
        # so the entry always matches inventory_hostname.
        guest_policies: dict[str, Any] = {}
        for g in guests:
            policy: dict[str, Any] = {
                "allowed_inbound": [
                    {
                        "source": "management",
                        "protocol": "tcp",
                        "ports": [22],
                        "description": "Operator and Ansible SSH access",
                    },
                ],
            }
            if g.get("template_key") == "docker-host":
                policy["allow_container_forwarding"] = True
            guest_policies[g["name"]] = policy
        # `linux_guest_firewall` consumes top-level
        # `network_policy.{guest_management_sources, host_source}` to render
        # the host-source allow lines in the guest nftables ruleset. Default
        # to: tailscale CIDR (operator path) + the host's internal bridge IP
        # (10.10.10.1/32), which the host owns as the guests' gateway.
        guest_prefix = ".".join(guests[0]["ipv4"].split(".")[:3])
        host_source = f"{guest_prefix}.1/32"
        tailscale_cidr = identity.get("platform_tailscale_network_cidr", "100.64.0.0/10")
        out["network_policy"] = {
            "guest_management_sources": [tailscale_cidr, host_source],
            "host_source": host_source,
            "guests": guest_policies,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Persist to .local/host_vars/proxmox-host.yml")
    args = parser.parse_args()

    for path in (CONNECTION_PATH, IDENTITY_PATH, TOPOLOGY_PATH):
        if not path.is_file():
            print(f"ERROR: {path} not found; run `make derive-deployment-files` "
                  "and `make probe-capacity` and `make resolve-topology` first.", file=sys.stderr)
            return 1

    connection = yaml.safe_load(CONNECTION_PATH.read_text()) or {}
    identity = yaml.safe_load(IDENTITY_PATH.read_text()) or {}
    topology = yaml.safe_load(TOPOLOGY_PATH.read_text()) or {}

    facts = probe_remote(connection["proxmox_host"])
    host_vars = build_host_vars(facts, identity, topology)

    text = yaml.safe_dump(host_vars, sort_keys=False)
    if args.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(text)
        print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
