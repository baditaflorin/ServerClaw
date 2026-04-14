#!/usr/bin/env python3
"""Detect (and optionally remove) containers running on VMs where they don't belong.

ADR 0417 — Service VM Migration IaC.

An orphaned container is one where:
  - The container is running on VM X
  - platform_service_registry says the service should run on VM Y (Y ≠ X)

This happens when a service is migrated to a new VM but the old container is
never cleaned up. The migration script (migrate_service.py) prevents this in
new migrations; this tool finds and cleans up existing orphans.

Usage:
    python scripts/detect_orphaned_containers.py --list            # report orphans
    python scripts/detect_orphaned_containers.py --purge           # stop & remove orphans
    python scripts/detect_orphaned_containers.py --list --mock fixtures/docker-ps.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

SERVICES_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
PLATFORM_YML_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"
SSH_KEY = REPO_ROOT / ".local" / "ssh" / "bootstrap.id_ed25519"
JUMP_HOST = "ops@10.10.10.1"
SSH_USER = "ops"


def _load_yaml(path: Path) -> Any:
    with path.open() as f:
        return yaml.safe_load(f)


def load_registry() -> dict[str, dict]:
    raw = _load_yaml(SERVICES_PATH)
    return raw.get("platform_service_registry", {})


def load_guest_catalog() -> dict[str, dict]:
    """Return {name: {ipv4: ...}} mapping from platform_guest_catalog."""
    try:
        raw = _load_yaml(PLATFORM_YML_PATH)
        return raw.get("platform_guest_catalog", {}).get("by_name", {})
    except Exception:
        return {}


def build_expected_containers(registry: dict[str, dict]) -> dict[str, str]:
    """Return {container_name: expected_vm} from the service registry.

    Only covers docker_compose services with a known container_name or
    a derivable default (lv3-<service_name>).
    """
    expected: dict[str, str] = {}
    for svc_name, svc in registry.items():
        if svc.get("service_type") != "docker_compose":
            continue
        host_group = svc.get("host_group", "")
        if not host_group:
            continue
        container = svc.get("container_name", svc_name)
        expected[container] = host_group
    return expected


def ssh_get_containers(vm_name: str, vm_ip: str, *, mock: dict | None = None) -> list[str]:
    """Return list of running container names on vm_name.

    If mock is provided, returns mock[vm_name] instead of SSHing.
    """
    if mock is not None:
        return mock.get(vm_name, [])

    if not SSH_KEY.exists():
        print(f"  WARN: SSH key not found at {SSH_KEY} — skipping {vm_name}", file=sys.stderr)
        return []

    cmd = [
        "ssh",
        "-i",
        str(SSH_KEY),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        f"ProxyCommand=ssh -i {SSH_KEY} -o StrictHostKeyChecking=no -W %h:%p {JUMP_HOST}",
        f"{SSH_USER}@{vm_ip}",
        "docker ps --format '{{.Names}}' 2>/dev/null || echo ''",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  WARN: docker ps failed on {vm_name}: {result.stderr.strip()}", file=sys.stderr)
            return []
        return [name.strip() for name in result.stdout.splitlines() if name.strip()]
    except subprocess.TimeoutExpired:
        print(f"  WARN: SSH timeout on {vm_name}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  WARN: SSH error on {vm_name}: {e}", file=sys.stderr)
        return []


def stop_container_on_vm(vm_ip: str, container_name: str) -> bool:
    """Stop and remove a container on the specified VM via SSH."""
    if not SSH_KEY.exists():
        print(f"  ERROR: SSH key not found at {SSH_KEY}", file=sys.stderr)
        return False

    cmd_stop = [
        "ssh",
        "-i",
        str(SSH_KEY),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        f"ProxyCommand=ssh -i {SSH_KEY} -o StrictHostKeyChecking=no -W %h:%p {JUMP_HOST}",
        f"{SSH_USER}@{vm_ip}",
        f"docker stop {container_name} && docker rm {container_name}",
    ]
    try:
        result = subprocess.run(cmd_stop, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return False


Orphan = dict  # {container, found_on_vm, expected_vm, vm_ip}


def detect_orphans(
    registry: dict[str, dict],
    guest_catalog: dict[str, dict],
    *,
    mock: dict | None = None,
) -> list[Orphan]:
    """Scan all known VMs for containers that shouldn't be there."""
    expected = build_expected_containers(registry)

    # Only scan VMs that host at least one docker_compose service
    docker_vms = set(expected.values())

    orphans: list[Orphan] = []
    for vm_name, vm_data in guest_catalog.items():
        if vm_name not in docker_vms:
            continue
        vm_ip = vm_data.get("ipv4", "")
        if not vm_ip:
            continue

        print(f"  Scanning {vm_name} ({vm_ip})...")
        running = ssh_get_containers(vm_name, vm_ip, mock=mock)

        for container in running:
            expected_vm = expected.get(container)
            if expected_vm is not None and expected_vm != vm_name:
                orphans.append(
                    {
                        "container": container,
                        "found_on_vm": vm_name,
                        "found_on_ip": vm_ip,
                        "expected_vm": expected_vm,
                        "expected_ip": guest_catalog.get(expected_vm, {}).get("ipv4", "?"),
                    }
                )

    return orphans


