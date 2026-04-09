#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from platform.datetime_compat import UTC, datetime
from controller_automation_toolkit import emit_cli_error, repo_path, write_json
from publication_contract import (
    publication_access_model,
    publication_audience,
    publication_delivery_model,
    registry_entries,
)
import subdomain_catalog


REGISTRY_PATH = repo_path("config", "subdomain-exposure-registry.json")
REGISTRY_SCHEMA_PATH = repo_path("docs", "schema", "subdomain-exposure-registry.schema.json")
CERTIFICATE_CATALOG_PATH = repo_path("config", "certificate-catalog.json")
HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
PUBLIC_EDGE_DEFAULTS_PATH = repo_path("roles", "nginx_edge_publication", "defaults", "main.yml")
GLOBAL_VARS_PATH = repo_path("inventory", "group_vars", "all.yml")
RECEIPTS_DIR = repo_path("receipts", "subdomain-exposure-audit")
HETZNER_DNS_API_TOKEN_ENV = "HETZNER_DNS_API_TOKEN"
EXPECTED_EDGE_OIDC_PREFIX = "https://sso.localhost/realms/lv3/protocol/openid-connect/auth"
PROBE_USER_AGENT = "lv3-subdomain-exposure-audit/1.0"
PUBLIC_ENDPOINT_STATUSES = {"active", "planned"}
EXPECTED_ISSUER_BY_TLS_PROVIDER = {
    "letsencrypt": "letsencrypt",
    "step-ca": "step-ca",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def compact_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def iso_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def load_certificate_catalog() -> dict[str, Any]:
    return json.loads(CERTIFICATE_CATALOG_PATH.read_text(encoding="utf-8"))


def hostname_record_type(target: str) -> str:
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


def _route_entry(
    *,
    hostname: str,
    route_source: str,
    route_kind: str,
    service_id: str | None,
    site: dict[str, Any],
    authenticated_sites: dict[str, Any],
) -> dict[str, Any]:
    protected = hostname in authenticated_sites
    return {
        "hostname": hostname,
        "route_source": route_source,
        "route_kind": route_kind,
        "service_id": service_id,
        "edge_auth": "oauth2_proxy" if protected else "none",
        "unauthenticated_paths": list(authenticated_sites.get(hostname, {}).get("unauthenticated_paths", [])),
        "unauthenticated_prefix_paths": list(
            authenticated_sites.get(hostname, {}).get("unauthenticated_prefix_paths", [])
        ),
        "metadata": {
            key: value
            for key, value in site.items()
            if key not in {"hostname", "aliases", "kind"}
        },
    }


def _publication_entry(
    entry: dict[str, Any],
    route: dict[str, Any] | None,
    service: dict[str, Any] | None,
) -> dict[str, Any]:
    route_mode = "edge" if route else "dns-only"
    delivery_model = publication_delivery_model(entry["exposure"])
    access_model = publication_access_model(entry["auth_requirement"])
    audience = publication_audience(
        exposure=entry["exposure"],
        auth_requirement=entry["auth_requirement"],
    )
    dns_records = subdomain_catalog.expected_dns_records_for_entry(entry, f"subdomains[{entry['fqdn']}]")
    service_dns = subdomain_catalog.require_mapping(service.get("dns", {}), f"service.{entry['fqdn']}.dns") if service else {}
    service_access = subdomain_catalog.require_mapping(service.get("access", {}), f"service.{entry['fqdn']}.access") if service else {}
    route_target = entry["target"]
    if route:
        route_target = (
            route["metadata"].get("upstream")
            or route["metadata"].get("redirect_target_hostname")
            or route_target
        )
    return {
        "fqdn": entry["fqdn"],
        "service_id": entry.get("service_id"),
        "environment": entry["environment"],
        "status": entry["status"],
        "owner_adr": entry["owner_adr"],
        "publication": {
            "delivery_model": delivery_model,
            "access_model": access_model,
            "audience": audience,
        },
        "assertions": {
            "publication_class": entry["exposure"],
            "environment": entry["environment"],
            "audience": audience,
            "auth_requirement": entry["auth_requirement"],
            "route_target": {
                "service_id": route["service_id"] if route and route["service_id"] else entry.get("service_id"),
                "kind": route["route_kind"] if route else service_access.get("kind", "dns-only"),
                "source": route["route_source"] if route else service_access.get("kind", "dns-only"),
                "target": route_target,
                "target_port": entry.get("target_port"),
            },
        },
        "evidence_plan": {
            "dns_resolution": bool(service_dns.get("managed", True)),
            "dns_zone": bool(service_dns.get("managed", True)),
            "http_auth": entry["status"] == "active"
            and entry["environment"] == "production"
            and access_model == "platform-sso",
            "private_route": entry["status"] == "active"
            and entry["environment"] == "production"
            and delivery_model == "private-network",
            "tls": entry["status"] == "active"
            and entry["environment"] == "production"
            and entry["tls"]["provider"] != "none"
            and entry.get("target_port") in (None, 443),
        },
        "adapter": {
            "dns": {
                "target": entry["target"],
                "target_port": entry.get("target_port"),
                "record_type": dns_records[0]["type"],
                "records": dns_records,
                "managed": bool(service_dns.get("managed", True)),
                "visibility": service_dns.get(
                    "visibility",
                    "public" if delivery_model != "private-network" else "tailnet",
                ),
                "zone_expected": bool(service_dns.get("managed", True)),
            },
            "routing": {
                "mode": route_mode,
                "source": route["route_source"] if route else "dns-only",
                "kind": route["route_kind"] if route else None,
            },
            "edge_auth": {
                "provider": route["edge_auth"] if route else "none",
                "unauthenticated_paths": route["unauthenticated_paths"] if route else [],
                "unauthenticated_prefix_paths": route["unauthenticated_prefix_paths"] if route else [],
            },
            "repo_route_service_id": route["service_id"] if route else None,
            "repo_route_metadata": route["metadata"] if route else {},
            "tls": deepcopy(entry["tls"]),
        },
        "live_tracking_expected": entry["status"] == "active"
        and entry["environment"] == "production"
        and delivery_model != "private-network",
        "notes": entry.get("notes"),
    }


def build_edge_route_index(
    host_vars: dict[str, Any],
    public_edge_defaults: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    authenticated_sites = subdomain_catalog.require_mapping(
        public_edge_defaults.get("public_edge_authenticated_sites", {}),
        "public_edge_authenticated_sites",
    )

    service_topology = subdomain_catalog.require_mapping(
        host_vars.get("lv3_service_topology"),
        "inventory/host_vars/proxmox_florin.yml.lv3_service_topology",
    )
    for service_id, service in service_topology.items():
        service = subdomain_catalog.require_mapping(
            service,
            f"inventory/host_vars/proxmox_florin.yml.lv3_service_topology.{service_id}",
        )
        edge = service.get("edge")
        if edge is None:
            continue
        edge = subdomain_catalog.require_mapping(
            edge,
            f"inventory/host_vars/proxmox_florin.yml.lv3_service_topology.{service_id}.edge",
        )
        if not edge.get("enabled"):
            continue
        site = {
            "hostname": service.get("public_hostname"),
            "aliases": edge.get("aliases", []),
            "kind": edge.get("kind"),
        }
        site.update(edge)
        for hostname in subdomain_catalog.collect_site_hostnames(
            site,
            f"inventory/host_vars/proxmox_florin.yml.lv3_service_topology.{service_id}",
            allow_wildcards=True,
        ):
            routes[hostname] = _route_entry(
                hostname=hostname,
                route_source="service_topology",
                route_kind=edge.get("kind", "unknown"),
                service_id=service_id,
                site=site,
                authenticated_sites=authenticated_sites,
            )

    for index, site in enumerate(
        subdomain_catalog.require_list(
            public_edge_defaults.get("public_edge_extra_sites", []),
            "public_edge_extra_sites",
        )
    ):
        site = subdomain_catalog.require_mapping(site, f"public_edge_extra_sites[{index}]")
        for hostname in subdomain_catalog.collect_site_hostnames(
            site,
            f"public_edge_extra_sites[{index}]",
            allow_wildcards=True,
        ):
            routes[hostname] = _route_entry(
                hostname=hostname,
                route_source="public_edge_extra_sites",
                route_kind=subdomain_catalog.require_str(
                    site.get("kind"), f"public_edge_extra_sites[{index}].kind"
                ),
                service_id=None,
                site=site,
                authenticated_sites=authenticated_sites,
            )

    apex_hostname = public_edge_defaults.get("public_edge_apex_hostname")
    if apex_hostname is not None:
        apex_hostname = subdomain_catalog.require_hostname(apex_hostname, "public_edge_apex_hostname")
        nginx_edge_service = subdomain_catalog.require_mapping(
            service_topology.get("nginx_edge"),
            "inventory/host_vars/proxmox_florin.yml.lv3_service_topology.nginx_edge",
        )
        routes[apex_hostname] = _route_entry(
            hostname=apex_hostname,
            route_source="public_edge_apex",
            route_kind="redirect",
            service_id="nginx_edge",
            site={
                "hostname": apex_hostname,
                "kind": "redirect",
                "redirect_target_hostname": subdomain_catalog.require_hostname(
                    nginx_edge_service.get("public_hostname"),
                    "inventory/host_vars/proxmox_florin.yml.lv3_service_topology.nginx_edge.public_hostname",
                ),
            },
            authenticated_sites=authenticated_sites,
        )

    return routes


def build_service_topology_index(host_vars: dict[str, Any]) -> dict[str, dict[str, Any]]:
    service_topology = subdomain_catalog.require_mapping(
        host_vars.get("lv3_service_topology"),
        "inventory/host_vars/proxmox_florin.yml.lv3_service_topology",
    )
    return {
        service_id: subdomain_catalog.require_mapping(
            service,
            f"inventory/host_vars/proxmox_florin.yml.lv3_service_topology.{service_id}",
        )
        for service_id, service in service_topology.items()
    }


def resolve_route_for_hostname(
    hostname: str,
    route_index: dict[str, dict[str, Any]] | list[dict[str, Any]],
) -> dict[str, Any] | None:
    if isinstance(route_index, list):
        route_index = {
            subdomain_catalog.require_str(entry.get("hostname"), "route.hostname"): entry
            for entry in route_index
        }
    route = route_index.get(hostname)
    if route is not None:
        return route
    for route_hostname, route_entry in route_index.items():
        if subdomain_catalog.hostname_matches_route(hostname, route_hostname):
            return route_entry
        for alias in route_entry.get("aliases", []):
            if subdomain_catalog.hostname_matches_route(hostname, alias):
                return route_entry
    return None


def build_registry(
    catalog: dict[str, Any] | None = None,
    host_vars: dict[str, Any] | None = None,
    public_edge_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if catalog is None:
        catalog = subdomain_catalog.load_subdomain_catalog()
    if host_vars is None:
        host_vars = subdomain_catalog.load_host_vars()
    if public_edge_defaults is None:
        public_edge_defaults = subdomain_catalog.load_public_edge_defaults()

    service_catalog = subdomain_catalog.load_json(subdomain_catalog.SERVICE_CATALOG_PATH)
    subdomain_catalog.validate_subdomain_catalog(catalog, service_catalog, host_vars, public_edge_defaults)

    route_index = build_edge_route_index(host_vars, public_edge_defaults)
    service_topology_index = build_service_topology_index(host_vars)
    publication_entries: list[dict[str, Any]] = []

    for entry in sorted(catalog["subdomains"], key=lambda item: item["fqdn"]):
        route = resolve_route_for_hostname(entry["fqdn"], route_index)
        publication_entries.append(_publication_entry(entry, route, service_topology_index.get(entry.get("service_id"))))

    active_entries = [entry for entry in publication_entries if entry["status"] == "active"]
    summary = {
        "catalog_total": len(publication_entries),
        "active_total": len(active_entries),
        "active_public_total": sum(1 for entry in active_entries if entry["live_tracking_expected"]),
        "active_private_total": sum(
            1 for entry in active_entries if entry["publication"]["delivery_model"] == "private-network"
        ),
        "planned_total": sum(1 for entry in publication_entries if entry["status"] == "planned"),
        "shared_edge_total": sum(
            1 for entry in publication_entries if entry["publication"]["delivery_model"] == "shared-edge"
        ),
        "platform_sso_total": sum(
            1 for entry in publication_entries if entry["publication"]["access_model"] == "platform-sso"
        ),
    }

    return {
        "schema_version": "2.0.0",
        "zone_name": "localhost",
        "publications": publication_entries,
        "summary": summary,
    }


def check_registry_current(registry: dict[str, Any]) -> None:
    current = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if current != registry:
        raise ValueError(
            "config/subdomain-exposure-registry.json is out of date; run "
            "'python3 scripts/subdomain_exposure_audit.py --write-registry'"
        )


def expected_edge_certificate_domains(
    host_vars: dict[str, Any] | None = None,
    public_edge_defaults: dict[str, Any] | None = None,
) -> set[str]:
    if host_vars is None:
        host_vars = subdomain_catalog.load_host_vars()
    if public_edge_defaults is None:
        public_edge_defaults = subdomain_catalog.load_public_edge_defaults()
    return {
        hostname
        for hostname in subdomain_catalog.collect_edge_route_hostnames(host_vars, public_edge_defaults)
        if not hostname.startswith("*.")
    }


def is_public_hostname(hostname: str, zone_name: str) -> bool:
    return hostname == zone_name or hostname.endswith(f".{zone_name}")


def collect_repo_findings(
    registry: dict[str, Any],
    *,
    certificate_catalog: dict[str, Any] | None = None,
    edge_certificate_domains: set[str] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if certificate_catalog is None:
        certificate_catalog = load_certificate_catalog()
    if edge_certificate_domains is None:
        edge_certificate_domains = expected_edge_certificate_domains()
    zone_name = registry.get("zone_name", "localhost")

    certificate_entries = subdomain_catalog.require_list(
        certificate_catalog.get("certificates"),
        "config/certificate-catalog.json.certificates",
    )
    certificates_by_host: dict[str, list[dict[str, Any]]] = {}
    for index, certificate in enumerate(certificate_entries):
        certificate = subdomain_catalog.require_mapping(
            certificate,
            f"config/certificate-catalog.json.certificates[{index}]",
        )
        endpoint = subdomain_catalog.require_mapping(
            certificate.get("endpoint"),
            f"config/certificate-catalog.json.certificates[{index}].endpoint",
        )
        host = subdomain_catalog.require_str(
            endpoint.get("host"),
            f"config/certificate-catalog.json.certificates[{index}].endpoint.host",
        )
        certificates_by_host.setdefault(host, []).append(certificate)

    catalogued_public_certificate_hosts: set[str] = set()
    for entry in registry_entries(registry):
        status = entry.get("status")
        access_model = entry["publication"]["access_model"]
        edge_auth_provider = entry["adapter"]["edge_auth"]["provider"]
        if status == "active" and access_model == "platform-sso" and edge_auth_provider != "oauth2_proxy":
            findings.append(
                {
                    "check": "repo_edge_auth",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "catalog_requires_edge_oidc_but_route_is_not_protected",
                    "detail": (
                        "The canonical publication model requires platform-sso access, "
                        "but the repo-managed edge adapter lacks oauth2-proxy protection."
                    ),
                }
            )
        if status == "active" and access_model != "platform-sso" and edge_auth_provider == "oauth2_proxy":
            findings.append(
                {
                    "check": "repo_edge_auth",
                    "severity": "WARN",
                    "subdomain": entry["fqdn"],
                    "finding": "route_is_protected_but_catalog_does_not_require_edge_oidc",
                    "detail": (
                        "The repo-managed edge adapter is protected by oauth2-proxy, "
                        "but the canonical publication model does not classify the hostname as platform-sso."
                    ),
                }
            )

        if entry.get("environment") != "production":
            continue
        if status not in PUBLIC_ENDPOINT_STATUSES:
            continue
        if entry["publication"]["delivery_model"] == "private-network":
            continue
        if entry["adapter"]["tls"]["provider"] == "none":
            continue

        fqdn = entry["fqdn"]
        catalogued_public_certificate_hosts.add(fqdn)
        matching_certificates = certificates_by_host.get(fqdn, [])
        if not matching_certificates:
            findings.append(
                {
                    "check": "certificate_plan",
                    "severity": "CRITICAL",
                    "subdomain": fqdn,
                    "finding": "catalog_public_hostname_missing_from_certificate_catalog",
                    "detail": (
                        "The canonical public-endpoint catalog declares a live TLS hostname, "
                        "but config/certificate-catalog.json does not plan certificate coverage for it."
                    ),
                }
            )
        elif len(matching_certificates) > 1:
            findings.append(
                {
                    "check": "certificate_plan",
                    "severity": "CRITICAL",
                    "subdomain": fqdn,
                    "finding": "catalog_public_hostname_has_duplicate_certificate_plan_entries",
                    "detail": (
                        "config/certificate-catalog.json defines more than one certificate entry "
                        f"for {fqdn}, so admission cannot prove which plan owns the hostname."
                    ),
                }
            )
        else:
            certificate = matching_certificates[0]
            if certificate.get("service_id") != entry.get("service_id"):
                findings.append(
                    {
                        "check": "certificate_plan",
                        "severity": "CRITICAL",
                        "subdomain": fqdn,
                        "finding": "certificate_plan_service_id_mismatch",
                        "detail": (
                            f"The public-endpoint catalog maps {fqdn} to service "
                            f"'{entry.get('service_id')}', but config/certificate-catalog.json maps it to "
                            f"'{certificate.get('service_id')}'."
                        ),
                    }
                )
            endpoint = certificate.get("endpoint", {})
            if endpoint.get("server_name") != fqdn:
                findings.append(
                    {
                        "check": "certificate_plan",
                        "severity": "CRITICAL",
                        "subdomain": fqdn,
                        "finding": "certificate_plan_server_name_mismatch",
                        "detail": (
                            "The certificate catalog does not use the public hostname as the "
                            f"declared TLS server_name for {fqdn}."
                        ),
                    }
                )
            expected_issuer = EXPECTED_ISSUER_BY_TLS_PROVIDER.get(entry["adapter"]["tls"]["provider"])
            if expected_issuer and certificate.get("expected_issuer") != expected_issuer:
                findings.append(
                    {
                        "check": "certificate_plan",
                        "severity": "CRITICAL",
                        "subdomain": fqdn,
                        "finding": "certificate_plan_expected_issuer_mismatch",
                        "detail": (
                            f"The public-endpoint catalog expects TLS provider "
                            f"'{entry['adapter']['tls']['provider']}', but config/certificate-catalog.json declares "
                            f"'{certificate.get('expected_issuer')}' for {fqdn}."
                        ),
                    }
                )

        if (
            entry["publication"]["delivery_model"] in {"shared-edge", "informational-edge"}
            and entry["adapter"]["tls"]["provider"] == "letsencrypt"
            and fqdn not in edge_certificate_domains
        ):
            findings.append(
                {
                    "check": "certificate_plan",
                    "severity": "CRITICAL",
                    "subdomain": fqdn,
                    "finding": "catalog_public_hostname_missing_from_shared_edge_certificate_domains",
                    "detail": (
                        "The public hostname is published through the shared edge, but the "
                        "rendered shared-edge certificate domain set does not include it."
                    ),
                }
            )

    for certificate_host in sorted(certificates_by_host):
        if not is_public_hostname(certificate_host, zone_name):
            continue
        if certificate_host in catalogued_public_certificate_hosts:
            continue
        findings.append(
            {
                "check": "certificate_plan",
                "severity": "CRITICAL",
                "subdomain": certificate_host,
                "finding": "certificate_catalog_public_hostname_missing_from_endpoint_catalog",
                "detail": (
                    "config/certificate-catalog.json carries a public hostname that the canonical "
                    "public-endpoint catalog does not declare as an active or planned TLS endpoint."
                ),
            }
        )
    return findings


def resolve_public_records(fqdn: str) -> list[str]:
    try:
        answers = socket.getaddrinfo(fqdn, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return sorted({normalize_resolved_address(item[4][0]) for item in answers})


def normalize_resolved_address(address: str) -> str:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        return str(parsed.ipv4_mapped)
    return str(parsed)


def expected_resolvable_dns_values(entry: dict[str, Any]) -> set[str]:
    return {
        record["value"]
        for record in entry["adapter"]["dns"].get("records", [])
        if record["type"] in {"A", "AAAA"}
    }


def collect_resolution_findings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in registry_entries(registry):
        if entry["environment"] != "production":
            continue
        if not entry["adapter"]["dns"].get("zone_expected", False):
            continue

        expected_values = expected_resolvable_dns_values(entry)
        if not expected_values:
            continue

        actual = set(resolve_public_records(entry["fqdn"]))
        expected_present = expected_values.issubset(actual)

        if entry["status"] == "active" and not expected_present:
            findings.append(
                {
                    "check": "dns_resolution",
                    "severity": "WARN",
                    "subdomain": entry["fqdn"],
                    "finding": "active_subdomain_missing_expected_public_resolution",
                    "detail": (
                        "Expected DNS resolution to include "
                        f"{sorted(expected_values)}; observed {sorted(actual) or ['<missing>']}."
                    ),
                }
            )
        elif entry["status"] != "active" and actual.intersection(expected_values):
            findings.append(
                {
                    "check": "dns_resolution",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "subdomain_resolves_publicly_but_is_not_tracked_active",
                    "detail": (
                        "The hostname resolves to the declared DNS target set "
                        f"{sorted(actual.intersection(expected_values))} while the catalog status is "
                        f"'{entry['status']}'."
                    ),
                }
            )
    return findings


def http_probe(url: str) -> tuple[int | None, str, dict[str, str]]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(url, headers={"User-Agent": PROBE_USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10, context=context) as response:
            return response.status, response.geturl(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.geturl(), dict(exc.headers.items())


def collect_http_auth_findings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in registry_entries(registry):
        if entry["status"] != "active":
            continue
        if entry["environment"] != "production":
            continue
        if entry["publication"]["access_model"] != "platform-sso":
            continue

        _, final_url, _ = http_probe(f"https://{entry['fqdn']}/")
        if not final_url.startswith(EXPECTED_EDGE_OIDC_PREFIX):
            findings.append(
                {
                    "check": "http_auth_probe",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "edge_oidc_not_enforced_on_live_probe",
                    "detail": f"Expected unauthenticated access to redirect into Keycloak; observed final URL {final_url}.",
                }
            )
    return findings


def fetch_hetzner_zone_records(
    *,
    api_base_url: str = "https://dns.hetzner.com/api/v1",
    zone_name: str = "localhost",
    api_token: str | None = None,
) -> list[dict[str, Any]]:
    token = api_token or os.environ.get(HETZNER_DNS_API_TOKEN_ENV, "").strip()
    if not token:
        return []

    zone_request = urllib.request.Request(
        f"{api_base_url}/zones?name={urllib.parse.quote(zone_name)}",
        headers={"Auth-API-Token": token},
    )
    with urllib.request.urlopen(zone_request, timeout=10) as response:
        zones_payload = json.loads(response.read().decode("utf-8"))
    zones = zones_payload.get("zones", [])
    if len(zones) != 1:
        raise ValueError(f"expected exactly one Hetzner DNS zone named {zone_name}")
    zone_id = zones[0]["id"]

    records_request = urllib.request.Request(
        f"{api_base_url}/records?zone_id={urllib.parse.quote(zone_id)}",
        headers={"Auth-API-Token": token},
    )
    with urllib.request.urlopen(records_request, timeout=10) as response:
        records_payload = json.loads(response.read().decode("utf-8"))
    return list(records_payload.get("records", []))


def dns_record_identity(record: dict[str, Any]) -> tuple[str, str]:
    return record["type"], record["value"]


def collect_zone_findings(registry: dict[str, Any], zone_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    catalog_by_fqdn = {entry["fqdn"]: entry for entry in registry_entries(registry)}
    relevant_zone_records: list[dict[str, Any]] = []

    for record in zone_records:
        name = record.get("name")
        record_type = record.get("type")
        value = record.get("value")
        if record_type not in {"A", "AAAA", "CNAME"}:
            continue
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        fqdn = zone_name_from_record(name, registry["zone_name"])
        if fqdn is None:
            continue
        relevant_zone_records.append({"fqdn": fqdn, "type": record_type, "value": value, "ttl": record.get("ttl")})

    zone_by_fqdn: dict[str, list[dict[str, Any]]] = {}
    for record in relevant_zone_records:
        zone_by_fqdn.setdefault(record["fqdn"], []).append(record)

    for fqdn, records in sorted(zone_by_fqdn.items()):
        if fqdn not in catalog_by_fqdn:
            for record in records:
                findings.append(
                    {
                        "check": "hetzner_zone",
                        "severity": "CRITICAL",
                        "subdomain": fqdn,
                        "finding": "undeclared_subdomain_present_in_zone",
                        "detail": f"Hetzner DNS exposes {record['type']} {record['value']} for {fqdn}, but the hostname is missing from the catalog.",
                    }
                )
            continue

        expected_dns_records = {
            dns_record_identity(record)
            for record in catalog_by_fqdn[fqdn]["adapter"]["dns"].get("records", [])
        }
        actual_dns_records = {dns_record_identity(record) for record in records}
        missing_dns_records = sorted(expected_dns_records - actual_dns_records)
        unexpected_dns_records = sorted(actual_dns_records - expected_dns_records)
        if missing_dns_records or unexpected_dns_records:
            findings.append(
                {
                    "check": "hetzner_zone",
                    "severity": "WARN",
                    "subdomain": fqdn,
                    "finding": "zone_record_differs_from_catalog",
                    "detail": (
                        f"Expected {sorted(expected_dns_records)} from the catalog; observed "
                        f"{sorted(actual_dns_records)} in Hetzner DNS."
                        + (
                            f" Missing {missing_dns_records}."
                            if missing_dns_records
                            else ""
                        )
                        + (
                            f" Unexpected {unexpected_dns_records}."
                            if unexpected_dns_records
                            else ""
                        )
                    ),
                }
            )

    for fqdn, entry in sorted(catalog_by_fqdn.items()):
        if entry["environment"] != "production":
            continue
        if entry["status"] != "active":
            continue
        if not entry["adapter"]["dns"].get("zone_expected", False):
            continue
        if fqdn not in zone_by_fqdn:
            findings.append(
                {
                    "check": "hetzner_zone",
                    "severity": "WARN",
                    "subdomain": fqdn,
                    "finding": "active_catalog_subdomain_missing_from_zone",
                    "detail": "Catalog marks the hostname active, but no corresponding A/AAAA/CNAME record exists in Hetzner DNS.",
                }
            )

    return findings


def zone_name_from_record(name: str, zone_name: str) -> str | None:
    if name == "@":
        return zone_name
    if name.endswith(f".{zone_name}"):
        return name
    if "." in name:
        return None
    return f"{name}.{zone_name}"


def decode_certificate(binary_certificate: bytes) -> dict[str, Any]:
    if not binary_certificate:
        raise ValueError("server did not present a decodable certificate")
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as handle:
        handle.write(ssl.DER_cert_to_PEM_cert(binary_certificate))
        certificate_path = handle.name
    try:
        return ssl._ssl._test_decode_cert(certificate_path)
    finally:
        os.unlink(certificate_path)


def fetch_tls_metadata(
    hostname: str,
    *,
    port: int = 443,
    connect_host: str | None = None,
) -> dict[str, Any]:
    verification_error: str | None = None
    cert: dict[str, Any]
    connect_target = connect_host or hostname

    context = ssl.create_default_context()
    try:
        with socket.create_connection((connect_target, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                cert = tls_sock.getpeercert() or decode_certificate(tls_sock.getpeercert(binary_form=True))
    except ssl.SSLCertVerificationError as exc:
        verification_error = str(exc)
        insecure_context = ssl.create_default_context()
        insecure_context.check_hostname = False
        insecure_context.verify_mode = ssl.CERT_NONE
        with socket.create_connection((connect_target, port), timeout=10) as sock:
            with insecure_context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
                cert = decode_certificate(tls_sock.getpeercert(binary_form=True))

    not_after = cert.get("notAfter")
    if not not_after:
        raise ValueError(f"certificate for {hostname} did not expose notAfter")
    expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    seconds_remaining = int((expires_at - utc_now()).total_seconds())
    issuer = ", ".join("=".join(part) for parts in cert.get("issuer", []) for part in parts)
    return {
        "expires_at": iso_timestamp(expires_at),
        "seconds_remaining": seconds_remaining,
        "hours_remaining": int(seconds_remaining // 3600),
        "days_remaining": int(seconds_remaining // 86400),
        "issuer": issuer,
        "verification_error": verification_error,
    }


def should_report_tls_verification_error(entry: dict[str, Any], verification_error: str) -> bool:
    if entry["adapter"]["tls"]["provider"] != "step-ca":
        return True
    return "hostname" in verification_error.lower()


def tls_expiry_policy(entry: dict[str, Any]) -> dict[str, int | str]:
    tls = entry.get("adapter", {}).get("tls", {})
    if tls.get("provider") == "step-ca" and tls.get("auto_renew"):
        return {
            "warn_seconds": 6 * 3600,
            "critical_seconds": 3600,
            "unit": "hours",
        }
    return {
        "warn_seconds": 14 * 86400,
        "critical_seconds": 7 * 86400,
        "unit": "days",
    }


def collect_tls_findings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in registry_entries(registry):
        if entry["status"] != "active":
            continue
        if entry["environment"] != "production":
            continue
        if entry["adapter"]["tls"]["provider"] == "none":
            continue
        if entry["adapter"]["dns"]["target_port"] not in (None, 443):
            continue

        try:
            metadata = fetch_tls_metadata(
                entry["fqdn"],
                port=entry["adapter"]["dns"].get("target_port") or 443,
                connect_host=(
                    entry["adapter"]["dns"]["target"]
                    if entry.get("publication", {}).get("delivery_model") == "private-network"
                    else None
                ),
            )
        except (OSError, ssl.SSLError, ValueError) as exc:
            findings.append(
                {
                    "check": "tls_certificate",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "tls_probe_failed",
                    "detail": f"TLS probe failed: {exc}",
                }
            )
            continue

        if metadata.get("verification_error") and should_report_tls_verification_error(entry, metadata["verification_error"]):
            findings.append(
                {
                    "check": "tls_certificate",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "certificate_hostname_mismatch",
                    "detail": f"TLS identity verification failed: {metadata['verification_error']}",
                }
            )
        expiry_policy = tls_expiry_policy(entry)
        if metadata["seconds_remaining"] < expiry_policy["warn_seconds"]:
            remaining_value = metadata["hours_remaining"] if expiry_policy["unit"] == "hours" else metadata["days_remaining"]
            findings.append(
                {
                    "check": "tls_certificate",
                    "severity": (
                        "WARN"
                        if metadata["seconds_remaining"] >= expiry_policy["critical_seconds"]
                        else "CRITICAL"
                    ),
                    "subdomain": entry["fqdn"],
                    "finding": "certificate_expiry_imminent",
                    "detail": (
                        f"TLS certificate expires on {metadata['expires_at']} "
                        f"({remaining_value} {expiry_policy['unit']} remaining)."
                    ),
                }
            )
    return findings


def collect_private_route_findings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in registry_entries(registry):
        if not entry.get("evidence_plan", {}).get("private_route", False):
            continue
        target = entry["adapter"]["dns"]["target"]
        port = entry["adapter"]["dns"].get("target_port")
        if port is None:
            continue
        try:
            with socket.create_connection((target, port), timeout=10):
                pass
        except OSError as exc:
            findings.append(
                {
                    "check": "private_route_probe",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "private_route_unreachable",
                    "detail": f"Failed to connect to the declared private route target {target}:{port}: {exc}",
                }
            )
    return findings


def build_report(
    registry: dict[str, Any],
    *,
    include_live_dns: bool = False,
    include_http_auth: bool = False,
    include_private_routes: bool = False,
    include_tls: bool = False,
    include_hetzner_zone: bool = False,
) -> dict[str, Any]:
    findings = collect_repo_findings(registry)
    zone_records: list[dict[str, Any]] = []
    if include_live_dns:
        findings.extend(collect_resolution_findings(registry))
    if include_http_auth:
        findings.extend(collect_http_auth_findings(registry))
    if include_private_routes:
        findings.extend(collect_private_route_findings(registry))
    if include_tls:
        findings.extend(collect_tls_findings(registry))
    if include_hetzner_zone:
        zone_records = fetch_hetzner_zone_records()
        if zone_records:
            findings.extend(collect_zone_findings(registry, zone_records))

    severity_counts: dict[str, int] = {}
    for finding in findings:
        severity = finding["severity"]
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    dns_records_checked = sum(
        1
        for entry in registry_entries(registry)
        if entry["status"] == "active"
        and entry["environment"] == "production"
        and entry["adapter"]["dns"].get("zone_expected", False)
    )
    private_routes_checked = sum(
        1
        for entry in registry_entries(registry)
        if entry.get("evidence_plan", {}).get("private_route", False)
    )

    return {
        "audit_run_id": str(uuid.uuid4()),
        "audited_at": iso_timestamp(utc_now()),
        "registry_path": str(REGISTRY_PATH),
        "publications_in_catalog": registry["summary"]["catalog_total"],
        "active_publications_tracked": registry["summary"]["active_total"],
        "dns_records_checked": dns_records_checked if include_live_dns else 0,
        "private_routes_checked": private_routes_checked if include_private_routes else 0,
        "nginx_vhosts_checked": registry["summary"]["shared_edge_total"],
        "hetzner_zone_records_checked": len(zone_records),
        "severity_counts": severity_counts,
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and audit the canonical publication registry.")
    parser.add_argument("--print-registry", action="store_true", help="Print the generated registry JSON.")
    parser.add_argument("--write-registry", action="store_true", help="Write config/subdomain-exposure-registry.json.")
    parser.add_argument("--check-registry", action="store_true", help="Fail if the committed registry is stale.")
    parser.add_argument("--validate", action="store_true", help="Validate the repo-side registry and auth contract.")
    parser.add_argument("--include-live-dns", action="store_true", help="Resolve production hostnames and report live status drift.")
    parser.add_argument("--include-http-auth", action="store_true", help="Probe live edge_oidc hostnames and validate redirects into Keycloak.")
    parser.add_argument(
        "--include-private-routes",
        action="store_true",
        help="Probe active private-network route targets from the current control-plane vantage point.",
    )
    parser.add_argument("--include-tls", action="store_true", help="Probe live TLS expiry for active HTTPS hostnames.")
    parser.add_argument(
        "--include-hetzner-zone",
        action="store_true",
        help="Query the Hetzner DNS API when HETZNER_DNS_API_TOKEN is available and compare the full zone to the catalog.",
    )
    parser.add_argument("--print-report-json", action="store_true", help="Print the audit report JSON.")
    parser.add_argument("--write-receipt", action="store_true", help="Write a timestamped audit receipt under receipts/subdomain-exposure-audit/.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        registry = build_registry()
        if args.check_registry or args.validate:
            check_registry_current(registry)

        if args.write_registry:
            write_json(REGISTRY_PATH, registry, indent=2, sort_keys=False)

        report = build_report(
            registry,
            include_live_dns=args.include_live_dns,
            include_http_auth=args.include_http_auth,
            include_private_routes=args.include_private_routes,
            include_tls=args.include_tls,
            include_hetzner_zone=args.include_hetzner_zone,
        )

        if args.validate and report["findings"]:
            critical = [finding for finding in report["findings"] if finding["severity"] == "CRITICAL"]
            if critical:
                raise ValueError(f"subdomain exposure audit found {len(critical)} CRITICAL findings")
            raise ValueError(f"subdomain exposure audit found {len(report['findings'])} findings")

        if args.write_receipt:
            receipt_path = RECEIPTS_DIR / f"{compact_timestamp(utc_now())}.json"
            write_json(receipt_path, report, indent=2, sort_keys=True)
            _publish_receipt_to_outline(receipt_path)

        if args.print_registry:
            print(json.dumps(registry, indent=2))
        if args.print_report_json:
            print(json.dumps(report, indent=2, sort_keys=True))
        if not any(
            [
                args.print_registry,
                args.write_registry,
                args.check_registry,
                args.validate,
                args.print_report_json,
                args.write_receipt,
            ]
        ):
            print(json.dumps(report, indent=2, sort_keys=True))

        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("subdomain exposure audit", exc)


def _publish_receipt_to_outline(receipt_path: Path) -> None:
    import subprocess, sys as _sys
    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = Path(__file__).resolve().parents[1] / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = Path(__file__).resolve().parent / "outline_tool.py"
    if not outline_tool.exists() or not receipt_path.exists():
        return
    try:
        subprocess.run(
            [_sys.executable, str(outline_tool), "receipt.publish", "--file", str(receipt_path)],
            capture_output=True, check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
