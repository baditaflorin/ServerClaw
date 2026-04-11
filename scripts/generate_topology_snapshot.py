#!/usr/bin/env python3
"""
generate_topology_snapshot.py — ADR 0344: Single-Source Environment Topology

Reads Ansible inventory files and generates scripts/topology-snapshot.json.
The generated snapshot is the single source of truth for non-Ansible tools
(e.g. proxmox_tool.py, controller_automation_toolkit.py).

Usage:
    python3 scripts/generate_topology_snapshot.py [--inventory <dir>] [--output <path>]

Flags:
    --inventory <dir>   Ansible inventory root (default: inventory/)
    --output <path>     Output JSON file (default: scripts/topology-snapshot.json)
    --write             Alias for --output default (kept for backward compat)
"""

from __future__ import annotations

import argparse
import json
import re
from platform.repo import TOPOLOGY_HOST
import sys
from datetime import datetime

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone

    UTC = timezone.utc  # type: ignore[assignment]
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# YAML loading — try PyYAML first, fall back to regex extraction
# ---------------------------------------------------------------------------

try:
    import yaml  # type: ignore[import]

    def _load_yaml(text: str) -> Any:
        return yaml.safe_load(text)

    _YAML_BACKEND = "pyyaml"
except ImportError:
    _YAML_BACKEND = "regex"

    def _load_yaml(text: str) -> Any:  # type: ignore[misc]
        """
        Minimal YAML parser using stdlib only.

        Limitations:
        - Handles simple key: value and list entries.
        - Jinja2 template expressions ({{ ... }}) in values are replaced with
          the sentinel string "<dynamic>" before parsing.
        - Complex nested blocks are parsed shallowly.
        """
        import json as _json

        # Strip Jinja2 expressions — replace with placeholder string
        cleaned = re.sub(r"\{\{[^}]*\}\}", '"<dynamic>"', text)
        # Try JSON just in case
        try:
            return _json.loads(cleaned)
        except _json.JSONDecodeError:
            pass
        # Very basic YAML parse — good enough for flat inventory files
        result: dict = {}
        current_key: str | None = None
        current_list: list | None = None

        for raw_line in cleaned.splitlines():
            line = raw_line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            # List item
            m_list = re.match(r"^(\s*)- (.+)$", line)
            if m_list and current_list is not None:
                current_list.append(m_list.group(2).strip().strip('"'))
                continue
            # Key: value
            m_kv = re.match(r"^(\s*)(\w[\w\-]*)\s*:\s*(.*)$", line)
            if m_kv:
                indent = len(m_kv.group(1))
                key = m_kv.group(2)
                val_raw = m_kv.group(3).strip()
                if indent == 0:
                    current_key = key
                    current_list = None
                    if val_raw:
                        # Remove quotes
                        val: Any = val_raw.strip('"').strip("'")
                        # Try int/bool
                        if val.isdigit():
                            val = int(val)
                        elif val.lower() in ("true", "yes"):
                            val = True
                        elif val.lower() in ("false", "no"):
                            val = False
                        result[key] = val
                    else:
                        result[key] = {}
                        current_list = None
                elif val_raw == "":
                    # Start of nested list
                    current_list = []
                    if current_key:
                        result[current_key] = current_list
        return result


# ---------------------------------------------------------------------------
# Inventory parsing helpers
# ---------------------------------------------------------------------------


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def _sanitise_jinja2(raw: str) -> str:
    """
    Remove Jinja2 template expressions so the file is valid YAML.

    Strategy (in order, per line):
    1. If the entire YAML *value* is a Jinja2 expression (possibly quoted),
       replace it with the string "<dynamic>".
    2. If a Jinja2 expression is *embedded* inside a quoted string value,
       replace just the expression with the literal text <dynamic> so the
       surrounding quotes stay intact.
    3. For bare (unquoted) Jinja2 inline expressions (e.g. "- {{ expr }}")
       replace with the string <dynamic>.

    This avoids producing double-quoted fragments like `"<dynamic>"` inside
    an already-quoted string, which would be invalid YAML.
    """
    result_lines: list[str] = []
    # Pattern: a YAML key followed by a value that is *entirely* a Jinja2 expr
    # e.g.  key: "{{ expr }}"  or  key: {{ expr }}
    entire_value_re = re.compile(
        r"^(\s*(?:- )?\w[\w\-]*\s*:\s*)"  # key part
        r'("?\{\{[^}]*\}\}"?)'  # value is purely Jinja2
        r"(\s*)$"  # optional trailing whitespace
    )
    # Pattern: Jinja2 expression embedded inside a quoted string value
    embedded_re = re.compile(r"\{\{[^}]*\}\}")

    for line in raw.splitlines(keepends=True):
        m = entire_value_re.match(line)
        if m:
            result_lines.append(f"{m.group(1)}'<dynamic>'{m.group(3)}\n")
        else:
            # Replace any remaining Jinja2 expressions in-place
            result_lines.append(embedded_re.sub("<dynamic>", line))

    return "".join(result_lines)


