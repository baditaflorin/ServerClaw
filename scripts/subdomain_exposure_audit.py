#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, repo_path, write_json
import subdomain_catalog


REGISTRY_PATH = repo_path("config", "subdomain-exposure-registry.json")
REGISTRY_SCHEMA_PATH = repo_path("docs", "schema", "subdomain-exposure-registry.schema.json")
HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
PUBLIC_EDGE_DEFAULTS_PATH = repo_path("roles", "nginx_edge_publication", "defaults", "main.yml")
GLOBAL_VARS_PATH = repo_path("inventory", "group_vars", "all.yml")
RECEIPTS_DIR = repo_path("receipts", "subdomain-exposure-audit")
HETZNER_DNS_API_TOKEN_ENV = "HETZNER_DNS_API_TOKEN"
EXPECTED_EDGE_OIDC_PREFIX = "https://sso.lv3.org/realms/lv3/protocol/openid-connect/auth"
PROBE_USER_AGENT = "lv3-subdomain-exposure-audit/1.0"


def utc_now() -> datetime:
    return datetime.now(UTC)


def compact_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def iso_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
        for hostname in subdomain_catalog.collect_site_hostnames(site, f"public_edge_extra_sites[{index}]"):
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

    return routes


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
    registry_entries: list[dict[str, Any]] = []

    for entry in sorted(catalog["subdomains"], key=lambda item: item["fqdn"]):
        route = route_index.get(entry["fqdn"])
        route_mode = "edge" if route else "dns-only"
        is_public_dns = entry["environment"] == "production" and entry["exposure"] != "private-only"
        registry_entries.append(
            {
                "fqdn": entry["fqdn"],
                "service_id": entry.get("service_id"),
                "environment": entry["environment"],
                "status": entry["status"],
                "exposure": entry["exposure"],
                "auth_requirement": entry["auth_requirement"],
                "target": entry["target"],
                "target_port": entry.get("target_port"),
                "owner_adr": entry["owner_adr"],
                "dns_record_type": hostname_record_type(entry["target"]),
                "route_mode": route_mode,
                "route_source": route["route_source"] if route else "dns-only",
                "route_kind": route["route_kind"] if route else None,
                "edge_auth": route["edge_auth"] if route else "none",
                "unauthenticated_paths": route["unauthenticated_paths"] if route else [],
                "unauthenticated_prefix_paths": route["unauthenticated_prefix_paths"] if route else [],
                "repo_route_service_id": route["service_id"] if route else None,
                "repo_route_metadata": route["metadata"] if route else {},
                "tls": deepcopy(entry["tls"]),
                "live_tracking_expected": entry["status"] == "active" and is_public_dns,
            }
        )

    active_entries = [entry for entry in registry_entries if entry["status"] == "active"]
    summary = {
        "catalog_total": len(registry_entries),
        "active_total": len(active_entries),
        "active_public_dns_total": sum(1 for entry in active_entries if entry["live_tracking_expected"]),
        "active_private_total": sum(1 for entry in active_entries if entry["exposure"] == "private-only"),
        "planned_total": sum(1 for entry in registry_entries if entry["status"] == "planned"),
        "edge_total": sum(1 for entry in registry_entries if entry["route_mode"] == "edge"),
        "edge_oidc_total": sum(1 for entry in registry_entries if entry["auth_requirement"] == "edge_oidc"),
    }

    return {
        "schema_version": "1.0.0",
        "zone_name": "lv3.org",
        "subdomains": registry_entries,
        "summary": summary,
    }


def check_registry_current(registry: dict[str, Any]) -> None:
    current = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if current != registry:
        raise ValueError(
            "config/subdomain-exposure-registry.json is out of date; run "
            "'python3 scripts/subdomain_exposure_audit.py --write-registry'"
        )


def collect_repo_findings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in registry["subdomains"]:
        if entry.get("status") != "active":
            continue
        if entry["auth_requirement"] == "edge_oidc" and entry["edge_auth"] != "oauth2_proxy":
            findings.append(
                {
                    "check": "repo_edge_auth",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "catalog_requires_edge_oidc_but_route_is_not_protected",
                    "detail": "Catalog marks the hostname as edge_oidc, but the repo-managed edge route lacks oauth2-proxy protection.",
                }
            )
        if entry["auth_requirement"] != "edge_oidc" and entry["edge_auth"] == "oauth2_proxy":
            findings.append(
                {
                    "check": "repo_edge_auth",
                    "severity": "WARN",
                    "subdomain": entry["fqdn"],
                    "finding": "route_is_protected_but_catalog_does_not_require_edge_oidc",
                    "detail": "The repo-managed edge route is protected by oauth2-proxy, but the catalog does not classify it as edge_oidc.",
                }
            )
    return findings


