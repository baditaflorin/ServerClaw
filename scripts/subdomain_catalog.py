#!/usr/bin/env python3

import argparse
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")

ALLOWED_STATUSES = {"active", "planned", "reserved", "retiring"}
ALLOWED_ENVIRONMENTS = {"production", "staging"}
ALLOWED_EXPOSURES = {"edge-published", "informational-only", "private-only"}
ALLOWED_TLS_PROVIDERS = {"letsencrypt", "step-ca", "none"}


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


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def load_subdomain_catalog() -> dict[str, Any]:
    return load_json(SUBDOMAIN_CATALOG_PATH)


def validate_subdomain_catalog(catalog: dict[str, Any], service_catalog: dict[str, Any]) -> None:
    if catalog.get("schema_version") != "1.0.0":
        raise ValueError("subdomain catalog must declare schema_version '1.0.0'")

    services = {service["id"] for service in service_catalog["services"]}
    subdomains = require_list(catalog.get("subdomains"), "subdomains")
    if not subdomains:
        raise ValueError("subdomains must not be empty")

    seen_fqdns: set[str] = set()
    for index, entry in enumerate(subdomains):
        entry = require_mapping(entry, f"subdomains[{index}]")
        fqdn = require_str(entry.get("fqdn"), f"subdomains[{index}].fqdn")
        if fqdn in seen_fqdns:
            raise ValueError(f"duplicate subdomain: {fqdn}")
        seen_fqdns.add(fqdn)

        environment = require_str(entry.get("environment"), f"subdomains[{index}].environment")
        if environment not in ALLOWED_ENVIRONMENTS:
            raise ValueError(
                f"subdomains[{index}].environment must be one of {sorted(ALLOWED_ENVIRONMENTS)}"
            )

        status = require_str(entry.get("status"), f"subdomains[{index}].status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"subdomains[{index}].status must be one of {sorted(ALLOWED_STATUSES)}")

        exposure = require_str(entry.get("exposure"), f"subdomains[{index}].exposure")
        if exposure not in ALLOWED_EXPOSURES:
            raise ValueError(
                f"subdomains[{index}].exposure must be one of {sorted(ALLOWED_EXPOSURES)}"
            )

        require_str(entry.get("target"), f"subdomains[{index}].target")
        require_str(entry.get("owner_adr"), f"subdomains[{index}].owner_adr")
        if "service_id" in entry and entry["service_id"] not in services and status == "active":
            raise ValueError(
                f"subdomains[{index}].service_id references unknown active service '{entry['service_id']}'"
            )

        tls = require_mapping(entry.get("tls"), f"subdomains[{index}].tls")
        provider = require_str(tls.get("provider"), f"subdomains[{index}].tls.provider")
        if provider not in ALLOWED_TLS_PROVIDERS:
            raise ValueError(
                f"subdomains[{index}].tls.provider must be one of {sorted(ALLOWED_TLS_PROVIDERS)}"
            )
        require_bool(tls.get("auto_renew"), f"subdomains[{index}].tls.auto_renew")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the subdomain catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate and exit.")
    args = parser.parse_args(argv)

    try:
        catalog = load_subdomain_catalog()
        service_catalog = load_json(SERVICE_CATALOG_PATH)
        validate_subdomain_catalog(catalog, service_catalog)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("subdomain catalog", exc)


if __name__ == "__main__":
    raise SystemExit(main())
