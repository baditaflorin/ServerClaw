#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_list, require_mapping

from controller_automation_toolkit import emit_cli_error, load_json, repo_path, run_command, write_json


SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
DEFAULT_POSTGRES_ADMIN_DSN_ENV = "LV3_POSTGRES_ADMIN_DSN"
DEFAULT_OPENBAO_ADDR_ENV = "OPENBAO_ADDR"
DEFAULT_OPENBAO_TOKEN_ENV = "OPENBAO_TOKEN"
DEFAULT_KEYCLOAK_TOKEN_ENV = "KEYCLOAK_ADMIN_TOKEN"

DATABASE_NAME_OVERRIDES = {
    "keycloak": "keycloak",
    "mattermost": "mattermost",
    "netbox": "netbox",
    "windmill": "windmill",
}


def load_service_catalog(path: Path = SERVICE_CATALOG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def load_subdomain_catalog(path: Path = SUBDOMAIN_CATALOG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def find_service_record(service_id: str, service_catalog: dict[str, Any]) -> dict[str, Any]:
    services = require_list(service_catalog.get("services"), "config/service-capability-catalog.json.services")
    for service in services:
        service = require_mapping(service, "config/service-capability-catalog.json.services[]")
        if service.get("id") == service_id:
            return service
    raise ValueError(f"service '{service_id}' is not present in config/service-capability-catalog.json")


def find_subdomain_records(service_id: str, subdomain_catalog: dict[str, Any]) -> list[dict[str, Any]]:
    subdomains = require_list(subdomain_catalog.get("subdomains"), "config/subdomain-catalog.json.subdomains")
    matches: list[dict[str, Any]] = []
    for record in subdomains:
        record = require_mapping(record, "config/subdomain-catalog.json.subdomains[]")
        if record.get("service") == service_id:
            matches.append(record)
    return matches


def infer_database_name(service_id: str) -> str | None:
    return DATABASE_NAME_OVERRIDES.get(service_id)


def build_plan(service_id: str) -> dict[str, Any]:
    service_catalog = load_service_catalog()
    subdomain_catalog = load_subdomain_catalog()
    service_record = find_service_record(service_id, service_catalog)
    subdomains = find_subdomain_records(service_id, subdomain_catalog)
    database_name = infer_database_name(service_id)
    return {
        "service_id": service_id,
        "service_name": service_record.get("name", service_id),
        "database_name": database_name,
        "loki_delete_query": f'{{service="{service_id}"}}',
        "openbao_policy_name": f"lv3-service-{service_id}-runtime",
        "openbao_approle_name": f"{service_id}-runtime",
        "keycloak_client_id": service_id,
        "subdomains": [record.get("hostname") for record in subdomains],
        "catalog_changes": {
            "service_capability_catalog": service_id,
            "subdomain_catalog": [record.get("hostname") for record in subdomains],
        },
    }


def rewrite_service_catalog(service_id: str, path: Path = SERVICE_CATALOG_PATH) -> bool:
    catalog = load_service_catalog(path)
    services = require_list(catalog.get("services"), "config/service-capability-catalog.json.services")
    filtered = [service for service in services if require_mapping(service, "service").get("id") != service_id]
    changed = len(filtered) != len(services)
    if changed:
        catalog["services"] = filtered
        write_json(path, catalog, indent=2)
    return changed


def rewrite_subdomain_catalog(service_id: str, path: Path = SUBDOMAIN_CATALOG_PATH) -> bool:
    catalog = load_subdomain_catalog(path)
    subdomains = require_list(catalog.get("subdomains"), "config/subdomain-catalog.json.subdomains")
    filtered = [record for record in subdomains if require_mapping(record, "subdomain").get("service") != service_id]
    changed = len(filtered) != len(subdomains)
    if changed:
        catalog["subdomains"] = filtered
        write_json(path, catalog, indent=2)
    return changed


def drop_postgres_database(admin_dsn: str, database_name: str) -> None:
    terminate_sql = (
        "SELECT pg_terminate_backend(pid) "
        f"FROM pg_stat_activity WHERE datname = '{database_name}' AND pid <> pg_backend_pid();"
    )
    drop_sql = f"DROP DATABASE IF EXISTS {database_name};"
    for sql in (terminate_sql, drop_sql):
        completed = run_command(["psql", admin_dsn, "-v", "ON_ERROR_STOP=1", "-c", sql])
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


def _http_request(url: str, *, method: str, headers: dict[str, str] | None = None, payload: Any = None) -> None:
    data = None
    resolved_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        resolved_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=resolved_headers, method=method)
    with urllib.request.urlopen(request, timeout=10):
        return


def delete_loki_stream(loki_base_url: str, query: str) -> None:
    encoded_query = urllib.parse.quote(query, safe="")
    _http_request(f"{loki_base_url.rstrip('/')}/loki/api/v1/admin/delete?query={encoded_query}", method="POST")


def delete_openbao_policy(openbao_addr: str, token: str, policy_name: str, approle_name: str) -> None:
    headers = {"X-Vault-Token": token}
    _http_request(f"{openbao_addr.rstrip('/')}/v1/sys/policies/acl/{policy_name}", method="DELETE", headers=headers)
    _http_request(f"{openbao_addr.rstrip('/')}/v1/auth/approle/role/{approle_name}", method="DELETE", headers=headers)


def delete_keycloak_client(base_url: str, token: str, client_id: str, realm: str) -> None:
    request_url = (
        f"{base_url.rstrip('/')}/admin/realms/{realm}/clients?clientId={urllib.parse.quote(client_id, safe='')}"
    )
    request = urllib.request.Request(
        request_url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        return
    client_uuid = payload[0]["id"]
    _http_request(
        f"{base_url.rstrip('/')}/admin/realms/{realm}/clients/{client_uuid}",
        method="DELETE",
        headers={"Authorization": f"Bearer {token}"},
    )


def execute_plan(
    plan: dict[str, Any],
    *,
    postgres_admin_dsn: str | None,
    loki_url: str | None,
    openbao_addr: str | None,
    openbao_token: str | None,
    keycloak_url: str | None,
    keycloak_token: str | None,
    keycloak_realm: str,
) -> dict[str, Any]:
    applied: dict[str, Any] = {
        "postgres_dropped": False,
        "loki_delete_requested": False,
        "openbao_deleted": False,
        "keycloak_deleted": False,
        "service_catalog_updated": False,
        "subdomain_catalog_updated": False,
    }

    if plan["database_name"]:
        if not postgres_admin_dsn:
            raise ValueError("LV3_POSTGRES_ADMIN_DSN or --postgres-admin-dsn is required to drop the service database")
        drop_postgres_database(postgres_admin_dsn, plan["database_name"])
        applied["postgres_dropped"] = True

    if loki_url:
        delete_loki_stream(loki_url, plan["loki_delete_query"])
        applied["loki_delete_requested"] = True

    if openbao_addr or openbao_token:
        if not openbao_addr or not openbao_token:
            raise ValueError("OpenBao deletion requires both OPENBAO_ADDR and OPENBAO_TOKEN")
        delete_openbao_policy(
            openbao_addr,
            openbao_token,
            plan["openbao_policy_name"],
            plan["openbao_approle_name"],
        )
        applied["openbao_deleted"] = True

    if keycloak_url or keycloak_token:
        if not keycloak_url or not keycloak_token:
            raise ValueError("Keycloak deletion requires both --keycloak-url and KEYCLOAK_ADMIN_TOKEN")
        delete_keycloak_client(keycloak_url, keycloak_token, plan["keycloak_client_id"], keycloak_realm)
        applied["keycloak_deleted"] = True

    applied["service_catalog_updated"] = rewrite_service_catalog(plan["service_id"])
    applied["subdomain_catalog_updated"] = rewrite_subdomain_catalog(plan["service_id"])
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or execute service decommission data cleanup.")
    parser.add_argument("--service", required=True, help="Service id from config/service-capability-catalog.json.")
    parser.add_argument("--execute", action="store_true", help="Execute the destructive decommission steps.")
    parser.add_argument(
        "--confirm",
        help="Repeat the service id to confirm destructive execution.",
    )
    parser.add_argument("--postgres-admin-dsn", help="Superuser DSN for PostgreSQL cleanup.")
    parser.add_argument("--loki-url", help="Loki base URL with admin deletion enabled.")
    parser.add_argument("--openbao-addr", help="OpenBao base URL.")
    parser.add_argument("--keycloak-url", help="Keycloak admin base URL, for example https://sso.lv3.org.")
    parser.add_argument("--keycloak-realm", default="lv3", help="Keycloak realm containing the service client.")
    args = parser.parse_args(argv)

    try:
        plan = build_plan(args.service)
        payload: dict[str, Any] = {"plan": plan, "executed": False}
        if args.execute:
            if args.confirm != args.service:
                raise ValueError("--confirm must exactly match --service when --execute is used")
            payload["results"] = execute_plan(
                plan,
                postgres_admin_dsn=args.postgres_admin_dsn or os.environ.get(DEFAULT_POSTGRES_ADMIN_DSN_ENV),
                loki_url=args.loki_url,
                openbao_addr=args.openbao_addr or os.environ.get(DEFAULT_OPENBAO_ADDR_ENV),
                openbao_token=os.environ.get(DEFAULT_OPENBAO_TOKEN_ENV),
                keycloak_url=args.keycloak_url,
                keycloak_token=os.environ.get(DEFAULT_KEYCLOAK_TOKEN_ENV),
                keycloak_realm=args.keycloak_realm,
            )
            payload["executed"] = True
    except (OSError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Service decommission", exc)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
