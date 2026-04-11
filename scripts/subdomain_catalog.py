#!/usr/bin/env python3

import argparse
import re
import socket
import sys
from pathlib import Path
from platform.repo import TOPOLOGY_HOST_VARS_PATH
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import (
    load_yaml_with_identity,
    require_bool,
    require_list,
    require_mapping,
    require_str,
    require_string_list,
)

from controller_automation_toolkit import emit_cli_error, load_json, repo_path
from environment_catalog import configured_environment_ids


SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
PUBLIC_EDGE_DEFAULTS_PATH = repo_path(
    "collections",
    "ansible_collections",
    "lv3",
    "platform",
    "roles",
    "nginx_edge_publication",
    "defaults",
    "main.yml",
)

ALLOWED_STATUSES = {"active", "planned", "reserved", "retiring"}
ALLOWED_EXPOSURES = {"edge-published", "informational-only", "private-only"}
ALLOWED_TLS_PROVIDERS = {"letsencrypt", "step-ca", "none"}
ALLOWED_AUTH_REQUIREMENTS = {"none", "edge_oidc", "upstream_auth", "private_network"}
ALLOWED_DNS_RECORD_TYPES = {"A", "AAAA", "CNAME"}
EDGE_ROUTE_EXPOSURES = {"edge-published", "informational-only"}
PROVISIONABLE_STATUSES = {"active", "planned"}
HOSTNAME_PATTERN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
ROUTE_HOSTNAME_PATTERN = re.compile(r"^(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)+$")
PREFIX_PATTERN = re.compile(r"^[a-z0-9-]+$")
ALLOWED_ENVIRONMENTS = set(configured_environment_ids())


def _is_jinja2_expression(value: str) -> bool:
    """Return True if the value contains a Jinja2 template expression."""
    return "{{" in value


def require_hostname(value: Any, path: str) -> str:
    value = require_str(value, path)
    if _is_jinja2_expression(value):
        return value  # Jinja2 template — resolved at Ansible runtime
    if not HOSTNAME_PATTERN.match(value):
        raise ValueError(f"{path} must be a lowercase hostname")
    return value


def require_route_hostname(value: Any, path: str) -> str:
    value = require_str(value, path)
    if _is_jinja2_expression(value):
        return value  # Jinja2 template — resolved at Ansible runtime
    if not ROUTE_HOSTNAME_PATTERN.match(value):
        raise ValueError(f"{path} must be a lowercase hostname or wildcard route hostname")
    return value


def require_prefix(value: Any, path: str) -> str:
    value = require_str(value, path)
    if _is_jinja2_expression(value):
        return value  # Jinja2 template — resolved at Ansible runtime
    if not PREFIX_PATTERN.match(value):
        raise ValueError(f"{path} must be a lowercase DNS label")
    return value


def require_adr_id(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not re.fullmatch(r"\d{4}", value):
        raise ValueError(f"{path} must be a four-digit ADR id")
    return value


def require_dns_record_type(value: Any, path: str) -> str:
    value = require_str(value, path)
    if value not in ALLOWED_DNS_RECORD_TYPES:
        raise ValueError(f"{path} must be one of {sorted(ALLOWED_DNS_RECORD_TYPES)}")
    return value


def infer_dns_record_type(target: str) -> str:
    try:
        socket.inet_pton(socket.AF_INET, target)
        return "A"
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, target)
        return "AAAA"
    except OSError:
        return "CNAME"


