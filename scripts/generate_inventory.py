#!/usr/bin/env python3
"""Generate inventory/hosts.yml from the authoritative source of truth.

Single source of truth for guest network topology:
  inventory/host_vars/proxmox-host.yml  →  proxmox_guests list
  inventory/group_vars/all/identity.yml →  network prefix (validation only)

All guest ansible_host values come from proxmox_guests[*].ipv4.
Staging hosts are derived from guests where has_staging: true, using the
staging network prefix read from proxmox_host_vars.proxmox_staging_ipv4.

Group membership is derived from tags in proxmox_guests:
  - postgres_guests: guests whose tags include 'postgres'
  - backup_guests:   guests whose tags include 'backup'

Usage:
  python3 scripts/generate_inventory.py --write    # regenerate inventory/hosts.yml
  python3 scripts/generate_inventory.py --check    # exit 1 if drift detected
  python3 scripts/generate_inventory.py --print    # print to stdout (dry-run)
  python3 scripts/generate_inventory.py --list     # Ansible dynamic inventory JSON

Design:
  - Pure function: build_inventory(host_vars) -> dict
  - Serialisation: render_yaml(inv) -> str
  - Entry points for both human (--write/--check) and Ansible (--list/--host) use
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from validation_toolkit import require_list, require_mapping, require_str

REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
HOSTS_YML_PATH = REPO_ROOT / "inventory" / "hosts.yml"
PLATFORM_YML_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"

GENERATED_HEADER_BASE = """\
# =============================================================================
# GENERATED — do not edit manually.
# Run: make generate-inventory
# Source: inventory/host_vars/proxmox-host.yml (proxmox_guests)
#         inventory/group_vars/all/identity.yml (network prefix)
# =============================================================================
"""

GENERATED_HEADER_OVERLAY = """\
# =============================================================================
# GENERATED (overlay mode) — do not edit manually.
# Run: PLATFORM_IDENTITY_OVERLAY=<path> make generate-inventory
# Sources:
#   base:    inventory/host_vars/proxmox-host.yml
#   overlay: {overlay}
# ADR 0437 — overlay-aware bootstrap.
# =============================================================================
"""

# Group execution-scope pattern selectors.
# Maps logical group name → {environment → Ansible host/group pattern}.
# No IPs — purely symbolic references. Staging entries that share a single
# staging VM (e.g. runtime-ai → docker-runtime-staging) are encoded here.
_EXECUTION_HOST_PATTERNS: dict[str, dict[str, str]] = {
    "proxmox_hosts": {
        "production": "proxmox_hosts:&production",
        "staging": "proxmox_hosts:&staging",
    },
    "lv3_guests": {
        "production": "lv3_guests:&production",
        "staging": "lv3_guests:&staging",
    },
    "postgres_guests": {
        "production": "postgres_guests:&production",
        "staging": "postgres_guests:&staging",
    },
    "backup_guests": {
        "production": "backup_guests:&production",
        "staging": "backup_guests:&staging",
    },
    # Hosts with dedicated staging VMs
    "coolify": {"production": "coolify-lv3", "staging": "coolify-staging"},
    "coolify_apps": {"production": "coolify-apps-lv3", "staging": "coolify-apps-staging"},
    "nginx_edge": {"production": "nginx-lv3", "staging": "nginx-staging"},
    "docker_runtime": {"production": "docker-runtime-lv3", "staging": "docker-runtime-staging"},
    "docker_build": {"production": "docker-build-lv3", "staging": "docker-build-staging"},
    "monitoring": {"production": "monitoring-lv3", "staging": "monitoring-staging"},
    "postgres": {"production": "postgres-lv3", "staging": "postgres-staging"},
    "backup": {"production": "backup-lv3", "staging": "backup-staging"},
    # Hosts without dedicated staging VMs — fall back to shared staging VM
    "runtime_ai": {"production": "runtime-ai-lv3", "staging": "docker-runtime-staging"},
    "runtime_control": {"production": "runtime-control-lv3", "staging": "docker-runtime-staging"},
    "runtime_general": {"production": "runtime-general-lv3", "staging": "docker-runtime-staging"},
    "runtime_comms": {"production": "runtime-comms-lv3", "staging": "docker-runtime-staging"},
    "runtime_apps": {"production": "runtime-apps-lv3", "staging": "docker-runtime-staging"},
    "postgres_apps": {"production": "postgres-apps-lv3", "staging": "postgres-staging"},
    "postgres_data": {"production": "postgres-data-lv3", "staging": "postgres-staging"},
}


# ---------------------------------------------------------------------------
# YAML serialisation helpers
# ---------------------------------------------------------------------------


class _JinjaQuoteDumper(yaml.SafeDumper):
    """SafeDumper that double-quotes any string containing a Jinja2 template.

    Ansible evaluates {{ ... }} expressions in inventory strings. PyYAML's
    default behaviour may choose block or single-quote style, which prevents
    Ansible from recognising them. Forcing double-quote style ensures correct
    parsing by both Ansible and human readers.
    """


def _jinja_str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    # Force double-quote style for strings containing Jinja2 templates or YAML
    # special characters that would otherwise be misinterpreted (&, *, :&).
    if "{{" in data and "}}" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    if data.startswith("&") or ":&" in data or ":*" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_JinjaQuoteDumper.add_representer(str, _jinja_str_representer)


def render_yaml(inventory: dict) -> str:
    """Serialise an inventory dict to YAML with Jinja2-safe quoting."""
    return yaml.dump(
        inventory,
        Dumper=_JinjaQuoteDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


# ---------------------------------------------------------------------------
# Core builder — pure function
# ---------------------------------------------------------------------------


def _net_prefix(ipv4_with_host: str) -> str:
    """Strip last octet from an IP: '10.10.10.1' → '10.10.10.'"""
    return ipv4_with_host.rsplit(".", 1)[0] + "."


def build_inventory(host_vars: dict) -> dict:
    """Build the full Ansible YAML inventory from proxmox_guests.

    Args:
        host_vars: Parsed content of inventory/host_vars/proxmox-host.yml

    Returns:
        Dict representing the complete hosts.yml inventory structure.

    Group derivation rules:
        production   – proxmox-host + all production guests
        staging      – proxmox-host + guests where has_staging=true (with -staging suffix)
        lv3_guests   – all production + staging guests (with ansible_host)
        postgres_guests – guests tagged 'postgres' (prod + staging)
        backup_guests   – guests tagged 'backup'   (prod + staging)
    """
    guests: list[dict] = require_list(host_vars.get("proxmox_guests", []), "proxmox_guests")
    ts_ip: str = require_str(
        host_vars.get("management_tailscale_ipv4", "100.64.0.1"),
        "management_tailscale_ipv4",
    )
    staging_pfx: str = _net_prefix(host_vars.get("proxmox_staging_ipv4", "10.20.10.1"))

    # --- lv3_guests: production entries ---
    lv3_hosts: dict[str, Any] = {}
    for g in guests:
        name = require_str(g.get("name", ""), f"proxmox_guests[vmid={g.get('vmid')}].name")
        ipv4 = require_str(g.get("ipv4", ""), f"proxmox_guests[{name}].ipv4")
        lv3_hosts[name] = {
            "ansible_host": ipv4,
            "deployment_environment": "production",
        }

    # --- lv3_guests: staging entries (derived from has_staging: true) ---
    for g in guests:
        if not g.get("has_staging", False):
            continue
        name = g["name"]
        vmid = int(g["vmid"])
        last_octet = str(vmid % 100)
        staging_name = f"{name}-staging"
        lv3_hosts[staging_name] = {
            "ansible_host": staging_pfx + last_octet,
            "deployment_environment": "staging",
        }

    # --- production group: just host names, no extra vars ---
    prod_names: dict[str, None] = {"proxmox-host": None}
    for g in guests:
        prod_names[g["name"]] = None

    # --- staging group: just names for staging counterparts ---
    staging_names: dict[str, None] = {"proxmox-host": None}
    for g in guests:
        if g.get("has_staging", False):
            staging_names[f"{g['name']}-staging"] = None

    # --- postgres_guests subgroup ---
    postgres_names: dict[str, None] = {}
    for g in guests:
        if "postgres" in g.get("tags", []):
            postgres_names[g["name"]] = None
            if g.get("has_staging", False):
                postgres_names[f"{g['name']}-staging"] = None

    # --- backup_guests subgroup ---
    backup_names: dict[str, None] = {}
    for g in guests:
        if "backup" in g.get("tags", []):
            backup_names[g["name"]] = None
            if g.get("has_staging", False):
                backup_names[f"{g['name']}-staging"] = None

    return {
        "all": {
            "vars": {
                "playbook_execution_env": "{{ env | default('production') }}",
                "playbook_execution_allowed_envs": ["production", "staging"],
                "playbook_execution_host_patterns": _EXECUTION_HOST_PATTERNS,
            },
            "children": {
                "production": {"hosts": prod_names},
                "staging": {"hosts": staging_names},
                "platform": {
                    "children": {
                        "proxmox_hosts": None,
                        "lv3_guests": None,
                        "postgres_guests": None,
                        "backup_guests": None,
                    }
                },
                "platform_services": {"children": {"proxmox_hosts": None}},
                "proxmox_hosts": {
                    "hosts": {
                        "proxmox-host": {
                            "ansible_host": (
                                f"{{{{ lookup('env', 'LV3_PROXMOX_HOST_ADDR') | default('{ts_ip}', true) }}}}"
                            ),
                            "ansible_user": "ops",
                            "ansible_become": True,
                            "ansible_become_method": "sudo",
                        }
                    }
                },
                "lv3_guests": {"hosts": lv3_hosts},
                "postgres_guests": {"hosts": postgres_names},
                "backup_guests": {"hosts": backup_names},
            },
        }
    }


# ---------------------------------------------------------------------------
# Ansible dynamic inventory protocol
# ---------------------------------------------------------------------------


def ansible_list(host_vars: dict) -> dict:
    """Return Ansible --list JSON output from proxmox_guests."""
    inv = build_inventory(host_vars)
    guests: list[dict] = host_vars.get("proxmox_guests", [])
    staging_pfx = _net_prefix(host_vars.get("proxmox_staging_ipv4", "10.20.10.1"))
    ts_ip = host_vars.get("management_tailscale_ipv4", "100.64.0.1")

    # Flatten into Ansible's JSON inventory format
    hostvars: dict[str, dict] = {
        "proxmox-host": {"ansible_host": ts_ip, "ansible_user": "ops"},
    }
    for g in guests:
        hostvars[g["name"]] = {
            "ansible_host": g["ipv4"],
            "deployment_environment": "production",
        }
        if g.get("has_staging", False):
            sname = f"{g['name']}-staging"
            hostvars[sname] = {
                "ansible_host": staging_pfx + str(g["vmid"] % 100),
                "deployment_environment": "staging",
            }

    all_hosts = list(hostvars.keys())
    return {
        "all": {"hosts": all_hosts, "vars": {}},
        "_meta": {"hostvars": hostvars},
    }


def ansible_host(host_vars: dict, hostname: str) -> dict:
    """Return Ansible --host JSON output for a single host."""
    inv_list = ansible_list(host_vars)
    return inv_list["_meta"]["hostvars"].get(hostname, {})


# ---------------------------------------------------------------------------
# File I/O and drift detection
# ---------------------------------------------------------------------------


def load_host_vars(path: Path = HOST_VARS_PATH) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


def merge_overlay(base: dict, overlay: dict) -> dict:
    """Merge an overlay host_vars dict on top of the base.

    Semantics (ADR 0437):
      - Top-level scalars in overlay replace base values (management_*,
        proxmox_staging_ipv4, etc.).
      - If overlay defines proxmox_guests, it replaces the base list wholesale
        (consistent with the ADR 0430 "wholesale replacement" convention for
        the .local/host_vars overlay).
      - Keys present only in base are preserved.
    """
    merged = dict(base)
    for key, value in overlay.items():
        merged[key] = value
    return merged


def load_host_vars_with_overlay(
    base_path: Path = HOST_VARS_PATH,
    overlay_path: Path | None = None,
) -> dict:
    """Load base host_vars and optionally merge an overlay on top."""
    base = load_host_vars(base_path)
    if overlay_path is None or not overlay_path.exists():
        return base
    with overlay_path.open() as fh:
        overlay = yaml.safe_load(fh) or {}
    return merge_overlay(base, overlay)


def generate(host_vars: dict, overlay_path: Path | None = None) -> str:
    """Return the complete hosts.yml string (header + YAML)."""
    if overlay_path is not None:
        header = GENERATED_HEADER_OVERLAY.format(overlay=str(overlay_path))
    else:
        header = GENERATED_HEADER_BASE
    return header + render_yaml(build_inventory(host_vars))


def check_drift(
    host_vars: dict,
    current_path: Path = HOSTS_YML_PATH,
    overlay_path: Path | None = None,
) -> bool:
    """Return True if current hosts.yml matches generated output, False if drift."""
    generated = generate(host_vars, overlay_path=overlay_path)
    if not current_path.exists():
        return False
    current = current_path.read_text()
    return current == generated


def show_diff(
    host_vars: dict,
    current_path: Path = HOSTS_YML_PATH,
    overlay_path: Path | None = None,
) -> str:
    """Return a unified diff between current file and generated output."""
    generated = generate(host_vars, overlay_path=overlay_path).splitlines(keepends=True)
    current = current_path.read_text().splitlines(keepends=True) if current_path.exists() else []
    return "".join(
        difflib.unified_diff(
            current,
            generated,
            fromfile=str(current_path),
            tofile="<generated>",
        )
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate inventory/hosts.yml from proxmox_guests in "
            "inventory/host_vars/proxmox-host.yml. "
            "Run 'make generate-inventory' to regenerate after topology changes."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Write inventory/hosts.yml")
    mode.add_argument("--check", action="store_true", help="Exit 1 if drift detected")
    mode.add_argument("--print", action="store_true", help="Print generated YAML to stdout")
    mode.add_argument("--list", action="store_true", help="Ansible dynamic inventory --list")
    mode.add_argument("--host", metavar="HOSTNAME", help="Ansible dynamic inventory --host")
    parser.add_argument(
        "--host-vars",
        metavar="PATH",
        default=str(HOST_VARS_PATH),
        help=f"Path to proxmox-host.yml (default: {HOST_VARS_PATH})",
    )
    parser.add_argument(
        "--host-vars-overlay",
        metavar="PATH",
        default=None,
        help=(
            "Optional overlay host_vars file (ADR 0437). When present, merges "
            "on top of --host-vars. Top-level scalars override base; "
            "proxmox_guests replaces the base list wholesale."
        ),
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=str(HOSTS_YML_PATH),
        help=(
            f"Output path for --write/--check (default: {HOSTS_YML_PATH}). "
            "For fork bootstraps, write to .local/inventory/hosts.yml so the "
            "committed production file is not polluted."
        ),
    )
    parser.add_argument(
        "--deployment",
        metavar="SLUG",
        help=(
            "ADR 0440: read topology from .local/deployments/<slug>/topology.yml "
            "and write hosts.yml under .local/deployments/<slug>/generated/. "
            "When set, --host-vars / --host-vars-overlay / --out are ignored. "
            "When omitted, the legacy single-deployment paths are used."
        ),
    )
    args = parser.parse_args()

    if args.deployment:
        # ADR 0440: redirect inputs/outputs to the per-deployment layout.
        from scripts.deployment import load as load_deployment

        deployment = load_deployment(args.deployment, validate=False)
        deployment.ensure_runtime_dirs()

        # The deployment's topology.yml replaces the host_vars input wholesale —
        # there is no "base + overlay" inside a deployment, the deployment
        # owns its topology.
        deployment_topology = deployment.root / "topology.yml"
        if not deployment_topology.is_file():
            print(f"ERROR: {deployment_topology} not found", file=sys.stderr)
            sys.exit(2)
        args.host_vars = str(deployment_topology)
        args.host_vars_overlay = None
        args.out = str(deployment.generated_dir / "hosts.yml")

    host_vars_path = Path(args.host_vars)
    if not host_vars_path.exists():
        print(f"ERROR: {host_vars_path} not found", file=sys.stderr)
        sys.exit(2)

    overlay_path: Path | None = None
    if args.host_vars_overlay:
        overlay_path = Path(args.host_vars_overlay)
        if not overlay_path.exists():
            print(f"ERROR: overlay {overlay_path} not found", file=sys.stderr)
            sys.exit(2)

    out_path = Path(args.out)

    try:
        host_vars = load_host_vars_with_overlay(host_vars_path, overlay_path)
    except Exception as exc:
        src_desc = f"{host_vars_path}"
        if overlay_path:
            src_desc += f" + overlay {overlay_path}"
        print(f"ERROR loading {src_desc}: {exc}", file=sys.stderr)
        sys.exit(2)

    if args.list:
        json.dump(ansible_list(host_vars), sys.stdout, indent=2)
        print()
        return

    if args.host:
        json.dump(ansible_host(host_vars, args.host), sys.stdout, indent=2)
        print()
        return

    if args.print:
        print(generate(host_vars, overlay_path=overlay_path), end="")
        return

    if args.check:
        if check_drift(host_vars, current_path=out_path, overlay_path=overlay_path):
            print(f"{out_path} is up to date.", file=sys.stderr)
            sys.exit(0)
        diff = show_diff(host_vars, current_path=out_path, overlay_path=overlay_path)
        if diff:
            print(f"DRIFT DETECTED — {out_path} is out of date:", file=sys.stderr)
            print(diff, file=sys.stderr)
        else:
            print(
                f"DRIFT DETECTED — {out_path} does not exist or is empty.",
                file=sys.stderr,
            )
        print("Run: make generate-inventory", file=sys.stderr)
        sys.exit(1)

    if args.write:
        content = generate(host_vars, overlay_path=overlay_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content)
        guests = host_vars.get("proxmox_guests", [])
        staging_count = sum(1 for g in guests if g.get("has_staging", False))
        overlay_note = f" (overlay: {overlay_path})" if overlay_path else ""
        print(
            f"Written {out_path}{overlay_note} — {len(guests)} production guests, "
            f"{staging_count} staging counterparts.",
            file=sys.stderr,
        )
        # ADR 0437 — when generating an overlay inventory, also emit the merged
        # host_vars/proxmox-host.yml alongside it. Ansible only auto-discovers
        # host_vars from directories co-located with the inventory file; if the
        # fork's overlay host_vars stays at .local/host_vars/ (parallel to
        # .local/inventory/), Ansible never reads it and the committed
        # inventory/host_vars/proxmox-host.yml wins during Stage 4 guest
        # provisioning — producing guests on the committed subnet while the
        # overlay inventory tries to SSH to the fork's intended subnet.
        # Writing the merged host_vars next to the overlay inventory makes the
        # overlay self-contained so ansible-inventory discovers it without any
        # extra wiring.
        if overlay_path is not None:
            host_vars_dir = out_path.parent / "host_vars"
            host_vars_dir.mkdir(parents=True, exist_ok=True)
            merged_host_vars_path = host_vars_dir / "proxmox-host.yml"
            merged_header = (
                "# =============================================================================\n"
                "# GENERATED (overlay mode) — do not edit manually.\n"
                "# Emitted alongside overlay inventory so ansible host_vars discovery\n"
                "# picks up the fork's merged proxmox_guests + network values.\n"
                f"# Run: PLATFORM_IDENTITY_OVERLAY=<path> make generate-inventory\n"
                f"# Sources: inventory/host_vars/proxmox-host.yml + {overlay_path}\n"
                "# ADR 0437 — overlay-aware bootstrap.\n"
                "# =============================================================================\n"
            )
            # Enrich platform_service_topology with computed fields from the generated
            # platform.yml (group_vars). host_vars override group_vars in Ansible, so
            # the topology dict here would otherwise shadow urls, ports, and other fields
            # that generate_platform_vars.py computes — causing platform_service_url()
            # and platform_service_port() filter failures at runtime.
            _TOPOLOGY_ENRICH_KEYS = (
                "urls",
                "ports",
                "service_id",
                "runtime_pool",
                "deployment_surface",
                "restart_domain",
                "api_contract_ref",
                "mobility_tier",
            )
            if PLATFORM_YML_PATH.exists():
                with open(PLATFORM_YML_PATH) as _pf:
                    platform_group_vars = yaml.safe_load(_pf) or {}
                platform_topo = platform_group_vars.get("platform_service_topology", {})
                overlay_topo = host_vars.get("platform_service_topology", {})
                for svc_id, svc_data in overlay_topo.items():
                    for _key in _TOPOLOGY_ENRICH_KEYS:
                        if not svc_data.get(_key) and platform_topo.get(svc_id, {}).get(_key):
                            svc_data[_key] = platform_topo[svc_id][_key]
            merged_host_vars_path.write_text(
                merged_header + yaml.safe_dump(host_vars, sort_keys=False, default_flow_style=False)
            )
            print(
                f"Written {merged_host_vars_path} — merged host_vars for ansible discovery.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
