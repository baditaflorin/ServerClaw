#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from typing import Any, Final

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


SERVICE_REDUNDANCY_PATH: Final = repo_path("config", "service-redundancy-catalog.json")
SERVICE_REDUNDANCY_SCHEMA_PATH: Final = repo_path(
    "docs", "schema", "service-redundancy-catalog.schema.json"
)
SERVICE_CATALOG_PATH: Final = repo_path("config", "service-capability-catalog.json")
HOST_VARS_PATH: Final = repo_path("inventory", "host_vars", "proxmox_florin.yml")

TIER_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
STANDBY_KIND_BY_TIER = {"R0": "none", "R1": "cold", "R2": "warm", "R3": "active"}
LIVE_APPLY_MODE_BY_TIER = {
    "R0": "primary_only",
    "R1": "primary_only",
    "R2": "primary_and_standby",
    "R3": "multi_domain",
}
KNOWN_EMPTY_LOCATIONS = {"none", "n/a", "not_applicable", "primary-only"}


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_int(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_enum(value: Any, path: str, allowed: set[str]) -> str:
    value = require_str(value, path)
    if value not in allowed:
        raise ValueError(f"{path} must be one of {sorted(allowed)}")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        normalized_item = require_str(item, f"{path}[{index}]")
        if normalized_item in seen:
            raise ValueError(f"{path} must not contain duplicates")
        seen.add(normalized_item)
        normalized.append(normalized_item)
    return normalized


def load_redundancy_catalog() -> dict[str, Any]:
    payload = load_json(SERVICE_REDUNDANCY_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{SERVICE_REDUNDANCY_PATH} must be an object")
    return payload


def load_service_catalog_index() -> dict[str, dict[str, Any]]:
    payload = load_json(SERVICE_CATALOG_PATH)
    services = require_list(payload.get("services"), "config/service-capability-catalog.json.services")
    index: dict[str, dict[str, Any]] = {}
    for index_number, service in enumerate(services):
        service = require_mapping(service, f"config/service-capability-catalog.json.services[{index_number}]")
        service_id = require_str(service.get("id"), f"config/service-capability-catalog.json.services[{index_number}].id")
        index[service_id] = service
    return index


def active_service_ids(service_catalog_index: dict[str, dict[str, Any]]) -> list[str]:
    active_ids = []
    for service_id, service in sorted(service_catalog_index.items()):
        if service.get("lifecycle_status") == "active":
            active_ids.append(service_id)
    return active_ids


def known_locations() -> set[str]:
    host_vars = load_yaml(HOST_VARS_PATH)
    guests = require_list(host_vars.get("proxmox_guests"), "inventory/host_vars/proxmox_florin.yml.proxmox_guests")
    locations = {"proxmox_florin"}
    for index, guest in enumerate(guests):
        guest = require_mapping(guest, f"inventory/host_vars/proxmox_florin.yml.proxmox_guests[{index}]")
        locations.add(require_str(guest.get("name"), f"inventory/host_vars/proxmox_florin.yml.proxmox_guests[{index}].name"))
    return locations


def max_supported_tier_for_domains(failure_domain_count: int) -> str:
    return "R3" if failure_domain_count >= 2 else "R2"


def effective_tier(
    declared_tier: str,
    platform_max_tier: str,
    *,
    allow_fallback: bool = False,
) -> str:
    if TIER_ORDER[declared_tier] <= TIER_ORDER[platform_max_tier]:
        return declared_tier
    if not allow_fallback:
        raise ValueError(
            f"declared tier {declared_tier} exceeds the current platform limit {platform_max_tier}; "
            "downgrade the declaration or add another failure domain first"
        )
    return platform_max_tier


def validate_redundancy_catalog(catalog: dict[str, Any]) -> None:
    jsonschema.validate(
        instance=catalog,
        schema=load_json(SERVICE_REDUNDANCY_SCHEMA_PATH),
    )

    platform = require_mapping(catalog.get("platform"), "platform")
    failure_domain_count = require_int(platform.get("failure_domain_count"), "platform.failure_domain_count", 1)
    max_supported_tier = require_enum(
        platform.get("max_supported_tier"),
        "platform.max_supported_tier",
        set(TIER_ORDER),
    )
    expected_max_tier = max_supported_tier_for_domains(failure_domain_count)
    if TIER_ORDER[max_supported_tier] > TIER_ORDER[expected_max_tier]:
        raise ValueError(
            "platform.max_supported_tier exceeds what the declared failure_domain_count supports"
        )
    require_string_list(platform.get("notes"), "platform.notes")

    services = require_mapping(catalog.get("services"), "services")
    service_catalog_index = load_service_catalog_index()
    if set(services) != set(service_catalog_index):
        missing = sorted(set(service_catalog_index) - set(services))
        extra = sorted(set(services) - set(service_catalog_index))
        details = []
        if missing:
            details.append(f"missing services: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected services: {', '.join(extra)}")
        raise ValueError("service redundancy catalog must match the service capability catalog: " + "; ".join(details))

    allowed_locations = known_locations()
    for service_id, entry in services.items():
        entry = require_mapping(entry, f"services.{service_id}")
        tier = require_enum(entry.get("tier"), f"services.{service_id}.tier", set(TIER_ORDER))

        recovery_objective = require_mapping(
            entry.get("recovery_objective"),
            f"services.{service_id}.recovery_objective",
        )
        require_int(
            recovery_objective.get("rto_minutes"),
            f"services.{service_id}.recovery_objective.rto_minutes",
            1,
        )
        require_int(
            recovery_objective.get("rpo_minutes"),
            f"services.{service_id}.recovery_objective.rpo_minutes",
            0,
        )

        require_string_list(entry.get("backup_sources"), f"services.{service_id}.backup_sources")
        standby = require_mapping(entry.get("standby"), f"services.{service_id}.standby")
        standby_kind = require_enum(
            standby.get("kind"),
            f"services.{service_id}.standby.kind",
            {"none", "cold", "warm", "active"},
        )
        expected_kind = STANDBY_KIND_BY_TIER[tier]
        if standby_kind != expected_kind:
            raise ValueError(
                f"services.{service_id}.standby.kind must be {expected_kind!r} for tier {tier}"
            )

        location = require_str(standby.get("location"), f"services.{service_id}.standby.location")
        require_str(
            standby.get("failover_trigger"),
            f"services.{service_id}.standby.failover_trigger",
        )
        require_str(
            standby.get("failback_method"),
            f"services.{service_id}.standby.failback_method",
        )
        if standby_kind == "none":
            if location.lower() not in KNOWN_EMPTY_LOCATIONS:
                raise ValueError(
                    f"services.{service_id}.standby.location must describe an empty standby location for tier {tier}"
                )
        elif location not in allowed_locations:
            raise ValueError(
                f"services.{service_id}.standby.location must reference a known host or guest location"
            )


def build_live_apply_plan(
    catalog: dict[str, Any],
    *,
    service_id: str | None = None,
    allow_fallback: bool = False,
) -> list[dict[str, str]]:
    services = require_mapping(catalog.get("services"), "services")
    service_index = load_service_catalog_index()
    if service_id:
        if service_id not in services:
            raise ValueError(f"unknown service: {service_id}")
        target_ids = [service_id]
    else:
        target_ids = active_service_ids(service_index)

    platform = require_mapping(catalog.get("platform"), "platform")
    platform_max_tier = require_enum(
        platform.get("max_supported_tier"),
        "platform.max_supported_tier",
        set(TIER_ORDER),
    )

    plans: list[dict[str, str]] = []
    for current_service_id in target_ids:
        entry = require_mapping(services[current_service_id], f"services.{current_service_id}")
        declared_tier = require_enum(
            entry.get("tier"),
            f"services.{current_service_id}.tier",
            set(TIER_ORDER),
        )
        effective = effective_tier(
            declared_tier,
            platform_max_tier,
            allow_fallback=allow_fallback,
        )
        standby = require_mapping(entry.get("standby"), f"services.{current_service_id}.standby")
        plans.append(
            {
                "service_id": current_service_id,
                "declared_tier": declared_tier,
                "effective_tier": effective,
                "live_apply_mode": LIVE_APPLY_MODE_BY_TIER[effective],
                "standby_kind": require_str(standby.get("kind"), f"services.{current_service_id}.standby.kind"),
                "standby_location": require_str(
                    standby.get("location"),
                    f"services.{current_service_id}.standby.location",
                ),
            }
        )
    return plans


def list_services(catalog: dict[str, Any]) -> int:
    service_catalog_index = load_service_catalog_index()
    print(f"Service redundancy catalog: {SERVICE_REDUNDANCY_PATH}")
    print("Available services:")
    for service_id, entry in sorted(require_mapping(catalog.get("services"), "services").items()):
        entry = require_mapping(entry, f"services.{service_id}")
        service_name = service_catalog_index[service_id]["name"]
        print(
            f"  - {service_id} [{service_name}] "
            f"tier={entry['tier']} standby={entry['standby']['kind']} location={entry['standby']['location']}"
        )
    return 0


def show_service(catalog: dict[str, Any], service_id: str) -> int:
    services = require_mapping(catalog.get("services"), "services")
    if service_id not in services:
        print(f"Unknown service: {service_id}", file=sys.stderr)
        return 2

    service_catalog_index = load_service_catalog_index()
    entry = require_mapping(services[service_id], f"services.{service_id}")
    standby = require_mapping(entry.get("standby"), f"services.{service_id}.standby")
    recovery_objective = require_mapping(
        entry.get("recovery_objective"),
        f"services.{service_id}.recovery_objective",
    )
    print(f"Service: {service_id}")
    print(f"Name: {service_catalog_index[service_id]['name']}")
    print(f"Tier: {entry['tier']}")
    print(
        "Recovery Objective: "
        f"RTO {recovery_objective['rto_minutes']}m / RPO {recovery_objective['rpo_minutes']}m"
    )
    print("Backup Sources:")
    for backup_source in entry["backup_sources"]:
        print(f"  - {backup_source}")
    print(f"Standby Kind: {standby['kind']}")
    print(f"Standby Location: {standby['location']}")
    print(f"Failover Trigger: {standby['failover_trigger']}")
    print(f"Failback Method: {standby['failback_method']}")
    if "notes" in entry:
        print(f"Notes: {entry['notes']}")
    return 0


def check_live_apply(
    catalog: dict[str, Any],
    *,
    service_id: str | None,
    allow_fallback: bool,
) -> int:
    plans = build_live_apply_plan(
        catalog,
        service_id=service_id,
        allow_fallback=allow_fallback,
    )
    for plan in plans:
        print(
            f"{plan['service_id']}: declared {plan['declared_tier']} -> "
            f"effective {plan['effective_tier']} ({plan['live_apply_mode']}) "
            f"standby={plan['standby_kind']}@{plan['standby_location']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate the service redundancy tier catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and exit.")
    parser.add_argument("--list", action="store_true", help="List all services and their redundancy tiers.")
    parser.add_argument("--service", help="Show one service entry.")
    parser.add_argument(
        "--check-live-apply",
        action="store_true",
        help="Validate the catalog and render the live-apply interpretation.",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow declared tiers to fall back to the platform-supported tier instead of failing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog = load_redundancy_catalog()
        validate_redundancy_catalog(catalog)
        if args.validate:
            print(f"Service redundancy catalog OK: {SERVICE_REDUNDANCY_PATH}")
            return 0
        if args.check_live_apply:
            return check_live_apply(
                catalog,
                service_id=args.service,
                allow_fallback=args.allow_fallback,
            )
        if args.service:
            return show_service(catalog, args.service)
        return list_services(catalog)
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("Service redundancy catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
