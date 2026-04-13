#!/usr/bin/env python3
"""Validate the platform service registry (inventory/group_vars/platform_services.yml).

ADR 0373 — Service Registry and Derived Defaults.

Usage:
    python scripts/validate_service_registry.py --check   # validate and exit
    python scripts/validate_service_registry.py --list    # list all registered services
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from identity_yaml import load_yaml_with_identity, resolve_jinja2_vars
from validation_toolkit import (
    require_enum,
    require_int,
    require_mapping,
    require_str,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
INVENTORY_PATH = REPO_ROOT / "inventory" / "hosts.yml"
IMAGE_CATALOG_PATH = REPO_ROOT / "config" / "image-catalog.json"
ROLES_DIR = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"

SERVICE_TYPES = {"docker_compose", "system_package", "infrastructure", "multi_instance"}
NULLABLE_PORT_SERVICE_TYPES = {"system_package", "infrastructure"}
CATALOG_VALIDATED_SERVICE_TYPES = {"docker_compose"}


def _make_unique_key_loader(path: Path) -> type[yaml.SafeLoader]:
    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict:
        mapping: dict = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                line = key_node.start_mark.line + 1
                raise ValueError(f"Duplicate key {key!r} in {path} at line {line}")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    return UniqueKeyLoader


def load_registry_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    resolved = resolve_jinja2_vars(raw)
    data = yaml.load(resolved, Loader=_make_unique_key_loader(path))
    return require_mapping(data, str(path))


def load_registry() -> dict:
    return load_registry_file(REGISTRY_PATH)


def load_image_catalog() -> dict | None:
    if not IMAGE_CATALOG_PATH.exists():
        return None
    with IMAGE_CATALOG_PATH.open() as f:
        data = json.load(f)
    return data.get("images", {})


def load_inventory_names() -> set[str]:
    data = load_yaml_with_identity(INVENTORY_PATH)
    names: set[str] = set()

    def visit(node: object, *, node_name: str | None = None) -> None:
        if node_name:
            names.add(node_name)
        if not isinstance(node, dict):
            return

        hosts = node.get("hosts")
        if isinstance(hosts, dict):
            names.update(str(host) for host in hosts.keys())

        children = node.get("children")
        if isinstance(children, dict):
            for child_name, child_node in children.items():
                visit(child_node, node_name=str(child_name))

    if isinstance(data, dict):
        for top_name, top_node in data.items():
            visit(top_node, node_name=str(top_name))

    return names


def discover_runtime_roles() -> list[str]:
    """Return role names for all *_runtime roles found on disk."""
    roles = []
    if not ROLES_DIR.exists():
        return roles
    for entry in sorted(ROLES_DIR.iterdir()):
        if entry.is_dir() and entry.name.endswith("_runtime"):
            roles.append(entry.name)
    return roles


def validate_entry(
    service_name: str,
    entry: object,
    image_catalog: dict | None,
    inventory_names: set[str],
) -> list[str]:
    """Validate a single registry entry. Returns a list of error strings."""
    errors: list[str] = []
    path = f"platform_service_registry.{service_name}"

    try:
        entry = require_mapping(entry, path)
    except ValueError as exc:
        return [str(exc)]

    service_type_value: str | None = None
    if "service_type" not in entry:
        errors.append(f"{path}.service_type is required but missing")
    else:
        try:
            service_type_value = require_enum(entry["service_type"], f"{path}.service_type", SERVICE_TYPES)
        except ValueError as exc:
            errors.append(str(exc))

    if "host_group" not in entry:
        errors.append(f"{path}.host_group is required but missing")
    else:
        try:
            host_group = require_str(entry["host_group"], f"{path}.host_group")
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if host_group not in inventory_names:
                errors.append(f"{path}.host_group '{host_group}' not found in inventory hosts/groups")

    image_catalog_key = entry.get("image_catalog_key")
    if service_type_value in CATALOG_VALIDATED_SERVICE_TYPES and "image_catalog_key" not in entry:
        errors.append(f"{path}.image_catalog_key is required but missing")
    else:
        if image_catalog_key is not None:
            try:
                image_catalog_key = require_str(image_catalog_key, f"{path}.image_catalog_key", allow_empty=True)
            except ValueError as exc:
                errors.append(str(exc))
            else:
                if (
                    service_type_value in CATALOG_VALIDATED_SERVICE_TYPES
                    and image_catalog_key
                    and image_catalog is not None
                    and image_catalog_key not in image_catalog
                ):
                    errors.append(
                        f"{path}.image_catalog_key '{image_catalog_key}' not found in config/image-catalog.json"
                    )

    if "internal_port" not in entry:
        errors.append(f"{path}.internal_port is required but missing")
    elif service_type_value in NULLABLE_PORT_SERVICE_TYPES:
        if entry["internal_port"] is not None:
            try:
                require_int(entry["internal_port"], f"{path}.internal_port", minimum=1, maximum=65535)
            except ValueError as exc:
                errors.append(str(exc))
    else:
        try:
            require_int(entry["internal_port"], f"{path}.internal_port", minimum=1, maximum=65535)
        except ValueError as exc:
            errors.append(str(exc))

    # optional string fields
    for opt_field in ("site_dir", "secret_dir", "container_name", "local_artifact_dir"):
        if opt_field in entry:
            try:
                require_str(entry[opt_field], f"{path}.{opt_field}")
            except ValueError as exc:
                errors.append(str(exc))

    # optional bool fields
    for bool_field in ("needs_openbao", "needs_redis", "needs_postgres"):
        if bool_field in entry:
            val = entry[bool_field]
            if not isinstance(val, bool):
                errors.append(f"{path}.{bool_field} must be a boolean (got {type(val).__name__})")

    # extra_defaults: must be a mapping if present
    if "extra_defaults" in entry:
        try:
            require_mapping(entry["extra_defaults"], f"{path}.extra_defaults")
        except ValueError as exc:
            errors.append(str(exc))

    if "state_dirs" in entry:
        try:
            state_dirs = require_mapping(entry["state_dirs"], f"{path}.state_dirs")
        except ValueError as exc:
            errors.append(str(exc))
        else:
            for key in ("config", "data", "secrets"):
                if key not in state_dirs:
                    errors.append(f"{path}.state_dirs.{key} is required but missing")
                    continue
                try:
                    require_str(state_dirs[key], f"{path}.state_dirs.{key}")
                except ValueError as exc:
                    errors.append(str(exc))
    elif service_type_value == "system_package":
        errors.append(f"{path}.state_dirs is required for system_package services")

    return errors


def check(
    registry: dict,
    image_catalog: dict | None,
    runtime_roles: list[str],
    inventory_names: set[str],
) -> tuple[list[str], list[str]]:
    """Validate registry. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # Top-level structure
    if "platform_service_registry" not in registry:
        errors.append("platform_service_registry key is missing from the registry file")
        return errors, warnings

    service_map = registry["platform_service_registry"]
    try:
        service_map = require_mapping(service_map, "platform_service_registry")
    except ValueError as exc:
        errors.append(str(exc))
        return errors, warnings

    # Validate each entry
    for service_name, entry in service_map.items():
        errors.extend(validate_entry(service_name, entry, image_catalog, inventory_names))

    # Check for duplicate keys (YAML itself prevents true dupes, but confirm)
    registered_names = set(service_map.keys())

    # Warn about *_runtime roles that have no registry entry
    for role_name in runtime_roles:
        candidate_keys = [role_name]
        if role_name.endswith("_runtime"):
            candidate_keys.append(role_name[: -len("_runtime")])
        if not any(candidate in registered_names for candidate in candidate_keys):
            warnings.append(
                "Runtime role "
                f"'{role_name}' has no entry in platform_service_registry "
                f"(expected one of: {', '.join(repr(candidate) for candidate in candidate_keys)})"
            )

    return errors, warnings


