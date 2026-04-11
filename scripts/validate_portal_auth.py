#!/usr/bin/env python3

from __future__ import annotations

import argparse
from typing import Any

import subdomain_catalog
from controller_automation_toolkit import emit_cli_error


ALLOWED_AUTH_REQUIREMENTS = {
    "edge_oidc",
    "none",
    "private_network",
    "upstream_auth",
}
EDGE_OIDC_REQUIREMENTS = {"edge_oidc"}
PORTAL_REQUIREMENTS = {
    "changelog.localhost": "edge_oidc",
    "docs.localhost": "edge_oidc",
    "grafana.localhost": "upstream_auth",
    "ops.localhost": "edge_oidc",
}


def require_auth_requirement(entry: dict[str, Any], path: str) -> str:
    value = subdomain_catalog.require_str(entry.get("auth_requirement"), f"{path}.auth_requirement")
    if value not in ALLOWED_AUTH_REQUIREMENTS:
        raise ValueError(f"{path}.auth_requirement must be one of {sorted(ALLOWED_AUTH_REQUIREMENTS)}")
    return value


def require_optional_justification(entry: dict[str, Any], path: str) -> str | None:
    value = entry.get("justification")
    if value is None:
        return None
    return subdomain_catalog.require_str(value, f"{path}.justification")


def validate_portal_auth(
    catalog: dict[str, Any],
    public_edge_defaults: dict[str, Any],
) -> None:
    entries_by_fqdn: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(subdomain_catalog.require_list(catalog.get("subdomains"), "subdomains")):
        entry = subdomain_catalog.require_mapping(entry, f"subdomains[{index}]")
        fqdn = subdomain_catalog.require_hostname(entry.get("fqdn"), f"subdomains[{index}].fqdn")
        auth_requirement = require_auth_requirement(entry, f"subdomains[{index}]")
        exposure = subdomain_catalog.require_str(entry.get("exposure"), f"subdomains[{index}].exposure")
        justification = require_optional_justification(entry, f"subdomains[{index}]")
        if justification is not None:
            subdomain_catalog.require_str(justification, f"subdomains[{index}].justification")
        if auth_requirement == "private_network" and exposure != "private-only":
            raise ValueError(f"subdomains[{index}].auth_requirement=private_network requires exposure=private-only")

        entries_by_fqdn[fqdn] = entry

    for fqdn, expected in PORTAL_REQUIREMENTS.items():
        entry = entries_by_fqdn.get(fqdn)
        if entry is None:
            raise ValueError(f"required portal hostname '{fqdn}' is missing from config/subdomain-catalog.json")
        actual = entry["auth_requirement"]
        if actual != expected:
            raise ValueError(f"portal hostname '{fqdn}' must declare auth_requirement='{expected}', found '{actual}'")

    protected_sites = subdomain_catalog.require_mapping(
        public_edge_defaults.get("public_edge_authenticated_sites", {}),
        "public_edge_authenticated_sites",
    )
    for fqdn in sorted(protected_sites):
        if fqdn not in entries_by_fqdn:
            raise ValueError(f"protected edge hostname '{fqdn}' is missing from config/subdomain-catalog.json")
        auth_requirement = entries_by_fqdn[fqdn]["auth_requirement"]
        if auth_requirement not in EDGE_OIDC_REQUIREMENTS:
            raise ValueError(f"protected edge hostname '{fqdn}' must use edge_oidc auth, found '{auth_requirement}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate portal auth policy in the subdomain catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the configured portal auth policy.")
    args = parser.parse_args(argv)

    try:
        if not args.validate:
            raise ValueError("use --validate")
        validate_portal_auth(
            subdomain_catalog.load_subdomain_catalog(),
            subdomain_catalog.load_public_edge_defaults(),
        )
        return 0
    except Exception as exc:
        return emit_cli_error("portal auth", exc)


if __name__ == "__main__":
    raise SystemExit(main())
