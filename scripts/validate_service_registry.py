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

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402 — must come after sys.path adjustment
from validation_toolkit import load_yaml_with_identity, require_int, require_mapping, require_str  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
IMAGE_CATALOG_PATH = REPO_ROOT / "config" / "image-catalog.json"
ROLES_DIR = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"

REQUIRED_FIELDS = ("image_catalog_key", "internal_port", "host_group")


def load_registry() -> dict:
    data = load_yaml_with_identity(REGISTRY_PATH)
    return require_mapping(data, str(REGISTRY_PATH))


def load_image_catalog() -> dict | None:
    if not IMAGE_CATALOG_PATH.exists():
        return None
    with IMAGE_CATALOG_PATH.open() as f:
        data = json.load(f)
    return data.get("images", {})


def discover_runtime_roles() -> list[str]:
    """Return role names for all *_runtime roles found on disk."""
    roles = []
    if not ROLES_DIR.exists():
        return roles
    for entry in sorted(ROLES_DIR.iterdir()):
        if entry.is_dir() and entry.name.endswith("_runtime"):
            roles.append(entry.name)
    return roles


def validate_entry(service_name: str, entry: object, image_catalog: dict | None) -> list[str]:
    """Validate a single registry entry. Returns a list of error strings."""
    errors: list[str] = []
    path = f"platform_service_registry.{service_name}"

    try:
        entry = require_mapping(entry, path)
    except ValueError as exc:
        return [str(exc)]

    # Validate required fields
    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"{path}.{field} is required but missing")

    # image_catalog_key: may be empty string (no catalog entry) or a valid catalog key
    image_catalog_key = entry.get("image_catalog_key", "")
    try:
        require_str(image_catalog_key, f"{path}.image_catalog_key", allow_empty=True)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if image_catalog_key and image_catalog is not None:
            if image_catalog_key not in image_catalog:
                errors.append(
                    f"{path}.image_catalog_key '{image_catalog_key}' not found in"
                    f" config/image-catalog.json"
                )

    # internal_port: must be a positive integer
    if "internal_port" in entry:
        try:
            require_int(entry["internal_port"], f"{path}.internal_port", minimum=1, maximum=65535)
        except ValueError as exc:
            errors.append(str(exc))

    # host_group: must be a non-empty string
    if "host_group" in entry:
        try:
            require_str(entry["host_group"], f"{path}.host_group")
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

    return errors


def check(registry: dict, image_catalog: dict | None, runtime_roles: list[str]) -> tuple[list[str], list[str]]:
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
        errors.extend(validate_entry(service_name, entry, image_catalog))

    # Check for duplicate keys (YAML itself prevents true dupes, but confirm)
    registered_names = set(service_map.keys())

    # Warn about *_runtime roles that have no registry entry
    for role_name in runtime_roles:
        # Convert role name to registry key: strip _runtime suffix
        service_key = role_name[: -len("_runtime")]
        if service_key not in registered_names:
            warnings.append(
                f"Runtime role '{role_name}' has no entry in platform_service_registry"
                f" (expected key: '{service_key}')"
            )

    return errors, warnings


def cmd_check(args: argparse.Namespace) -> int:
    registry = load_registry()
    image_catalog = load_image_catalog()
    runtime_roles = discover_runtime_roles()

    errors, warnings = check(registry, image_catalog, runtime_roles)

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
    registry = load_registry()
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
    parser = argparse.ArgumentParser(
        description="Validate the platform service registry (ADR 0373)."
    )
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