def resolve_public_records(fqdn: str) -> list[str]:
    try:
        answers = socket.getaddrinfo(fqdn, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return sorted({item[4][0] for item in answers})


def collect_resolution_findings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in registry["subdomains"]:
        if entry["environment"] != "production":
            continue
        if entry["exposure"] == "private-only":
            continue

        actual = resolve_public_records(entry["fqdn"])
        expected = entry["target"]
        expected_present = expected in actual

        if entry["status"] == "active" and not expected_present:
            findings.append(
                {
                    "check": "dns_resolution",
                    "severity": "WARN",
                    "subdomain": entry["fqdn"],
                    "finding": "active_subdomain_missing_expected_public_resolution",
                    "detail": f"Expected public resolution to include {expected}; observed {actual or ['<missing>']}.",
                }
            )
        elif entry["status"] != "active" and expected_present:
            findings.append(
                {
                    "check": "dns_resolution",
                    "severity": "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "subdomain_resolves_publicly_but_is_not_tracked_active",
                    "detail": f"The hostname resolves publicly to {expected} while the catalog status is '{entry['status']}'.",
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
    for entry in registry["subdomains"]:
        if entry["status"] != "active":
            continue
        if entry["environment"] != "production":
            continue
        if entry["auth_requirement"] != "edge_oidc":
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
    zone_name: str = "lv3.org",
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


def collect_zone_findings(registry: dict[str, Any], zone_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    catalog_by_fqdn = {entry["fqdn"]: entry for entry in registry["subdomains"]}
    relevant_zone_records = []

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

    zone_by_fqdn = {record["fqdn"]: record for record in relevant_zone_records}
    for fqdn, record in sorted(zone_by_fqdn.items()):
        if fqdn not in catalog_by_fqdn:
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
        expected = catalog_by_fqdn[fqdn]
        if expected["dns_record_type"] != record["type"] or expected["target"] != record["value"]:
            findings.append(
                {
                    "check": "hetzner_zone",
                    "severity": "WARN",
                    "subdomain": fqdn,
                    "finding": "zone_record_differs_from_catalog",
                    "detail": (
                        f"Expected {expected['dns_record_type']} {expected['target']} from the catalog; "
                        f"observed {record['type']} {record['value']} in Hetzner DNS."
                    ),
                }
            )

    for fqdn, entry in sorted(catalog_by_fqdn.items()):
        if entry["environment"] != "production" or entry["exposure"] == "private-only":
            continue
        if entry["status"] != "active":
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


def fetch_tls_metadata(hostname: str, port: int = 443) -> dict[str, Any]:
    context = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=10) as sock:
        with context.wrap_socket(sock, server_hostname=hostname) as tls_sock:
            cert = tls_sock.getpeercert()

    not_after = cert.get("notAfter")
    if not not_after:
        raise ValueError(f"certificate for {hostname} did not expose notAfter")
    expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    issuer = ", ".join("=".join(part) for parts in cert.get("issuer", []) for part in parts)
    return {
        "expires_at": iso_timestamp(expires_at),
        "days_remaining": int((expires_at - utc_now()).total_seconds() // 86400),
        "issuer": issuer,
    }


def collect_tls_findings(registry: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in registry["subdomains"]:
        if entry["status"] != "active":
            continue
        if entry["environment"] != "production":
            continue
        if entry["tls"]["provider"] == "none":
            continue
        if entry["target_port"] not in (None, 443):
            continue

        metadata = fetch_tls_metadata(entry["fqdn"])
        if metadata["days_remaining"] < 14:
            findings.append(
                {
                    "check": "tls_certificate",
                    "severity": "WARN" if metadata["days_remaining"] >= 7 else "CRITICAL",
                    "subdomain": entry["fqdn"],
                    "finding": "certificate_expiry_imminent",
                    "detail": (
                        f"TLS certificate expires on {metadata['expires_at']} "
                        f"({metadata['days_remaining']} days remaining)."
                    ),
                }
            )
    return findings


def build_report(
    registry: dict[str, Any],
    *,
    include_live_dns: bool = False,
    include_http_auth: bool = False,
    include_tls: bool = False,
    include_hetzner_zone: bool = False,
) -> dict[str, Any]:
    findings = collect_repo_findings(registry)
    zone_records: list[dict[str, Any]] = []
    if include_live_dns:
        findings.extend(collect_resolution_findings(registry))
    if include_http_auth:
        findings.extend(collect_http_auth_findings(registry))
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

    return {
        "audit_run_id": str(uuid.uuid4()),
        "audited_at": iso_timestamp(utc_now()),
        "registry_path": str(REGISTRY_PATH),
        "subdomains_in_catalog": registry["summary"]["catalog_total"],
        "active_subdomains_tracked": registry["summary"]["active_total"],
        "dns_records_checked": registry["summary"]["active_public_dns_total"] if include_live_dns else 0,
        "nginx_vhosts_checked": registry["summary"]["edge_total"],
        "hetzner_zone_records_checked": len(zone_records),
        "severity_counts": severity_counts,
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and audit the subdomain exposure registry.")
    parser.add_argument("--print-registry", action="store_true", help="Print the generated registry JSON.")
    parser.add_argument("--write-registry", action="store_true", help="Write config/subdomain-exposure-registry.json.")
    parser.add_argument("--check-registry", action="store_true", help="Fail if the committed registry is stale.")
    parser.add_argument("--validate", action="store_true", help="Validate the repo-side registry and auth contract.")
    parser.add_argument("--include-live-dns", action="store_true", help="Resolve production hostnames and report live status drift.")
    parser.add_argument("--include-http-auth", action="store_true", help="Probe live edge_oidc hostnames and validate redirects into Keycloak.")
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


if __name__ == "__main__":
    raise SystemExit(main())
