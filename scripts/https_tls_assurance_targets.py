#!/usr/bin/env python3

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse, urlunparse

from controller_automation_toolkit import load_json, repo_path


SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
CERTIFICATE_CATALOG_PATH = repo_path("config", "certificate-catalog.json")
HEALTH_PROBE_CATALOG_PATH = repo_path("config", "health-probe-catalog.json")
PROMETHEUS_TARGETS_PATH = repo_path("config", "prometheus", "file_sd", "https_tls_targets.yml")
PROMETHEUS_ALERTS_PATH = repo_path("config", "prometheus", "rules", "https_tls_alerts.yml")
BLACKBOX_JOB_NAME = "https-tls-blackbox"
DEFAULT_ENVIRONMENT = "production"

POLICY_DEFAULTS: dict[str, dict[str, int | str]] = {
    "letsencrypt": {"unit": "days", "warn": 21, "critical": 14},
    "step-ca": {"unit": "hours", "warn": 6, "critical": 2},
    "self-signed": {"unit": "days", "warn": 21, "critical": 14},
    "any": {"unit": "days", "warn": 21, "critical": 14},
}
SPECIAL_PROBE_PATHS = {
    "backup_pbs": "/api2/json/version",
    "step_ca": "/health",
}


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


def is_https_url(url: str | None) -> bool:
    return isinstance(url, str) and url.startswith("https://")


def is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    port = parsed.port or 443
    path = parsed.path or "/"
    return urlunparse(
        ParseResult(
            scheme=parsed.scheme,
            netloc=f"{parsed.hostname}:{port}" if parsed.hostname else parsed.netloc,
            path=path,
            params="",
            query=parsed.query,
            fragment="",
        )
    )


def url_with_path(base_url: str, path_url: str) -> str:
    base = urlparse(base_url)
    path = urlparse(path_url)
    return urlunparse(
        ParseResult(
            scheme=base.scheme,
            netloc=base.netloc,
            path=path.path or "/",
            params="",
            query=path.query,
            fragment="",
        )
    )


