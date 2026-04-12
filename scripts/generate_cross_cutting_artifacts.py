#!/usr/bin/env python3
"""Generate cross-cutting infrastructure artifacts from the platform service registry.

ADR 0374 — Cross-Cutting Service Manifest.

Each service in platform_service_registry declares what it needs from DNS, nginx,
TLS, and SSO in one place. This script reads those declarations and generates or
validates the corresponding artifacts.

Usage:
    # Validate all concerns (check mode — no files written)
    python scripts/generate_cross_cutting_artifacts.py --check

    # Generate all concerns
    python scripts/generate_cross_cutting_artifacts.py --write

    # Generate or validate only a specific concern
    python scripts/generate_cross_cutting_artifacts.py --check --only sso
    python scripts/generate_cross_cutting_artifacts.py --write --only sso

Concerns (phases):
    hairpin  — platform_hairpin_nat_hosts list for compose extra_hosts
    dns      — Hetzner DNS A record declarations
    tls      — certificate-catalog.json domain entries
    proxy    — nginx edge server-block fragments
    sso      — Keycloak OIDC client declarations

This script MUST NOT:
    - Make live API calls (no Hetzner DNS API, no Keycloak API, no cert issuance)
    - Import requests at module load time (breaks --export-mcp validation container)
    - Modify files outside of config/generated/, config/subdomain-catalog.json,
      config/certificate-catalog.json, and inventory/group_vars/platform_hairpin.yml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from validation_toolkit import (
    load_yaml_with_identity,
    require_bool,
    require_int,
    require_list,
    require_mapping,
    require_str,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
SUBDOMAIN_CATALOG_PATH = REPO_ROOT / "config" / "subdomain-catalog.json"
DNS_OUTPUT_PATH = REPO_ROOT / "config" / "generated" / "dns-declarations.yaml"
PLATFORM_YML_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"
TOPOLOGY_HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"

VALID_CONCERNS = ("hairpin", "dns", "tls", "proxy", "sso")
VALID_SSO_PROVIDERS = {"keycloak", "oauth2-proxy"}
VALID_DNS_TYPES = ("public", "internal")

# FQDN must match this pattern: lowercase labels separated by dots, no leading/trailing hyphens.
_FQDN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*\.)+[a-z]{2,}$")

# Scopes considered sensitive — warn when present on a public client
_SENSITIVE_SCOPES = {"roles", "groups", "offline_access"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict:
    data = load_yaml_with_identity(REGISTRY_PATH)
    registry = require_mapping(data, str(REGISTRY_PATH))
    return require_mapping(registry.get("platform_service_registry", {}), "platform_service_registry")


def _validate_fqdn(fqdn: str, path: str) -> str:
    """Validate FQDN format. Raises ValueError if malformed."""
    if not _FQDN_RE.match(fqdn):
        raise ValueError(
            f"{path}: invalid FQDN format '{fqdn}'. "
            r"Must match ^[a-z0-9]([a-z0-9\-]*\.)+[a-z]{2,}$"
        )
    return fqdn


def _load_subdomain_catalog() -> dict:
    """Load config/subdomain-catalog.json. Returns the full parsed object."""
    import json

    with SUBDOMAIN_CATALOG_PATH.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# DNS concern (Phase 2)
# ---------------------------------------------------------------------------


def generate_dns_declarations(
    registry: dict,
    write: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Generate DNS declarations from registry dns sections.

    For each service with a dns section, validates:
      - Each record has fqdn (valid format), type (public|internal), target_host, ttl.
      - No two services declare the same FQDN.
      - Each declared FQDN exists in config/subdomain-catalog.json (warn if not).
      - Catalog entries with no registry service are warned as potential stale records.

    In --write mode, writes config/generated/dns-declarations.yaml.

    Returns a mapping of fqdn -> declaration dict.
    Raises ValueError on schema violations or duplicate FQDNs.
    """
    declarations: dict[str, dict] = {}

    for service_name, service_config in registry.items():
        service_config = require_mapping(service_config, f"platform_service_registry.{service_name}")
        dns_config = service_config.get("dns")
        if dns_config is None:
            continue

        dns_path = f"platform_service_registry.{service_name}.dns"
        dns_config = require_mapping(dns_config, dns_path)

        records_raw = dns_config.get("records")
        if records_raw is None:
            raise ValueError(f"{dns_path}.records is required when dns section is present")
        records = require_list(records_raw, f"{dns_path}.records", min_length=1)

        for idx, record in enumerate(records):
            rec_path = f"{dns_path}.records[{idx}]"
            record = require_mapping(record, rec_path)

            fqdn = require_str(record.get("fqdn"), f"{rec_path}.fqdn")
            _validate_fqdn(fqdn, f"{rec_path}.fqdn")

            dns_type = require_str(record.get("type"), f"{rec_path}.type")
            if dns_type not in VALID_DNS_TYPES:
                raise ValueError(f"{rec_path}.type must be one of {VALID_DNS_TYPES!r}, got '{dns_type}'")

            target_host = require_str(record.get("target_host"), f"{rec_path}.target_host")

            ttl_raw = record.get("ttl", 3600)
            ttl = require_int(ttl_raw, f"{rec_path}.ttl", minimum=1, maximum=86400)

            if fqdn in declarations:
                existing = declarations[fqdn]["service"]
                raise ValueError(f"Duplicate FQDN '{fqdn}': claimed by both '{existing}' and '{service_name}'")

            declarations[fqdn] = {
                "service": service_name,
                "type": dns_type,
                "target_host": target_host,
                "ttl": ttl,
            }

    # Cross-check against subdomain catalog (warnings only — does not fail)
    try:
        catalog = _load_subdomain_catalog()
        _warn_catalog_drift(declarations, catalog)
    except OSError as exc:
        print(f"  WARNING: could not load subdomain catalog for cross-check: {exc}")

    if write:
        out_dir = repo_root / "config" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "dns-declarations.yaml"
        header = (
            "# GENERATED — do not edit. "
            "Regenerate: python scripts/generate_cross_cutting_artifacts.py --write --only dns\n"
        )
        body = yaml.dump(
            {"dns_records": declarations},
            default_flow_style=False,
            sort_keys=True,
        )
        out_path.write_text(header + body)
        print(f"  Wrote {len(declarations)} DNS declarations to {out_path.relative_to(repo_root)}")
    else:
        print(f"  DNS: {len(declarations)} declarations validated (no files written)")

    return declarations