def _read_yaml(path: Path) -> dict | list | None:
    """Read a YAML file, return parsed content or None on error."""
    if not path.exists():
        _warn(f"File not found, skipping: {path}")
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        _warn(f"Cannot read {path}: {exc}")
        return None
    # Strip Jinja2 expressions in raw text before passing to regex backend
    # (PyYAML backend also needs this so it doesn't choke on {{ ... }})
    cleaned = _sanitise_jinja2(raw)
    try:
        return _load_yaml(cleaned)  # type: ignore[return-value]
    except Exception as exc:
        _warn(f"YAML parse error in {path}: {exc}")
        return None


def _extract_hosts_groups(hosts_yml: dict) -> dict[str, list[str]]:
    """Return {group_name: [hostname, ...]} from hosts.yml."""
    groups: dict[str, list[str]] = {}

    def _walk(node: Any, group: str | None) -> None:
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            if key == "hosts":
                if isinstance(val, dict):
                    groups.setdefault(group or "all", []).extend(val.keys())
            elif key in ("children", "vars"):
                _walk(val, group)
            else:
                _walk(val, key)

    _walk(hosts_yml, None)
    return groups


def _extract_production_hosts(hosts_yml: dict) -> dict[str, str]:
    """Return {hostname: ansible_host} for production group."""
    result: dict[str, str] = {}
    all_section = hosts_yml.get("all", hosts_yml)
    children = all_section.get("children", {})
    lv3_guests = children.get("lv3_guests", {})
    hosts = lv3_guests.get("hosts", {})
    for hostname, host_vars in hosts.items():
        if isinstance(host_vars, dict):
            ansible_host = host_vars.get("ansible_host", "<dynamic>")
            env = host_vars.get("deployment_environment", "")
            if env == "production" or (hostname.endswith("-lv3") and not hostname.endswith("-staging-lv3")):
                result[hostname] = str(ansible_host)
    return result


def _extract_proxmox_guests(host_vars: dict) -> list[dict]:
    """Extract proxmox_guests list from host_vars."""
    guests = host_vars.get("proxmox_guests", [])
    if not isinstance(guests, list):
        return []
    result = []
    for g in guests:
        if not isinstance(g, dict):
            continue
        vmid = g.get("vmid")
        name = g.get("name")
        ipv4 = g.get("ipv4")
        if vmid and name:
            result.append(
                {
                    "vmid": int(vmid) if str(vmid).isdigit() else vmid,
                    "name": str(name),
                    "ipv4": str(ipv4) if ipv4 else "<dynamic>",
                }
            )
    return result


def _extract_platform_ports(platform_yml: dict) -> dict[str, Any]:
    """Extract platform_ports mapping from platform.yml."""
    ports = platform_yml.get("platform_ports", {})
    if not isinstance(ports, dict):
        return {}
    return ports


def _extract_platform_guests(platform_yml: dict) -> list[dict]:
    """Extract proxmox_guests from platform.yml (the deduplicated list)."""
    guests = platform_yml.get("proxmox_guests", [])
    if not isinstance(guests, list):
        return []
    result = []
    for g in guests:
        if not isinstance(g, dict):
            continue
        vmid = g.get("vmid")
        name = g.get("name")
        ipv4 = g.get("ipv4")
        if vmid and name:
            result.append(
                {
                    "vmid": int(vmid) if str(vmid).isdigit() else vmid,
                    "name": str(name),
                    "ipv4": str(ipv4) if ipv4 else "<dynamic>",
                }
            )
    return result


# ---------------------------------------------------------------------------
# Topology builder
# ---------------------------------------------------------------------------


def _find_guest(guests: list[dict], name: str) -> dict | None:
    for g in guests:
        if g.get("name") == name:
            return g
    return None


