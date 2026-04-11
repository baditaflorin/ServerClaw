#!/usr/bin/env python3
"""Validate the generated nginx upstream configuration against the platform service registry.

ADR 0374 Phase 4 — Nginx Edge Publication.

Loads config/generated/nginx-upstreams.yaml and cross-checks it against:
  - The platform service registry (inventory/group_vars/platform_services.yml)
  - The subdomain catalog (config/subdomain-catalog.json)

Checks performed:
  1. Every upstream port matches the service's proxy.upstream_port or internal_port.
  2. Every upstream FQDN appears in the subdomain catalog with exposure=edge-published.
  3. Every service with proxy.enabled=true has a corresponding entry in the generated file.
  4. path_prefix values all start with /.
  5. No duplicate FQDNs across upstream entries.

Usage:
    python scripts/validate_nginx_config.py           # check mode (default)
    python scripts/validate_nginx_config.py --check   # explicit check mode

Exit codes:
    0 — all checks pass
    1 — one or more checks failed

This script MUST NOT import requests at module load time.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from validation_toolkit import load_yaml_with_identity, require_int, require_list, require_mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
SUBDOMAIN_CATALOG_PATH = REPO_ROOT / "config" / "subdomain-catalog.json"
NGINX_UPSTREAMS_YAML = REPO_ROOT / "config" / "generated" / "nginx-upstreams.yaml"


def _load_registry() -> dict:
    data = load_yaml_with_identity(REGISTRY_PATH)
    reg = require_mapping(data, str(REGISTRY_PATH))
    return require_mapping(reg.get("platform_service_registry", {}), "platform_service_registry")


def _load_upstreams() -> list[dict]:
    if not NGINX_UPSTREAMS_YAML.exists():
        raise FileNotFoundError(
            f"Generated nginx upstreams not found at {NGINX_UPSTREAMS_YAML}. "
            "Run: python scripts/generate_cross_cutting_artifacts.py --write --only proxy"
        )
    with NGINX_UPSTREAMS_YAML.open() as f:
        data = yaml.safe_load(f)
    mapping = require_mapping(data, str(NGINX_UPSTREAMS_YAML))
    return require_list(mapping.get("platform_nginx_upstreams", []), "platform_nginx_upstreams")


def _load_subdomain_catalog() -> dict[str, dict]:
    """Return a dict keyed by fqdn for fast lookup."""
    with SUBDOMAIN_CATALOG_PATH.open() as f:
        data = json.load(f)
    subdomains = data.get("subdomains", [])
    return {entry["fqdn"]: entry for entry in subdomains if "fqdn" in entry}


def validate(registry: dict, upstreams: list[dict], subdomain_catalog: dict[str, dict]) -> list[str]:
    """Run all validation checks. Returns a list of error/warning strings."""
    issues: list[str] = []

    # --- Build expected state from registry ---
    expected_upstreams: dict[str, dict] = {}  # service_name -> proxy_config + internal_port
    for service_name, service_config in registry.items():
        proxy_config = service_config.get("proxy")
        if proxy_config is None:
            continue
        if not proxy_config.get("enabled", False):
            continue
        expected_upstreams[service_name] = {
            "upstream_port": proxy_config.get("upstream_port") or service_config.get("internal_port"),
            "public_fqdn": proxy_config.get("public_fqdn"),
            "extra_fqdns": proxy_config.get("extra_fqdns", []),
            "path_prefix": proxy_config.get("path_prefix", "/"),
        }

    # --- Index generated upstreams by service_name ---
    generated_by_service: dict[str, dict] = {}
    seen_fqdns: dict[str, str] = {}  # fqdn -> service_name (for duplicate detection)

    for entry in upstreams:
        service_name = entry.get("service_name", "")
        if not service_name:
            issues.append("ERROR: upstream entry missing service_name field")
            continue

        if service_name in generated_by_service:
            issues.append(f"ERROR: duplicate upstream entry for service '{service_name}'")
        generated_by_service[service_name] = entry

        # Collect all FQDNs from this entry
        all_fqdns = [entry.get("fqdn", "")] + entry.get("extra_fqdns", [])
        for fqdn in all_fqdns:
            if not fqdn:
                continue
            if fqdn in seen_fqdns:
                issues.append(
                    f"ERROR: FQDN '{fqdn}' appears in upstreams for both '{seen_fqdns[fqdn]}' and '{service_name}'"
                )
            else:
                seen_fqdns[fqdn] = service_name

    # --- Check 1: All expected services are present in generated output ---
    for service_name in expected_upstreams:
        if service_name not in generated_by_service:
            issues.append(
                f"ERROR: service '{service_name}' has proxy.enabled=true in registry "
                f"but is missing from generated nginx-upstreams.yaml. "
                f"Re-run: python scripts/generate_cross_cutting_artifacts.py --write --only proxy"
            )

    # --- Check 2: No extra services in generated output (drift detection) ---
    for service_name in generated_by_service:
        if service_name not in expected_upstreams:
            issues.append(
                f"ERROR: generated nginx-upstreams.yaml contains service '{service_name}' "
                f"which has no proxy.enabled=true in registry. Generated file is stale."
            )

    # --- Check 3: Port consistency ---
    for service_name, expected in expected_upstreams.items():
        generated = generated_by_service.get(service_name)
        if generated is None:
            continue  # Already reported above

        expected_port = expected["upstream_port"]
        generated_port = generated.get("port")

        if expected_port is not None and generated_port is not None:
            try:
                exp_int = require_int(expected_port, f"registry.{service_name}.proxy.upstream_port")
                gen_int = require_int(generated_port, f"generated.{service_name}.port")
                if exp_int != gen_int:
                    issues.append(
                        f"ERROR: port mismatch for '{service_name}': "
                        f"registry declares {exp_int}, generated file has {gen_int}"
                    )
            except ValueError as e:
                issues.append(f"ERROR: invalid port for '{service_name}': {e}")

    # --- Check 4: FQDN consistency ---
    for service_name, expected in expected_upstreams.items():
        generated = generated_by_service.get(service_name)
        if generated is None:
            continue

        expected_fqdn = expected["public_fqdn"]
        generated_fqdn = generated.get("fqdn")

        if expected_fqdn and generated_fqdn and expected_fqdn != generated_fqdn:
            issues.append(
                f"ERROR: FQDN mismatch for '{service_name}': "
                f"registry declares '{expected_fqdn}', generated file has '{generated_fqdn}'"
            )

    # --- Check 5: path_prefix format ---
    for service_name, expected in expected_upstreams.items():
        path_prefix = expected.get("path_prefix", "/")
        if path_prefix is not None:
            if not isinstance(path_prefix, str) or not path_prefix.startswith("/"):
                issues.append(f"ERROR: '{service_name}'.proxy.path_prefix must start with / (got: {path_prefix!r})")

    # --- Check 6: Subdomain catalog coverage ---
    for service_name, generated in generated_by_service.items():
        all_fqdns = [generated.get("fqdn", "")] + generated.get("extra_fqdns", [])
        for fqdn in all_fqdns:
            if not fqdn:
                continue
            catalog_entry = subdomain_catalog.get(fqdn)
            if catalog_entry is None:
                issues.append(f"WARNING: '{service_name}' proxy FQDN '{fqdn}' is not in config/subdomain-catalog.json")
            elif catalog_entry.get("exposure") != "edge-published":
                exposure = catalog_entry.get("exposure", "unknown")
                issues.append(
                    f"WARNING: '{service_name}' FQDN '{fqdn}' is in subdomain-catalog.json "
                    f"but exposure='{exposure}' (expected 'edge-published')"
                )

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate generated nginx upstream config — ADR 0374 Phase 4.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Validates config/generated/nginx-upstreams.yaml against:
  - inventory/group_vars/platform_services.yml (proxy declarations)
  - config/subdomain-catalog.json (edge-published FQDNs)

Exits 0 if all checks pass, 1 if any errors are found.
""",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=True,
        help="Validate the generated nginx config (default mode)",
    )
    args = parser.parse_args(argv)  # noqa: F841 — parsed for --help

    print("Validating nginx upstreams...")
    print(f"  Registry:         {REGISTRY_PATH.relative_to(REPO_ROOT)}")
    print(f"  Generated config: {NGINX_UPSTREAMS_YAML.relative_to(REPO_ROOT)}")
    print(f"  Subdomain catalog: {SUBDOMAIN_CATALOG_PATH.relative_to(REPO_ROOT)}")
    print()

    try:
        registry = _load_registry()
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR: Failed to load registry: {exc}", file=sys.stderr)
        return 1

    try:
        upstreams = _load_upstreams()
    except (FileNotFoundError, OSError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR: Failed to load nginx upstreams: {exc}", file=sys.stderr)
        return 1

    try:
        subdomain_catalog = _load_subdomain_catalog()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: Failed to load subdomain catalog: {exc}", file=sys.stderr)
        return 1

    issues = validate(registry, upstreams, subdomain_catalog)

    errors = [i for i in issues if i.startswith("ERROR:")]
    warnings = [i for i in issues if i.startswith("WARNING:")]

    for warn in warnings:
        print(f"  {warn}")
    for err in errors:
        print(f"  {err}", file=sys.stderr)

    print()
    if errors:
        print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s).", file=sys.stderr)
        return 1

    print(f"OK: {len(upstreams)} upstreams validated. {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
