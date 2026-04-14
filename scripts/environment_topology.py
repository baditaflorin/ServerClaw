#!/usr/bin/env python3

import argparse
import ipaddress
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

loaded_platform = sys.modules.get("platform")
if loaded_platform is not None and not hasattr(loaded_platform, "__path__"):
    loaded_platform_file = getattr(loaded_platform, "__file__", "")
    if not str(loaded_platform_file).startswith(str(REPO_ROOT / "platform")):
        sys.modules.pop("platform", None)

from platform.repo import TOPOLOGY_HOST, TOPOLOGY_HOST_VARS_PATH

from validation_toolkit import apply_identity_domain_overlay, require_list, require_mapping, require_str

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from shared_policy_packs import load_shared_policy_packs


ENVIRONMENT_TOPOLOGY_PATH = repo_path("config", "environment-topology.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")

ALLOWED_ENVIRONMENT_STATUSES = {"active", "planned"}
ALLOWED_TOPOLOGY_MODELS = {"single-node-shared-edge"}
ALLOWED_BINDING_STATUSES = {"active", "planned"}
SHARED_POLICIES = load_shared_policy_packs()
ALLOWED_ENVIRONMENT_PLACEMENT_CLASSES = SHARED_POLICIES.environment_placement_classes
ALLOWED_RESERVED_CAPACITY_EXCLUSIONS = SHARED_POLICIES.reserved_capacity_exclusions
ENVIRONMENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


def unique_string_list(value: Any, path: str) -> list[str]:
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


def load_environment_topology() -> dict[str, Any]:
    return apply_identity_domain_overlay(load_json(ENVIRONMENT_TOPOLOGY_PATH))


