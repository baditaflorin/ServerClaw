#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_int, require_list, require_mapping, require_str

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path

import service_redundancy
from service_id_resolver import resolve_service_id

try:
    import jsonschema
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
    ) from exc


IMMUTABLE_GUEST_REPLACEMENT_PATH: Final = repo_path(
    "config",
    "immutable-guest-replacement-catalog.json",
)
IMMUTABLE_GUEST_REPLACEMENT_SCHEMA_PATH: Final = repo_path(
    "docs",
    "schema",
    "immutable-guest-replacement-catalog.schema.json",
)
HOST_VARS_PATH: Final = repo_path("inventory", "host_vars", "proxmox_florin.yml")

EDGE_EXPOSURES = {"edge-published", "edge-static"}
CLASSIFICATIONS = {"edge", "stateful", "edge_and_stateful"}
VALIDATION_MODES = {"inactive_edge_peer", "preview_guest", "restore_preview", "warm_standby"}


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


def load_guest_replacement_catalog() -> dict[str, Any]:
    payload = load_json(IMMUTABLE_GUEST_REPLACEMENT_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{IMMUTABLE_GUEST_REPLACEMENT_PATH} must be an object")
    return payload


def load_inventory_guest_index() -> dict[str, dict[str, Any]]:
    payload = load_yaml(HOST_VARS_PATH)
    guests = require_list(payload.get("proxmox_guests"), "inventory/host_vars/proxmox_florin.yml.proxmox_guests")
    index: dict[str, dict[str, Any]] = {}
    for guest_index, guest in enumerate(guests):
        guest = require_mapping(guest, f"inventory/host_vars/proxmox_florin.yml.proxmox_guests[{guest_index}]")
        guest_name = require_str(
            guest.get("name"),
            f"inventory/host_vars/proxmox_florin.yml.proxmox_guests[{guest_index}].name",
        )
        index[guest_name] = guest
    return index


def load_active_service_records() -> list[dict[str, Any]]:
    service_catalog_index = service_redundancy.load_service_catalog_index()
    redundancy_catalog = service_redundancy.load_redundancy_catalog()
    redundancy_services = require_mapping(
        redundancy_catalog.get("services"), "config/service-redundancy-catalog.json.services"
    )
    active_ids = service_redundancy.active_service_ids(service_catalog_index)
    records: list[dict[str, Any]] = []
    for service_id in active_ids:
        service = require_mapping(
            service_catalog_index[service_id],
            f"config/service-capability-catalog.json.services[{service_id}]",
        )
        redundancy = require_mapping(
            redundancy_services[service_id],
            f"config/service-redundancy-catalog.json.services.{service_id}",
        )
        records.append(
            {
                "service_id": service_id,
                "service_name": require_str(service.get("name"), f"service {service_id}.name"),
                "guest": require_str(service.get("vm"), f"service {service_id}.vm"),
                "tier": require_enum(
                    redundancy.get("tier"), f"service {service_id}.tier", set(service_redundancy.TIER_ORDER)
                ),
                "exposure": require_str(service.get("exposure"), f"service {service_id}.exposure"),
            }
        )
    return records


def load_active_services_by_guest() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in load_active_service_records():
        grouped.setdefault(record["guest"], []).append(record)
    for records in grouped.values():
        records.sort(key=lambda item: item["service_id"])
    return grouped


def default_exception_rule(catalog: dict[str, Any]) -> str:
    platform = require_mapping(catalog.get("platform"), "platform")
    return require_str(platform.get("default_exception_rule"), "platform.default_exception_rule")


def validate_guest_replacement_catalog(catalog: dict[str, Any]) -> None:
    jsonschema.validate(
        instance=catalog,
        schema=load_json(IMMUTABLE_GUEST_REPLACEMENT_SCHEMA_PATH),
    )

    platform = require_mapping(catalog.get("platform"), "platform")
    require_str(platform.get("default_exception_rule"), "platform.default_exception_rule")
    require_string_list(platform.get("notes"), "platform.notes")

    guest_policies = require_mapping(catalog.get("guests"), "guests")
    inventory_guest_index = load_inventory_guest_index()
    active_services_by_guest = load_active_services_by_guest()

    for guest_name, policy in guest_policies.items():
        policy = require_mapping(policy, f"guests.{guest_name}")
        if guest_name not in inventory_guest_index:
            raise ValueError(
                f"guests.{guest_name} must reference a known guest in inventory/host_vars/proxmox_florin.yml"
            )

        hosted_services = active_services_by_guest.get(guest_name, [])
        if not hosted_services:
            raise ValueError(f"guests.{guest_name} must host at least one active managed service")

        classification = require_enum(
            policy.get("classification"),
            f"guests.{guest_name}.classification",
            CLASSIFICATIONS,
        )
        validation_mode = require_enum(
            policy.get("validation_mode"),
            f"guests.{guest_name}.validation_mode",
            VALIDATION_MODES,
        )
        require_str(policy.get("cutover_method"), f"guests.{guest_name}.cutover_method")
        require_int(policy.get("rollback_window_minutes"), f"guests.{guest_name}.rollback_window_minutes", minimum=15)
        require_str(policy.get("rollback_method"), f"guests.{guest_name}.rollback_method")
        if policy.get("exception_rule") is not None:
            require_str(policy.get("exception_rule"), f"guests.{guest_name}.exception_rule")
        if policy.get("notes") is not None:
            require_string_list(policy.get("notes"), f"guests.{guest_name}.notes")

        if not any(
            service_redundancy.TIER_ORDER[item["tier"]] >= service_redundancy.TIER_ORDER["R1"]
            for item in hosted_services
        ):
            raise ValueError(f"guests.{guest_name} must host at least one service at redundancy tier R1 or higher")

        if classification in {"edge", "edge_and_stateful"} and not any(
            item["exposure"] in EDGE_EXPOSURES for item in hosted_services
        ):
            raise ValueError(
                f"guests.{guest_name}.classification={classification} requires at least one edge-published or edge-static hosted service"
            )

        if validation_mode == "inactive_edge_peer" and classification not in {"edge", "edge_and_stateful"}:
            raise ValueError(
                f"guests.{guest_name}.validation_mode=inactive_edge_peer requires classification edge or edge_and_stateful"
            )

        if validation_mode == "warm_standby" and not any(
            service_redundancy.TIER_ORDER[item["tier"]] >= service_redundancy.TIER_ORDER["R2"]
            for item in hosted_services
        ):
            raise ValueError(
                f"guests.{guest_name}.validation_mode=warm_standby requires at least one hosted service at redundancy tier R2 or higher"
            )


def build_guest_plan(catalog: dict[str, Any], guest_name: str) -> dict[str, Any]:
    guest_policies = require_mapping(catalog.get("guests"), "guests")
    if guest_name not in guest_policies:
        raise ValueError(f"unknown immutable guest replacement policy: {guest_name}")

    inventory_guest_index = load_inventory_guest_index()
    active_services_by_guest = load_active_services_by_guest()
    guest_inventory = require_mapping(inventory_guest_index[guest_name], f"inventory guest {guest_name}")
    policy = require_mapping(guest_policies[guest_name], f"guests.{guest_name}")
    hosted_services = active_services_by_guest.get(guest_name, [])

    return {
        "guest": guest_name,
        "vmid": guest_inventory.get("vmid"),
        "role": guest_inventory.get("role"),
        "template_key": guest_inventory.get("template_key"),
        "classification": policy["classification"],
        "validation_mode": policy["validation_mode"],
        "cutover_method": policy["cutover_method"],
        "rollback_window_minutes": policy["rollback_window_minutes"],
        "rollback_method": policy["rollback_method"],
        "exception_rule": policy.get("exception_rule", default_exception_rule(catalog)),
        "notes": policy.get("notes", []),
        "hosted_services": hosted_services,
    }


def build_service_plan(catalog: dict[str, Any], service_id: str) -> dict[str, Any]:
    canonical_service_id = resolve_service_id(service_id)
    service_catalog_index = service_redundancy.load_service_catalog_index()
    if canonical_service_id not in service_catalog_index:
        raise ValueError(f"unknown service: {service_id}")

    redundancy_catalog = service_redundancy.load_redundancy_catalog()
    redundancy_services = require_mapping(
        redundancy_catalog.get("services"), "config/service-redundancy-catalog.json.services"
    )
    service = require_mapping(service_catalog_index[canonical_service_id], f"service {canonical_service_id}")
    redundancy = require_mapping(redundancy_services[canonical_service_id], f"redundancy {canonical_service_id}")
    guest_name = require_str(service.get("vm"), f"service {canonical_service_id}.vm")
    tier = require_enum(
        redundancy.get("tier"),
        f"service {canonical_service_id}.tier",
        set(service_redundancy.TIER_ORDER),
    )

    plan = {
        "service_id": canonical_service_id,
        "service_name": require_str(service.get("name"), f"service {canonical_service_id}.name"),
        "guest": guest_name,
        "tier": tier,
        "exposure": require_str(service.get("exposure"), f"service {canonical_service_id}.exposure"),
        "immutable_guest_replacement": False,
        "reason": "guest is not governed by ADR 0191 immutable replacement policy",
    }

    guest_policies = require_mapping(catalog.get("guests"), "guests")
    if guest_name not in guest_policies or service_redundancy.TIER_ORDER[tier] < service_redundancy.TIER_ORDER["R1"]:
        return plan

    guest_plan = build_guest_plan(catalog, guest_name)
    plan.update(
        {
            "immutable_guest_replacement": True,
            "classification": guest_plan["classification"],
            "validation_mode": guest_plan["validation_mode"],
            "cutover_method": guest_plan["cutover_method"],
            "rollback_window_minutes": guest_plan["rollback_window_minutes"],
            "rollback_method": guest_plan["rollback_method"],
            "exception_rule": guest_plan["exception_rule"],
            "vmid": guest_plan["vmid"],
            "role": guest_plan["role"],
            "template_key": guest_plan["template_key"],
            "hosted_services": guest_plan["hosted_services"],
            "reason": f"guest {guest_name} is governed by ADR 0191 immutable guest replacement",
        }
    )
    return plan


def build_target_plans(catalog: dict[str, Any], *, service_id: str | None = None) -> list[dict[str, Any]]:
    if service_id:
        return [build_service_plan(catalog, service_id)]

    service_catalog_index = service_redundancy.load_service_catalog_index()
    active_ids = service_redundancy.active_service_ids(service_catalog_index)
    return [build_service_plan(catalog, current_service_id) for current_service_id in active_ids]


def render_json(payload: Any) -> int:
    print(json.dumps(payload, indent=2))
    return 0


def list_guest_policies(catalog: dict[str, Any], *, as_json: bool) -> int:
    guest_policies = sorted(require_mapping(catalog.get("guests"), "guests"))
    plans = [build_guest_plan(catalog, guest_name) for guest_name in guest_policies]
    if as_json:
        return render_json(plans)

    print(f"Immutable guest replacement catalog: {IMMUTABLE_GUEST_REPLACEMENT_PATH}")
    for plan in plans:
        hosted = ", ".join(item["service_id"] for item in plan["hosted_services"])
        print(
            f"  - {plan['guest']} [vmid={plan['vmid']} role={plan['role']} template={plan['template_key']}] "
            f"classification={plan['classification']} validation={plan['validation_mode']} "
            f"rollback={plan['rollback_window_minutes']}m services={hosted}"
        )
    return 0


def show_guest_policy(catalog: dict[str, Any], guest_name: str, *, as_json: bool) -> int:
    plan = build_guest_plan(catalog, guest_name)
    if as_json:
        return render_json(plan)

    print(f"Guest: {plan['guest']}")
    print(f"VMID: {plan['vmid']}")
    print(f"Role: {plan['role']}")
    print(f"Template Key: {plan['template_key']}")
    print(f"Classification: {plan['classification']}")
    print(f"Validation Mode: {plan['validation_mode']}")
    print(f"Rollback Window: {plan['rollback_window_minutes']}m")
    print(f"Cutover Method: {plan['cutover_method']}")
    print(f"Rollback Method: {plan['rollback_method']}")
    print(f"Exception Rule: {plan['exception_rule']}")
    print("Hosted Services:")
    for item in plan["hosted_services"]:
        print(f"  - {item['service_id']} [{item['service_name']}] tier={item['tier']} exposure={item['exposure']}")
    for note in plan["notes"]:
        print(f"Note: {note}")
    return 0


def show_service_policy(catalog: dict[str, Any], service_id: str, *, as_json: bool) -> int:
    plan = build_service_plan(catalog, service_id)
    if as_json:
        return render_json(plan)

    print(f"Service: {plan['service_id']}")
    print(f"Name: {plan['service_name']}")
    print(f"Guest: {plan['guest']}")
    print(f"Tier: {plan['tier']}")
    print(f"Exposure: {plan['exposure']}")
    print(f"Immutable Guest Replacement: {'yes' if plan['immutable_guest_replacement'] else 'no'}")
    print(f"Reason: {plan['reason']}")
    if not plan["immutable_guest_replacement"]:
        return 0

    print(f"VMID: {plan['vmid']}")
    print(f"Role: {plan['role']}")
    print(f"Template Key: {plan['template_key']}")
    print(f"Classification: {plan['classification']}")
    print(f"Validation Mode: {plan['validation_mode']}")
    print(f"Rollback Window: {plan['rollback_window_minutes']}m")
    print(f"Cutover Method: {plan['cutover_method']}")
    print(f"Rollback Method: {plan['rollback_method']}")
    print(f"Exception Rule: {plan['exception_rule']}")
    print("Hosted Services On The Guest:")
    for item in plan["hosted_services"]:
        print(f"  - {item['service_id']} [{item['service_name']}] tier={item['tier']} exposure={item['exposure']}")
    return 0


def check_live_apply(
    catalog: dict[str, Any],
    *,
    service_id: str | None,
    allow_in_place_mutation: bool,
) -> int:
    plans = build_target_plans(catalog, service_id=service_id)
    governed = [plan for plan in plans if plan["immutable_guest_replacement"]]
    if not governed:
        target = service_id or "active services"
        print(f"No ADR 0191 immutable guest replacement policy blocks the requested live apply for {target}.")
        return 0

    if allow_in_place_mutation:
        for plan in governed:
            print(
                f"override: {plan['service_id']} remains governed by immutable guest replacement on "
                f"{plan['guest']} ({plan['validation_mode']}, rollback {plan['rollback_window_minutes']}m); "
                "ALLOW_IN_PLACE_MUTATION=true was supplied for this run."
            )
        return 0

    details = []
    for plan in governed:
        details.append(
            f"{plan['service_id']} -> {plan['guest']} "
            f"[classification={plan['classification']}, validation={plan['validation_mode']}, "
            f"rollback={plan['rollback_window_minutes']}m]"
        )
    raise ValueError(
        "Immutable guest replacement is required before in-place live apply:\n"
        + "\n".join(details)
        + "\nUse `make immutable-guest-replacement-plan service=<service-id>` to inspect the replacement policy, "
        "or rerun with `ALLOW_IN_PLACE_MUTATION=true` only for a documented narrow exception."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and validate the ADR 0191 immutable guest replacement catalog."
    )
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and exit.")
    parser.add_argument("--list", action="store_true", help="List all immutable guest replacement policies.")
    parser.add_argument("--guest", help="Show one guest replacement policy.")
    parser.add_argument("--service", help="Show the replacement policy affecting one service.")
    parser.add_argument("--json", action="store_true", help="Render the selected output as JSON.")
    parser.add_argument(
        "--check-live-apply",
        action="store_true",
        help="Fail when the requested service is governed by immutable guest replacement and no explicit override is supplied.",
    )
    parser.add_argument(
        "--allow-in-place-mutation",
        action="store_true",
        help="Acknowledge a documented narrow exception and allow the preflight to continue.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog = load_guest_replacement_catalog()
        validate_guest_replacement_catalog(catalog)
        if args.validate:
            print(f"Immutable guest replacement catalog OK: {IMMUTABLE_GUEST_REPLACEMENT_PATH}")
            return 0
        if args.check_live_apply:
            return check_live_apply(
                catalog,
                service_id=args.service,
                allow_in_place_mutation=args.allow_in_place_mutation,
            )
        if args.guest:
            return show_guest_policy(catalog, args.guest, as_json=args.json)
        if args.service:
            return show_service_policy(catalog, args.service, as_json=args.json)
        return list_guest_policies(catalog, as_json=args.json or args.list)
    except Exception as exc:
        return emit_cli_error("Immutable guest replacement catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