def url_with_host(base_url: str, host: str) -> str:
    parsed = urlparse(base_url)
    port = parsed.port
    if port and not ((parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    return urlunparse(
        ParseResult(
            scheme=parsed.scheme,
            netloc=netloc,
            path=parsed.path,
            params="",
            query=parsed.query,
            fragment="",
        )
    )


def slugify(value: str) -> str:
    return value.replace("_", "-").replace(".", "-")


def public_monitor_url(service_url: str, health_probe: dict[str, Any] | None) -> str | None:
    if not health_probe:
        return None
    uptime_kuma = health_probe.get("uptime_kuma")
    if not isinstance(uptime_kuma, dict) or not uptime_kuma.get("enabled"):
        return None
    monitor = uptime_kuma.get("monitor")
    if not isinstance(monitor, dict):
        return None
    monitor_url = monitor.get("url")
    if not isinstance(monitor_url, str) or not monitor_url.startswith(("https://", "http://")):
        return None

    service_parsed = urlparse(service_url)
    monitor_parsed = urlparse(monitor_url)
    if service_parsed.hostname != monitor_parsed.hostname:
        return None
    return normalize_url(monitor_url)


def public_edge_connect_host(services: list[dict[str, Any]]) -> str | None:
    for service in services:
        service_id = service.get("id")
        if not isinstance(service_id, str) or service_id != "nginx_edge":
            continue
        internal_url = service.get("internal_url")
        if not isinstance(internal_url, str) or not internal_url.startswith(("http://", "https://")):
            continue
        parsed = urlparse(internal_url)
        if parsed.hostname and is_ip_address(parsed.hostname):
            return parsed.hostname
    return None


def public_probe_target_url(
    service_url: str,
    probe_url: str,
    *,
    connect_host: str | None,
) -> tuple[str, str]:
    if not connect_host:
        return normalize_url(probe_url), ""

    public_host = urlparse(service_url).hostname or urlparse(probe_url).hostname
    if not public_host or is_ip_address(public_host):
        return normalize_url(probe_url), ""

    return normalize_url(url_with_host(probe_url, connect_host)), public_host


def policy_from_certificate(certificate: dict[str, Any] | None, *, provider: str) -> dict[str, int | str]:
    if certificate is not None:
        policy = require_mapping(certificate.get("policy"), f"certificate[{certificate['id']}].policy")
        if "warn_hours" in policy:
            return {
                "unit": "hours",
                "warn": int(policy["warn_hours"]),
                "critical": int(policy["critical_hours"]),
            }
        return {
            "unit": "days",
            "warn": int(policy["warn_days"]),
            "critical": int(policy["critical_days"]),
        }
    return dict(POLICY_DEFAULTS.get(provider, POLICY_DEFAULTS["any"]))


def load_service_catalog(path: Path = SERVICE_CATALOG_PATH) -> list[dict[str, Any]]:
    payload = require_mapping(load_json(path), str(path))
    return [
        require_mapping(item, f"{path}.services[{index}]")
        for index, item in enumerate(require_list(payload.get("services"), f"{path}.services"))
    ]


def load_subdomain_catalog(path: Path = SUBDOMAIN_CATALOG_PATH, *, environment: str) -> dict[str, dict[str, Any]]:
    payload = require_mapping(load_json(path), str(path))
    result: dict[str, dict[str, Any]] = {}
    for index, raw_entry in enumerate(require_list(payload.get("subdomains"), f"{path}.subdomains")):
        entry = require_mapping(raw_entry, f"{path}.subdomains[{index}]")
        fqdn = require_str(entry.get("fqdn"), f"{path}.subdomains[{index}].fqdn")
        if entry.get("status") != "active" or entry.get("environment") != environment:
            continue
        result[fqdn] = entry
    return result


def load_certificate_catalog(path: Path = CERTIFICATE_CATALOG_PATH) -> list[dict[str, Any]]:
    payload = require_mapping(load_json(path), str(path))
    return [
        require_mapping(item, f"{path}.certificates[{index}]")
        for index, item in enumerate(require_list(payload.get("certificates"), f"{path}.certificates"))
        if item.get("status") == "active"
    ]


def load_health_probe_catalog(path: Path = HEALTH_PROBE_CATALOG_PATH) -> dict[str, dict[str, Any]]:
    payload = require_mapping(load_json(path), str(path))
    services = require_mapping(payload.get("services"), f"{path}.services")
    return {service_id: require_mapping(item, f"{path}.services.{service_id}") for service_id, item in services.items()}


def certificate_matches_url(certificate: dict[str, Any], *, service_id: str, host: str, port: int) -> bool:
    if certificate.get("service_id") != service_id:
        return False
    endpoint = require_mapping(certificate.get("endpoint"), f"certificate[{certificate['id']}].endpoint")
    endpoint_port = int(endpoint.get("port"))
    if endpoint_port != port:
        return False
    endpoint_host = require_str(endpoint.get("host"), f"certificate[{certificate['id']}].endpoint.host")
    endpoint_server_name = require_str(
        endpoint.get("server_name"),
        f"certificate[{certificate['id']}].endpoint.server_name",
    )
    return host in {endpoint_host, endpoint_server_name}


def find_certificate_for_url(
    certificates: list[dict[str, Any]],
    *,
    service_id: str,
    host: str,
    port: int,
) -> dict[str, Any] | None:
    for certificate in certificates:
        if certificate_matches_url(certificate, service_id=service_id, host=host, port=port):
            return certificate
    return None


def determine_scope(*, host: str, exposure: str) -> str:
    if is_ip_address(host):
        return "internal"
    if exposure in {"edge-published", "informational-only"}:
        return "public"
    return "operator"


def determine_probe_module(*, expected_issuer: str, host: str) -> str:
    if expected_issuer == "self-signed":
        return "http_2xx_follow_redirects_insecure_tls"
    if expected_issuer == "any" and is_ip_address(host):
        return "http_2xx_follow_redirects_insecure_tls"
    return "http_2xx_follow_redirects"


def preferred_probe_url(service: dict[str, Any], *, service_url: str, scope: str, health_probe: dict[str, Any] | None) -> str:
    service_id = require_str(service.get("id"), "service.id")
    if scope == "public":
        monitor_url = public_monitor_url(service_url, health_probe)
        if monitor_url:
            return monitor_url
        if service_id in SPECIAL_PROBE_PATHS:
            return normalize_url(url_with_path(service_url, SPECIAL_PROBE_PATHS[service_id]))
        return normalize_url(service_url)

    if not health_probe:
        if service_id in SPECIAL_PROBE_PATHS and scope != "public":
            return normalize_url(url_with_path(service_url, SPECIAL_PROBE_PATHS[service_id]))
        return normalize_url(service_url)

    for key in ("readiness", "liveness"):
        raw_probe = health_probe.get(key)
        if not isinstance(raw_probe, dict):
            continue
        probe_url = raw_probe.get("url")
        if is_https_url(probe_url) or (isinstance(probe_url, str) and probe_url.startswith("http://")):
            return normalize_url(url_with_path(service_url, probe_url))
    if service_id in SPECIAL_PROBE_PATHS:
        return normalize_url(url_with_path(service_url, SPECIAL_PROBE_PATHS[service_id]))
    return normalize_url(service_url)


def discover_https_tls_targets(environment: str = DEFAULT_ENVIRONMENT) -> list[dict[str, Any]]:
    services = load_service_catalog()
    subdomains = load_subdomain_catalog(environment=environment)
    certificates = load_certificate_catalog()
    health_probes = load_health_probe_catalog()
    edge_connect_host = public_edge_connect_host(services)

    targets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for service in sorted(services, key=lambda item: require_str(item.get("id"), "service.id")):
        service_id = require_str(service.get("id"), "service.id")
        if service.get("lifecycle_status") != "active":
            continue

        environment_entry = require_mapping(
            require_mapping(service.get("environments", {}), f"service[{service_id}].environments").get(environment, {}),
            f"service[{service_id}].environments.{environment}",
        )
        candidate_urls: list[tuple[str, str]] = []
        environment_url = environment_entry.get("url")
        if environment_entry.get("status") == "active" and is_https_url(environment_url):
            candidate_urls.append(("environment", require_str(environment_url, f"service[{service_id}].environments.{environment}.url")))
        internal_url = service.get("internal_url")
        if is_https_url(internal_url):
            normalized_internal = normalize_url(require_str(internal_url, f"service[{service_id}].internal_url"))
            if normalized_internal not in {normalize_url(url) for _, url in candidate_urls}:
                candidate_urls.append(("internal", require_str(internal_url, f"service[{service_id}].internal_url")))
        public_url = service.get("public_url")
        if is_https_url(public_url):
            normalized_public = normalize_url(require_str(public_url, f"service[{service_id}].public_url"))
            if normalized_public not in {normalize_url(url) for _, url in candidate_urls}:
                candidate_urls.append(("public", require_str(public_url, f"service[{service_id}].public_url")))

        health_probe_id = service.get("health_probe_id")
        health_probe = health_probes.get(str(health_probe_id)) if isinstance(health_probe_id, str) else None

        for source_kind, raw_url in candidate_urls:
            normalized_url = normalize_url(raw_url)
            parsed = urlparse(normalized_url)
            host = require_str(parsed.hostname, f"{normalized_url}.hostname")
            port = parsed.port or 443
            subdomain_entry = subdomains.get(host)
            exposure = str(subdomain_entry.get("exposure")) if subdomain_entry else str(service.get("exposure", "private-only"))
            auth_requirement = (
                str(subdomain_entry.get("auth_requirement"))
                if subdomain_entry
                else ("private_network" if exposure == "private-only" or is_ip_address(host) else "none")
            )
            scope = determine_scope(host=host, exposure=exposure)
            certificate = find_certificate_for_url(certificates, service_id=service_id, host=host, port=port)

            tls_provider = "any"
            if certificate is not None:
                tls_provider = str(certificate["expected_issuer"])
            elif subdomain_entry:
                tls_provider = str(require_mapping(subdomain_entry.get("tls", {}), f"subdomain[{host}].tls").get("provider", "any"))

            preferred_public_url = preferred_probe_url(
                service,
                service_url=normalized_url,
                scope=scope,
                health_probe=health_probe,
            )
            display_url = preferred_public_url if preferred_public_url != normalized_url else normalized_url
            probe_url = preferred_public_url
            probe_hostname = ""
            testssl_url = normalized_url
            testssl_ip = ""
            if scope == "public":
                probe_url, probe_hostname = public_probe_target_url(
                    normalized_url,
                    preferred_public_url,
                    connect_host=edge_connect_host,
                )
            if certificate is not None:
                endpoint = require_mapping(certificate.get("endpoint"), f"certificate[{certificate['id']}].endpoint")
                server_name = require_str(endpoint.get("server_name"), f"certificate[{certificate['id']}].endpoint.server_name")
                if is_ip_address(host) and server_name != host:
                    probe_hostname = server_name
                    testssl_url = url_with_host(normalized_url, server_name)
                    testssl_ip = host

            surface = scope
            target_id = f"{slugify(service_id)}-{surface}"
            suffix = 2
            while target_id in seen_ids:
                target_id = f"{slugify(service_id)}-{surface}-{suffix}"
                suffix += 1
            seen_ids.add(target_id)

            policy = policy_from_certificate(certificate, provider=tls_provider)
            targets.append(
                {
                    "id": target_id,
                    "service_id": service_id,
                    "service_name": require_str(service.get("name"), f"service[{service_id}].name"),
                    "environment": environment,
                    "scope": scope,
                    "source_kind": source_kind,
                    "exposure": exposure,
                    "auth_requirement": auth_requirement,
                    "probe_url": probe_url,
                    "probe_hostname": probe_hostname,
                    "probe_module": determine_probe_module(expected_issuer=tls_provider, host=host),
                    "display_url": display_url,
                    "testssl_url": testssl_url,
                    "testssl_ip": testssl_ip,
                    "certificate_id": certificate["id"] if certificate else "",
                    "expected_issuer": tls_provider,
                    "policy": policy,
                }
            )

    return targets


def build_prometheus_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in targets:
        rows.append(
            {
                "targets": [target["probe_url"]],
                "labels": {
                    "assurance_id": target["id"],
                    "service_id": target["service_id"],
                    "service_name": target["service_name"],
                    "environment": target["environment"],
                    "scope": target["scope"],
                    "exposure": target["exposure"],
                    "auth_requirement": target["auth_requirement"],
                    "probe_module": target["probe_module"],
                    "probe_hostname": target["probe_hostname"],
                    "certificate_id": target["certificate_id"],
                    "expected_issuer": target["expected_issuer"],
                    "policy_unit": target["policy"]["unit"],
                    "policy_warn": str(target["policy"]["warn"]),
                    "policy_critical": str(target["policy"]["critical"]),
                    "display_url": target["display_url"],
                },
            }
        )
    return rows


def alert_name(prefix: str, target_id: str) -> str:
    return f"{prefix}_{target_id.replace('-', '_')}"


def build_prometheus_alert_rules(targets: list[dict[str, Any]]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for target in targets:
        labels = {
            "service_id": target["service_id"],
            "assurance_id": target["id"],
            "environment": target["environment"],
            "scope": target["scope"],
        }
        selector = f'job="{BLACKBOX_JOB_NAME}",assurance_id="{target["id"]}"'
        unit_seconds = 3600 if target["policy"]["unit"] == "hours" else 86400
        threshold_warn = int(target["policy"]["warn"])
        threshold_critical = int(target["policy"]["critical"])
        runbook_url = str(Path("docs/runbooks/https-tls-assurance.md"))

        rules.append(
            {
                "alert": alert_name("HTTPSProbeFailed", target["id"]),
                "expr": f'probe_success{{{selector}}} == 0',
                "for": "5m",
                "labels": {**labels, "severity": "critical"},
                "annotations": {
                    "summary": f'{target["id"]} HTTPS probe is failing.',
                    "description": f'{target["display_url"]} is no longer completing a healthy HTTPS probe through blackbox exporter.',
                    "runbook_url": runbook_url,
                },
            }
        )
        rules.append(
            {
                "alert": alert_name("TLSCertificateExpiringWarning", target["id"]),
                "expr": (
                    f'((probe_ssl_earliest_cert_expiry{{{selector}}} - time()) / {unit_seconds}) < {threshold_warn}'
                ),
                "for": "15m",
                "labels": {**labels, "severity": "warning"},
                "annotations": {
                    "summary": f'{target["id"]} TLS certificate is approaching expiry.',
                    "description": (
                        f'{target["display_url"]} has less than {threshold_warn} {target["policy"]["unit"]} '
                        "remaining before certificate expiry."
                    ),
                    "runbook_url": runbook_url,
                },
            }
        )
        rules.append(
            {
                "alert": alert_name("TLSCertificateExpiringCritical", target["id"]),
                "expr": (
                    f'((probe_ssl_earliest_cert_expiry{{{selector}}} - time()) / {unit_seconds}) < {threshold_critical}'
                ),
                "for": "15m",
                "labels": {**labels, "severity": "critical"},
                "annotations": {
                    "summary": f'{target["id"]} TLS certificate is within the critical expiry window.',
                    "description": (
                        f'{target["display_url"]} has less than {threshold_critical} {target["policy"]["unit"]} '
                        "remaining before certificate expiry."
                    ),
                    "runbook_url": runbook_url,
                },
            }
        )

    return {
        "groups": [
            {
                "name": "https_tls_assurance",
                "interval": "1m",
                "rules": rules,
            }
        ]
    }
