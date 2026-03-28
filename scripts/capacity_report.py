#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller_automation_toolkit import REPO_ROOT, load_json, load_yaml
from shared_policy_packs import load_shared_policy_packs


CAPACITY_MODEL_PATH = REPO_ROOT / "config" / "capacity-model.json"
INVENTORY_PATH = REPO_ROOT / "inventory" / "hosts.yml"
SECRET_MANIFEST_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
FIXTURE_RECEIPTS_DIR = REPO_ROOT / "receipts" / "fixtures"
SSH_TIMEOUT_SECONDS = 10
SHARED_POLICIES = load_shared_policy_packs()
CAPACITY_CLASSES = SHARED_POLICIES.capacity_class_ids
REQUESTER_CLASS_ALIASES = SHARED_POLICIES.requester_class_aliases
PRIMARY_CLASS_FOR_REQUESTER = SHARED_POLICIES.primary_capacity_class_by_requester
DECLARED_DRILL_BORROW_BY_REQUESTER = SHARED_POLICIES.declared_drill_borrow_by_requester
BREAK_GLASS_BORROW_BY_REQUESTER = SHARED_POLICIES.break_glass_borrow_by_requester


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


def require_number(value: Any, path: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    numeric = float(value)
    if minimum is not None and numeric < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return numeric


def safe_percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator * 100.0


def clamp_negative(value: float) -> float:
    return value if value >= 0 else 0.0


def subtract_resources(total: "ResourceAmount", occupied: "ResourceAmount") -> "ResourceAmount":
    return ResourceAmount(
        ram_gb=clamp_negative(total.ram_gb - occupied.ram_gb),
        vcpu=clamp_negative(total.vcpu - occupied.vcpu),
        disk_gb=clamp_negative(total.disk_gb - occupied.disk_gb),
    )


@dataclass(frozen=True)
class ResourceAmount:
    ram_gb: float
    vcpu: float
    disk_gb: float

    def add(self, other: "ResourceAmount") -> "ResourceAmount":
        return ResourceAmount(
            ram_gb=self.ram_gb + other.ram_gb,
            vcpu=self.vcpu + other.vcpu,
            disk_gb=self.disk_gb + other.disk_gb,
        )


ZERO_RESOURCES = ResourceAmount(0.0, 0.0, 0.0)


@dataclass(frozen=True)
class HostModel:
    identifier: str
    name: str
    metrics_host: str
    physical: ResourceAmount
    target_utilisation: ResourceAmount
    reserved_for_platform: ResourceAmount

    @property
    def usable(self) -> ResourceAmount:
        return ResourceAmount(
            ram_gb=max(self.physical.ram_gb - self.reserved_for_platform.ram_gb, 0.0),
            vcpu=max(self.physical.vcpu - self.reserved_for_platform.vcpu, 0.0),
            disk_gb=max(self.physical.disk_gb - self.reserved_for_platform.disk_gb, 0.0),
        )

    @property
    def target_absolute(self) -> ResourceAmount:
        usable = self.usable
        return ResourceAmount(
            ram_gb=usable.ram_gb * self.target_utilisation.ram_gb / 100.0,
            vcpu=usable.vcpu * self.target_utilisation.vcpu / 100.0,
            disk_gb=usable.disk_gb * self.target_utilisation.disk_gb / 100.0,
        )


@dataclass(frozen=True)
class GuestModel:
    vmid: int
    name: str
    status: str
    environment: str
    metrics_host: str
    allocated: ResourceAmount
    budget: ResourceAmount
    disk_paths: tuple[str, ...]
    capacity_class: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ReservationModel:
    identifier: str
    kind: str
    status: str
    reserved: ResourceAmount
    capacity_class: str | None = None
    service_id: str | None = None
    standby_vm: str | None = None
    standby_vmid: int | None = None
    storage_class: str | None = None
    required_network_attachment: str | None = None
    max_concurrent_vms: int | None = None
    vmid_range: tuple[int, int] | None = None
    notes: str | None = None


@dataclass(frozen=True)
class CapacityModel:
    host: HostModel
    guests: tuple[GuestModel, ...]
    reservations: tuple[ReservationModel, ...]


@dataclass(frozen=True)
class GuestActuals:
    memory_used_gb: float | None = None
    cpu_used_cores_p95: float | None = None
    disk_used_gb: float | None = None


@dataclass(frozen=True)
class HostActuals:
    memory_used_gb: float | None = None
    cpu_used_cores_p95: float | None = None
    disk_used_gb: float | None = None


@dataclass(frozen=True)
class CapacityReport:
    model: CapacityModel
    host_actuals: HostActuals
    guest_actuals: dict[str, GuestActuals]
    metrics_source: str


@dataclass(frozen=True)
class CapacityClassState:
    identifier: str
    reserved: ResourceAmount
    occupied: ResourceAmount
    available: ResourceAmount
    sources: tuple[str, ...]


def resource_from_mapping(value: Any, path: str) -> ResourceAmount:
    payload = require_mapping(value, path)
    return ResourceAmount(
        ram_gb=require_number(payload.get("ram_gb"), f"{path}.ram_gb", 0),
        vcpu=require_number(payload.get("vcpu"), f"{path}.vcpu", 0),
        disk_gb=require_number(payload.get("disk_gb"), f"{path}.disk_gb", 0),
    )


def load_capacity_model(path: Path = CAPACITY_MODEL_PATH) -> CapacityModel:
    payload = require_mapping(load_json(path), str(path))
    validate_capacity_model_payload(payload)

    host_payload = require_mapping(payload["host"], f"{path}.host")
    host = HostModel(
        identifier=require_str(host_payload.get("id"), f"{path}.host.id"),
        name=require_str(host_payload.get("name"), f"{path}.host.name"),
        metrics_host=require_str(host_payload.get("metrics_host"), f"{path}.host.metrics_host"),
        physical=resource_from_mapping(host_payload.get("physical"), f"{path}.host.physical"),
        target_utilisation=resource_from_mapping(
            {
                "ram_gb": host_payload["target_utilisation"]["ram_percent"],
                "vcpu": host_payload["target_utilisation"]["vcpu_percent"],
                "disk_gb": host_payload["target_utilisation"]["disk_percent"],
            },
            f"{path}.host.target_utilisation",
        ),
        reserved_for_platform=resource_from_mapping(
            host_payload.get("reserved_for_platform"),
            f"{path}.host.reserved_for_platform",
        ),
    )

    guests = []
    for index, item in enumerate(require_list(payload.get("guests"), f"{path}.guests")):
        guest = require_mapping(item, f"{path}.guests[{index}]")
        disk_paths = tuple(
            require_str(entry, f"{path}.guests[{index}].disk_paths[{disk_index}]")
            for disk_index, entry in enumerate(guest.get("disk_paths", ["/"]))
        )
        guests.append(
            GuestModel(
                vmid=int(require_number(guest.get("vmid"), f"{path}.guests[{index}].vmid", 1)),
                name=require_str(guest.get("name"), f"{path}.guests[{index}].name"),
                status=require_str(guest.get("status"), f"{path}.guests[{index}].status"),
                environment=require_str(
                    guest.get("environment"),
                    f"{path}.guests[{index}].environment",
                ),
                metrics_host=require_str(
                    guest.get("metrics_host"),
                    f"{path}.guests[{index}].metrics_host",
                ),
                allocated=resource_from_mapping(
                    guest.get("allocated"),
                    f"{path}.guests[{index}].allocated",
                ),
                budget=resource_from_mapping(
                    guest.get("budget"),
                    f"{path}.guests[{index}].budget",
                ),
                disk_paths=disk_paths,
                capacity_class=(
                    require_str(
                        guest.get("capacity_class"),
                        f"{path}.guests[{index}].capacity_class",
                    )
                    if guest.get("capacity_class") is not None
                    else None
                ),
                notes=guest.get("notes"),
            )
        )

    reservations = []
    for index, item in enumerate(require_list(payload.get("reservations"), f"{path}.reservations")):
        reservation = require_mapping(item, f"{path}.reservations[{index}]")
        vmid_range = None
        if "vmid_range" in reservation:
            range_payload = require_mapping(
                reservation.get("vmid_range"),
                f"{path}.reservations[{index}].vmid_range",
            )
            vmid_range = (
                int(require_number(range_payload.get("start"), f"{path}.reservations[{index}].vmid_range.start", 1)),
                int(require_number(range_payload.get("end"), f"{path}.reservations[{index}].vmid_range.end", 1)),
            )
        max_concurrent_vms = reservation.get("max_concurrent_vms")
        reservations.append(
            ReservationModel(
                identifier=require_str(
                    reservation.get("id"),
                    f"{path}.reservations[{index}].id",
                ),
                kind=require_str(
                    reservation.get("kind"),
                    f"{path}.reservations[{index}].kind",
                ),
                status=require_str(
                    reservation.get("status"),
                    f"{path}.reservations[{index}].status",
                ),
                reserved=resource_from_mapping(
                    reservation.get("reserved"),
                    f"{path}.reservations[{index}].reserved",
                ),
                capacity_class=(
                    require_str(
                        reservation.get("capacity_class"),
                        f"{path}.reservations[{index}].capacity_class",
                    )
                    if reservation.get("capacity_class") is not None
                    else ("preview_burst" if reservation.get("kind") == "ephemeral_pool" else "ha_reserved" if reservation.get("kind") == "standby" else None)
                ),
                service_id=(
                    require_str(reservation.get("service_id"), f"{path}.reservations[{index}].service_id")
                    if reservation.get("service_id") is not None
                    else None
                ),
                standby_vm=(
                    require_str(reservation.get("standby_vm"), f"{path}.reservations[{index}].standby_vm")
                    if reservation.get("standby_vm") is not None
                    else None
                ),
                standby_vmid=(
                    int(require_number(reservation.get("standby_vmid"), f"{path}.reservations[{index}].standby_vmid", 1))
                    if reservation.get("standby_vmid") is not None
                    else None
                ),
                storage_class=(
                    require_str(
                        reservation.get("storage_class"),
                        f"{path}.reservations[{index}].storage_class",
                    )
                    if reservation.get("storage_class") is not None
                    else None
                ),
                required_network_attachment=(
                    require_str(
                        reservation.get("required_network_attachment"),
                        f"{path}.reservations[{index}].required_network_attachment",
                    )
                    if reservation.get("required_network_attachment") is not None
                    else None
                ),
                max_concurrent_vms=(
                    int(require_number(max_concurrent_vms, f"{path}.reservations[{index}].max_concurrent_vms", 1))
                    if max_concurrent_vms is not None
                    else None
                ),
                vmid_range=vmid_range,
                notes=reservation.get("notes"),
            )
        )

    return CapacityModel(host=host, guests=tuple(guests), reservations=tuple(reservations))


def load_inventory_hosts() -> dict[str, str]:
    inventory = require_mapping(load_yaml(INVENTORY_PATH), str(INVENTORY_PATH))
    children = require_mapping(inventory.get("all"), "inventory/hosts.yml.all").get("children", {})
    children = require_mapping(children, "inventory/hosts.yml.all.children")
    hosts: dict[str, str] = {}
    for group_name in ("proxmox_hosts", "lv3_guests"):
        group = require_mapping(children.get(group_name), f"inventory/hosts.yml.all.children.{group_name}")
        group_hosts = require_mapping(group.get("hosts"), f"inventory/hosts.yml.all.children.{group_name}.hosts")
        for name, payload in group_hosts.items():
            payload = payload or {}
            if not isinstance(payload, dict):
                payload = {}
            if "ansible_host" in payload:
                hosts[name] = require_str(
                    payload.get("ansible_host"),
                    f"inventory/hosts.yml host '{name}'.ansible_host",
                )
    return hosts


def bootstrap_key_path() -> Path | None:
    candidate = Path(REPO_ROOT / ".local" / "ssh" / "hetzner_llm_agents_ed25519")
    if candidate.exists():
        return candidate
    secrets = require_mapping(load_json(SECRET_MANIFEST_PATH), str(SECRET_MANIFEST_PATH))
    secret = require_mapping(secrets.get("secrets"), "controller-local-secrets.secrets").get(
        "bootstrap_ssh_private_key"
    )
    if not isinstance(secret, dict):
        return None
    path = secret.get("path")
    if isinstance(path, str) and path.strip():
        resolved = Path(path)
        if resolved.exists():
            return resolved
    return None


def validate_capacity_model_payload(payload: dict[str, Any]) -> None:
    require_str(payload.get("$schema"), "config/capacity-model.json.$schema")
    if payload["$schema"] != "docs/schema/capacity-model.schema.json":
        raise ValueError("config/capacity-model.json.$schema must reference docs/schema/capacity-model.schema.json")
    require_str(payload.get("schema_version"), "config/capacity-model.json.schema_version")

    host = require_mapping(payload.get("host"), "config/capacity-model.json.host")
    require_str(host.get("id"), "config/capacity-model.json.host.id")
    require_str(host.get("name"), "config/capacity-model.json.host.name")
    require_str(host.get("metrics_host"), "config/capacity-model.json.host.metrics_host")
    resource_from_mapping(host.get("physical"), "config/capacity-model.json.host.physical")

    target = require_mapping(
        host.get("target_utilisation"),
        "config/capacity-model.json.host.target_utilisation",
    )
    for field in ("ram_percent", "vcpu_percent", "disk_percent"):
        value = require_number(
            target.get(field),
            f"config/capacity-model.json.host.target_utilisation.{field}",
            1,
        )
        if value > 100:
            raise ValueError(
                f"config/capacity-model.json.host.target_utilisation.{field} must be <= 100"
            )
    resource_from_mapping(
        host.get("reserved_for_platform"),
        "config/capacity-model.json.host.reserved_for_platform",
    )

    inventory_hosts = load_inventory_hosts()
    proxmox_host = inventory_hosts.get("proxmox_florin")
    if not proxmox_host:
        raise ValueError("inventory/hosts.yml must define proxmox_florin under proxmox_hosts")

    seen_vmids: set[int] = set()
    seen_names: set[str] = set()
    inventory_guest_names = {name for name in inventory_hosts if name != "proxmox_florin"}
    for index, item in enumerate(require_list(payload.get("guests"), "config/capacity-model.json.guests")):
        guest = require_mapping(item, f"config/capacity-model.json.guests[{index}]")
        vmid = int(require_number(guest.get("vmid"), f"config/capacity-model.json.guests[{index}].vmid", 1))
        name = require_str(guest.get("name"), f"config/capacity-model.json.guests[{index}].name")
        status = require_str(guest.get("status"), f"config/capacity-model.json.guests[{index}].status")
        if status not in {"active", "planned"}:
            raise ValueError(
                f"config/capacity-model.json.guests[{index}].status must be 'active' or 'planned'"
            )
        environment = require_str(
            guest.get("environment"),
            f"config/capacity-model.json.guests[{index}].environment",
        )
        if environment not in {"production", "staging"}:
            raise ValueError(
                f"config/capacity-model.json.guests[{index}].environment must be production or staging"
            )
        metrics_host = require_str(
            guest.get("metrics_host"),
            f"config/capacity-model.json.guests[{index}].metrics_host",
        )
        if vmid in seen_vmids:
            raise ValueError(f"duplicate capacity-model vmid {vmid}")
        if name in seen_names:
            raise ValueError(f"duplicate capacity-model guest name '{name}'")
        seen_vmids.add(vmid)
        seen_names.add(name)
        if status == "active":
            if name not in inventory_guest_names:
                raise ValueError(
                    f"active capacity-model guest '{name}' must exist in inventory/hosts.yml"
                )
        if metrics_host != name and status == "active":
            raise ValueError(
                f"active capacity-model guest '{name}' must use metrics_host equal to the guest name"
            )
        allocated = resource_from_mapping(
            guest.get("allocated"),
            f"config/capacity-model.json.guests[{index}].allocated",
        )
        budget = resource_from_mapping(
            guest.get("budget"),
            f"config/capacity-model.json.guests[{index}].budget",
        )
        if allocated.ram_gb > budget.ram_gb or allocated.vcpu > budget.vcpu or allocated.disk_gb > budget.disk_gb:
            raise ValueError(
                f"config/capacity-model.json.guests[{index}] allocated resources must not exceed budget"
            )
        for disk_index, path_value in enumerate(guest.get("disk_paths", ["/"])):
            require_str(
                path_value,
                f"config/capacity-model.json.guests[{index}].disk_paths[{disk_index}]",
            )
        capacity_class = guest.get("capacity_class")
        if capacity_class is not None:
            require_str(
                capacity_class,
                f"config/capacity-model.json.guests[{index}].capacity_class",
            )
            if capacity_class not in CAPACITY_CLASSES:
                raise ValueError(
                    "config/capacity-model.json.guests["
                    f"{index}].capacity_class must be one of {list(CAPACITY_CLASSES)}"
                )
            if status != "planned":
                raise ValueError(
                    f"config/capacity-model.json.guests[{index}].capacity_class is only valid for planned guests"
                )

    for missing_guest in sorted(inventory_guest_names - seen_names):
        raise ValueError(
            f"capacity-model coverage is missing inventory guest '{missing_guest}'"
        )

    seen_reservations: set[str] = set()
    for index, item in enumerate(
        require_list(payload.get("reservations"), "config/capacity-model.json.reservations")
    ):
        reservation = require_mapping(item, f"config/capacity-model.json.reservations[{index}]")
        identifier = require_str(
            reservation.get("id"),
            f"config/capacity-model.json.reservations[{index}].id",
        )
        if identifier in seen_reservations:
            raise ValueError(f"duplicate capacity-model reservation id '{identifier}'")
        seen_reservations.add(identifier)
        kind = require_str(
            reservation.get("kind"),
            f"config/capacity-model.json.reservations[{index}].kind",
        )
        if kind not in {"ephemeral_pool", "planned_growth", "standby"}:
            raise ValueError(
                "config/capacity-model.json.reservations["
                f"{index}].kind must be ephemeral_pool, planned_growth, or standby"
            )
        status = require_str(
            reservation.get("status"),
            f"config/capacity-model.json.reservations[{index}].status",
        )
        if status not in {"reserved", "planned"}:
            raise ValueError(
                f"config/capacity-model.json.reservations[{index}].status must be reserved or planned"
            )
        resource_from_mapping(
            reservation.get("reserved"),
            f"config/capacity-model.json.reservations[{index}].reserved",
        )
        capacity_class = reservation.get("capacity_class")
        if capacity_class is not None:
            require_str(
                capacity_class,
                f"config/capacity-model.json.reservations[{index}].capacity_class",
            )
            if capacity_class not in CAPACITY_CLASSES:
                raise ValueError(
                    "config/capacity-model.json.reservations["
                    f"{index}].capacity_class must be one of {list(CAPACITY_CLASSES)}"
                )
        if kind == "ephemeral_pool":
            if capacity_class not in {None, "preview_burst"}:
                raise ValueError(
                    f"config/capacity-model.json.reservations[{index}].capacity_class must be preview_burst for ephemeral_pool"
                )
            vmid_range = require_mapping(
                reservation.get("vmid_range"),
                f"config/capacity-model.json.reservations[{index}].vmid_range",
            )
            start = int(
                require_number(
                    vmid_range.get("start"),
                    f"config/capacity-model.json.reservations[{index}].vmid_range.start",
                    1,
                )
            )
            end = int(
                require_number(
                    vmid_range.get("end"),
                    f"config/capacity-model.json.reservations[{index}].vmid_range.end",
                    1,
                )
            )
            if start > end:
                raise ValueError(
                    f"config/capacity-model.json.reservations[{index}].vmid_range.start must be <= end"
                )
            require_number(
                reservation.get("max_concurrent_vms"),
                f"config/capacity-model.json.reservations[{index}].max_concurrent_vms",
                1,
            )
        if kind == "standby":
            if capacity_class not in {None, "ha_reserved"}:
                raise ValueError(
                    f"config/capacity-model.json.reservations[{index}].capacity_class must be ha_reserved for standby reservations"
                )
            require_str(
                reservation.get("service_id"),
                f"config/capacity-model.json.reservations[{index}].service_id",
            )
            require_str(
                reservation.get("standby_vm"),
                f"config/capacity-model.json.reservations[{index}].standby_vm",
            )
            if reservation.get("standby_vmid") is not None:
                require_number(
                    reservation.get("standby_vmid"),
                    f"config/capacity-model.json.reservations[{index}].standby_vmid",
                    1,
                )
            require_str(
                reservation.get("storage_class"),
                f"config/capacity-model.json.reservations[{index}].storage_class",
            )
            require_str(
                reservation.get("required_network_attachment"),
                f"config/capacity-model.json.reservations[{index}].required_network_attachment",
            )
            if "vmid_range" in reservation:
                raise ValueError(
                    f"config/capacity-model.json.reservations[{index}].vmid_range is not valid for standby reservations"
                )
            if "max_concurrent_vms" in reservation:
                raise ValueError(
                    f"config/capacity-model.json.reservations[{index}].max_concurrent_vms is not valid for standby reservations"
                )
        if kind == "planned_growth" and capacity_class == "ha_reserved":
            raise ValueError(
                f"config/capacity-model.json.reservations[{index}] planned_growth must not use ha_reserved; use a planned standby guest or standby reservation instead"
            )


def normalize_requester_class(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    canonical = REQUESTER_CLASS_ALIASES.get(normalized)
    if canonical is None:
        raise ValueError(
            f"requester class '{value}' must be one of {sorted(REQUESTER_CLASS_ALIASES)}"
        )
    return canonical


def resources_fit(available: ResourceAmount, requested: ResourceAmount) -> bool:
    return (
        available.ram_gb >= requested.ram_gb
        and available.vcpu >= requested.vcpu
        and available.disk_gb >= requested.disk_gb
    )


def class_sources(model: CapacityModel) -> dict[str, list[str]]:
    sources = {identifier: [] for identifier in CAPACITY_CLASSES}
    for guest in model.guests:
        if guest.capacity_class is None:
            continue
        sources[guest.capacity_class].append(f"guest:{guest.name}[{guest.status}]")
    for reservation in model.reservations:
        if reservation.capacity_class is None:
            continue
        sources[reservation.capacity_class].append(
            f"reservation:{reservation.identifier}[{reservation.kind}]"
        )
    return sources


def reserved_capacity_by_class(model: CapacityModel) -> dict[str, ResourceAmount]:
    totals = {identifier: ZERO_RESOURCES for identifier in CAPACITY_CLASSES}
    for guest in model.guests:
        if guest.capacity_class is None:
            continue
        guest_resources = guest.allocated if guest.status == "active" else guest.budget
        totals[guest.capacity_class] = totals[guest.capacity_class].add(guest_resources)
    for reservation in model.reservations:
        if reservation.capacity_class is None:
            continue
        totals[reservation.capacity_class] = totals[reservation.capacity_class].add(reservation.reserved)
    return totals


def active_fixture_preview_usage() -> ResourceAmount:
    if not FIXTURE_RECEIPTS_DIR.exists():
        return ZERO_RESOURCES

    total = ZERO_RESOURCES
    for path in sorted(FIXTURE_RECEIPTS_DIR.glob("*.json")):
        try:
            payload = load_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict) or payload.get("status") != "active":
            continue
        definition = payload.get("definition")
        resources = definition.get("resources") if isinstance(definition, dict) else None
        if not isinstance(resources, dict):
            continue
        memory_mb = resources.get("memory_mb")
        cores = resources.get("cores")
        disk_gb = resources.get("disk_gb")
        if (
            not isinstance(memory_mb, (int, float))
            or not isinstance(cores, (int, float))
            or not isinstance(disk_gb, (int, float))
        ):
            continue
        total = total.add(
            ResourceAmount(
                ram_gb=math.ceil(float(memory_mb) / 1024.0),
                vcpu=float(cores),
                disk_gb=float(disk_gb),
            )
        )
    return total


def occupied_capacity_by_class(model: CapacityModel) -> dict[str, ResourceAmount]:
    occupied = {identifier: ZERO_RESOURCES for identifier in CAPACITY_CLASSES}
    occupied[PRIMARY_CLASS_FOR_REQUESTER["preview"]] = active_fixture_preview_usage()
    return occupied


def summarize_capacity_classes(model: CapacityModel) -> list[CapacityClassState]:
    reserved = reserved_capacity_by_class(model)
    occupied = occupied_capacity_by_class(model)
    sources = class_sources(model)
    return [
        CapacityClassState(
            identifier=identifier,
            reserved=reserved[identifier],
            occupied=occupied[identifier],
            available=subtract_resources(reserved[identifier], occupied[identifier]),
            sources=tuple(sorted(sources[identifier])),
        )
        for identifier in CAPACITY_CLASSES
    ]


def capacity_class_state_map(model: CapacityModel) -> dict[str, CapacityClassState]:
    return {entry.identifier: entry for entry in summarize_capacity_classes(model)}


def check_capacity_class_request(
    model: CapacityModel,
    *,
    requester_class: str,
    requested: ResourceAmount,
    declared_drill: bool = False,
    break_glass_ref: str | None = None,
    duration_hours: float | None = None,
) -> dict[str, Any]:
    canonical_requester = normalize_requester_class(requester_class)
    primary_class = PRIMARY_CLASS_FOR_REQUESTER[canonical_requester]
    states = capacity_class_state_map(model)
    primary_available = states[primary_class].available
    declared_drill_borrow_classes = DECLARED_DRILL_BORROW_BY_REQUESTER.get(canonical_requester, ())
    break_glass_borrow_classes = BREAK_GLASS_BORROW_BY_REQUESTER.get(canonical_requester, ())

    result: dict[str, Any] = {
        "approved": False,
        "requester_class": canonical_requester,
        "primary_class": primary_class,
        "requested": requested.__dict__,
        "admitted_classes": [primary_class],
        "borrowed_from": [],
        "declared_drill": declared_drill,
        "break_glass_ref": break_glass_ref,
        "duration_hours": duration_hours,
        "reasons": [],
        "conditions": [],
        "capacity_classes": [
            {
                "id": state.identifier,
                "reserved": state.reserved.__dict__,
                "occupied": state.occupied.__dict__,
                "available": state.available.__dict__,
            }
            for state in states.values()
        ],
    }

    if resources_fit(primary_available, requested):
        result["approved"] = True
        return result

    if declared_drill_borrow_classes:
        if not declared_drill:
            result["reasons"].append(
                f"{canonical_requester} requests may borrow from "
                f"{', '.join(declared_drill_borrow_classes)} only for a declared drill"
            )
        else:
            combined = primary_available
            admitted_classes = [primary_class]
            for borrow_class in declared_drill_borrow_classes:
                combined = combined.add(states[borrow_class].available)
                admitted_classes.append(borrow_class)
            if resources_fit(combined, requested):
                result["approved"] = True
                result["borrowed_from"] = admitted_classes[1:]
                result["admitted_classes"] = admitted_classes
                result["conditions"].append(
                    "Declared recovery drill approved with protected spillover."
                )
                return result

    if break_glass_borrow_classes:
        if not break_glass_ref:
            result["reasons"].append(
                "borrowing from protected classes requires explicit break-glass evidence"
            )
        if duration_hours is None or duration_hours <= 0:
            result["reasons"].append(
                "borrowing from protected classes must declare a positive time-bounded duration"
            )
        if break_glass_ref and duration_hours is not None and duration_hours > 0:
            combined = primary_available
            admitted_classes = [primary_class]
            if declared_drill:
                for borrow_class in declared_drill_borrow_classes:
                    combined = combined.add(states[borrow_class].available)
                    if borrow_class not in admitted_classes:
                        admitted_classes.append(borrow_class)
            for borrow_class in break_glass_borrow_classes:
                combined = combined.add(states[borrow_class].available)
                if borrow_class not in admitted_classes:
                    admitted_classes.append(borrow_class)
            if resources_fit(combined, requested):
                result["approved"] = True
                result["borrowed_from"] = admitted_classes[1:]
                result["admitted_classes"] = admitted_classes
                result["conditions"].append(
                    f"Break-glass admission approved with evidence `{break_glass_ref}` for {duration_hours:g}h."
                )
                return result
            result["reasons"].append(
                "requested resources still exceed the combined available protected capacity"
            )

    if canonical_requester == "preview":
        result["reasons"].append(
            "preview demand must remain within preview_burst and should spill to the auxiliary cloud domain before protected classes are borrowed"
        )
    elif canonical_requester == "standby":
        result["reasons"].append(
            "standby promotion requests must fit within the protected ha_reserved class"
        )
    else:
        result["reasons"].append(
            "requested resources exceed the available class capacity for this admission rule"
        )
    return result


def normalize_rows(raw_csv: str) -> list[dict[str, str]]:
    lines = [line for line in raw_csv.splitlines() if line and not line.startswith("#")]
    if not lines:
        return []
    reader = csv.DictReader(lines)
    return [row for row in reader if row]


def influx_scalar_query(command: list[str], flux: str) -> dict[str, float]:
    remote_command = (
        "sudo influx query --raw --host http://127.0.0.1:8086 --org lv3 "
        '--token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" '
        + shlex.quote(flux)
    )
    result = subprocess.run(
        [*command, remote_command],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    values: dict[str, float] = {}
    for row in normalize_rows(result.stdout):
        host = row.get("host")
        value = row.get("_value")
        if not host or value in {None, ""}:
            continue
        values[host] = float(value)
    return values


def ssh_monitoring_command() -> list[str] | None:
    key_path = bootstrap_key_path()
    inventory_hosts = load_inventory_hosts()
    jump_host = inventory_hosts.get("proxmox_florin")
    monitoring_host = inventory_hosts.get("monitoring-lv3")
    if not key_path or not jump_host or not monitoring_host:
        return None
    proxy = (
        f"ssh -q -i {shlex.quote(str(key_path))} "
        "-o IdentitiesOnly=yes -o BatchMode=yes "
        f"-o ConnectTimeout={SSH_TIMEOUT_SECONDS} "
        "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        f"ops@{jump_host} -W %h:%p"
    )
    return [
        "ssh",
        "-q",
        "-i",
        str(key_path),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={SSH_TIMEOUT_SECONDS}",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        f"ProxyCommand={proxy}",
        f"ops@{monitoring_host}",
    ]


def build_host_filters(hosts: list[str]) -> str:
    return " or ".join(f'r.host == "{host}"' for host in hosts)


def collect_live_actuals(model: CapacityModel) -> tuple[HostActuals, dict[str, GuestActuals], str]:
    ssh_command = ssh_monitoring_command()
    if not ssh_command:
        return HostActuals(), {guest.name: GuestActuals() for guest in model.guests}, "unavailable"

    metric_hosts = sorted({model.host.metrics_host} | {guest.metrics_host for guest in model.guests if guest.status == "active"})
    host_filter = build_host_filters(metric_hosts)

    memory_flux = (
        'from(bucket: "proxmox") '
        '|> range(start: -7d) '
        '|> filter(fn: (r) => r._measurement == "mem" and r._field == "used" and '
        + f"({host_filter})) "
        '|> group(columns: ["host"]) '
        "|> mean()"
    )
    cpu_flux = (
        'from(bucket: "proxmox") '
        '|> range(start: -7d) '
        '|> filter(fn: (r) => r._measurement == "cpu" and r.cpu == "cpu-total" and r._field == "usage_active" and '
        + f"({host_filter})) "
        '|> group(columns: ["host"]) '
        '|> quantile(column: "_value", q: 0.95, method: "estimate_tdigest")'
    )
    disk_flux = (
        'from(bucket: "proxmox") '
        '|> range(start: -24h) '
        '|> filter(fn: (r) => r._measurement == "disk" and r._field == "used" and r.path == "/" and '
        + f"({host_filter})) "
        '|> group(columns: ["host"]) '
        "|> last()"
    )

    memory_values = influx_scalar_query(ssh_command, memory_flux)
    cpu_values = influx_scalar_query(ssh_command, cpu_flux)
    disk_values = influx_scalar_query(ssh_command, disk_flux)

    guest_actuals: dict[str, GuestActuals] = {}
    for guest in model.guests:
        guest_disk = disk_values.get(guest.metrics_host)
        guest_actuals[guest.name] = GuestActuals(
            memory_used_gb=(
                memory_values[guest.metrics_host] / (1024**3)
                if guest.metrics_host in memory_values
                else None
            ),
            cpu_used_cores_p95=(
                cpu_values[guest.metrics_host] / 100.0 * guest.allocated.vcpu
                if guest.metrics_host in cpu_values
                else None
            ),
            disk_used_gb=(guest_disk / (1024**3)) if guest_disk is not None else None,
        )

    host_actuals = HostActuals(
        memory_used_gb=(
            memory_values[model.host.metrics_host] / (1024**3)
            if model.host.metrics_host in memory_values
            else None
        ),
        cpu_used_cores_p95=(
            cpu_values[model.host.metrics_host] / 100.0 * model.host.physical.vcpu
            if model.host.metrics_host in cpu_values
            else None
        ),
        disk_used_gb=(
            disk_values[model.host.metrics_host] / (1024**3)
            if model.host.metrics_host in disk_values
            else None
        ),
    )
    return host_actuals, guest_actuals, "ssh+influx"


def totals_for_guests(guests: list[GuestModel], attribute: str) -> ResourceAmount:
    total = ZERO_RESOURCES
    for guest in guests:
        total = total.add(getattr(guest, attribute))
    return total


def totals_for_reservations(reservations: list[ReservationModel]) -> ResourceAmount:
    total = ZERO_RESOURCES
    for reservation in reservations:
        total = total.add(reservation.reserved)
    return total


def calculate_committed(model: CapacityModel, *, include_planned: bool = False, include_reservations: bool = False) -> ResourceAmount:
    guests = [guest for guest in model.guests if guest.status == "active" or (include_planned and guest.status == "planned")]
    total = model.host.reserved_for_platform.add(totals_for_guests(guests, "allocated"))
    if include_reservations:
        total = total.add(totals_for_reservations(list(model.reservations)))
    return total


def calculate_budgeted(model: CapacityModel, *, include_planned: bool = True, include_reservations: bool = True) -> ResourceAmount:
    guests = [guest for guest in model.guests if guest.status == "active" or (include_planned and guest.status == "planned")]
    total = model.host.reserved_for_platform.add(totals_for_guests(guests, "budget"))
    if include_reservations:
        total = total.add(totals_for_reservations(list(model.reservations)))
    return total


def build_report(model: CapacityModel, *, with_live_metrics: bool = True) -> CapacityReport:
    if with_live_metrics:
        host_actuals, guest_actuals, source = collect_live_actuals(model)
    else:
        host_actuals = HostActuals()
        guest_actuals = {guest.name: GuestActuals() for guest in model.guests}
        source = "disabled"
    return CapacityReport(
        model=model,
        host_actuals=host_actuals,
        guest_actuals=guest_actuals,
        metrics_source=source,
    )


def render_resource_summary(label: str, committed: float, target: float, actual: float | None, unit: str) -> str:
    actual_text = f"{actual:.1f}{unit}" if actual is not None else "n/a"
    return (
        f"{label}: committed {committed:.1f}{unit} / target {target:.1f}{unit} "
        f"({safe_percent(committed, target):.1f}%), actual {actual_text}"
    )


def render_text(report: CapacityReport) -> str:
    model = report.model
    current = calculate_committed(model, include_planned=False, include_reservations=False)
    projected = calculate_committed(model, include_planned=True, include_reservations=True)
    budgeted = calculate_budgeted(model)
    target = model.host.target_absolute

    lines = [
        f"Capacity Report for {model.host.name} ({model.host.identifier})",
        f"Metrics source: {report.metrics_source}",
        "",
        "Host summary:",
        f"- {render_resource_summary('RAM', current.ram_gb, target.ram_gb, report.host_actuals.memory_used_gb, ' GB')}",
        f"- {render_resource_summary('vCPU', current.vcpu, target.vcpu, report.host_actuals.cpu_used_cores_p95, ' cores')}",
        f"- {render_resource_summary('Disk', current.disk_gb, target.disk_gb, report.host_actuals.disk_used_gb, ' GB')}",
        f"- Projected committed with planned capacity and reservations: RAM {projected.ram_gb:.1f} GB, vCPU {projected.vcpu:.1f}, disk {projected.disk_gb:.1f} GB",
        f"- Budget envelope with planned growth: RAM {budgeted.ram_gb:.1f} GB, vCPU {budgeted.vcpu:.1f}, disk {budgeted.disk_gb:.1f} GB",
        "",
        "Guest summary:",
    ]

    for guest in sorted(model.guests, key=lambda item: item.vmid):
        actuals = report.guest_actuals.get(guest.name, GuestActuals())
        base = (
            "- "
            f"{guest.name} [{guest.status}] "
            f"alloc={guest.allocated.ram_gb:.0f}GB/{guest.allocated.vcpu:.0f}vCPU/{guest.allocated.disk_gb:.0f}GB "
            f"budget={guest.budget.ram_gb:.0f}GB/{guest.budget.vcpu:.0f}vCPU/{guest.budget.disk_gb:.0f}GB "
        )
        if actuals.memory_used_gb is None:
            lines.append(base + "actual=n/a")
            continue

        cpu_text = "CPU n/a" if actuals.cpu_used_cores_p95 is None else f"{actuals.cpu_used_cores_p95:.2f} cores CPU p95"
        disk_text = "disk n/a" if actuals.disk_used_gb is None else f"{actuals.disk_used_gb:.1f}GB disk"
        lines.append(base + f"actual={actuals.memory_used_gb:.1f}GB RAM, {cpu_text}, {disk_text}")

    if model.reservations:
        lines.extend(["", "Reservations:"])
        for reservation in model.reservations:
            lines.append(
                "- "
                f"{reservation.identifier} [{reservation.kind}] "
                f"{reservation.reserved.ram_gb:.0f}GB RAM / {reservation.reserved.vcpu:.0f} vCPU / {reservation.reserved.disk_gb:.0f}GB disk"
            )
    lines.extend(["", "Capacity classes:"])
    for state in summarize_capacity_classes(model):
        sources = ", ".join(state.sources) if state.sources else "none declared"
        lines.append(
            "- "
            f"{state.identifier} reserved={state.reserved.ram_gb:.0f}GB/{state.reserved.vcpu:.0f}vCPU/{state.reserved.disk_gb:.0f}GB "
            f"occupied={state.occupied.ram_gb:.0f}GB/{state.occupied.vcpu:.0f}vCPU/{state.occupied.disk_gb:.0f}GB "
            f"available={state.available.ram_gb:.0f}GB/{state.available.vcpu:.0f}vCPU/{state.available.disk_gb:.0f}GB "
            f"sources={sources}"
        )
    return "\n".join(lines) + "\n"


def render_markdown(report: CapacityReport) -> str:
    model = report.model
    current = calculate_committed(model, include_planned=False, include_reservations=False)
    projected = calculate_committed(model, include_planned=True, include_reservations=True)
    target = model.host.target_absolute
    lines = [
        f"# Capacity Report ({model.host.name})",
        "",
        f"- Metrics source: `{report.metrics_source}`",
        f"- Current committed RAM: `{current.ram_gb:.1f} GB` of target `{target.ram_gb:.1f} GB`",
        f"- Current committed vCPU: `{current.vcpu:.1f}` of target `{target.vcpu:.1f}`",
        f"- Current committed disk: `{current.disk_gb:.1f} GB` of target `{target.disk_gb:.1f} GB`",
        f"- Projected committed with planned capacity and reservations: `{projected.ram_gb:.1f} GB RAM`, `{projected.vcpu:.1f} vCPU`, `{projected.disk_gb:.1f} GB disk`",
        "",
        "| Guest | Status | Allocated | Budget | Actual RAM | Actual CPU p95 | Actual Disk |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for guest in sorted(model.guests, key=lambda item: item.vmid):
        actuals = report.guest_actuals.get(guest.name, GuestActuals())
        lines.append(
            "| "
            + " | ".join(
                [
                    guest.name,
                    guest.status,
                    f"{guest.allocated.ram_gb:.0f} GB / {guest.allocated.vcpu:.0f} / {guest.allocated.disk_gb:.0f} GB",
                    f"{guest.budget.ram_gb:.0f} GB / {guest.budget.vcpu:.0f} / {guest.budget.disk_gb:.0f} GB",
                    "n/a" if actuals.memory_used_gb is None else f"{actuals.memory_used_gb:.1f} GB",
                    "n/a" if actuals.cpu_used_cores_p95 is None else f"{actuals.cpu_used_cores_p95:.2f} cores",
                    "n/a" if actuals.disk_used_gb is None else f"{actuals.disk_used_gb:.1f} GB",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "| Capacity Class | Reserved | Occupied | Available | Sources |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for state in summarize_capacity_classes(model):
        lines.append(
            "| "
            + " | ".join(
                [
                    state.identifier,
                    f"{state.reserved.ram_gb:.0f} GB / {state.reserved.vcpu:.0f} / {state.reserved.disk_gb:.0f} GB",
                    f"{state.occupied.ram_gb:.0f} GB / {state.occupied.vcpu:.0f} / {state.occupied.disk_gb:.0f} GB",
                    f"{state.available.ram_gb:.0f} GB / {state.available.vcpu:.0f} / {state.available.disk_gb:.0f} GB",
                    ", ".join(state.sources) if state.sources else "none declared",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def render_json(report: CapacityReport) -> str:
    model = report.model
    current = calculate_committed(model, include_planned=False, include_reservations=False)
    projected = calculate_committed(model, include_planned=True, include_reservations=True)
    payload = {
        "host": {
            "id": model.host.identifier,
            "name": model.host.name,
            "metrics_source": report.metrics_source,
            "target_absolute": {
                "ram_gb": model.host.target_absolute.ram_gb,
                "vcpu": model.host.target_absolute.vcpu,
                "disk_gb": model.host.target_absolute.disk_gb,
            },
            "current_committed": current.__dict__,
            "projected_committed": projected.__dict__,
            "actual": report.host_actuals.__dict__,
        },
        "guests": [
            {
                "vmid": guest.vmid,
                "name": guest.name,
                "status": guest.status,
                "environment": guest.environment,
                "capacity_class": guest.capacity_class,
                "allocated": guest.allocated.__dict__,
                "budget": guest.budget.__dict__,
                "actual": report.guest_actuals.get(guest.name, GuestActuals()).__dict__,
            }
            for guest in sorted(model.guests, key=lambda item: item.vmid)
        ],
        "reservations": [
            {
                "id": reservation.identifier,
                "kind": reservation.kind,
                "status": reservation.status,
                "reserved": reservation.reserved.__dict__,
                "capacity_class": reservation.capacity_class,
                "service_id": reservation.service_id,
                "standby_vm": reservation.standby_vm,
                "standby_vmid": reservation.standby_vmid,
                "storage_class": reservation.storage_class,
                "required_network_attachment": reservation.required_network_attachment,
                "max_concurrent_vms": reservation.max_concurrent_vms,
                "vmid_range": reservation.vmid_range,
            }
            for reservation in model.reservations
        ],
        "capacity_classes": [
            {
                "id": state.identifier,
                "reserved": state.reserved.__dict__,
                "occupied": state.occupied.__dict__,
                "available": state.available.__dict__,
                "sources": list(state.sources),
            }
            for state in summarize_capacity_classes(model)
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def render_prometheus(report: CapacityReport) -> str:
    model = report.model
    current = calculate_committed(model, include_planned=False, include_reservations=False)
    projected = calculate_committed(model, include_planned=True, include_reservations=True)
    target = model.host.target_absolute

    lines = [
        f'lv3_capacity_committed_ram_gb{{scope="active",host="{model.host.identifier}"}} {current.ram_gb:.6f}',
        f'lv3_capacity_committed_ram_gb{{scope="projected",host="{model.host.identifier}"}} {projected.ram_gb:.6f}',
        f'lv3_capacity_target_ram_gb{{host="{model.host.identifier}"}} {target.ram_gb:.6f}',
        f'lv3_capacity_committed_vcpu{{scope="active",host="{model.host.identifier}"}} {current.vcpu:.6f}',
        f'lv3_capacity_committed_vcpu{{scope="projected",host="{model.host.identifier}"}} {projected.vcpu:.6f}',
        f'lv3_capacity_target_vcpu{{host="{model.host.identifier}"}} {target.vcpu:.6f}',
        f'lv3_capacity_committed_disk_gb{{scope="active",host="{model.host.identifier}"}} {current.disk_gb:.6f}',
        f'lv3_capacity_committed_disk_gb{{scope="projected",host="{model.host.identifier}"}} {projected.disk_gb:.6f}',
        f'lv3_capacity_target_disk_gb{{host="{model.host.identifier}"}} {target.disk_gb:.6f}',
    ]
    if report.host_actuals.memory_used_gb is not None:
        lines.append(
            f'lv3_capacity_actual_ram_gb{{host="{model.host.identifier}"}} {report.host_actuals.memory_used_gb:.6f}'
        )
    if report.host_actuals.cpu_used_cores_p95 is not None:
        lines.append(
            f'lv3_capacity_actual_vcpu_p95{{host="{model.host.identifier}"}} {report.host_actuals.cpu_used_cores_p95:.6f}'
        )
    if report.host_actuals.disk_used_gb is not None:
        lines.append(
            f'lv3_capacity_actual_disk_gb{{host="{model.host.identifier}"}} {report.host_actuals.disk_used_gb:.6f}'
        )
    for guest in sorted(model.guests, key=lambda item: item.vmid):
        labels = f'guest="{guest.name}",status="{guest.status}"'
        lines.append(f"lv3_guest_allocated_ram_gb{{{labels}}} {guest.allocated.ram_gb:.6f}")
        lines.append(f"lv3_guest_budget_ram_gb{{{labels}}} {guest.budget.ram_gb:.6f}")
        lines.append(f"lv3_guest_allocated_vcpu{{{labels}}} {guest.allocated.vcpu:.6f}")
        lines.append(f"lv3_guest_budget_vcpu{{{labels}}} {guest.budget.vcpu:.6f}")
        lines.append(f"lv3_guest_allocated_disk_gb{{{labels}}} {guest.allocated.disk_gb:.6f}")
        lines.append(f"lv3_guest_budget_disk_gb{{{labels}}} {guest.budget.disk_gb:.6f}")
        actuals = report.guest_actuals.get(guest.name, GuestActuals())
        if actuals.memory_used_gb is not None:
            lines.append(f"lv3_guest_actual_ram_gb{{{labels}}} {actuals.memory_used_gb:.6f}")
        if actuals.cpu_used_cores_p95 is not None:
            lines.append(f"lv3_guest_actual_vcpu_p95{{{labels}}} {actuals.cpu_used_cores_p95:.6f}")
        if actuals.disk_used_gb is not None:
            lines.append(f"lv3_guest_actual_disk_gb{{{labels}}} {actuals.disk_used_gb:.6f}")
    for state in summarize_capacity_classes(model):
        lines.append(
            f'lv3_capacity_class_reserved_ram_gb{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.reserved.ram_gb:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_occupied_ram_gb{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.occupied.ram_gb:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_available_ram_gb{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.available.ram_gb:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_reserved_vcpu{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.reserved.vcpu:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_occupied_vcpu{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.occupied.vcpu:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_available_vcpu{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.available.vcpu:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_reserved_disk_gb{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.reserved.disk_gb:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_occupied_disk_gb{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.occupied.disk_gb:.6f}'
        )
        lines.append(
            f'lv3_capacity_class_available_disk_gb{{host="{model.host.identifier}",capacity_class="{state.identifier}"}} {state.available.disk_gb:.6f}'
        )
    return "\n".join(lines) + "\n"


def check_capacity_gate(
    model: CapacityModel,
    proposed_changes: list[ResourceAmount] | None = None,
) -> tuple[bool, list[str]]:
    proposed = proposed_changes or []
    baseline = calculate_committed(model, include_planned=False, include_reservations=False)
    delta = ZERO_RESOURCES
    for change in proposed:
        delta = delta.add(change)
    projected = baseline.add(delta)
    target = model.host.target_absolute

    reasons: list[str] = []
    if projected.ram_gb > target.ram_gb:
        reasons.append(
            f"projected RAM commitment {projected.ram_gb:.1f} GB exceeds target {target.ram_gb:.1f} GB"
        )
    if projected.vcpu > target.vcpu:
        reasons.append(
            f"projected vCPU commitment {projected.vcpu:.1f} exceeds target {target.vcpu:.1f}"
        )
    if projected.disk_gb > target.disk_gb:
        reasons.append(
            f"projected disk commitment {projected.disk_gb:.1f} GB exceeds target {target.disk_gb:.1f} GB"
        )
    return (not reasons, reasons)


def parse_proposed_changes(values: list[str]) -> list[ResourceAmount]:
    changes: list[ResourceAmount] = []
    for index, raw in enumerate(values):
        try:
            ram_text, vcpu_text, disk_text = raw.split(",", 2)
        except ValueError as exc:
            raise ValueError(
                f"--proposed-change #{index + 1} must use ram_gb,vcpu,disk_gb"
            ) from exc
        changes.append(
            ResourceAmount(
                ram_gb=float(ram_text),
                vcpu=float(vcpu_text),
                disk_gb=float(disk_text),
            )
        )
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the LV3 platform capacity report.")
    parser.add_argument("--model", type=Path, default=CAPACITY_MODEL_PATH)
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json", "prometheus"],
        default="text",
    )
    parser.add_argument("--no-live-metrics", action="store_true")
    parser.add_argument("--check-gate", action="store_true")
    parser.add_argument("--check-class-request", action="store_true")
    parser.add_argument("--requester-class", help="Capacity requester class: preview, recovery, or standby.")
    parser.add_argument("--declared-drill", action="store_true")
    parser.add_argument("--break-glass-ref")
    parser.add_argument("--duration-hours", type=float)
    parser.add_argument(
        "--proposed-change",
        action="append",
        default=[],
        help="Optional resource delta encoded as ram_gb,vcpu,disk_gb. Repeatable.",
    )
    args = parser.parse_args(argv)

    try:
        model = load_capacity_model(args.model)
        requested = ZERO_RESOURCES
        for change in parse_proposed_changes(args.proposed_change):
            requested = requested.add(change)
        if args.check_class_request:
            if not args.requester_class:
                raise ValueError("--requester-class is required with --check-class-request")
            payload = check_capacity_class_request(
                model,
                requester_class=args.requester_class,
                requested=requested,
                declared_drill=args.declared_drill,
                break_glass_ref=args.break_glass_ref,
                duration_hours=args.duration_hours,
            )
            print(json.dumps(payload, indent=2))
            return 0 if payload["approved"] else 2
        if args.check_gate:
            approved, reasons = check_capacity_gate(
                model,
                proposed_changes=parse_proposed_changes(args.proposed_change),
            )
            payload = {
                "approved": approved,
                "reasons": reasons,
            }
            print(json.dumps(payload, indent=2))
            return 0 if approved else 2

        report = build_report(model, with_live_metrics=not args.no_live_metrics)
        renderer = {
            "text": render_text,
            "markdown": render_markdown,
            "json": render_json,
            "prometheus": render_prometheus,
        }[args.format]
        print(renderer(report), end="")
        return 0
    except Exception as exc:
        print(f"capacity-report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
