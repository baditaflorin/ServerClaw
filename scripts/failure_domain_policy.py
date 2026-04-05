#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Final

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_list, require_mapping, require_str

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from shared_policy_packs import load_shared_policy_packs


HOST_VARS_PATH: Final = repo_path("inventory", "host_vars", "proxmox_florin.yml")
ENVIRONMENT_TOPOLOGY_PATH: Final = repo_path("config", "environment-topology.json")
SERVICE_CATALOG_PATH: Final = repo_path("config", "service-capability-catalog.json")

SHARED_POLICIES = load_shared_policy_packs()
ALLOWED_DOMAIN_KINDS = SHARED_POLICIES.failure_domain_kinds
ALLOWED_DOMAIN_STATUSES = SHARED_POLICIES.failure_domain_statuses
ALLOWED_GUEST_PLACEMENT_CLASSES = SHARED_POLICIES.guest_placement_classes
ALLOWED_ENVIRONMENT_PLACEMENT_CLASSES = SHARED_POLICIES.environment_placement_classes
ALLOWED_RESERVED_CAPACITY_EXCLUSIONS = SHARED_POLICIES.reserved_capacity_exclusions
LIVE_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        text = require_str(item, f"{path}[{index}]")
        if text in seen:
            raise ValueError(f"{path} must not contain duplicates")
        seen.add(text)
        normalized.append(text)
    return normalized


def normalize_tag_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not normalized:
        raise ValueError(f"unable to derive a live tag token from {value!r}")
    return normalized


def load_host_vars() -> dict[str, Any]:
    return require_mapping(load_yaml(HOST_VARS_PATH), str(HOST_VARS_PATH))


def load_environment_topology() -> dict[str, Any]:
    return require_mapping(load_json(ENVIRONMENT_TOPOLOGY_PATH), str(ENVIRONMENT_TOPOLOGY_PATH))


def load_service_catalog() -> dict[str, Any]:
    return require_mapping(load_json(SERVICE_CATALOG_PATH), str(SERVICE_CATALOG_PATH))


def validate_domain_registry(host_vars: dict[str, Any]) -> dict[str, dict[str, Any]]:
    domains = require_list(host_vars.get("platform_failure_domains"), "host_vars.platform_failure_domains")
    if not domains:
        raise ValueError("host_vars.platform_failure_domains must not be empty")

    indexed: dict[str, dict[str, Any]] = {}
    seen_labels: set[str] = set()
    for index, domain in enumerate(domains):
        domain = require_mapping(domain, f"host_vars.platform_failure_domains[{index}]")
        domain_id = require_str(domain.get("id"), f"host_vars.platform_failure_domains[{index}].id")
        if domain_id in indexed:
            raise ValueError(f"duplicate failure domain id: {domain_id}")
        kind = require_str(domain.get("kind"), f"host_vars.platform_failure_domains[{index}].kind")
        if kind not in ALLOWED_DOMAIN_KINDS:
            raise ValueError(
                "host_vars.platform_failure_domains["
                f"{index}].kind must be one of {sorted(ALLOWED_DOMAIN_KINDS)}"
            )
        status = require_str(domain.get("status"), f"host_vars.platform_failure_domains[{index}].status")
        if status not in ALLOWED_DOMAIN_STATUSES:
            raise ValueError(
                "host_vars.platform_failure_domains["
                f"{index}].status must be one of {sorted(ALLOWED_DOMAIN_STATUSES)}"
            )
        live_label = require_str(
            domain.get("live_label"),
            f"host_vars.platform_failure_domains[{index}].live_label",
        )
        if not LIVE_LABEL_PATTERN.fullmatch(live_label):
            raise ValueError(
                f"host_vars.platform_failure_domains[{index}].live_label must match {LIVE_LABEL_PATTERN.pattern}"
            )
        if live_label in seen_labels:
            raise ValueError(f"duplicate failure-domain live_label: {live_label}")
        seen_labels.add(live_label)
        require_str(domain.get("summary"), f"host_vars.platform_failure_domains[{index}].summary")
        indexed[domain_id] = domain
    return indexed