def expected_dns_records_for_entry(entry: dict[str, Any], path: str) -> list[dict[str, str]]:
    target = require_str(entry.get("target"), f"{path}.target")
    records = entry.get("expected_dns_records")
    if records is None:
        return [{"type": infer_dns_record_type(target), "value": target}]

    parsed_records: list[dict[str, str]] = []
    for index, record in enumerate(require_list(records, f"{path}.expected_dns_records")):
        record = require_mapping(record, f"{path}.expected_dns_records[{index}]")
        parsed_records.append(
            {
                "type": require_dns_record_type(
                    record.get("type"),
                    f"{path}.expected_dns_records[{index}].type",
                ),
                "value": require_str(
                    record.get("value"),
                    f"{path}.expected_dns_records[{index}].value",
                ),
            }
        )
    if not parsed_records:
        raise ValueError(f"{path}.expected_dns_records must not be empty when declared")
    if target not in {record["value"] for record in parsed_records}:
        raise ValueError(f"{path}.target must match one declared expected_dns_records value")
    return parsed_records


def load_subdomain_catalog() -> dict[str, Any]:
    return load_json(SUBDOMAIN_CATALOG_PATH)


def load_host_vars() -> dict[str, Any]:
    return load_yaml_with_identity(TOPOLOGY_HOST_VARS_PATH)


def load_public_edge_defaults() -> dict[str, Any]:
    return load_yaml_with_identity(PUBLIC_EDGE_DEFAULTS_PATH)


def validate_reserved_prefixes(catalog: dict[str, Any]) -> dict[str, set[str]]:
    reserved_prefixes = require_list(catalog.get("reserved_prefixes"), "reserved_prefixes")
    if not reserved_prefixes:
        raise ValueError("reserved_prefixes must not be empty")

    allowed_fqdns_by_prefix: dict[str, set[str]] = {}
    for index, entry in enumerate(reserved_prefixes):
        entry = require_mapping(entry, f"reserved_prefixes[{index}]")
        prefix = require_prefix(entry.get("prefix"), f"reserved_prefixes[{index}].prefix")
        if prefix in allowed_fqdns_by_prefix:
            raise ValueError(f"duplicate reserved prefix: {prefix}")

        require_adr_id(entry.get("owner_adr"), f"reserved_prefixes[{index}].owner_adr")
        allowed_fqdns = set()
        for allowed_index, fqdn in enumerate(
            require_string_list(
                entry.get("allowed_fqdns", []),
                f"reserved_prefixes[{index}].allowed_fqdns",
            )
        ):
            fqdn = require_hostname(
                fqdn,
                f"reserved_prefixes[{index}].allowed_fqdns[{allowed_index}]",
            )
            if fqdn.split(".", 1)[0] != prefix:
                raise ValueError(
                    f"reserved_prefixes[{index}].allowed_fqdns[{allowed_index}] must use prefix '{prefix}'"
                )
            allowed_fqdns.add(fqdn)

        notes = entry.get("notes")
        if notes is not None:
            require_str(notes, f"reserved_prefixes[{index}].notes")

        allowed_fqdns_by_prefix[prefix] = allowed_fqdns

    return allowed_fqdns_by_prefix


def collect_site_hostnames(
    site: dict[str, Any],
    path: str,
    *,
    allow_wildcards: bool = False,
) -> set[str]:
    require_site_hostname = require_route_hostname if allow_wildcards else require_hostname
    hostnames = {require_site_hostname(site.get("hostname"), f"{path}.hostname")}
    aliases = site.get("aliases", [])
    for index, alias in enumerate(require_string_list(aliases, f"{path}.aliases")):
        hostnames.add(require_site_hostname(alias, f"{path}.aliases[{index}]"))
    return hostnames


def hostname_matches_route(hostname: str, route_hostname: str) -> bool:
    if hostname == route_hostname:
        return True
    if not route_hostname.startswith("*."):
        return False
    suffix = route_hostname[1:]
    return hostname.endswith(suffix) and hostname != route_hostname[2:]