def cmd_check(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
    except ValueError as exc:
        print(f"  ERROR    {exc}", file=sys.stderr)
        return 1
    image_catalog = load_image_catalog()
    inventory_names = load_inventory_names()
    runtime_roles = discover_runtime_roles()

    errors, warnings = check(registry, image_catalog, runtime_roles, inventory_names)

    service_count = len(registry.get("platform_service_registry", {}))
    print(f"platform_service_registry: {service_count} service(s) registered")

    for warning in warnings:
        print(f"  WARNING  {warning}", file=sys.stderr)

    if errors:
        for error in errors:
            print(f"  ERROR    {error}", file=sys.stderr)
        print(f"\n{len(errors)} error(s) found — FAILED", file=sys.stderr)
        return 1

    if warnings:
        print(f"\n{len(warnings)} warning(s) — registry is valid but incomplete", file=sys.stderr)
    else:
        print("  OK  service registry is valid")

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    try:
        registry = load_registry()
    except ValueError as exc:
        print(f"  ERROR    {exc}", file=sys.stderr)
        return 1
    service_map = registry.get("platform_service_registry", {})

    if not service_map:
        print("No services registered.")
        return 0

    col_w = max(len(n) for n in service_map) + 2
    header = f"{'SERVICE':<{col_w}}  {'HOST_GROUP':<30}  {'PORT':>6}  IMAGE_CATALOG_KEY"
    print(header)
    print("-" * len(header))

    for name in sorted(service_map):
        entry = service_map[name]
        host_group = entry.get("host_group", "")
        port = entry.get("internal_port", "")
        image_key = entry.get("image_catalog_key", "")
        print(f"{name:<{col_w}}  {host_group:<30}  {port:>6}  {image_key}")

    print(f"\nTotal: {len(service_map)} service(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the platform service registry (ADR 0373).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check",
        action="store_true",
        help="Validate the registry and exit non-zero on any error.",
    )
    group.add_argument(
        "--list",
        action="store_true",
        help="List all registered services in a human-readable table.",
    )
    args = parser.parse_args()

    if args.check:
        return cmd_check(args)
    if args.list:
        return cmd_list(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