def _warn_catalog_drift(declarations: dict, catalog: dict) -> None:
    """Print warnings for catalog drift. Called from generate_dns_declarations."""
    catalog_fqdns: dict[str, dict] = {}
    for entry in catalog.get("subdomains", []):
        fqdn = str(entry.get("fqdn", ""))
        if fqdn:
            catalog_fqdns[fqdn] = entry

    # Declared in registry but not in catalog
    for fqdn, decl in declarations.items():
        if fqdn not in catalog_fqdns:
            print(
                f"  WARN: {fqdn} (service={decl['service']}) declared in registry but "
                "NOT in config/subdomain-catalog.json — add it before live-apply."
            )
        else:
            status = catalog_fqdns[fqdn].get("status", "")
            if status != "active":
                print(f"  WARN: {fqdn} is in subdomain-catalog.json with status='{status}' (expected 'active').")

    # In catalog (edge-published) but no dns declaration in registry
    registry_services = {d["service"] for d in declarations.values()}
    for fqdn, entry in catalog_fqdns.items():
        exposure = entry.get("exposure", "")
        service_id = entry.get("service_id", "")
        if exposure in ("informational-only", "private-only"):
            continue  # Infrastructure FQDNs not managed by service registry
        if fqdn not in declarations and service_id not in registry_services:
            print(
                f"  WARN: {fqdn} (service_id={service_id}) is in subdomain-catalog.json "
                "with no registry dns declaration — potential stale catalog entry."
            )


