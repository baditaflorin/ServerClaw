#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from capacity_report import (
    CAPACITY_MODEL_PATH,
    CapacityModel,
    ResourceAmount,
    ZERO_RESOURCES,
    calculate_committed,
    load_capacity_model,
)
from service_id_resolver import resolve_service_id


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
ALLOWED_REDUNDANCY_TIERS = {"R0", "R1", "R2", "R3"}
ENFORCED_REDUNDANCY_TIERS = {"R2", "R3"}
ALLOWED_STANDBY_MODES = {"warm", "passive", "active"}
CONTROL_PLANE_CATEGORIES = {"automation", "security", "access", "infrastructure"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
    return value.strip()


def require_number(value: Any, path: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    numeric = float(value)
    if numeric < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return numeric


def load_service_catalog(path: Path = SERVICE_CATALOG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def service_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    services = require_list(catalog.get("services"), "service-capability-catalog.services")
    indexed: dict[str, dict[str, Any]] = {}
    for index, service in enumerate(services):
        item = require_mapping(service, f"service-capability-catalog.services[{index}]")
        service_id = require_str(item.get("id"), f"service-capability-catalog.services[{index}].id")
        indexed[service_id] = item
    return indexed


def resource_from_mapping(value: Any, path: str) -> ResourceAmount:
    payload = require_mapping(value, path)
    return ResourceAmount(
        ram_gb=require_number(payload.get("ram_gb"), f"{path}.ram_gb"),
        vcpu=require_number(payload.get("vcpu"), f"{path}.vcpu"),
        disk_gb=require_number(payload.get("disk_gb"), f"{path}.disk_gb"),
    )


def resource_shortfalls(available: ResourceAmount, required: ResourceAmount) -> list[str]:
    shortages: list[str] = []
    if available.ram_gb < required.ram_gb:
        shortages.append(f"RAM {available.ram_gb:.1f} GB < {required.ram_gb:.1f} GB")
    if available.vcpu < required.vcpu:
        shortages.append(f"vCPU {available.vcpu:.1f} < {required.vcpu:.1f}")
    if available.disk_gb < required.disk_gb:
        shortages.append(f"disk {available.disk_gb:.1f} GB < {required.disk_gb:.1f} GB")
    return shortages


def totals_for_reservations(model: CapacityModel, service_id: str) -> ResourceAmount:
    total = ZERO_RESOURCES
    for reservation in model.reservations:
        if reservation.kind == "standby" and reservation.service_id == service_id:
            total = total.add(reservation.reserved)
    return total


def find_guest(model: CapacityModel, *, name: str | None = None, vmid: int | None = None) -> Any | None:
    for guest in model.guests:
        if name and guest.name == name:
            return guest
        if vmid is not None and guest.vmid == vmid:
            return guest
    return None


def matching_standby_reservations(model: CapacityModel, service_id: str) -> list[Any]:
    return [
        reservation
        for reservation in model.reservations
        if reservation.kind == "standby" and reservation.service_id == service_id
    ]


def failure_domain_statement_is_honest(statement: str) -> bool:
    normalized = statement.lower()
    host_markers = ("host", "single-node", "single host", "single proxmox")
    limitation_markers = ("does not cover", "not cover", "not protect", "cannot cover", "host loss")
    return any(marker in normalized for marker in host_markers) and any(
        marker in normalized for marker in limitation_markers
    )


def evaluate_service_standby(
    service_id: str,
    *,
    catalog: dict[str, Any] | None = None,
    model: CapacityModel | None = None,
    enforce_capacity_target: bool = False,
) -> dict[str, Any]:
    canonical_service_id = resolve_service_id(service_id)
    loaded_catalog = catalog or load_service_catalog()
    indexed = service_index(loaded_catalog)
    if canonical_service_id not in indexed:
        raise ValueError(f"unknown service '{service_id}'")

    service = indexed[canonical_service_id]
    redundancy = service.get("redundancy")
    result: dict[str, Any] = {
        "service_id": canonical_service_id,
        "approved": True,
        "enforced": False,
        "tier": None,
        "reasons": [],
        "warnings": [],
        "backing_source": None,
    }
    if not isinstance(redundancy, dict):
        return result

    tier = require_str(redundancy.get("tier"), f"service '{canonical_service_id}'.redundancy.tier")
    if tier not in ALLOWED_REDUNDANCY_TIERS:
        raise ValueError(
            f"service '{canonical_service_id}'.redundancy.tier must be one of {sorted(ALLOWED_REDUNDANCY_TIERS)}"
        )
    result["tier"] = tier
    if tier not in ENFORCED_REDUNDANCY_TIERS:
        return result

    loaded_model = model or load_capacity_model(CAPACITY_MODEL_PATH)
    result["enforced"] = True

    standby = require_mapping(redundancy.get("standby"), f"service '{canonical_service_id}'.redundancy.standby")
    placement = require_mapping(
        standby.get("placement"),
        f"service '{canonical_service_id}'.redundancy.standby.placement",
    )
    reservation = require_mapping(
        standby.get("reservation"),
        f"service '{canonical_service_id}'.redundancy.standby.reservation",
    )

    primary_vm = require_str(service.get("vm"), f"service '{canonical_service_id}'.vm")
    standby_vm = require_str(standby.get("vm"), f"service '{canonical_service_id}'.redundancy.standby.vm")
    standby_vmid = standby.get("vmid")
    if standby_vmid is not None:
        standby_vmid = int(
            require_number(
                standby_vmid,
                f"service '{canonical_service_id}'.redundancy.standby.vmid",
                minimum=1,
            )
        )
    mode = require_str(standby.get("mode"), f"service '{canonical_service_id}'.redundancy.standby.mode")
    if mode not in ALLOWED_STANDBY_MODES:
        raise ValueError(
            f"service '{service_id}'.redundancy.standby.mode must be one of {sorted(ALLOWED_STANDBY_MODES)}"
        )

    required_resources = resource_from_mapping(
        reservation.get("resources"),
        f"service '{canonical_service_id}'.redundancy.standby.reservation.resources",
    )
    storage_class = require_str(
        reservation.get("storage_class"),
        f"service '{canonical_service_id}'.redundancy.standby.reservation.storage_class",
    )
    network_attachment = require_str(
        reservation.get("required_network_attachment"),
        f"service '{canonical_service_id}'.redundancy.standby.reservation.required_network_attachment",
    )

    primary_compose_project = require_str(
        placement.get("primary_compose_project"),
        f"service '{canonical_service_id}'.redundancy.standby.placement.primary_compose_project",
    )
    standby_compose_project = require_str(
        placement.get("standby_compose_project"),
        f"service '{canonical_service_id}'.redundancy.standby.placement.standby_compose_project",
    )
    primary_namespace = require_str(
        placement.get("primary_namespace"),
        f"service '{canonical_service_id}'.redundancy.standby.placement.primary_namespace",
    )
    standby_namespace = require_str(
        placement.get("standby_namespace"),
        f"service '{canonical_service_id}'.redundancy.standby.placement.standby_namespace",
    )
    primary_data_paths = {
        require_str(
            item,
            f"service '{canonical_service_id}'.redundancy.standby.placement.primary_data_paths[{index}]",
        )
        for index, item in enumerate(
            require_list(
                placement.get("primary_data_paths"),
                f"service '{canonical_service_id}'.redundancy.standby.placement.primary_data_paths",
            )
        )
    }
    standby_data_paths = {
        require_str(
            item,
            f"service '{canonical_service_id}'.redundancy.standby.placement.standby_data_paths[{index}]",
        )
        for index, item in enumerate(
            require_list(
                placement.get("standby_data_paths"),
                f"service '{canonical_service_id}'.redundancy.standby.placement.standby_data_paths",
            )
        )
    }
    failure_domain_honesty = require_str(
        standby.get("failure_domain_honesty"),
        f"service '{canonical_service_id}'.redundancy.standby.failure_domain_honesty",
    )

    reasons = result["reasons"]
    warnings = result["warnings"]
    capacity_delta = ZERO_RESOURCES

    if primary_compose_project == standby_compose_project:
        reasons.append(
            f"service '{service_id}' primary and standby share compose project '{primary_compose_project}'"
        )
    if primary_namespace == standby_namespace:
        reasons.append(
            f"service '{service_id}' primary and standby share namespace '{primary_namespace}'"
        )
    overlapping_paths = sorted(primary_data_paths & standby_data_paths)
    if overlapping_paths:
        reasons.append(
            f"service '{service_id}' primary and standby share data paths: {', '.join(overlapping_paths)}"
        )
    if standby_vm == primary_vm:
        warnings.append(f"service '{service_id}' standby shares guest VM '{standby_vm}' with the primary")
    if not failure_domain_statement_is_honest(failure_domain_honesty):
        reasons.append(
            f"service '{service_id}' standby must state that same-host standby does not cover Proxmox host loss"
        )

    standby_guest = find_guest(loaded_model, name=standby_vm)
    if standby_guest is not None:
        if standby_vmid is not None and standby_guest.vmid != standby_vmid:
            reasons.append(
                f"service '{service_id}' standby vmid {standby_vmid} does not match capacity-model guest {standby_guest.vmid}"
            )
        guest_resources = standby_guest.allocated if standby_guest.status == "active" else standby_guest.budget
        shortages = resource_shortfalls(guest_resources, required_resources)
        if shortages:
            reasons.append(
                f"service '{service_id}' standby guest '{standby_vm}' does not meet reserved capacity: "
                + "; ".join(shortages)
            )
        if standby_guest.status != "active":
            capacity_delta = required_resources
        result["backing_source"] = {
            "type": "guest_allocated" if standby_guest.status == "active" else "guest_budget",
            "guest": standby_guest.name,
            "guest_status": standby_guest.status,
            "storage_class": storage_class,
            "required_network_attachment": network_attachment,
        }
    else:
        reservations = matching_standby_reservations(loaded_model, canonical_service_id)
        if not reservations:
            reasons.append(
                f"service '{service_id}' declares tier {tier} but has no standby guest or standby reservation in the capacity model"
            )
        else:
            reserved_total = totals_for_reservations(loaded_model, canonical_service_id)
            shortages = resource_shortfalls(reserved_total, required_resources)
            if shortages:
                reasons.append(
                    f"service '{service_id}' standby reservations do not meet reserved capacity: "
                    + "; ".join(shortages)
                )
            capacity_delta = reserved_total
            if not any(reservation.standby_vm == standby_vm for reservation in reservations):
                reasons.append(
                    f"service '{service_id}' standby reservations do not target standby VM '{standby_vm}'"
                )
            if standby_vmid is not None and not any(
                reservation.standby_vmid == standby_vmid for reservation in reservations
            ):
                reasons.append(
                    f"service '{service_id}' standby reservations do not declare standby vmid {standby_vmid}"
                )
            if not any(reservation.storage_class == storage_class for reservation in reservations):
                reasons.append(
                    f"service '{service_id}' standby reservations do not declare storage class '{storage_class}'"
                )
            if not any(
                reservation.required_network_attachment == network_attachment for reservation in reservations
            ):
                reasons.append(
                    "service "
                    f"'{service_id}' standby reservations do not declare network attachment '{network_attachment}'"
                )
            result["backing_source"] = {
                "type": "standby_reservation",
                "reservation_ids": [reservation.identifier for reservation in reservations],
                "storage_class": storage_class,
                "required_network_attachment": network_attachment,
            }

    if standby_vm == "backup-lv3":
        if mode != "passive":
            reasons.append("backup-lv3 may host only passive standbys")
        category = require_str(service.get("category"), f"service '{service_id}'.category")
        if category not in CONTROL_PLANE_CATEGORIES:
            reasons.append(
                f"backup-lv3 standby placement is limited to passive control-plane roles, not category '{category}'"
            )

    if enforce_capacity_target:
        projected = calculate_committed(loaded_model, include_planned=False, include_reservations=False).add(capacity_delta)
        target = loaded_model.host.target_absolute
        if projected.ram_gb > target.ram_gb:
            reasons.append(
                f"projected standby-aware RAM commitment {projected.ram_gb:.1f} GB exceeds target {target.ram_gb:.1f} GB"
            )
        if projected.vcpu > target.vcpu:
            reasons.append(
                f"projected standby-aware vCPU commitment {projected.vcpu:.1f} exceeds target {target.vcpu:.1f}"
            )
        if projected.disk_gb > target.disk_gb:
            reasons.append(
                f"projected standby-aware disk commitment {projected.disk_gb:.1f} GB exceeds target {target.disk_gb:.1f} GB"
            )

    result["approved"] = not reasons
    result["required_reservation"] = {
        "resources": required_resources.__dict__,
        "storage_class": storage_class,
        "required_network_attachment": network_attachment,
    }
    return result


def validate_catalog_standby_policies(
    catalog: dict[str, Any] | None = None,
    *,
    model: CapacityModel | None = None,
) -> None:
    loaded_catalog = catalog or load_service_catalog()
    loaded_model = model or load_capacity_model(CAPACITY_MODEL_PATH)
    for service_id in sorted(service_index(loaded_catalog)):
        verdict = evaluate_service_standby(service_id, catalog=loaded_catalog, model=loaded_model)
        if verdict["enforced"] and not verdict["approved"]:
            raise ValueError(
                f"standby policy for service '{service_id}' is invalid: " + "; ".join(verdict["reasons"])
            )


def render_text(verdict: dict[str, Any]) -> str:
    lines = [
        f"Service: {verdict['service_id']}",
        f"Tier: {verdict['tier'] or 'n/a'}",
        f"Standby enforcement: {'enabled' if verdict['enforced'] else 'not required'}",
        f"Decision: {'approved' if verdict['approved'] else 'rejected'}",
    ]
    backing_source = verdict.get("backing_source")
    if isinstance(backing_source, dict) and backing_source:
        lines.append(f"Backing source: {json.dumps(backing_source, sort_keys=True)}")
    if verdict["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in verdict["warnings"])
    if verdict["reasons"]:
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in verdict["reasons"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate standby capacity and placement declarations.")
    parser.add_argument("--service", help="Service id from config/service-capability-catalog.json.")
    parser.add_argument("--validate", action="store_true", help="Validate all standby declarations.")
    parser.add_argument("--enforce-target", action="store_true", help="Fail when the standby reservation would exceed host target capacity.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args(argv)

    try:
        catalog = load_service_catalog()
        model = load_capacity_model(CAPACITY_MODEL_PATH)
        if args.validate:
            validate_catalog_standby_policies(catalog, model=model)
            print("Standby capacity policies OK")
            return 0
        if not args.service:
            parser.print_help()
            return 0
        verdict = evaluate_service_standby(
            args.service,
            catalog=catalog,
            model=model,
            enforce_capacity_target=args.enforce_target,
        )
        if args.format == "json":
            print(json.dumps(verdict, indent=2, sort_keys=True))
        else:
            print(render_text(verdict), end="")
        return 0 if verdict["approved"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