def validate_environment_topology(catalog: dict[str, Any], host_vars: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if catalog.get("schema_version") != "1.0.0":
        raise ValueError("environment topology must declare schema_version '1.0.0'")

    environments = require_list(catalog.get("environments"), "environments")
    if not environments:
        raise ValueError("environments must not be empty")

    guest_names = {
        guest["name"]
        for guest in require_list(host_vars.get("proxmox_guests"), "proxmox_guests")
        if isinstance(guest, dict) and "name" in guest
    }
    guest_names.add(TOPOLOGY_HOST)

    seen_ids: set[str] = set()
    indexed: dict[str, dict[str, Any]] = {}
    for index, environment in enumerate(environments):
        environment = require_mapping(environment, f"environments[{index}]")
        env_id = require_str(environment.get("id"), f"environments[{index}].id")
        if not ENVIRONMENT_ID_PATTERN.fullmatch(env_id):
            raise ValueError(f"environments[{index}].id must match {ENVIRONMENT_ID_PATTERN.pattern}")
        if env_id in seen_ids:
            raise ValueError(f"duplicate environment id: {env_id}")
        seen_ids.add(env_id)

        require_str(environment.get("name"), f"environments[{index}].name")
        status = require_str(environment.get("status"), f"environments[{index}].status")
        if status not in ALLOWED_ENVIRONMENT_STATUSES:
            raise ValueError(f"environments[{index}].status must be one of {sorted(ALLOWED_ENVIRONMENT_STATUSES)}")

        require_str(environment.get("purpose"), f"environments[{index}].purpose")
        base_domain = require_str(environment.get("base_domain"), f"environments[{index}].base_domain")
        require_str(
            environment.get("hostname_pattern"),
            f"environments[{index}].hostname_pattern",
        )
        require_str(
            environment.get("edge_service_id"),
            f"environments[{index}].edge_service_id",
        )
        edge_vm = require_str(environment.get("edge_vm"), f"environments[{index}].edge_vm")
        if edge_vm not in guest_names:
            raise ValueError(f"environments[{index}].edge_vm must reference a known guest or host id")
        ingress_ipv4 = require_str(
            environment.get("ingress_ipv4"),
            f"environments[{index}].ingress_ipv4",
        )
        try:
            ipaddress.IPv4Address(ingress_ipv4)
        except ipaddress.AddressValueError as exc:
            raise ValueError(f"environments[{index}].ingress_ipv4 must be a valid IPv4 address") from exc

        topology_model = require_str(
            environment.get("topology_model"),
            f"environments[{index}].topology_model",
        )
        if topology_model not in ALLOWED_TOPOLOGY_MODELS:
            raise ValueError(f"environments[{index}].topology_model must be one of {sorted(ALLOWED_TOPOLOGY_MODELS)}")

        require_str(
            environment.get("isolation_model"),
            f"environments[{index}].isolation_model",
        )
        if "operator_access" in environment:
            require_str(environment.get("operator_access"), f"environments[{index}].operator_access")
        if "notes" in environment:
            require_str(environment.get("notes"), f"environments[{index}].notes")
        if "placement" in environment:
            placement = require_mapping(environment.get("placement"), f"environments[{index}].placement")
            require_str(
                placement.get("failure_domain"),
                f"environments[{index}].placement.failure_domain",
            )
            placement_class = require_str(
                placement.get("placement_class"),
                f"environments[{index}].placement.placement_class",
            )
            if placement_class not in ALLOWED_ENVIRONMENT_PLACEMENT_CLASSES:
                raise ValueError(
                    "environments["
                    f"{index}].placement.placement_class must be one of "
                    f"{sorted(ALLOWED_ENVIRONMENT_PLACEMENT_CLASSES)}"
                )
            require_str(
                placement.get("anti_affinity_group"),
                f"environments[{index}].placement.anti_affinity_group",
            )
            for exception_index, exception in enumerate(
                require_list(
                    placement.get("co_location_exceptions"),
                    f"environments[{index}].placement.co_location_exceptions",
                )
            ):
                exception = require_mapping(
                    exception,
                    f"environments[{index}].placement.co_location_exceptions[{exception_index}]",
                )
                require_str(
                    exception.get("scope"),
                    f"environments[{index}].placement.co_location_exceptions[{exception_index}].scope",
                )
                require_str(
                    exception.get("rationale"),
                    f"environments[{index}].placement.co_location_exceptions[{exception_index}].rationale",
                )
            exclusions = unique_string_list(
                placement.get("reserved_capacity_exclusions"),
                f"environments[{index}].placement.reserved_capacity_exclusions",
            )
            invalid_exclusions = sorted(set(exclusions) - ALLOWED_RESERVED_CAPACITY_EXCLUSIONS)
            if invalid_exclusions:
                raise ValueError(
                    "environments["
                    f"{index}].placement.reserved_capacity_exclusions contains unknown values: "
                    + ", ".join(invalid_exclusions)
                )
        private_network = environment.get("private_network")
        if private_network is not None:
            private_network = require_mapping(private_network, f"environments[{index}].private_network")
            require_str(
                private_network.get("bridge"),
                f"environments[{index}].private_network.bridge",
            )
            gateway_ipv4 = require_str(
                private_network.get("gateway_ipv4"),
                f"environments[{index}].private_network.gateway_ipv4",
            )
            try:
                ipaddress.IPv4Address(gateway_ipv4)
            except ipaddress.AddressValueError as exc:
                raise ValueError(
                    f"environments[{index}].private_network.gateway_ipv4 must be a valid IPv4 address"
                ) from exc
            cidr = private_network.get("cidr")
            if isinstance(cidr, bool) or not isinstance(cidr, int) or not 1 <= cidr <= 32:
                raise ValueError(f"environments[{index}].private_network.cidr must be an integer between 1 and 32")
            network = require_str(
                private_network.get("network"),
                f"environments[{index}].private_network.network",
            )
            try:
                parsed_network = ipaddress.IPv4Network(network, strict=True)
            except ipaddress.AddressValueError as exc:
                raise ValueError(f"environments[{index}].private_network.network must be a valid IPv4 CIDR") from exc
            if parsed_network.prefixlen != cidr:
                raise ValueError(f"environments[{index}].private_network.network prefix length must match cidr {cidr}")
            if ipaddress.IPv4Address(gateway_ipv4) not in parsed_network:
                raise ValueError(f"environments[{index}].private_network.gateway_ipv4 must be inside {parsed_network}")

        if env_id == "production" and not base_domain:
            raise ValueError("production.base_domain must be set")

        indexed[env_id] = environment

    if "production" not in indexed:
        raise ValueError("environment topology must define a production environment")

    return indexed


def validate_environment_references(
    catalog: dict[str, Any],
    service_catalog: dict[str, Any],
    subdomain_catalog: dict[str, Any],
    host_vars: dict[str, Any],
) -> None:
    environments = validate_environment_topology(catalog, host_vars)
    services = require_list(service_catalog.get("services"), "services")
    subdomains = require_list(subdomain_catalog.get("subdomains"), "subdomains")

    service_index = {
        require_str(service.get("id"), f"services[{index}].id"): require_mapping(service, f"services[{index}]")
        for index, service in enumerate(services)
    }
    subdomain_index = {
        (
            require_str(entry.get("environment"), f"subdomains[{index}].environment"),
            require_str(entry.get("fqdn"), f"subdomains[{index}].fqdn"),
        ): require_mapping(entry, f"subdomains[{index}]")
        for index, entry in enumerate(subdomains)
    }

    for env_id, environment in environments.items():
        edge_service_id = environment["edge_service_id"]
        if edge_service_id not in service_index:
            raise ValueError(f"environment '{env_id}' references unknown edge service '{edge_service_id}'")
        if service_index[edge_service_id]["vm"] != environment["edge_vm"]:
            raise ValueError(
                f"environment '{env_id}' edge_vm '{environment['edge_vm']}' does not match "
                f"service '{edge_service_id}' vm '{service_index[edge_service_id]['vm']}'"
            )

    for service_id, service in service_index.items():
        bindings = require_mapping(service.get("environments"), f"services.{service_id}.environments")
        for env_id, binding in bindings.items():
            if env_id not in environments:
                raise ValueError(f"service '{service_id}' references unknown environment '{env_id}'")
            binding = require_mapping(binding, f"services.{service_id}.environments.{env_id}")
            status = require_str(
                binding.get("status"),
                f"services.{service_id}.environments.{env_id}.status",
            )
            if status not in ALLOWED_BINDING_STATUSES:
                raise ValueError(
                    "services."
                    f"{service_id}.environments.{env_id}.status must be one of "
                    f"{sorted(ALLOWED_BINDING_STATUSES)}"
                )
            require_str(binding.get("url"), f"services.{service_id}.environments.{env_id}.url")

            subdomain = binding.get("subdomain")
            if subdomain is None:
                continue
            subdomain = require_str(
                subdomain,
                f"services.{service_id}.environments.{env_id}.subdomain",
            )
            expected_suffix = environments[env_id]["base_domain"]
            if not subdomain.endswith(expected_suffix):
                raise ValueError(
                    f"service '{service_id}' environment '{env_id}' subdomain '{subdomain}' "
                    f"must end with '{expected_suffix}'"
                )
            entry = subdomain_index.get((env_id, subdomain))
            if entry is None:
                raise ValueError(
                    f"service '{service_id}' environment '{env_id}' subdomain '{subdomain}' "
                    "is missing from the subdomain catalog"
                )
            owner_service_id = entry.get("service_id")
            if owner_service_id != service_id:
                owner_service = service_index.get(str(owner_service_id))
                owner_bindings = (
                    require_mapping(owner_service.get("environments"), f"services.{owner_service_id}.environments")
                    if owner_service is not None
                    else {}
                )
                owner_binding = owner_bindings.get(env_id) if isinstance(owner_bindings, dict) else None
                owner_subdomain = (
                    require_str(
                        owner_binding.get("subdomain"), f"services.{owner_service_id}.environments.{env_id}.subdomain"
                    )
                    if isinstance(owner_binding, dict) and owner_binding.get("subdomain") is not None
                    else None
                )
                if owner_subdomain != subdomain:
                    raise ValueError(f"subdomain '{subdomain}' must reference service_id '{service_id}'")
            if entry.get("status") != status:
                raise ValueError(
                    f"service '{service_id}' environment '{env_id}' status '{status}' "
                    f"does not match subdomain status '{entry.get('status')}'"
                )

    for (env_id, fqdn), entry in subdomain_index.items():
        if env_id not in environments:
            raise ValueError(f"subdomain '{fqdn}' references unknown environment '{env_id}'")
        if not fqdn.endswith(environments[env_id]["base_domain"]):
            raise ValueError(
                f"subdomain '{fqdn}' does not fit the '{env_id}' base domain '{environments[env_id]['base_domain']}'"
            )
        service_id = entry.get("service_id")
        if service_id is None:
            continue
        if service_id not in service_index:
            raise ValueError(f"subdomain '{fqdn}' references unknown service_id '{service_id}'")
        bindings = require_mapping(
            service_index[service_id].get("environments"),
            f"services.{service_id}.environments",
        )
        binding = bindings.get(env_id)
        if binding is None:
            raise ValueError(
                f"subdomain '{fqdn}' environment '{env_id}' has no matching service binding for service '{service_id}'"
            )


def list_environments(catalog: dict[str, Any]) -> int:
    environments = catalog["environments"]
    for environment in sorted(environments, key=lambda item: item["id"]):
        print(f"{environment['id']}: {environment['name']} [{environment['status']}] {environment['hostname_pattern']}")
    return 0


def show_environment(catalog: dict[str, Any], environment_id: str) -> int:
    for environment in catalog["environments"]:
        if environment["id"] != environment_id:
            continue
        print(f"Environment: {environment['name']} ({environment['id']})")
        print(f"Status: {environment['status']}")
        print(f"Hostname pattern: {environment['hostname_pattern']}")
        print(f"Base domain: {environment['base_domain']}")
        print(f"Edge: {environment['edge_service_id']} on {environment['edge_vm']}")
        print(f"Ingress IPv4: {environment['ingress_ipv4']}")
        print(f"Topology model: {environment['topology_model']}")
        print(f"Isolation: {environment['isolation_model']}")
        print(f"Purpose: {environment['purpose']}")
        if environment.get("operator_access"):
            print(f"Operator access: {environment['operator_access']}")
        if environment.get("notes"):
            print(f"Notes: {environment['notes']}")
        return 0

    print(f"Unknown environment: {environment_id}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate the environment topology catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and exit.")
    parser.add_argument("--list", action="store_true", help="List known environments.")
    parser.add_argument("--environment", help="Print a readable summary for one environment id.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        catalog = load_environment_topology()
        host_vars = load_yaml(TOPOLOGY_HOST_VARS_PATH)
        validate_environment_topology(catalog, host_vars)
        if args.validate:
            service_catalog = apply_identity_domain_overlay(load_json(SERVICE_CATALOG_PATH))
            subdomain_catalog = apply_identity_domain_overlay(load_json(SUBDOMAIN_CATALOG_PATH))
            validate_environment_references(catalog, service_catalog, subdomain_catalog, host_vars)
            return 0
        if args.list:
            return list_environments(catalog)
        if args.environment:
            return show_environment(catalog, args.environment)
        if not args.environment:
            return list_environments(catalog)
        return 0
    except Exception as exc:
        return emit_cli_error("environment topology", exc)


if __name__ == "__main__":
    raise SystemExit(main())
