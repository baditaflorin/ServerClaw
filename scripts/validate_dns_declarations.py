#!/usr/bin/env python3
"""Validate the generated DNS declarations file against the service registry.

ADR 0374 — Cross-Cutting Service Manifest (Phase 2: DNS Publication).

Checks that config/generated/dns-declarations.yaml:
  - Is present and well-formed.
  - Contains only well-formed FQDNs.
  - Has no duplicate FQDNs.
  - Each declaration references a service that exists in platform_service_registry.
  - Each declaration is consistent with the dns.records in the registry.
  - The generated file is up-to-date with the registry (drift detection).

Usage:
    python scripts/validate_dns_declarations.py --check   # validate, exit non-zero on error
    python scripts/validate_dns_declarations.py --diff    # show diff vs what would be generated
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from validation_toolkit import load_yaml_with_identity, require_int, require_mapping, require_str  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
DNS_DECLARATIONS_PATH = REPO_ROOT / "config" / "generated" / "dns-declarations.yaml"
SUBDOMAIN_CATALOG_PATH = REPO_ROOT / "config" / "subdomain-catalog.json"

_FQDN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*\.)+[a-z]{2,}$")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_registry() -> dict[str, Any]:
    """Load and return platform_service_registry dict."""
    data = load_yaml_with_identity(REGISTRY_PATH)
    data = require_mapping(data, str(REGISTRY_PATH))
    return require_mapping(
        data.get("platform_service_registry"),
        "platform_service_registry",
    )


def load_declarations() -> dict[str, Any]:
    """Load config/generated/dns-declarations.yaml.

    Returns the dns_records mapping.  Raises FileNotFoundError if not present.
    """
    with DNS_DECLARATIONS_PATH.open() as f:
        data = yaml.safe_load(f)
    if not data:
        return {}
    data = require_mapping(data, str(DNS_DECLARATIONS_PATH))
    return require_mapping(
        data.get("dns_records", {}),
        "dns_records",
    )


def load_subdomain_catalog() -> dict[str, Any]:
    """Load config/subdomain-catalog.json."""
    import json

    with SUBDOMAIN_CATALOG_PATH.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_fqdn(fqdn: str, path: str) -> None:
    """Raise ValueError if fqdn is not a valid FQDN."""
    if not _FQDN_RE.match(fqdn):
        raise ValueError(
            f"{path}: invalid FQDN format '{fqdn}'. "
            r"Must match ^[a-z0-9]([a-z0-9\-]*\.)+[a-z]{2,}$"
        )


def derive_expected_declarations(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Derive the expected dns-declarations from the registry (same logic as generator).

    Returns a mapping of fqdn -> {service, type, target_host, ttl}.
    Raises ValueError on duplicate FQDNs or schema violations.
    """
    expected: dict[str, dict[str, Any]] = {}

    for service_name, service_config in registry.items():
        service_config = require_mapping(
            service_config, f"platform_service_registry.{service_name}"
        )
        dns_config = service_config.get("dns")
        if not dns_config:
            continue

        dns_path = f"platform_service_registry.{service_name}.dns"
        dns_config = require_mapping(dns_config, dns_path)

        records = dns_config.get("records", [])
        if not isinstance(records, list):
            raise ValueError(f"{dns_path}.records must be a list")

        for idx, record in enumerate(records):
            rec_path = f"{dns_path}.records[{idx}]"
            record = require_mapping(record, rec_path)

            fqdn = require_str(record.get("fqdn"), f"{rec_path}.fqdn")
            validate_fqdn(fqdn, f"{rec_path}.fqdn")

            dns_type = require_str(record.get("type"), f"{rec_path}.type")
            target_host = require_str(record.get("target_host"), f"{rec_path}.target_host")
            ttl_raw = record.get("ttl", 3600)
            ttl = require_int(ttl_raw, f"{rec_path}.ttl", minimum=1, maximum=86400)

            if fqdn in expected:
                existing = expected[fqdn]["service"]
                raise ValueError(
                    f"Duplicate FQDN '{fqdn}': claimed by '{existing}' and '{service_name}'"
                )

            expected[fqdn] = {
                "service": service_name,
                "type": dns_type,
                "target_host": target_host,
                "ttl": ttl,
            }

    return expected


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_declarations_structure(
    declarations: dict[str, Any],
    registry_services: set[str],
) -> list[str]:
    """Validate the structure of the declarations file.

    Returns a list of error strings.
    """
    errors: list[str] = []
    seen_fqdns: set[str] = set()

    for fqdn, decl in declarations.items():
        path = f"dns_records.{fqdn}"

        # FQDN format
        try:
            validate_fqdn(fqdn, path)
        except ValueError as exc:
            errors.append(str(exc))

        # Duplicate check
        if fqdn in seen_fqdns:
            errors.append(f"{path}: duplicate FQDN '{fqdn}'")
        seen_fqdns.add(fqdn)

        # Structure of declaration value
        if not isinstance(decl, dict):
            errors.append(f"{path}: declaration must be a mapping, got {type(decl).__name__}")
            continue

        # Required fields
        service = decl.get("service")
        if not service:
            errors.append(f"{path}: missing 'service' field")
        elif service not in registry_services:
            errors.append(
                f"{path}: service '{service}' is not in platform_service_registry"
            )

        dns_type = decl.get("type")
        if dns_type not in ("public", "internal"):
            errors.append(
                f"{path}: type must be 'public' or 'internal', got '{dns_type}'"
            )

        target_host = decl.get("target_host")
        if not target_host or not isinstance(target_host, str):
            errors.append(f"{path}: target_host must be a non-empty string")

        ttl = decl.get("ttl")
        if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl < 1:
            errors.append(f"{path}: ttl must be a positive integer")

    return errors