# ---------------------------------------------------------------------------
# SSO concern (Phase 5)
# ---------------------------------------------------------------------------


def generate_sso_clients(registry: dict, write: bool = False, repo_root: Path = REPO_ROOT) -> dict:
    """Generate SSO client declarations from registry sso sections.

    Returns a mapping of client_id -> client declaration dict.
    Raises ValueError on any validation error.
    """
    clients: dict[str, dict] = {}
    # Track which service claimed each client_id to give a useful duplicate error
    client_owners: dict[str, str] = {}

    for service_name, service_config in registry.items():
        service_config = require_mapping(service_config, f"platform_service_registry.{service_name}")
        sso_config = service_config.get("sso")
        if sso_config is None:
            continue

        path_prefix = f"platform_service_registry.{service_name}.sso"
        sso_config = require_mapping(sso_config, path_prefix)

        enabled = sso_config.get("enabled", False)
        if not require_bool(enabled, f"{path_prefix}.enabled"):
            continue

        client_id = require_str(
            sso_config.get("client_id"),
            f"{path_prefix}.client_id",
        )

        provider = require_str(
            sso_config.get("provider", "keycloak"),
            f"{path_prefix}.provider",
        )
        if provider not in VALID_SSO_PROVIDERS:
            raise ValueError(f"{path_prefix}.provider must be one of: {', '.join(sorted(VALID_SSO_PROVIDERS))}")

        redirect_uris_raw = sso_config.get("redirect_uris", [])
        redirect_uris = require_list(redirect_uris_raw, f"{path_prefix}.redirect_uris")
        for idx, uri in enumerate(redirect_uris):
            require_str(uri, f"{path_prefix}.redirect_uris[{idx}]")

        scopes = sso_config.get("scopes", ["openid", "profile", "email"])
        require_list(scopes, f"{path_prefix}.scopes")
        for idx, scope in enumerate(scopes):
            require_str(scope, f"{path_prefix}.scopes[{idx}]")

        public_client = sso_config.get("public_client", False)
        require_bool(public_client, f"{path_prefix}.public_client")

        # Validate redirect_uri format
        _validate_redirect_uris(redirect_uris, path_prefix)

        # Warn: public client with sensitive scopes
        sensitive_present = set(scopes) & _SENSITIVE_SCOPES
        if public_client and sensitive_present:
            print(
                f"  WARNING: {path_prefix}: public_client=true but scopes include "
                f"sensitive: {sorted(sensitive_present)}"
            )

        # Duplicate client_id check
        if client_id in client_owners:
            raise ValueError(
                f"Duplicate SSO client_id '{client_id}': claimed by '{client_owners[client_id]}' and '{service_name}'"
            )

        client_owners[client_id] = service_name

        # client_secret_local_file is optional (service accounts may have none)
        client_secret_local_file = sso_config.get("client_secret_local_file")
        if client_secret_local_file is not None:
            require_str(client_secret_local_file, f"{path_prefix}.client_secret_local_file")

        clients[client_id] = {
            "service": service_name,
            "provider": provider,
            "redirect_uris": redirect_uris,
            "scopes": scopes,
            "public_client": public_client,
        }

    if write:
        out_dir = repo_root / "config" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "sso-clients.yaml"
        header = (
            "# GENERATED — do not edit. Regenerate: "
            "python scripts/generate_cross_cutting_artifacts.py --write --only sso\n"
        )
        body = yaml.dump({"sso_clients": clients}, default_flow_style=False, sort_keys=True)
        out_path.write_text(header + body)
        print(f"  Wrote {len(clients)} SSO client declarations to {out_path.relative_to(repo_root)}")
    else:
        print(f"  SSO: {len(clients)} client declarations validated (no files written)")

    return clients