def validate_co_location_exceptions(value: Any, path: str) -> list[dict[str, str]]:
    exceptions = require_list(value, path)
    normalized: list[dict[str, str]] = []
    for index, exception in enumerate(exceptions):
        exception = require_mapping(exception, f"{path}[{index}]")
        normalized.append(
            {
                "scope": require_str(exception.get("scope"), f"{path}[{index}].scope"),
                "rationale": require_str(exception.get("rationale"), f"{path}[{index}].rationale"),
            }
        )
    return normalized


def validate_guest_placement(
    guest: dict[str, Any],
    *,
    path: str,
    domain_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    placement = require_mapping(guest.get("placement"), f"{path}.placement")
    failure_domain = require_str(placement.get("failure_domain"), f"{path}.placement.failure_domain")
    if failure_domain not in domain_index:
        raise ValueError(f"{path}.placement.failure_domain references unknown domain '{failure_domain}'")
    placement_class = require_str(placement.get("placement_class"), f"{path}.placement.placement_class")
    if placement_class not in ALLOWED_GUEST_PLACEMENT_CLASSES:
        raise ValueError(
            f"{path}.placement.placement_class must be one of {sorted(ALLOWED_GUEST_PLACEMENT_CLASSES)}"
        )
    anti_affinity_group = require_str(
        placement.get("anti_affinity_group"),
        f"{path}.placement.anti_affinity_group",
    )
    normalize_tag_token(anti_affinity_group)
    return {
        "failure_domain": failure_domain,
        "placement_class": placement_class,
        "anti_affinity_group": anti_affinity_group,
        "co_location_exceptions": validate_co_location_exceptions(
            placement.get("co_location_exceptions"),
            f"{path}.placement.co_location_exceptions",
        ),
    }


def validate_environment_placement(
    environment: dict[str, Any],
    *,
    path: str,
    domain_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    placement = require_mapping(environment.get("placement"), f"{path}.placement")
    failure_domain = require_str(placement.get("failure_domain"), f"{path}.placement.failure_domain")
    if failure_domain not in domain_index:
        raise ValueError(f"{path}.placement.failure_domain references unknown domain '{failure_domain}'")
    placement_class = require_str(placement.get("placement_class"), f"{path}.placement.placement_class")
    if placement_class not in ALLOWED_ENVIRONMENT_PLACEMENT_CLASSES:
        raise ValueError(
            f"{path}.placement.placement_class must be one of {sorted(ALLOWED_ENVIRONMENT_PLACEMENT_CLASSES)}"
        )
    anti_affinity_group = require_str(
        placement.get("anti_affinity_group"),
        f"{path}.placement.anti_affinity_group",
    )
    normalize_tag_token(anti_affinity_group)
    exclusions = require_string_list(
        placement.get("reserved_capacity_exclusions"),
        f"{path}.placement.reserved_capacity_exclusions",
    )
    invalid_exclusions = sorted(set(exclusions) - ALLOWED_RESERVED_CAPACITY_EXCLUSIONS)
    if invalid_exclusions:
        raise ValueError(
            f"{path}.placement.reserved_capacity_exclusions contains unknown values: "
            + ", ".join(invalid_exclusions)
        )
    if "standby" not in exclusions:
        raise ValueError(
            f"{path}.placement.reserved_capacity_exclusions must include 'standby' for {placement_class} environments"
        )
    return {
        "failure_domain": failure_domain,
        "placement_class": placement_class,
        "anti_affinity_group": anti_affinity_group,
        "co_location_exceptions": validate_co_location_exceptions(
            placement.get("co_location_exceptions"),
            f"{path}.placement.co_location_exceptions",
        ),
        "reserved_capacity_exclusions": exclusions,
    }


def active_failure_domain_ids(domain_index: dict[str, dict[str, Any]]) -> set[str]:
    return {
        domain_id
        for domain_id, domain in domain_index.items()
        if domain["status"] == "active"
    }


def placement_live_tags(placement: dict[str, Any], domain_index: dict[str, dict[str, Any]]) -> list[str]:
    tags = [
        domain_index[placement["failure_domain"]]["live_label"],
        f"pc-{placement['placement_class']}",
        f"aag-{normalize_tag_token(placement['anti_affinity_group'])}",
    ]
    if placement["co_location_exceptions"]:
        tags.append("exc-same-domain")
    return tags


def guest_placement_index(
    host_vars: dict[str, Any],
    domain_index: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    guests = require_list(host_vars.get("proxmox_guests"), "host_vars.proxmox_guests")
    indexed: dict[str, dict[str, Any]] = {}
    for index, guest in enumerate(guests):
        guest = require_mapping(guest, f"host_vars.proxmox_guests[{index}]")
        guest_name = require_str(guest.get("name"), f"host_vars.proxmox_guests[{index}].name")
        placement = validate_guest_placement(
            guest,
            path=f"host_vars.proxmox_guests[{index}]",
            domain_index=domain_index,
        )
        indexed[guest_name] = {
            "name": guest_name,
            "vmid": guest.get("vmid"),
            "placement": placement,
            "base_tags": require_string_list(guest.get("tags"), f"host_vars.proxmox_guests[{index}].tags"),
            "live_tags": placement_live_tags(placement, domain_index),
        }
    return indexed


def environment_placement_index(
    environment_topology: dict[str, Any],
    domain_index: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    environments = require_list(environment_topology.get("environments"), "environment_topology.environments")
    indexed: dict[str, dict[str, Any]] = {}
    for index, environment in enumerate(environments):
        environment = require_mapping(environment, f"environment_topology.environments[{index}]")
        env_id = require_str(environment.get("id"), f"environment_topology.environments[{index}].id")
        if env_id == "production":
            continue
        if "placement" not in environment:
            raise ValueError(
                f"environment_topology.environments[{index}] must declare placement metadata for non-production environment '{env_id}'"
            )
        indexed[env_id] = {
            "id": env_id,
            "placement": validate_environment_placement(
                environment,
                path=f"environment_topology.environments[{index}]",
                domain_index=domain_index,
            ),
        }
    return indexed


def validate_service_alignment(
    service_catalog: dict[str, Any],
    guest_index: dict[str, dict[str, Any]],
    domain_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    services = require_list(service_catalog.get("services"), "service_catalog.services")
    active_domains = active_failure_domain_ids(domain_index)
    standby_pairs: list[dict[str, Any]] = []
    standby_guests: set[str] = set()

    for index, service in enumerate(services):
        service = require_mapping(service, f"service_catalog.services[{index}]")
        service_id = require_str(service.get("id"), f"service_catalog.services[{index}].id")
        redundancy = service.get("redundancy")
        if not isinstance(redundancy, dict):
            continue
        standby = redundancy.get("standby")
        if not isinstance(standby, dict):
            continue

        primary_vm = require_str(service.get("vm"), f"service_catalog.services[{index}].vm")
        standby_vm = require_str(
            standby.get("vm"),
            f"service_catalog.services[{index}].redundancy.standby.vm",
        )
        if primary_vm not in guest_index:
            raise ValueError(f"service '{service_id}' primary vm '{primary_vm}' is missing placement metadata")
        if standby_vm not in guest_index:
            raise ValueError(f"service '{service_id}' standby vm '{standby_vm}' is missing placement metadata")

        primary = guest_index[primary_vm]["placement"]
        replica = guest_index[standby_vm]["placement"]
        if primary["placement_class"] != "primary":
            raise ValueError(
                f"service '{service_id}' primary vm '{primary_vm}' must use placement_class 'primary'"
            )
        if replica["placement_class"] != "standby":
            raise ValueError(
                f"service '{service_id}' standby vm '{standby_vm}' must use placement_class 'standby'"
            )
        if primary["anti_affinity_group"] != replica["anti_affinity_group"]:
            raise ValueError(
                f"service '{service_id}' primary and standby must share one anti_affinity_group"
            )
        if primary["failure_domain"] == replica["failure_domain"]:
            if len(active_domains) > 1:
                raise ValueError(
                    f"service '{service_id}' primary and standby share failure domain '{primary['failure_domain']}' despite multiple active domains"
                )
            if not replica["co_location_exceptions"]:
                raise ValueError(
                    f"service '{service_id}' standby must declare a same-domain co_location_exception while only one active failure domain exists"
                )
        standby_pairs.append(
            {
                "service_id": service_id,
                "primary_vm": primary_vm,
                "standby_vm": standby_vm,
                "anti_affinity_group": primary["anti_affinity_group"],
                "primary_failure_domain": primary["failure_domain"],
                "standby_failure_domain": replica["failure_domain"],
            }
        )
        standby_guests.add(standby_vm)

    declared_standby_guests = {
        guest_name
        for guest_name, guest in guest_index.items()
        if guest["placement"]["placement_class"] == "standby"
    }
    if declared_standby_guests != standby_guests:
        missing = sorted(declared_standby_guests - standby_guests)
        extra = sorted(standby_guests - declared_standby_guests)
        details: list[str] = []
        if missing:
            details.append("standby guests without service alignment: " + ", ".join(missing))
        if extra:
            details.append("standby services missing guest declarations: " + ", ".join(extra))
        raise ValueError("failure-domain standby alignment is incomplete: " + "; ".join(details))

    return standby_pairs


def build_policy_report(
    host_vars: dict[str, Any] | None = None,
    environment_topology: dict[str, Any] | None = None,
    service_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    loaded_host_vars = host_vars or load_host_vars()
    loaded_environment_topology = environment_topology or load_environment_topology()
    loaded_service_catalog = service_catalog or load_service_catalog()

    domain_index = validate_domain_registry(loaded_host_vars)
    guest_index = guest_placement_index(loaded_host_vars, domain_index)
    environment_index = environment_placement_index(loaded_environment_topology, domain_index)
    standby_pairs = validate_service_alignment(loaded_service_catalog, guest_index, domain_index)

    return {
        "active_failure_domains": sorted(active_failure_domain_ids(domain_index)),
        "failure_domains": [
            {
                "id": domain_id,
                "kind": domain["kind"],
                "status": domain["status"],
                "live_label": domain["live_label"],
            }
            for domain_id, domain in sorted(domain_index.items())
        ],
        "guests": [
            {
                "name": guest_name,
                "vmid": guest["vmid"],
                "placement": guest["placement"],
                "live_tags": guest["live_tags"],
            }
            for guest_name, guest in sorted(guest_index.items())
        ],
        "environments": [
            {
                "id": env_id,
                "placement": environment["placement"],
            }
            for env_id, environment in sorted(environment_index.items())
        ],
        "standby_pairs": standby_pairs,
    }


def validate_failure_domain_policy(
    host_vars: dict[str, Any] | None = None,
    environment_topology: dict[str, Any] | None = None,
    service_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_policy_report(
        host_vars=host_vars,
        environment_topology=environment_topology,
        service_catalog=service_catalog,
    )


def render_text(report: dict[str, Any]) -> str:
    lines = ["Failure Domains:"]
    for domain in report["failure_domains"]:
        lines.append(
            f"- {domain['id']} [{domain['status']}] kind={domain['kind']} label={domain['live_label']}"
        )
    lines.append("Guests:")
    for guest in report["guests"]:
        placement = guest["placement"]
        lines.append(
            f"- {guest['name']} vmid={guest['vmid']} class={placement['placement_class']} "
            f"domain={placement['failure_domain']} group={placement['anti_affinity_group']} "
            f"tags={','.join(guest['live_tags'])}"
        )
    if report["environments"]:
        lines.append("Environments:")
        for environment in report["environments"]:
            placement = environment["placement"]
            lines.append(
                f"- {environment['id']} class={placement['placement_class']} "
                f"domain={placement['failure_domain']} group={placement['anti_affinity_group']} "
                f"reserved={','.join(placement['reserved_capacity_exclusions'])}"
            )
    if report["standby_pairs"]:
        lines.append("Standby Pairs:")
        for pair in report["standby_pairs"]:
            lines.append(
                f"- {pair['service_id']}: {pair['primary_vm']} -> {pair['standby_vm']} "
                f"(group={pair['anti_affinity_group']})"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate failure-domain labels and anti-affinity policy.")
    parser.add_argument("--validate", action="store_true", help="Validate the repo failure-domain policy.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    try:
        report = validate_failure_domain_policy()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_cli_error(str(exc))
        return 2

    if args.validate:
        print("Failure-domain policy OK")
        return 0
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