def build_topology(
    inventory_dir: Path,
) -> dict:
    """Read inventory and return the topology snapshot dict."""
    hosts_yml_path = inventory_dir / "hosts.yml"
    host_vars_path = inventory_dir / "host_vars" / f"{TOPOLOGY_HOST}.yml"
    platform_yml_path = inventory_dir / "group_vars" / "platform.yml"

    generated_from = [
        "inventory/hosts.yml",
        f"inventory/host_vars/{TOPOLOGY_HOST}.yml",
        "inventory/group_vars/platform.yml",
    ]

    hosts_yml: dict = _read_yaml(hosts_yml_path) or {}
    host_vars: dict = _read_yaml(host_vars_path) or {}
    platform_yml: dict = _read_yaml(platform_yml_path) or {}

    # Collect guests from both sources (platform.yml has them fully resolved)
    guests_from_host_vars = _extract_proxmox_guests(host_vars)
    guests_from_platform = _extract_platform_guests(platform_yml)

    # Prefer platform.yml guests if available (fully resolved values)
    guests = guests_from_platform if guests_from_platform else guests_from_host_vars

    # Also fold in hosts.yml ansible_host values as a fallback for IP
    prod_hosts = _extract_production_hosts(hosts_yml)

    def _resolve_ip(name: str, guest_record: dict | None) -> str:
        if guest_record and guest_record.get("ipv4") not in (None, "<dynamic>"):
            return guest_record["ipv4"]
        return prod_hosts.get(name, "<dynamic>")

    # Platform ports
    ports = _extract_platform_ports(platform_yml)

    # Resolve specific well-known entries
    coolify_guest = _find_guest(guests, "coolify")
    coolify_apps_guest = _find_guest(guests, "coolify-apps")

    coolify_vmid = (coolify_guest or {}).get("vmid", 170)
    coolify_apps_vmid = (coolify_apps_guest or {}).get("vmid", 171)
    coolify_ip = _resolve_ip("coolify", coolify_guest)
    coolify_apps_ip = _resolve_ip("coolify-apps", coolify_apps_guest)

    coolify_dashboard_port = ports.get("coolify_dashboard_port", 8000)
    coolify_proxy_port = ports.get("coolify_proxy_port", 80)

    # Build VMs dict for prod (all production guests)
    prod_vms: dict[str, dict] = {}
    for g in guests:
        name = g["name"]
        # Only include production (non-staging) VMs
        if "staging" not in name:
            ip = _resolve_ip(name, g)
            prod_vms[name] = {
                "vmid": g["vmid"],
                "ip": ip,
            }

    # If we couldn't get guests at all, use hardcoded minimum
    if not prod_vms:
        _warn("Could not extract VM list from inventory; using hardcoded defaults")
        prod_vms = {
            "coolify": {"vmid": 170, "ip": "10.10.10.70"},
            "coolify-apps": {"vmid": 171, "ip": "10.10.10.71"},
        }

    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_from": generated_from,
        "environments": {
            "prod": {
                "node": "debian-base-template",
                "api_url": "https://proxmox.localhost:8006/api2/json",
                "vms": prod_vms,
                "services": {
                    "coolify": {
                        "dashboard_port": int(coolify_dashboard_port),
                        "db_container": "coolify-db",
                        "db_user": "coolify",
                        "app_container": "coolify",
                        "vmid": int(coolify_vmid),
                    },
                    "coolify_apps": {
                        "proxy_port": int(coolify_proxy_port),
                        "vmid": int(coolify_apps_vmid),
                    },
                },
            },
        },
    }

    return snapshot


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate scripts/topology-snapshot.json from Ansible inventory (ADR 0344).",
    )
    parser.add_argument(
        "--inventory",
        default="inventory/",
        metavar="DIR",
        help="Ansible inventory root directory (default: inventory/)",
    )
    parser.add_argument(
        "--output",
        default="scripts/topology-snapshot.json",
        metavar="PATH",
        help="Output JSON path (default: scripts/topology-snapshot.json)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Alias: write to the default output path (kept for backward compat)",
    )
    args = parser.parse_args()

    # Resolve paths relative to repo root (script lives in scripts/)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    inventory_dir = Path(args.inventory)
    if not inventory_dir.is_absolute():
        inventory_dir = repo_root / inventory_dir

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path

    print(f"YAML backend: {_YAML_BACKEND}", file=sys.stderr)
    print(f"Inventory:    {inventory_dir}", file=sys.stderr)
    print(f"Output:       {output_path}", file=sys.stderr)

    snapshot = build_topology(inventory_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