def collect_edge_route_hostnames(
    host_vars: dict[str, Any],
    public_edge_defaults: dict[str, Any],
) -> set[str]:
    hostnames: set[str] = set()

    service_topology = require_mapping(
        host_vars.get("lv3_service_topology"),
        "inventory/host_vars/proxmox-host.yml.lv3_service_topology",
    )
    for service_id, service in service_topology.items():
        service = require_mapping(
            service,
            f"inventory/host_vars/proxmox-host.yml.lv3_service_topology.{service_id}",
        )
        edge = service.get("edge")
        if edge is None:
            continue
        edge = require_mapping(
            edge,
            f"inventory/host_vars/proxmox-host.yml.lv3_service_topology.{service_id}.edge",
        )
        enabled = edge.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError(
                f"inventory/host_vars/proxmox-host.yml.lv3_service_topology.{service_id}.edge.enabled must be boolean"
            )
        if not enabled:
            continue

        route = {"hostname": service.get("public_hostname"), "aliases": edge.get("aliases", [])}
        hostnames.update(
            collect_site_hostnames(
                route,
                f"inventory/host_vars/proxmox-host.yml.lv3_service_topology.{service_id}",
                allow_wildcards=True,
            )
        )

    for index, site in enumerate(
        require_list(public_edge_defaults.get("public_edge_extra_sites", []), "public_edge_extra_sites")
    ):
        site = require_mapping(site, f"public_edge_extra_sites[{index}]")
        hostnames.update(collect_site_hostnames(site, f"public_edge_extra_sites[{index}]", allow_wildcards=True))

    apex_hostname = public_edge_defaults.get("public_edge_apex_hostname")
    if apex_hostname is not None:
        hostnames.add(require_hostname(apex_hostname, "public_edge_apex_hostname"))

    return hostnames


def collect_authenticated_edge_hostnames(public_edge_defaults: dict[str, Any]) -> set[str]:
    authenticated_sites = require_mapping(
        public_edge_defaults.get("public_edge_authenticated_sites", {}),
        "public_edge_authenticated_sites",
    )
    return {
        require_hostname(hostname, f"public_edge_authenticated_sites key '{hostname}'")
        for hostname in authenticated_sites
    }


def get_subdomain_entry(catalog: dict[str, Any], fqdn: str) -> dict[str, Any]:
    fqdn = require_hostname(fqdn, "fqdn")
    for index, entry in enumerate(require_list(catalog.get("subdomains"), "subdomains")):
        entry = require_mapping(entry, f"subdomains[{index}]")
        if entry.get("fqdn") == fqdn:
            return entry
    raise ValueError(f"subdomain '{fqdn}' is missing from the catalog")


def route_mode_for_entry(entry: dict[str, Any], edge_route_hostnames: set[str]) -> str:
    return (
        "edge"
        if any(hostname_matches_route(entry["fqdn"], route_hostname) for route_hostname in edge_route_hostnames)
        else "dns-only"
    )


def validate_provisionable_subdomain(entry: dict[str, Any], edge_route_hostnames: set[str]) -> str:
    fqdn = require_hostname(entry.get("fqdn"), "selected_subdomain.fqdn")
    status = require_str(entry.get("status"), "selected_subdomain.status")
    if status not in PROVISIONABLE_STATUSES:
        raise ValueError(f"subdomain '{fqdn}' has status '{status}' and cannot be provisioned")

    exposure = require_str(entry.get("exposure"), "selected_subdomain.exposure")
    route_mode = route_mode_for_entry(entry, edge_route_hostnames)
    if exposure == "edge-published" and route_mode != "edge":
        raise ValueError(f"subdomain '{fqdn}' is marked edge-published but no repo-managed NGINX route exists yet")

    return route_mode