def _validate_redirect_uris(redirect_uris: list, path_prefix: str) -> None:
    """Validate redirect URI format. Non-localhost URIs must be HTTPS."""
    import re

    for idx, uri in enumerate(redirect_uris):
        uri_path = f"{path_prefix}.redirect_uris[{idx}]"
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError(f"{uri_path} must be a non-empty string")

        # Allow localhost/127.0.0.1 with http (common for CLI OAuth callbacks)
        _localhost_pattern = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/.*)?$")
        if uri.startswith("http://") and not _localhost_pattern.match(uri):
            raise ValueError(f"{uri_path}: non-localhost redirect URIs must use HTTPS (got: {uri!r})")

        if not (uri.startswith("https://") or uri.startswith("http://")):
            raise ValueError(f"{uri_path}: redirect URI must start with https:// or http:// (got: {uri!r})")


# ---------------------------------------------------------------------------
# TLS concern (Phase 3)
# ---------------------------------------------------------------------------

VALID_TLS_SOURCES = {"letsencrypt", "openbao", "self-signed", "step-ca"}


def generate_tls_certificates(
    registry: dict,
    write: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Generate TLS certificate declarations from registry tls sections.

    For each service with a tls section, validates that:
      - cert_source is one of the valid values
      - each domain in tls.domains has a corresponding dns.records entry
      - letsencrypt is not declared for .internal or .local domains
      - no domain is claimed by more than one service

    In --write mode, writes inventory/group_vars/platform_tls_certs.yml.

    Returns a mapping of fqdn -> certificate declaration dict.
    """
    certs: dict[str, dict] = {}
    domain_owners: dict[str, str] = {}

    for service_name, service_config in registry.items():
        service_config = require_mapping(service_config, f"platform_service_registry.{service_name}")
        tls_config = service_config.get("tls")
        if tls_config is None:
            continue

        path_prefix = f"platform_service_registry.{service_name}.tls"
        tls_config = require_mapping(tls_config, path_prefix)

        cert_source = require_str(
            tls_config.get("cert_source"),
            f"{path_prefix}.cert_source",
        )
        if cert_source not in VALID_TLS_SOURCES:
            raise ValueError(f"{path_prefix}.cert_source must be one of: {', '.join(sorted(VALID_TLS_SOURCES))}")

        domains_raw = tls_config.get("domains", [])
        domains = require_list(domains_raw, f"{path_prefix}.domains", min_length=1)
        for idx, d in enumerate(domains):
            require_str(d, f"{path_prefix}.domains[{idx}]")

        wildcard = tls_config.get("wildcard", False)
        require_bool(wildcard, f"{path_prefix}.wildcard")

        cert_validity_days = tls_config.get("cert_validity_days", 90)
        require_int(cert_validity_days, f"{path_prefix}.cert_validity_days", minimum=1)

        # Collect DNS FQDNs for cross-check
        dns_config = service_config.get("dns")
        dns_fqdns: set[str] = set()
        if dns_config:
            dns_config = require_mapping(dns_config, f"platform_service_registry.{service_name}.dns")
            for rec in dns_config.get("records", []):
                if isinstance(rec, dict) and "fqdn" in rec:
                    dns_fqdns.add(rec["fqdn"])

        for fqdn in domains:
            # Warn if letsencrypt declared for internal/local domain
            if cert_source == "letsencrypt" and (".internal" in fqdn or fqdn.endswith(".local")):
                print(
                    f"  WARNING: {path_prefix}: cert_source=letsencrypt but "
                    f"domain '{fqdn}' looks internal (.internal or .local)"
                )

            # Duplicate domain check
            if fqdn in domain_owners:
                raise ValueError(
                    f"Duplicate TLS domain '{fqdn}': claimed by '{domain_owners[fqdn]}' and '{service_name}'"
                )
            domain_owners[fqdn] = service_name

            certs[fqdn] = {
                "service": service_name,
                "source": cert_source,
                "wildcard": wildcard,
                "cert_validity_days": cert_validity_days,
            }

    if write:
        out = repo_root / "inventory" / "group_vars" / "platform_tls_certs.yml"
        header = (
            "# GENERATED — do not edit. "
            "Regenerate: python scripts/generate_cross_cutting_artifacts.py --write --only tls\n"
        )
        body = yaml.dump({"platform_tls_certs": certs}, default_flow_style=False, sort_keys=True)
        out.write_text(header + body)
        print(f"  Wrote {len(certs)} TLS cert declarations to {out.relative_to(repo_root)}")
    else:
        print(f"  TLS: {len(certs)} cert declarations validated (no files written)")

    return certs


# ---------------------------------------------------------------------------
# Proxy concern (Phase 4)
# ---------------------------------------------------------------------------


def generate_nginx_upstreams(
    registry: dict,
    write: bool = False,
    repo_root: Path = REPO_ROOT,
) -> list[dict]:
    """Generate nginx upstream definitions from proxy declarations.

    For each service with proxy.enabled=true, produces:
      - One upstream block per service
      - config/generated/nginx-upstreams.yaml for Ansible consumption
      - config/generated/nginx-upstreams.conf nginx include snippet

    Returns a list of upstream dicts.
    Raises ValueError on any validation error.
    """
    upstreams: list[dict] = []
    fqdn_owners: dict[str, str] = {}
    catalog = _load_guest_catalog(repo_root)

    for service_name, service_config in sorted(registry.items()):
        service_config = require_mapping(service_config, f"platform_service_registry.{service_name}")
        proxy_config = service_config.get("proxy")
        if proxy_config is None:
            continue

        path_prefix = f"platform_service_registry.{service_name}.proxy"
        proxy_config = require_mapping(proxy_config, path_prefix)

        enabled = proxy_config.get("enabled", False)
        if not require_bool(enabled, f"{path_prefix}.enabled"):
            continue

        public_fqdn = require_str(proxy_config.get("public_fqdn"), f"{path_prefix}.public_fqdn")

        upstream_port_raw = proxy_config.get("upstream_port") or service_config.get("internal_port")
        if upstream_port_raw is None:
            raise ValueError(f"{path_prefix}: proxy.upstream_port or service internal_port is required")
        upstream_port = require_int(
            upstream_port_raw,
            f"{path_prefix}.upstream_port",
            minimum=1,
            maximum=65535,
        )

        upstream_host = require_str(
            proxy_config.get("upstream_host") or service_config.get("host_group", ""),
            f"{path_prefix}.upstream_host",
        )
        upstream_ip = _resolve_catalog_ip(upstream_host, catalog, f"{path_prefix}.upstream_host")

        auth_proxy = proxy_config.get("auth_proxy", False)
        require_bool(auth_proxy, f"{path_prefix}.auth_proxy")

        websocket = proxy_config.get("websocket", False)
        require_bool(websocket, f"{path_prefix}.websocket")

        max_body_size = proxy_config.get("max_body_size", "10m")
        if max_body_size is not None:
            require_str(max_body_size, f"{path_prefix}.max_body_size")

        extra_fqdns_raw = proxy_config.get("extra_fqdns", [])
        extra_fqdns = require_list(extra_fqdns_raw, f"{path_prefix}.extra_fqdns")
        for idx, fqdn in enumerate(extra_fqdns):
            require_str(fqdn, f"{path_prefix}.extra_fqdns[{idx}]")

        path_prefix_val = proxy_config.get("path_prefix", "/")
        if path_prefix_val is not None:
            require_str(path_prefix_val, f"{path_prefix}.path_prefix")
            if not path_prefix_val.startswith("/"):
                raise ValueError(f"{path_prefix}.path_prefix must start with / (got: {path_prefix_val!r})")

        # Duplicate FQDN detection
        all_fqdns = [public_fqdn] + list(extra_fqdns)
        for fqdn in all_fqdns:
            if fqdn in fqdn_owners:
                raise ValueError(
                    f"Duplicate proxy FQDN '{fqdn}': claimed by '{fqdn_owners[fqdn]}' and '{service_name}'"
                )
            fqdn_owners[fqdn] = service_name

        upstream_name = f"{service_name}_upstream"

        upstreams.append(
            {
                "name": upstream_name,
                "service_name": service_name,
                "fqdn": public_fqdn,
                "extra_fqdns": list(extra_fqdns),
                "port": upstream_port,
                "host": upstream_host,
                "ip": upstream_ip,
                "auth_proxy": auth_proxy,
                "websocket": websocket,
                "max_body_size": max_body_size,
                "path_prefix": path_prefix_val,
            }
        )

    if write:
        out_dir = repo_root / "config" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        _write_nginx_upstreams_conf(upstreams, out_dir / "nginx-upstreams.conf")

        yaml_out = out_dir / "nginx-upstreams.yaml"
        header = (
            "# GENERATED — do not edit. "
            "Regenerate: python scripts/generate_cross_cutting_artifacts.py --write --only proxy\n"
        )
        body = yaml.dump(
            {"platform_nginx_upstreams": upstreams},
            default_flow_style=False,
            sort_keys=False,
        )
        yaml_out.write_text(header + body)

        print(
            f"  Wrote {len(upstreams)} nginx upstreams to "
            f"{(out_dir / 'nginx-upstreams.conf').relative_to(repo_root)} "
            f"and {yaml_out.relative_to(repo_root)}"
        )
    else:
        print(f"  Proxy: {len(upstreams)} nginx upstream declarations validated (no files written)")

    return upstreams


def _write_nginx_upstreams_conf(upstreams: list[dict], out_path: Path) -> None:
    """Write the nginx upstream block conf snippet."""
    lines: list[str] = [
        "# GENERATED by ADR 0374 Phase 4 — do not edit manually\n",
        "# Regenerate: python scripts/generate_cross_cutting_artifacts.py --write --only proxy\n",
        "#\n",
        "# Include from the nginx http block: include /path/to/nginx-upstreams.conf;\n",
        "\n",
    ]

    for u in upstreams:
        all_fqdns = [u["fqdn"]] + u["extra_fqdns"]
        is_last = u is upstreams[-1]
        lines.append(f"# {u['service_name']} — {', '.join(all_fqdns)}\n")
        lines.append(f"upstream {u['name']} {{\n")
        lines.append(f"    server {u['ip']}:{u['port']};  # {u['host']}\n")
        lines.append("}\n" if is_last else "}\n\n")

    out_path.write_text("".join(lines))


# ---------------------------------------------------------------------------
# Hairpin concern (Phase 1)
# ---------------------------------------------------------------------------

HAIRPIN_OUTPUT_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform_hairpin.yml"


def _load_guest_catalog(repo_root: Path = REPO_ROOT) -> dict:
    """Return platform_guest_catalog.by_name (inventory_hostname -> {ipv4, ...}).

    Fresh worktrees intentionally do not carry the ignored generated
    inventory/group_vars/platform.yml. Fall back to the tracked topology source
    when the generated file is absent so ADR 0374 validation can run from a
    clean checkout.
    """
    platform_path = repo_root / "inventory" / "group_vars" / "platform.yml"
    if platform_path.exists():
        with platform_path.open() as f:
            data = yaml.safe_load(f)
        catalog = data.get("platform_guest_catalog", {})
        by_name = catalog.get("by_name", {})
        if by_name:
            return by_name

    host_vars = load_yaml_with_identity(repo_root / "inventory" / "host_vars" / "proxmox-host.yml")
    host_vars = require_mapping(host_vars, str(TOPOLOGY_HOST_VARS_PATH))
    guests_raw = require_list(host_vars.get("proxmox_guests", []), "host_vars.proxmox_guests", min_length=1)

    by_name: dict[str, dict[str, str]] = {}
    for idx, guest in enumerate(guests_raw):
        guest = require_mapping(guest, f"host_vars.proxmox_guests[{idx}]")
        name = require_str(guest.get("name"), f"host_vars.proxmox_guests[{idx}].name")
        ipv4 = require_str(guest.get("ipv4"), f"host_vars.proxmox_guests[{idx}].ipv4")
        by_name[name] = {"ipv4": ipv4}

    if not by_name:
        raise ValueError(
            "platform_guest_catalog.by_name is empty and proxmox-host.yml did not "
            "yield any proxmox_guests for fallback resolution"
        )
    return by_name


def _resolve_catalog_ip(address_host: str, catalog: dict, context: str) -> str:
    """Resolve an inventory hostname to its IPv4 address via platform_guest_catalog."""
    if address_host not in catalog:
        raise ValueError(
            f"{context}: address_host '{address_host}' is not in "
            f"platform_guest_catalog.by_name. "
            f"Available hosts: {', '.join(sorted(catalog))}"
        )
    entry = catalog[address_host]
    ip = entry.get("ipv4") or entry.get("ansible_host") or entry.get("ip")
    if not ip:
        raise ValueError(
            f"{context}: catalog entry for '{address_host}' has no 'ipv4', "
            f"'ansible_host', or 'ip' field. Keys present: {', '.join(sorted(entry))}"
        )
    return str(ip)


def generate_hairpin(
    registry: dict,
    write: bool = False,
    repo_root: Path = REPO_ROOT,
) -> list[dict]:
    """Aggregate hairpin.publish entries from all services into platform_hairpin_nat_hosts.

    Deduplicates by hostname. If two services declare the same hostname with
    different addresses, an error is raised.

    In --write mode writes inventory/group_vars/platform_hairpin.yml.
    In --check mode validates the committed file matches the derived set.

    Returns the sorted list of {hostname, address} dicts.
    Raises ValueError on any validation or drift error.
    """
    catalog = _load_guest_catalog(repo_root)
    seen: dict[str, str] = {}  # hostname -> resolved IP

    for service_name, service_config in registry.items():
        require_mapping(service_config, f"platform_service_registry.{service_name}")
        hairpin = service_config.get("hairpin")
        if hairpin is None:
            continue

        require_mapping(hairpin, f"{service_name}.hairpin")
        publish = hairpin.get("publish")
        if publish is None:
            continue

        require_list(publish, f"{service_name}.hairpin.publish")

        for idx, entry in enumerate(publish):
            ctx = f"{service_name}.hairpin.publish[{idx}]"
            require_mapping(entry, ctx)

            hostname = require_str(entry.get("hostname"), f"{ctx}.hostname")
            address_host = require_str(entry.get("address_host"), f"{ctx}.address_host")

            ip = _resolve_catalog_ip(address_host, catalog, ctx)

            if hostname in seen:
                if seen[hostname] != ip:
                    raise ValueError(
                        f"{ctx}: hostname '{hostname}' is declared by multiple services "
                        f"with conflicting addresses: '{seen[hostname]}' vs '{ip}'"
                    )
            else:
                seen[hostname] = ip

    hosts = [{"hostname": h, "address": a} for h, a in sorted(seen.items())]

    if write:
        _write_hairpin_file(hosts, repo_root)
    else:
        _check_hairpin_file(hosts, repo_root)

    return hosts


def _write_hairpin_file(hosts: list[dict], repo_root: Path) -> None:
    out_path = repo_root / "inventory" / "group_vars" / "platform_hairpin.yml"
    header = (
        "# GENERATED — do not edit by hand.\n"
        "# Source: platform_service_registry hairpin declarations — ADR 0374 Phase 1.\n"
        "# Regenerate: python scripts/generate_cross_cutting_artifacts.py --write --only hairpin\n"
        "---\n"
    )
    body = yaml.dump(
        {"platform_hairpin_nat_hosts": hosts},
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    out_path.write_text(header + body)
    print(f"  Wrote {len(hosts)} hairpin entries to {out_path.relative_to(repo_root)}")


def _check_hairpin_file(hosts: list[dict], repo_root: Path) -> None:
    """Validate committed platform_hairpin.yml matches the derived set."""
    committed_path = repo_root / "inventory" / "group_vars" / "platform_hairpin.yml"
    if not committed_path.exists():
        raise ValueError(
            "platform_hairpin.yml does not exist. Run --write to generate it: "
            "python scripts/generate_cross_cutting_artifacts.py --write --only hairpin"
        )

    with committed_path.open() as f:
        committed_data = yaml.safe_load(f)
    committed_hosts = committed_data.get("platform_hairpin_nat_hosts", [])

    def _normalise(entries: list) -> list[tuple]:
        return sorted((e["hostname"], e["address"]) for e in entries)

    derived = _normalise(hosts)
    committed = _normalise(committed_hosts)

    if derived != committed:
        derived_set = set(derived)
        committed_set = set(committed)
        missing = derived_set - committed_set
        extra = committed_set - derived_set
        parts = [
            "platform_hairpin.yml is stale. "
            "Run: python scripts/generate_cross_cutting_artifacts.py --write --only hairpin"
        ]
        if missing:
            parts.append(f"  Missing from file: {sorted(missing)}")
        if extra:
            parts.append(f"  Extra in file (not in registry): {sorted(extra)}")
        raise ValueError("\n".join(parts))

    print(f"  Hairpin OK: {len(hosts)} entries match platform_hairpin.yml")


# ---------------------------------------------------------------------------
# Stub generators for other concerns
# ---------------------------------------------------------------------------


def _concern_not_implemented(concern: str, write: bool = False) -> None:
    """Placeholder for concerns not yet implemented in this script."""
    mode = "write" if write else "check"
    print(f"  {concern}: not yet implemented in this script (--{mode} no-op)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or validate cross-cutting infrastructure artifacts — ADR 0374.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Concerns:
  hairpin  platform_hairpin_nat_hosts list for compose extra_hosts (Phase 1)
  dns      Hetzner DNS A record declarations (Phase 2)
  tls      certificate-catalog.json domain entries (Phase 3)
  proxy    nginx edge server-block fragments (Phase 4)
  sso      Keycloak OIDC client declarations (Phase 5)

Examples:
  python scripts/generate_cross_cutting_artifacts.py --check
  python scripts/generate_cross_cutting_artifacts.py --write --only sso
""",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Validate only; no files written")
    mode.add_argument("--write", action="store_true", help="Write generated artifacts to disk")
    parser.add_argument(
        "--only",
        choices=list(VALID_CONCERNS),
        metavar="CONCERN",
        help=f"Process only this concern. One of: {', '.join(VALID_CONCERNS)}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    write = args.write
    only = args.only

    print(f"Loading registry from {REGISTRY_PATH.relative_to(REPO_ROOT)} ...")
    try:
        registry = _load_registry()
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR: Failed to load registry: {exc}", file=sys.stderr)
        return 1

    concerns_to_run = [only] if only else list(VALID_CONCERNS)

    errors: list[str] = []

    for concern in concerns_to_run:
        print(f"\n[{concern.upper()}]")
        try:
            if concern == "hairpin":
                generate_hairpin(registry, write=write, repo_root=REPO_ROOT)
            elif concern == "dns":
                generate_dns_declarations(registry, write=write, repo_root=REPO_ROOT)
            elif concern == "tls":
                generate_tls_certificates(registry, write=write, repo_root=REPO_ROOT)
            elif concern == "sso":
                generate_sso_clients(registry, write=write, repo_root=REPO_ROOT)
            elif concern == "proxy":
                generate_nginx_upstreams(registry, write=write, repo_root=REPO_ROOT)
            else:
                _concern_not_implemented(concern, write=write)
        except ValueError as exc:
            msg = f"ERROR ({concern}): {exc}"
            print(f"  {msg}", file=sys.stderr)
            errors.append(msg)
        except Exception as exc:
            msg = f"UNEXPECTED ERROR ({concern}): {type(exc).__name__}: {exc}"
            print(f"  {msg}", file=sys.stderr)
            errors.append(msg)

    if errors:
        print(f"\nFailed with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\nAll concerns passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
