#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.timeouts import timeout_limit


API_GATEWAY_CATALOG_PATH = repo_path("config", "api-gateway-catalog.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
ENV_VAR_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


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


def require_int(value: Any, path: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def require_identifier(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"{path} must use lowercase letters, numbers, and underscores only")
    return value


def require_path_prefix(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not value.startswith("/"):
        raise ValueError(f"{path} must start with '/'")
    return value.rstrip("/") or "/"


def require_http_url(value: Any, path: str) -> str:
    value = require_str(value, path)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{path} must be an http or https URL")
    return value.rstrip("/")


def load_service_catalog_ids(service_catalog_path: Any = SERVICE_CATALOG_PATH) -> set[str]:
    service_catalog_path = Path(service_catalog_path)
    catalog = require_mapping(load_json(service_catalog_path), str(service_catalog_path))
    services = require_list(catalog.get("services"), "service-capability-catalog.services")
    return {
        require_identifier(
            require_mapping(service, f"service-capability-catalog.services[{index}]").get("id"),
            f"service-capability-catalog.services[{index}].id",
        )
        for index, service in enumerate(services)
    }


def validate_api_gateway_catalog(
    catalog: dict[str, Any],
    *,
    service_catalog_path: Any = SERVICE_CATALOG_PATH,
) -> list[dict[str, Any]]:
    if require_str(catalog.get("schema_version"), "api-gateway-catalog.schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"api-gateway-catalog.schema_version must be '{SUPPORTED_SCHEMA_VERSION}'"
        )

    known_service_ids = load_service_catalog_ids(service_catalog_path)
    services = require_list(catalog.get("services"), "api-gateway-catalog.services")
    if not services:
        raise ValueError("api-gateway-catalog.services must not be empty")

    seen_ids: set[str] = set()
    seen_prefixes: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for index, service in enumerate(services):
        path = f"api-gateway-catalog.services[{index}]"
        service = require_mapping(service, path)
        service_id = require_identifier(service.get("id"), f"{path}.id")
        if service_id in seen_ids:
            raise ValueError(f"duplicate gateway service id '{service_id}'")
        if service_id not in known_service_ids:
            raise ValueError(f"{path}.id references unknown service '{service_id}'")
        seen_ids.add(service_id)

        gateway_prefix = require_path_prefix(service.get("gateway_prefix"), f"{path}.gateway_prefix")
        if gateway_prefix in seen_prefixes:
            raise ValueError(f"duplicate gateway prefix '{gateway_prefix}'")
        if not gateway_prefix.startswith("/v1/"):
            raise ValueError(f"{path}.gateway_prefix must stay under /v1/")
        seen_prefixes.add(gateway_prefix)

        upstream = require_http_url(service.get("upstream"), f"{path}.upstream")
        auth = require_str(service.get("auth"), f"{path}.auth")
        if auth != "keycloak_jwt":
            raise ValueError(f"{path}.auth must stay 'keycloak_jwt' in this iteration")

        normalized_service = {
            "id": service_id,
            "name": require_str(service.get("name"), f"{path}.name"),
            "upstream": upstream,
            "gateway_prefix": gateway_prefix,
            "required_role": require_str(service.get("required_role"), f"{path}.required_role"),
            "strip_prefix": require_bool(service.get("strip_prefix"), f"{path}.strip_prefix"),
            "timeout_seconds": require_int(service.get("timeout_seconds"), f"{path}.timeout_seconds"),
            "auth": auth,
            "forward_authorization": require_bool(
                service.get("forward_authorization", False),
                f"{path}.forward_authorization",
            ),
        }
        if normalized_service["timeout_seconds"] > timeout_limit("http_request"):
            raise ValueError(
                f"{path}.timeout_seconds must be <= {timeout_limit('http_request')} "
                f"to stay within the http_request layer budget"
            )

        healthcheck_path = service.get("healthcheck_path")
        if healthcheck_path is not None:
            normalized_service["healthcheck_path"] = require_path_prefix(
                healthcheck_path, f"{path}.healthcheck_path"
            )

        openapi_path = service.get("openapi_path")
        if openapi_path is not None:
            normalized_service["openapi_path"] = require_path_prefix(openapi_path, f"{path}.openapi_path")

        upstream_auth_env_var = service.get("upstream_auth_env_var")
        if upstream_auth_env_var is not None:
            upstream_auth_env_var = require_str(upstream_auth_env_var, f"{path}.upstream_auth_env_var")
            if not ENV_VAR_PATTERN.match(upstream_auth_env_var):
                raise ValueError(f"{path}.upstream_auth_env_var must be an uppercase env var name")
            normalized_service["upstream_auth_env_var"] = upstream_auth_env_var

        normalized.append(normalized_service)

    return normalized


def load_api_gateway_catalog(
    catalog_path: Any = API_GATEWAY_CATALOG_PATH,
    *,
    service_catalog_path: Any = SERVICE_CATALOG_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    catalog_path = Path(catalog_path)
    catalog = require_mapping(load_json(catalog_path), str(catalog_path))
    return catalog, validate_api_gateway_catalog(catalog, service_catalog_path=service_catalog_path)


def list_catalog(normalized: list[dict[str, Any]]) -> int:
    print(f"API gateway catalog: {API_GATEWAY_CATALOG_PATH}")
    for service in normalized:
        print(
            f"  - {service['id']}: {service['gateway_prefix']} -> {service['upstream']} "
            f"[role={service['required_role']}]"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or validate the canonical platform API gateway catalog."
    )
    parser.add_argument("--validate", action="store_true", help="Validate the API gateway catalog.")
    args = parser.parse_args()

    try:
        _catalog, normalized = load_api_gateway_catalog()
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        return emit_cli_error("API gateway catalog", exc)

    if args.validate:
        print(f"API gateway catalog OK: {API_GATEWAY_CATALOG_PATH}")
        return 0
    return list_catalog(normalized)


if __name__ == "__main__":
    sys.exit(main())
