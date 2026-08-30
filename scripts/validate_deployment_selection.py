#!/usr/bin/env python3
"""Fail-closed deployment selector validation for sensitive live workflows.

The guard evaluates the selected inventory locally without running a playbook
or contacting the deployment. An explicit identity and topology must agree
with the tracked ``platform_generation`` snapshot, service ownership, and the
exact inventory sources that the subsequent scoped run will consume.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRACKED_PLATFORM = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"
DEFAULT_SERVICE_REGISTRY = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
DEFAULT_INVENTORY = REPO_ROOT / "inventory" / "hosts.yml"
IDENTITY_FINGERPRINT_KEYS = {
    "host_public_hostname",
    "management_gateway4",
    "management_interface",
    "management_ipv4",
    "management_ipv6",
    "management_ipv6_cidr",
    "platform_domain",
}
REQUIRED_IDENTITY_FINGERPRINT_KEYS = {
    "host_public_hostname",
    "management_gateway4",
    "management_interface",
    "management_ipv4",
    "platform_domain",
}
FORBIDDEN_IDENTITY_KEYS = {
    "groups",
    "hostvars",
    "lv3_service_topology",
    "platform_service_registry",
    "platform_service_topology",
    "proxmox_guests",
}
SECRET_LIKE_IDENTITY_SUFFIXES = ("_api_key", "_password", "_secret", "_token")


class DeploymentSelectionError(RuntimeError):
    """Raised when selected deployment inputs do not form one deployment."""


def _load_mapping(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise DeploymentSelectionError(f"{label} is not a file: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DeploymentSelectionError(f"cannot read {label} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DeploymentSelectionError(f"{label} must contain a YAML mapping: {path}")
    return payload


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeploymentSelectionError(f"{label} must be a mapping")
    return value


def _nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeploymentSelectionError(f"{label} must be a non-empty string")
    return value.strip()


def _guest_map(payload: dict[str, Any], *, label: str) -> dict[str, dict[str, Any]]:
    guests = payload.get("proxmox_guests")
    if not isinstance(guests, list) or not guests:
        raise DeploymentSelectionError(f"{label}.proxmox_guests must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for index, raw_guest in enumerate(guests):
        guest = _mapping(raw_guest, label=f"{label}.proxmox_guests[{index}]")
        name = _nonempty_string(guest.get("name"), label=f"{label}.proxmox_guests[{index}].name")
        address = _nonempty_string(guest.get("ipv4"), label=f"{label}.proxmox_guests[{index}].ipv4")
        if name in result:
            raise DeploymentSelectionError(f"{label}.proxmox_guests contains duplicate guest {name!r}")
        result[name] = {**guest, "ipv4": address}
    return result


def _tracked_guest_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    catalog = _mapping(payload.get("platform_guest_catalog"), label="tracked platform_guest_catalog")
    by_name = _mapping(catalog.get("by_name"), label="tracked platform_guest_catalog.by_name")
    result: dict[str, dict[str, Any]] = {}
    for name, raw_guest in by_name.items():
        guest = _mapping(raw_guest, label=f"tracked platform_guest_catalog.by_name.{name}")
        result[str(name)] = guest
    if not result:
        raise DeploymentSelectionError("tracked platform_guest_catalog.by_name must not be empty")
    return result


def _inventory_hosts(
    inventory_paths: list[Path],
    *,
    environment: str,
    ansible_inventory_bin: str,
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    command = [ansible_inventory_bin]
    for path in inventory_paths:
        if not path.is_file():
            raise DeploymentSelectionError(f"selected inventory is not a file: {path}")
        command.extend(["-i", str(path)])
    command.extend(["--list", "-e", f"env={environment}"])
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        raise DeploymentSelectionError("ansible-inventory could not evaluate the selected inventory") from None
    if result.returncode != 0:
        raise DeploymentSelectionError("ansible-inventory rejected the selected inventory")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise DeploymentSelectionError("ansible-inventory returned invalid JSON") from None
    inventory = _mapping(payload, label="effective Ansible inventory")
    metadata = _mapping(inventory.get("_meta"), label="effective Ansible inventory._meta")
    raw_hostvars = _mapping(metadata.get("hostvars"), label="effective Ansible inventory._meta.hostvars")
    hostvars = {str(name): _mapping(value, label=f"effective hostvars.{name}") for name, value in raw_hostvars.items()}

    def expand_group(group_name: str, seen: set[str] | None = None) -> set[str]:
        active = set() if seen is None else set(seen)
        if group_name in active:
            raise DeploymentSelectionError("effective inventory contains a recursive production group")
        active.add(group_name)
        group = _mapping(inventory.get(group_name), label=f"effective inventory group {group_name}")
        hosts = {str(name) for name in group.get("hosts", [])}
        children = group.get("children", [])
        if not isinstance(children, list) or not all(isinstance(child, str) for child in children):
            raise DeploymentSelectionError(f"effective inventory group {group_name} has invalid children")
        for child in children:
            hosts.update(expand_group(child, active))
        return hosts

    return expand_group("production"), hostvars


def _compare_identity(
    selected_identity: dict[str, Any],
    tracked_platform: dict[str, Any],
) -> str:
    generation = _mapping(tracked_platform.get("platform_generation"), label="tracked platform_generation")
    tracked_identity = _mapping(
        generation.get("identity_overlay"), label="tracked platform_generation.identity_overlay"
    )
    selected_projection = {
        key: value
        for key, value in selected_identity.items()
        if key in IDENTITY_FINGERPRINT_KEYS and isinstance(value, (str, int, bool)) and "{{" not in str(value)
    }
    if not REQUIRED_IDENTITY_FINGERPRINT_KEYS.issubset(tracked_identity):
        missing = sorted(REQUIRED_IDENTITY_FINGERPRINT_KEYS - set(tracked_identity))
        raise DeploymentSelectionError(
            "tracked platform_generation.identity_overlay is missing canonical fields: " + ", ".join(missing)
        )
    if tracked_identity != selected_projection:
        raise DeploymentSelectionError(
            "selected identity fingerprint does not exactly match tracked platform_generation"
        )

    if not all(isinstance(key, str) for key in selected_identity):
        raise DeploymentSelectionError("selected identity keys must be strings")
    unsafe_keys = sorted(
        key
        for key in selected_identity
        if key in FORBIDDEN_IDENTITY_KEYS
        or key.startswith("ansible_")
        or key.lower().endswith(SECRET_LIKE_IDENTITY_SUFFIXES)
    )
    if unsafe_keys:
        raise DeploymentSelectionError(
            "selected identity contains forbidden structural, connection, or secret-like keys: "
            + ", ".join(unsafe_keys)
        )

    domain = _nonempty_string(selected_identity.get("platform_domain"), label="selected platform_domain")
    canonical_prefix = domain.split(".", 1)[0]
    selected_prefix = selected_identity.get("platform_config_prefix")
    if selected_prefix is not None and selected_prefix != canonical_prefix:
        raise DeploymentSelectionError("selected platform_config_prefix does not match the canonical domain prefix")
    tracked_host = _mapping(tracked_platform.get("platform_host"), label="tracked platform_host")
    tracked_management = _mapping(tracked_host.get("management"), label="tracked platform_host.management")
    if "management_ipv4" in selected_identity and selected_identity["management_ipv4"] != tracked_management.get(
        "ipv4"
    ):
        raise DeploymentSelectionError(
            "selected identity management_ipv4 does not match tracked platform_host.management.ipv4"
        )
    return domain


def validate_deployment_selection(
    *,
    identity_path: Path,
    topology_path: Path,
    inventory_paths: list[Path],
    services: list[str],
    required_hosts: list[str],
    environment: str,
    tracked_platform_path: Path = DEFAULT_TRACKED_PLATFORM,
    service_registry_path: Path = DEFAULT_SERVICE_REGISTRY,
    ansible_inventory_bin: str = "ansible-inventory",
) -> dict[str, Any]:
    """Validate a complete selection and return non-secret resolved facts."""

    if environment != "production":
        raise DeploymentSelectionError("sensitive deployment workflows require environment=production")
    selected_identity = _load_mapping(identity_path, label="selected identity")
    selected_topology = _load_mapping(topology_path, label="selected topology")
    tracked_platform = _load_mapping(tracked_platform_path, label="tracked platform variables")
    service_registry_payload = _load_mapping(service_registry_path, label="service registry")
    service_registry = _mapping(
        service_registry_payload.get("platform_service_registry"), label="platform_service_registry"
    )

    domain = _compare_identity(selected_identity, tracked_platform)
    selected_topology_host = selected_identity.get("platform_topology_host")
    allowed_topology_hosts = {topology_path.stem, "{{ groups['proxmox_hosts'][0] }}"}
    if selected_topology_host is not None and selected_topology_host not in allowed_topology_hosts:
        raise DeploymentSelectionError("selected platform_topology_host does not match the topology selector")
    selected_guests = _guest_map(selected_topology, label="selected topology")
    tracked_guests = _tracked_guest_map(tracked_platform)

    tracked_host = _mapping(tracked_platform.get("platform_host"), label="tracked platform_host")
    tracked_network = _mapping(tracked_host.get("network"), label="tracked platform_host.network")
    if selected_topology.get("proxmox_internal_ipv4") != tracked_network.get("internal_ipv4"):
        raise DeploymentSelectionError(
            "selected topology proxmox_internal_ipv4 does not match tracked platform_host.network.internal_ipv4"
        )

    selected_guest_addresses = {name: guest["ipv4"] for name, guest in selected_guests.items()}
    tracked_guest_addresses = {
        name: _nonempty_string(guest.get("ipv4"), label=f"tracked guest {name}.ipv4")
        for name, guest in tracked_guests.items()
    }
    if selected_guest_addresses != tracked_guest_addresses:
        differing = sorted(
            name
            for name in set(selected_guest_addresses) | set(tracked_guest_addresses)
            if selected_guest_addresses.get(name) != tracked_guest_addresses.get(name)
        )
        raise DeploymentSelectionError(
            "selected topology guest addresses do not match tracked platform_generation: " + ", ".join(differing)
        )

    selected_service_topology = _mapping(
        selected_topology.get("platform_service_topology"), label="selected platform_service_topology"
    )
    tracked_service_topology = _mapping(
        tracked_platform.get("platform_service_topology"), label="tracked platform_service_topology"
    )

    expected_hosts = set(required_hosts)
    resolved_services: dict[str, str] = {}
    for service_name in services:
        registry_entry = _mapping(service_registry.get(service_name), label=f"platform_service_registry.{service_name}")
        expected_owner = _nonempty_string(
            registry_entry.get("host_group"), label=f"platform_service_registry.{service_name}.host_group"
        )
        selected_service = _mapping(
            selected_service_topology.get(service_name),
            label=f"selected platform_service_topology.{service_name}",
        )
        tracked_service = _mapping(
            tracked_service_topology.get(service_name),
            label=f"tracked platform_service_topology.{service_name}",
        )
        for source_label, service_entry in (
            ("selected topology", selected_service),
            ("tracked platform", tracked_service),
        ):
            owner = _nonempty_string(service_entry.get("owning_vm"), label=f"{source_label} {service_name}.owning_vm")
            if owner != expected_owner:
                raise DeploymentSelectionError(
                    f"{source_label} owner for {service_name!r} is {owner!r}; "
                    f"service registry requires {expected_owner!r}"
                )
        expected_ip = selected_guest_addresses.get(expected_owner)
        if not expected_ip:
            raise DeploymentSelectionError(
                f"service {service_name!r} owner {expected_owner!r} is absent from selected topology guests"
            )
        if tracked_service.get("private_ip") != expected_ip:
            raise DeploymentSelectionError(
                f"tracked platform private_ip for {service_name!r} does not match owner {expected_owner!r}"
            )
        public_hostname = tracked_service.get("public_hostname")
        if public_hostname is not None and not str(public_hostname).endswith(f".{domain}"):
            raise DeploymentSelectionError(
                f"tracked public hostname for {service_name!r} does not match selected domain"
            )
        expected_hosts.add(expected_owner)
        resolved_services[service_name] = expected_owner

    effective_inventory_paths = inventory_paths or [DEFAULT_INVENTORY]
    production_hosts, inventory_hosts = _inventory_hosts(
        effective_inventory_paths,
        environment=environment,
        ansible_inventory_bin=ansible_inventory_bin,
    )
    for host in sorted(expected_hosts):
        if host not in selected_guests:
            raise DeploymentSelectionError(f"required host {host!r} is absent from selected topology guests")
        if host not in production_hosts:
            raise DeploymentSelectionError(f"required host {host!r} is absent from selected production inventory")
        inventory_host = _mapping(inventory_hosts.get(host), label=f"selected inventory host {host}")
        inventory_address = _nonempty_string(
            inventory_host.get("ansible_host"), label=f"selected inventory host {host}.ansible_host"
        )
        if inventory_address != selected_guest_addresses[host]:
            raise DeploymentSelectionError(
                f"selected inventory address for {host!r} does not match selected/tracked topology"
            )

    return {
        "platform_domain": domain,
        "services": resolved_services,
        "required_hosts": sorted(expected_hosts),
        "environment": environment,
        "inventory_paths": [str(path.resolve()) for path in effective_inventory_paths],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate explicit deployment identity/topology/inventory selectors before a sensitive mutation."
    )
    parser.add_argument("--identity-file", required=True, type=Path)
    parser.add_argument("--topology-file", required=True, type=Path)
    parser.add_argument("--inventory-file", action="append", type=Path, default=[])
    parser.add_argument("--service", action="append", default=[])
    parser.add_argument("--required-host", action="append", default=[])
    parser.add_argument("--environment", required=True)
    parser.add_argument("--tracked-platform", type=Path, default=DEFAULT_TRACKED_PLATFORM)
    parser.add_argument("--service-registry", type=Path, default=DEFAULT_SERVICE_REGISTRY)
    parser.add_argument("--ansible-inventory-bin", default="ansible-inventory", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = validate_deployment_selection(
            identity_path=args.identity_file,
            topology_path=args.topology_file,
            inventory_paths=args.inventory_file,
            services=args.service,
            required_hosts=args.required_host,
            environment=args.environment,
            tracked_platform_path=args.tracked_platform,
            service_registry_path=args.service_registry,
            ansible_inventory_bin=args.ansible_inventory_bin,
        )
    except DeploymentSelectionError as exc:
        print(f"deployment selection rejected: {exc}", file=sys.stderr)
        return 2

    service_summary = ", ".join(f"{service}={host}" for service, host in sorted(result["services"].items()))
    print(
        "deployment selection verified: "
        f"domain={result['platform_domain']} services=[{service_summary}] "
        f"hosts={','.join(result['required_hosts'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