def print_orphan_report(orphans: list[Orphan]) -> None:
    if not orphans:
        print("\n✓ No orphaned containers detected.")
        return
    print(f"\n⚠  {len(orphans)} orphaned container(s) detected:\n")
    print(f"  {'CONTAINER':<35}  {'FOUND ON':<20}  {'EXPECTED ON':<20}")
    print("  " + "-" * 80)
    for o in orphans:
        print(f"  {o['container']:<35}  {o['found_on_vm']:<20}  {o['expected_vm']:<20}")
    print()
    print("To remove orphans:")
    print("  python scripts/detect_orphaned_containers.py --purge")
    print("  Or manually per VM:")
    for o in orphans:
        print(
            f"  ssh -J {JUMP_HOST} {SSH_USER}@{o['found_on_ip']}"
            f" 'docker stop {o['container']} && docker rm {o['container']}'"
        )


def purge_orphans(orphans: list[Orphan], guest_catalog: dict[str, dict]) -> int:
    """Stop and remove all orphaned containers. Returns count of failures."""
    failures = 0
    for o in orphans:
        print(f"  Stopping {o['container']} on {o['found_on_vm']} ({o['found_on_ip']})...")
        ok = stop_container_on_vm(o["found_on_ip"], o["container"])
        if ok:
            print("    ✓ Removed")
        else:
            print("    ✗ Failed — remove manually:")
            print(
                f"      ssh -J {JUMP_HOST} {SSH_USER}@{o['found_on_ip']}"
                f" 'docker stop {o['container']} && docker rm {o['container']}'"
            )
            failures += 1
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="Report orphaned containers")
    mode.add_argument("--purge", action="store_true", help="Stop and remove orphaned containers")
    parser.add_argument(
        "--mock",
        metavar="JSON_FILE",
        help="Load mock docker ps output from JSON file (for testing): {vm_name: [container, ...]}",
    )
    args = parser.parse_args()

    mock: dict | None = None
    if args.mock:
        mock_path = Path(args.mock)
        if not mock_path.exists():
            sys.exit(f"ERROR: mock file not found: {args.mock}")
        mock = json.loads(mock_path.read_text())

    registry = load_registry()
    guest_catalog = load_guest_catalog()

    if not guest_catalog:
        sys.exit(
            "ERROR: platform_guest_catalog is empty or unreadable.\n"
            "  Ensure inventory/group_vars/platform.yml exists and is generated."
        )

    print("Scanning VMs for orphaned containers (ADR 0417)...")
    orphans = detect_orphans(registry, guest_catalog, mock=mock)
    print_orphan_report(orphans)

    if args.purge and orphans:
        print(f"\nPurging {len(orphans)} orphan(s)...")
        failures = purge_orphans(orphans, guest_catalog)
        if failures:
            print(f"\n✗ {failures} container(s) could not be removed — see above.")
            return 1
        print("\n✓ All orphaned containers removed.")

    return 1 if (args.list and orphans) else 0


if __name__ == "__main__":
    sys.exit(main())
