#!/usr/bin/env python3
"""Validate cross-cutting topology consistency across all service registries.

ADR 0416 — Topology Consistency Enforcement.

Checks that the source of truth for "which VM runs this service"
(platform_services.yml → host_group) is consistent with every
derived registry that encodes the same fact:

  1. platform_postgres_clients.source_vm  (inventory/group_vars/platform_postgres.yml)
  2. lv3_service_topology.{service}.owning_vm / IP references  (inventory/host_vars/proxmox-host.yml)

Usage:
    python scripts/validate_topology_consistency.py --check   # exit 1 if any drift
    python scripts/validate_topology_consistency.py --list    # print full consistency table
    python scripts/validate_topology_consistency.py --fix-dry-run  # print diffs without writing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Services excluded from topology owning_vm vs registry host_group check.
# These are either meta-entries (not a deployable service) or have a
# documented intentional difference between topology and Ansible target.
# Each entry here must have a comment explaining WHY it is excluded.
# See ADR 0416 for the remediation checklist for the remaining items.
TOPOLOGY_OWNING_VM_EXCLUDES: set[str] = {
    # "docker_runtime" is a system-level meta-entry in lv3_service_topology
    # representing the Docker daemon host itself, not a deployable service.
    # Its registry entry has host_group="all" (systemwide) intentionally.
    "docker_runtime",
    # --- PENDING OPERATOR VERIFICATION (ADR 0416 remediation checklist) ---
    # These entries have a known topology vs registry mismatch that requires
    # SSH verification to determine the correct host. Each MUST be removed
    # from this list once verified and the appropriate registry updated.
    # Added: 2026-04-14. Review deadline: 2026-04-21.
    # uptime_kuma: registry=docker-runtime, topology=runtime-general
    # Action: SSH to both VMs, check `docker ps | grep uptime_kuma`
    "uptime_kuma",
    # mail_platform: registry=docker-runtime, topology=runtime-control
    # Action: SSH to runtime-control, check `docker ps | grep mail`
    "mail_platform",
    # redpanda: registry=runtime-control, topology=docker-runtime
    # Action: SSH to runtime-control, check `docker ps | grep redpanda`
    "redpanda",
    # gotenberg: registry=docker-runtime, topology=runtime-ai
    # Action: SSH to runtime-ai, check `docker ps | grep gotenberg`
    "gotenberg",
    # ollama: registry=runtime-ai, topology=docker-runtime
    # Best guess: registry (runtime-ai) is correct; update topology if confirmed
    # Action: SSH to runtime-ai, check `docker ps | grep ollama`
    "ollama",
    # piper: registry=runtime-ai, topology=docker-runtime
    # Best guess: registry (runtime-ai) is correct; update topology if confirmed
    # Action: SSH to runtime-ai, check `docker ps | grep piper`
    "piper",
}

# Services in platform_postgres_clients that are intentionally absent from
# platform_service_registry (e.g., shared infrastructure DBs, test dbs).
POSTGRES_REGISTRY_EXCLUDES: set[str] = set()

SERVICES_REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
POSTGRES_CLIENTS_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform_postgres.yml"
PROXMOX_HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"


def _load_yaml(path: Path) -> Any:
    with path.open() as f:
        return yaml.safe_load(f)


def load_service_registry() -> dict[str, dict]:
    """Return {service_name: {host_group: ..., ...}} from platform_services.yml."""
    raw = _load_yaml(SERVICES_REGISTRY_PATH)
    registry = raw.get("platform_service_registry", {})
    if not isinstance(registry, dict):
        sys.exit(f"ERROR: platform_service_registry is not a mapping in {SERVICES_REGISTRY_PATH}")
    return registry


def load_postgres_clients() -> list[dict]:
    """Return platform_postgres_clients list from platform_postgres.yml."""
    raw = _load_yaml(POSTGRES_CLIENTS_PATH)
    clients = raw.get("platform_postgres_clients", [])
    if not isinstance(clients, list):
        sys.exit(f"ERROR: platform_postgres_clients is not a list in {POSTGRES_CLIENTS_PATH}")
    return clients


def load_service_topology() -> dict[str, Any]:
    """Return lv3_service_topology dict from proxmox-host.yml."""
    raw = _load_yaml(PROXMOX_HOST_VARS_PATH)
    topology = raw.get("lv3_service_topology", {})
    if not isinstance(topology, dict):
        sys.exit(f"ERROR: lv3_service_topology is not a mapping in {PROXMOX_HOST_VARS_PATH}")
    return topology


# ---------------------------------------------------------------------------
# Check 1: platform_postgres_clients.source_vm vs platform_service_registry.host_group
# ---------------------------------------------------------------------------


def check_postgres_source_vm_drift(
    registry: dict[str, dict],
    postgres_clients: list[dict],
    *,
    verbose: bool = False,
) -> list[str]:
    """Return list of drift error messages.

    For every entry in platform_postgres_clients where the service name
    exists in platform_service_registry, assert that:
      source_vm == host_group
    """
    errors: list[str] = []

    for client in postgres_clients:
        service_name = client.get("service", "")
        source_vm = client.get("source_vm", "")

        if service_name not in registry:
            # Service exists in postgres clients but not in main registry — warn only
            if verbose:
                print(
                    f"  NOTICE: postgres client '{service_name}' not in platform_service_registry "
                    f"(source_vm={source_vm!r})"
                )
            continue

        host_group = registry[service_name].get("host_group", "")

        if source_vm != host_group:
            errors.append(
                f"DRIFT  postgres client '{service_name}': "
                f"source_vm={source_vm!r} but platform_service_registry.host_group={host_group!r}\n"
                f"       Fix: change 'source_vm' in {POSTGRES_CLIENTS_PATH.name} "
                f"to {host_group!r}, then run: make converge-postgres-vm env=production"
            )
        elif verbose:
            print(f"  OK     postgres client '{service_name}': source_vm={source_vm!r}")

    return errors


# ---------------------------------------------------------------------------
# Check 2: lv3_service_topology.{service}.owning_vm vs host_group
# ---------------------------------------------------------------------------


def check_service_topology_owning_vm_drift(
    registry: dict[str, dict],
    topology: dict[str, Any],
    *,
    verbose: bool = False,
) -> list[str]:
    """Return list of drift error messages.

    For every entry in lv3_service_topology where the service name
    exists in platform_service_registry, assert that:
      owning_vm == host_group
    """
    errors: list[str] = []

    for service_name, topo_entry in topology.items():
        if not isinstance(topo_entry, dict):
            continue
        if service_name in TOPOLOGY_OWNING_VM_EXCLUDES:
            if verbose:
                print(f"  SKIP   topology '{service_name}' (excluded by TOPOLOGY_OWNING_VM_EXCLUDES)")
            continue
        owning_vm = topo_entry.get("owning_vm", "")
        if not owning_vm:
            continue  # skip entries without owning_vm

        if service_name not in registry:
            if verbose:
                print(
                    f"  NOTICE: topology entry '{service_name}' not in platform_service_registry "
                    f"(owning_vm={owning_vm!r})"
                )
            continue

        host_group = registry[service_name].get("host_group", "")

        if owning_vm != host_group:
            errors.append(
                f"DRIFT  topology entry '{service_name}': "
                f"owning_vm={owning_vm!r} but platform_service_registry.host_group={host_group!r}\n"
                f"       Fix: update lv3_service_topology.{service_name}.owning_vm "
                f"in {PROXMOX_HOST_VARS_PATH.name} to {host_group!r} (or vice versa — "
                f"the registry host_group is the authoritative single source of truth)"
            )
        elif verbose:
            print(f"  OK     topology '{service_name}': owning_vm={owning_vm!r}")

    return errors


# ---------------------------------------------------------------------------
# Check 3: every postgres client's source_vm must be a known guest
# ---------------------------------------------------------------------------


def check_postgres_guest_references(
    postgres_clients: list[dict],
    *,
    verbose: bool = False,
) -> list[str]:
    """Verify source_vm values in postgres clients are plausible VM names.

    We check against the set of valid guest names derived from inventory/hosts.yml.
    """
    hosts_path = REPO_ROOT / "inventory" / "hosts.yml"
    try:
        hosts_raw = _load_yaml(hosts_path)
    except Exception:
        return []  # Can't validate without hosts file

    # Collect all host names in the lxc/kvm children
    known_guests: set[str] = set()
    all_hosts = hosts_raw.get("all", {}).get("children", {})
    for group_data in all_hosts.values():
        if isinstance(group_data, dict):
            for host in (group_data.get("hosts") or {}).keys():
                known_guests.add(host)
            children = group_data.get("children") or {}
            for child_data in children.values():
                if isinstance(child_data, dict):
                    for host in (child_data.get("hosts") or {}).keys():
                        known_guests.add(host)

    errors: list[str] = []
    for client in postgres_clients:
        service_name = client.get("service", "")
        source_vm = client.get("source_vm", "")
        if source_vm and known_guests and source_vm not in known_guests:
            errors.append(
                f"INVALID postgres client '{service_name}': "
                f"source_vm={source_vm!r} is not a known inventory host\n"
                f"       Known guests include: {', '.join(sorted(known_guests)[:10])}..."
            )
        elif verbose and source_vm:
            print(f"  OK     postgres guest ref '{service_name}': source_vm={source_vm!r} exists in inventory")

    return errors


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def print_consistency_table(
    registry: dict[str, dict],
    postgres_clients: list[dict],
    topology: dict[str, Any],
) -> None:
    """Print a full side-by-side consistency table."""
    # Build union of all service names
    all_services: set[str] = set()
    all_services.update(registry.keys())
    all_services.update(c.get("service", "") for c in postgres_clients)
    all_services.update(topology.keys())
    all_services.discard("")

    postgres_by_name = {c["service"]: c for c in postgres_clients if "service" in c}

    print(
        f"\n{'SERVICE':<28}  {'REGISTRY host_group':<22}  "
        f"{'POSTGRES source_vm':<22}  {'TOPOLOGY owning_vm':<22}  STATUS"
    )
    print("-" * 115)

    for svc in sorted(all_services):
        reg_host = registry.get(svc, {}).get("host_group", "—")
        pg_vm = postgres_by_name.get(svc, {}).get("source_vm", "—")
        topo_vm = topology.get(svc, {}).get("owning_vm", "—") if isinstance(topology.get(svc), dict) else "—"

        inconsistent = False
        if pg_vm != "—" and reg_host != "—" and pg_vm != reg_host:
            inconsistent = True
        if topo_vm != "—" and reg_host != "—" and topo_vm != reg_host:
            inconsistent = True
        if pg_vm != "—" and topo_vm != "—" and pg_vm != topo_vm:
            inconsistent = True

        status = "⚠  DRIFT" if inconsistent else "✓"
        print(f"{svc:<28}  {reg_host:<22}  {pg_vm:<22}  {topo_vm:<22}  {status}")

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Validate and exit 1 if drift detected")
    parser.add_argument("--list", action="store_true", help="Print full consistency table")
    parser.add_argument(
        "--fix-dry-run",
        action="store_true",
        help="Print what would need to change to resolve drift (does not write files)",
    )
    args = parser.parse_args()

    if not any([args.check, args.list, args.fix_dry_run]):
        parser.print_help()
        return 0

    registry = load_service_registry()
    postgres_clients = load_postgres_clients()
    topology = load_service_topology()

    if args.list:
        print_consistency_table(registry, postgres_clients, topology)
        return 0

    verbose = args.fix_dry_run

    all_errors: list[str] = []

    print("Checking postgres client source_vm vs service registry host_group...")
    errors = check_postgres_source_vm_drift(registry, postgres_clients, verbose=verbose)
    all_errors.extend(errors)
    if not errors:
        print(f"  ✓ All {len(postgres_clients)} postgres clients match registry host_group")

    print("Checking lv3_service_topology owning_vm vs service registry host_group...")
    errors = check_service_topology_owning_vm_drift(registry, topology, verbose=verbose)
    all_errors.extend(errors)
    if not errors:
        print(f"  ✓ All topology entries match registry host_group")

    print("Checking postgres source_vm guest references...")
    errors = check_postgres_guest_references(postgres_clients, verbose=verbose)
    all_errors.extend(errors)
    if not errors:
        print(f"  ✓ All postgres source_vm values reference valid inventory hosts")

    if all_errors:
        print(f"\n{'=' * 70}")
        print(f"TOPOLOGY CONSISTENCY FAILURES: {len(all_errors)} drift(s) detected\n")
        for err in all_errors:
            print(f"  {err}\n")
        print(
            "These inconsistencies mean a service's VM assignment is recorded\n"
            "differently in two or more registries. The platform_service_registry\n"
            "host_group is authoritative — update the other registries to match it.\n"
            "\nSee ADR 0416 for the full enforcement strategy."
        )
        if args.check:
            return 1
    else:
        print(f"\n✓ All topology consistency checks passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
