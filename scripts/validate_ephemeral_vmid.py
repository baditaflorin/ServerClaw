#!/usr/bin/env python3
"""Validate that canonical managed VM declarations do not overlap the ephemeral VMID pool."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path


HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
STACK_PATH = repo_path("versions", "stack.yaml")
CAPACITY_MODEL_PATH = repo_path("config", "capacity-model.json")


def load_ephemeral_range() -> tuple[int, int]:
    payload = load_json(CAPACITY_MODEL_PATH)
    pool = payload.get("ephemeral_pool")
    if not isinstance(pool, dict):
        raise ValueError("config/capacity-model.json must define ephemeral_pool")
    vmid_range = pool.get("vmid_range")
    if not isinstance(vmid_range, list) or len(vmid_range) != 2:
        raise ValueError("config/capacity-model.json.ephemeral_pool.vmid_range must be a two-item list")
    start = int(vmid_range[0])
    end = int(vmid_range[1])
    if start > end:
        raise ValueError("config/capacity-model.json.ephemeral_pool.vmid_range must be ascending")
    return start, end


def vmid_in_range(vmid: int, vmid_range: tuple[int, int]) -> bool:
    return vmid_range[0] <= vmid <= vmid_range[1]


def append_violation(violations: list[str], vmid: int, label: str, vmid_range: tuple[int, int]) -> None:
    if vmid_in_range(vmid, vmid_range):
        violations.append(f"{label} uses reserved ephemeral VMID {vmid}")


def validate_ephemeral_vmid_ranges() -> list[str]:
    vmid_range = load_ephemeral_range()
    host_vars = load_yaml(HOST_VARS_PATH)
    stack = load_yaml(STACK_PATH)
    violations: list[str] = []

    for guest in host_vars.get("proxmox_guests", []):
        if not isinstance(guest, dict):
            continue
        vmid = guest.get("vmid")
        if isinstance(vmid, int):
            append_violation(violations, vmid, f"inventory guest {guest.get('name', 'unknown')}", vmid_range)

    template = stack.get("observed_state", {}).get("guests", {}).get("template", {})
    if isinstance(template, dict):
        vmid = template.get("vmid")
        if isinstance(vmid, int):
            append_violation(violations, vmid, "observed template", vmid_range)

    for guest in stack.get("observed_state", {}).get("guests", {}).get("instances", []):
        if not isinstance(guest, dict):
            continue
        vmid = guest.get("vmid")
        if isinstance(vmid, int):
            append_violation(violations, vmid, f"observed guest {guest.get('name', 'unknown')}", vmid_range)

    desired_vmids = stack.get("desired_state", {}).get("guest_provisioning", {}).get("guest_vmids", {})
    if isinstance(desired_vmids, dict):
        for name, vmid in desired_vmids.items():
            if isinstance(vmid, int):
                append_violation(violations, vmid, f"desired guest {name}", vmid_range)

    return violations


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="Validate and print a short status line.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        violations = validate_ephemeral_vmid_ranges()
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("validate ephemeral vmid", exc)

    if violations:
        for violation in violations:
            print(violation)
        return 1

    if args.validate:
        start, end = load_ephemeral_range()
        print(f"Ephemeral VMID range {start}-{end} is reserved for unmanaged temporary VMs only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