def check_drift(
    declarations: dict[str, Any],
    expected: dict[str, Any],
) -> list[str]:
    """Detect drift between committed declarations and what the generator would produce.

    Returns a list of error strings describing differences.
    """
    errors: list[str] = []

    declared_fqdns = set(declarations.keys())
    expected_fqdns = set(expected.keys())

    for fqdn in sorted(expected_fqdns - declared_fqdns):
        errors.append(
            f"DRIFT: {fqdn} is declared in registry but missing from "
            f"config/generated/dns-declarations.yaml — run --write to regenerate."
        )

    for fqdn in sorted(declared_fqdns - expected_fqdns):
        errors.append(
            f"DRIFT: {fqdn} is in dns-declarations.yaml but has no dns declaration "
            "in platform_service_registry — stale entry or registry was updated without regenerating."
        )

    for fqdn in sorted(declared_fqdns & expected_fqdns):
        decl = declarations[fqdn]
        exp = expected[fqdn]
        for field in ("service", "type", "target_host", "ttl"):
            if decl.get(field) != exp.get(field):
                errors.append(
                    f"DRIFT: {fqdn}.{field}: committed='{decl.get(field)}' "
                    f"vs expected='{exp.get(field)}' — run --write to regenerate."
                )

    return errors


def check_catalog_coverage(
    declarations: dict[str, Any],
    catalog: dict[str, Any],
) -> list[str]:
    """Warn about declared FQDNs not present in subdomain-catalog.json.

    Returns a list of warning strings (not errors — catalog may be updated separately).
    """
    warnings: list[str] = []
    catalog_fqdns = {
        str(e.get("fqdn", "")): e
        for e in catalog.get("subdomains", [])
        if e.get("fqdn")
    }

    for fqdn, decl in declarations.items():
        if fqdn not in catalog_fqdns:
            warnings.append(
                f"WARN: {fqdn} (service={decl['service']}) declared in registry but "
                "NOT in config/subdomain-catalog.json — add it before live-apply."
            )
        else:
            status = catalog_fqdns[fqdn].get("status", "")
            if status != "active":
                warnings.append(
                    f"WARN: {fqdn} is in subdomain-catalog.json with "
                    f"status='{status}' (expected 'active')."
                )

    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate config/generated/dns-declarations.yaml — ADR 0374 Phase 2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=True,
        help="Validate declarations file (default mode).",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show diff between committed declarations and what the generator would produce.",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    warnings: list[str] = []

    # Load registry
    try:
        registry = load_registry()
    except (OSError, ValueError) as exc:
        print(f"ERROR: Failed to load registry: {exc}", file=sys.stderr)
        return 1

    registry_services = set(registry.keys())

    # Load declarations file
    try:
        declarations = load_declarations()
    except FileNotFoundError:
        print(
            f"ERROR: {DNS_DECLARATIONS_PATH} not found.\n"
            "Run: python scripts/generate_cross_cutting_artifacts.py --write --only dns",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: Failed to load declarations: {exc}", file=sys.stderr)
        return 1

    # Structural validation of the declarations file
    struct_errors = check_declarations_structure(declarations, registry_services)
    errors.extend(struct_errors)

    # Derive expected declarations and check for drift
    try:
        expected = derive_expected_declarations(registry)
        drift_errors = check_drift(declarations, expected)
        errors.extend(drift_errors)
    except ValueError as exc:
        errors.append(f"Registry schema error: {exc}")

    # Catalog coverage warnings
    try:
        catalog = load_subdomain_catalog()
        warnings.extend(check_catalog_coverage(declarations, catalog))
    except OSError as exc:
        warnings.append(f"Could not load subdomain catalog for coverage check: {exc}")

    # Output
    for w in warnings:
        print(w, file=sys.stderr)

    if errors:
        print("\nValidation errors:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        print(
            f"\nFailed: {len(errors)} error(s), {len(warnings)} warning(s).",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {len(declarations)} DNS declarations valid. {len(warnings)} warning(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