def validate_subdomain_catalog(
    catalog: dict[str, Any],
    service_catalog: dict[str, Any],
    host_vars: dict[str, Any] | None = None,
    public_edge_defaults: dict[str, Any] | None = None,
) -> None:
    if catalog.get("schema_version") != "1.0.0":
        raise ValueError("subdomain catalog must declare schema_version '1.0.0'")

    allowed_fqdns_by_prefix = validate_reserved_prefixes(catalog)
    services = {service["id"] for service in service_catalog["services"]}
    subdomains = require_list(catalog.get("subdomains"), "subdomains")
    if not subdomains:
        raise ValueError("subdomains must not be empty")

    edge_route_hostnames: set[str] = set()
    authenticated_edge_hostnames: set[str] = set()
    if host_vars is not None and public_edge_defaults is not None:
        edge_route_hostnames = collect_edge_route_hostnames(host_vars, public_edge_defaults)
        authenticated_edge_hostnames = collect_authenticated_edge_hostnames(public_edge_defaults)

    seen_fqdns: set[str] = set()
    for index, entry in enumerate(subdomains):
        entry = require_mapping(entry, f"subdomains[{index}]")
        fqdn = require_hostname(entry.get("fqdn"), f"subdomains[{index}].fqdn")
        if fqdn in seen_fqdns:
            raise ValueError(f"duplicate subdomain: {fqdn}")
        seen_fqdns.add(fqdn)

        environment = require_str(entry.get("environment"), f"subdomains[{index}].environment")
        if environment not in ALLOWED_ENVIRONMENTS:
            raise ValueError(f"subdomains[{index}].environment must be one of {sorted(ALLOWED_ENVIRONMENTS)}")

        status = require_str(entry.get("status"), f"subdomains[{index}].status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"subdomains[{index}].status must be one of {sorted(ALLOWED_STATUSES)}")

        exposure = require_str(entry.get("exposure"), f"subdomains[{index}].exposure")
        if exposure not in ALLOWED_EXPOSURES:
            raise ValueError(f"subdomains[{index}].exposure must be one of {sorted(ALLOWED_EXPOSURES)}")

        auth_requirement = require_str(
            entry.get("auth_requirement"),
            f"subdomains[{index}].auth_requirement",
        )
        if auth_requirement not in ALLOWED_AUTH_REQUIREMENTS:
            raise ValueError(f"subdomains[{index}].auth_requirement must be one of {sorted(ALLOWED_AUTH_REQUIREMENTS)}")

        expected_dns_records_for_entry(entry, f"subdomains[{index}]")
        require_adr_id(entry.get("owner_adr"), f"subdomains[{index}].owner_adr")
        if "service_id" in entry and entry["service_id"] not in services and status == "active":
            raise ValueError(
                f"subdomains[{index}].service_id references unknown active service '{entry['service_id']}'"
            )

        reserved_prefix = fqdn.split(".", 1)[0]
        if reserved_prefix in allowed_fqdns_by_prefix and fqdn not in allowed_fqdns_by_prefix[reserved_prefix]:
            raise ValueError(
                f"subdomain '{fqdn}' uses reserved prefix '{reserved_prefix}' without an explicit allowlist entry"
            )

        tls = require_mapping(entry.get("tls"), f"subdomains[{index}].tls")
        provider = require_str(tls.get("provider"), f"subdomains[{index}].tls.provider")
        if provider not in ALLOWED_TLS_PROVIDERS:
            raise ValueError(f"subdomains[{index}].tls.provider must be one of {sorted(ALLOWED_TLS_PROVIDERS)}")
        auto_renew = require_bool(tls.get("auto_renew"), f"subdomains[{index}].tls.auto_renew")
        cert_path = tls.get("cert_path")
        if provider == "none":
            if auto_renew:
                raise ValueError(f"subdomains[{index}].tls.auto_renew must be false when tls.provider is 'none'")
            if cert_path is not None:
                raise ValueError(f"subdomains[{index}].tls.cert_path must be omitted when tls.provider is 'none'")
        else:
            require_str(cert_path, f"subdomains[{index}].tls.cert_path")

        if exposure == "edge-published" and provider == "none":
            raise ValueError(f"subdomains[{index}] edge-published hostnames must declare a TLS provider")
        if exposure == "private-only" and provider == "letsencrypt":
            raise ValueError(f"subdomains[{index}] private-only hostnames must not use Let's Encrypt")
        if exposure == "private-only" and auth_requirement != "private_network":
            raise ValueError(
                f"subdomains[{index}].auth_requirement must be 'private_network' for private-only hostnames"
            )
        if exposure != "private-only" and auth_requirement == "private_network":
            raise ValueError(
                f"subdomains[{index}].auth_requirement must not be 'private_network' for publicly exposed hostnames"
            )
        if auth_requirement == "edge_oidc" and status == "active" and fqdn not in edge_route_hostnames:
            raise ValueError(f"subdomain '{fqdn}' requires edge_oidc but has no repo-managed NGINX route")
        if (
            auth_requirement == "edge_oidc"
            and fqdn in edge_route_hostnames
            and fqdn not in authenticated_edge_hostnames
        ):
            raise ValueError(
                f"subdomain '{fqdn}' requires edge_oidc but is missing from public_edge_authenticated_sites"
            )
        if authenticated_edge_hostnames and fqdn in authenticated_edge_hostnames and auth_requirement != "edge_oidc":
            raise ValueError(
                f"subdomain '{fqdn}' is protected in public_edge_authenticated_sites but auth_requirement is '{auth_requirement}'"
            )

    for prefix, allowed_fqdns in allowed_fqdns_by_prefix.items():
        missing_allowed_fqdns = sorted(allowed_fqdns - seen_fqdns)
        if missing_allowed_fqdns:
            raise ValueError(
                f"reserved prefix '{prefix}' allowlist references uncatalogued hostnames: "
                + ", ".join(missing_allowed_fqdns)
            )

    if edge_route_hostnames:
        missing_edge_route_entries = sorted(
            route_hostname
            for route_hostname in edge_route_hostnames
            if not route_hostname.startswith("*.") and route_hostname not in seen_fqdns
        )
        if missing_edge_route_entries:
            raise ValueError(
                "repo-managed NGINX routes missing from the subdomain catalog: " + ", ".join(missing_edge_route_entries)
            )

        active_edge_published_missing_routes = sorted(
            entry["fqdn"]
            for entry in subdomains
            if entry["status"] == "active"
            and entry["exposure"] == "edge-published"
            and entry["fqdn"] not in edge_route_hostnames
        )
        if active_edge_published_missing_routes:
            raise ValueError(
                "active edge-published subdomains missing repo-managed NGINX routes: "
                + ", ".join(active_edge_published_missing_routes)
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the subdomain catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate and exit.")
    parser.add_argument("--fqdn", help="Select one FQDN from the catalog.")
    parser.add_argument(
        "--provision-check",
        action="store_true",
        help="Assert that the selected FQDN is provisionable with the repo-managed workflow.",
    )
    parser.add_argument(
        "--print-field",
        choices=("environment", "exposure", "status", "target", "route_mode"),
        help="Print one field from the selected FQDN after validation.",
    )
    args = parser.parse_args(argv)

    try:
        catalog = load_subdomain_catalog()
        service_catalog = load_json(SERVICE_CATALOG_PATH)
        host_vars = load_host_vars()
        public_edge_defaults = load_public_edge_defaults()
        validate_subdomain_catalog(catalog, service_catalog, host_vars, public_edge_defaults)

        if args.provision_check or args.print_field:
            if not args.fqdn:
                raise ValueError("--fqdn is required for --provision-check and --print-field")
            entry = get_subdomain_entry(catalog, args.fqdn)
            edge_route_hostnames = collect_edge_route_hostnames(host_vars, public_edge_defaults)
            route_mode = validate_provisionable_subdomain(entry, edge_route_hostnames)

            if args.print_field:
                if args.print_field == "route_mode":
                    print(route_mode)
                else:
                    print(entry[args.print_field])

        return 0
    except Exception as exc:
        return emit_cli_error("subdomain catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
