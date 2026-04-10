#!/usr/bin/env python3
"""Plan or execute service decommission — runtime teardown and/or code purge.

The entire service removal lifecycle is CPU-only. No AI agent required.

Usage (full lifecycle):

    # 1. Dry-run: inspect the plan as JSON

    # 2. Generate the removal ADR (templated from the dry-run, not AI-written)
        --generate-adr \
        --reason "Replaced by Dify for LLM interaction" \
        --replacement "Dify (ADR 0197)"

    # 3. Code purge (delete files, clean catalogs, regenerate artifacts)

    # 4. Runtime teardown (databases, secrets, OIDC — requires env vars)

    # 5. All at once
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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

ROLES_ROOT = repo_path(
    "collections", "ansible_collections", "lv3", "platform", "roles",
)
COLLECTION_PLAYBOOKS = repo_path(
    "collections", "ansible_collections", "lv3", "platform", "playbooks",
)
ROOT_PLAYBOOKS = repo_path("playbooks")
CONFIG_DIR = repo_path("config")
INVENTORY_DIR = repo_path("inventory")
TESTS_DIR = repo_path("tests")
VERSIONS_DIR = repo_path("versions")
DOCS_ADR_DIR = repo_path("docs", "adr")

# Comprehensive catalog registry — every catalog file that needs cleanup on service removal.
# Each entry describes the file path, cleanup strategy, and key field.
# Handlers: see _apply_catalog_registry_entry()
CATALOG_REGISTRY: list[dict[str, str]] = [
    # --- Array catalogs: filter items where item[id_field] == service_id ---
    {"path": "config/service-capability-catalog.json",      "type": "array",            "list_key": "services",      "id_field": "id"},
    {"path": "config/subdomain-catalog.json",               "type": "array",            "list_key": "subdomains",    "id_field": "service_id"},
    {"path": "config/slo-catalog.json",                     "type": "array",            "list_key": "slos",          "id_field": "service_id"},
    {"path": "config/data-catalog.json",                    "type": "array",            "list_key": "data_stores",   "id_field": "service"},
    {"path": "config/api-gateway-catalog.json",             "type": "array",            "list_key": "services",      "id_field": "id"},
    {"path": "config/secret-catalog.json",                  "type": "array",            "list_key": "secrets",       "id_field": "owner_service"},
    {"path": "config/subdomain-exposure-registry.json",     "type": "array",            "list_key": "publications",  "id_field": "service_id"},
    {"path": "config/certificate-catalog.json",             "type": "array",            "list_key": "certificates",  "id_field": "service_id"},
    # --- Dict-key catalogs: delete key == service_id variant ---
    {"path": "config/health-probe-catalog.json",            "type": "dict_key",     "list_key": "services"},
    {"path": "config/service-completeness.json",            "type": "dict_key",     "list_key": "services"},
    # --- Top-level key: service entries live directly at the root of the JSON ---
    # service-redundancy-catalog has entries at the top level, NOT nested under "services"
    {"path": "config/service-redundancy-catalog.json",      "type": "top_level_key"},
    # --- Dict-key-by-value: delete key where value[id_field] == service_id ---
    {"path": "config/image-catalog.json", "type": "dict_key_by_value", "list_key": "images", "id_field": "service_id"},
    # --- Workflow dict: delete keys containing any service variant ---
    {"path": "config/workflow-catalog.json",          "type": "workflow_dict", "list_key": "workflows"},
    {"path": "config/command-catalog.json",           "type": "workflow_dict", "list_key": "commands"},
    # --- Secrets dict: delete keys containing any service variant ---
    {"path": "config/controller-local-secrets.json",  "type": "secrets_dict",  "list_key": "secrets"},
    # --- Dependency graph: remove nodes by id AND edges by from/to ---
    {"path": "config/dependency-graph.json",          "type": "dep_graph",     "nodes_key": "nodes", "edges_key": "edges"},
    # --- Partitions: remove service_id from nested services[] string arrays ---
    {"path": "config/contracts/service-partitions/catalog.json", "type": "partitions"},
    # --- YAML dict-key: remove keys under list_key that match any variant ---
    {"path": "config/ansible-role-idempotency.yml",   "type": "yaml_dict_key",      "list_key": "roles"},
    # --- YAML topology block: remove service key from lv3_service_topology dict ---
    {"path": "inventory/host_vars/proxmox_florin.yml", "type": "yaml_topology_block", "list_key": "lv3_service_topology"},
    # --- YAML var-prefix: remove <service_id>_* lines under a named parent dict ---
    {"path": "inventory/host_vars/proxmox_florin.yml", "type": "yaml_var_prefix", "parent_key": "platform_port_assignments"},
    # --- YAML block-marker files: use BEGIN/END SERVICE markers (one entry per hand-authored file) ---
    {"path": "inventory/group_vars/all/platform_services.yml", "type": "yaml_marker_block"},
    # --- Flat JSON array (root IS the array, no list_key wrapper) ---
    {"path": "config/uptime-kuma/monitors.json", "type": "json_array_flat", "id_field": "service_id"},
    # --- workbench-IA service_overrides array (standard array with service_id) ---
    {"path": "config/workbench-information-architecture.json", "type": "array", "list_key": "service_overrides", "id_field": "service_id"},
]


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


def _find_role_name(service_id: str) -> str:
    """Return the Ansible role name for a service from service-capability-catalog.json.

    Falls back to ``<service_id>_runtime`` when not explicitly registered.
    """
    try:
        catalog = load_service_catalog()
        for svc in catalog.get("services", []):
            if isinstance(svc, dict) and svc.get("id") == service_id:
                return str(svc.get("role_name", f"{service_id}_runtime"))
    except Exception:
        pass
    return f"{service_id}_runtime"


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


# ============================================================================
# Phase 2: Code Purge — deterministic file removal and catalog rewriting
# ============================================================================

def _service_name_variants(service_id: str) -> list[str]:
    """Return all naming variants for grep patterns."""
    underscore = service_id
    hyphen = service_id.replace("_", "-")
    joined = service_id.replace("_", "")
    return sorted(set([underscore, hyphen, joined]))


def _grep_files(patterns: list[str], search_dirs: list[Path], *, exclude_dirs: list[str] | None = None) -> list[Path]:
    """Find files matching any pattern using ripgrep (fast) or grep fallback."""
    exclude_dirs = exclude_dirs or [".git", "receipts", "docs/release-notes", "__pycache__"]
    combined_pattern = "|".join(re.escape(p) for p in patterns)
    cmd = ["grep", "-rl", "-E", combined_pattern]
    for exc in exclude_dirs:
        cmd.extend(["--exclude-dir", exc])
    cmd.extend(str(d) for d in search_dirs if d.exists())
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return sorted(set(Path(line) for line in result.stdout.strip().splitlines() if line))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _discover_deletable_dirs(service_id: str) -> list[Path]:
    """Find entire directories to delete (roles, etc.)."""
    dirs: list[Path] = []
    underscore = service_id

    # Look up the canonical role name from the catalog first (Amendment 3)
    role_name = _find_role_name(service_id)
    candidates = {role_name, f"{underscore}_runtime", f"{underscore}_postgres"}
    for candidate in sorted(candidates):
        role_dir = ROLES_ROOT / candidate
        if role_dir.is_dir() and role_dir not in dirs:
            dirs.append(role_dir)

    return dirs


def _discover_deletable_files(service_id: str) -> list[Path]:
    """Find individual files to delete entirely."""
    files: list[Path] = []
    underscore = service_id
    hyphen = service_id.replace("_", "-")
    role_name = _find_role_name(service_id)

    # Collection playbook
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = COLLECTION_PLAYBOOKS / name
        if candidate.is_file():
            files.append(candidate)

    # Collection services playbook (Amendment 3)
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = COLLECTION_PLAYBOOKS / "services" / name
        if candidate.is_file():
            files.append(candidate)

    # Root playbooks
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = ROOT_PLAYBOOKS / name
        if candidate.is_file():
            files.append(candidate)

    # Root services playbook (Amendment 3: playbooks/services/<id>.yml)
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = ROOT_PLAYBOOKS / "services" / name
        if candidate.is_file():
            files.append(candidate)

    # Root playbook vars
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = ROOT_PLAYBOOKS / "vars" / name
        if candidate.is_file():
            files.append(candidate)

    # Alertmanager rules
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = CONFIG_DIR / "alertmanager" / "rules" / name
        if candidate.is_file():
            files.append(candidate)

    # Grafana dashboards
    for name in (f"{hyphen}.json", f"{underscore}.json"):
        candidate = CONFIG_DIR / "grafana" / "dashboards" / name
        if candidate.is_file():
            files.append(candidate)

    # Tests — use role_name-aware pattern as well as service_id patterns (Amendment 3)
    for pattern in (f"test_{underscore}_*.py", f"test_{hyphen}_*.py", f"test_{role_name}_*.py"):
        files.extend(TESTS_DIR.glob(pattern))

    # Keycloak client tasks
    kc_tasks = ROLES_ROOT / "keycloak_runtime" / "tasks"
    for name in (f"{underscore}_client.yml", f"{hyphen}_client.yml"):
        candidate = kc_tasks / name
        if candidate.is_file():
            files.append(candidate)

    return sorted(set(files))


def _remove_from_json_catalog(path: Path, service_id: str, list_key: str, id_key: str = "id") -> bool:
    """Remove entries matching service_id from a JSON catalog's list."""
    if not path.is_file():
        return False
    catalog = load_json(path)
    if not isinstance(catalog, dict) or list_key not in catalog:
        return False
    items = catalog[list_key]
    if not isinstance(items, list):
        return False
    filtered = [item for item in items if not (isinstance(item, dict) and item.get(id_key) == service_id)]
    if len(filtered) == len(items):
        return False
    catalog[list_key] = filtered
    write_json(path, catalog, indent=2)
    return True


def _remove_top_level_key(path: Path, service_id: str) -> bool:
    """Remove top-level JSON keys that match any service variant.

    Used for ``service-completeness.json`` where entries live directly at the
    root of the document rather than nested under a ``list_key``.
    """
    if not path.is_file():
        return False
    catalog = load_json(path)
    if not isinstance(catalog, dict):
        return False
    variants = set(_service_name_variants(service_id))
    to_remove = [k for k in catalog if k in variants]
    if not to_remove:
        return False
    for k in to_remove:
        del catalog[k]
    write_json(path, catalog, indent=2)
    return True


def _remove_from_dict_key_catalog(path: Path, service_id: str, list_key: str) -> bool:
    """Remove dict entry where key == service_id variant (e.g. health-probe-catalog)."""
    if not path.is_file():
        return False
    catalog = load_json(path)
    obj = catalog.get(list_key)
    if not isinstance(obj, dict):
        return False
    variants = set(_service_name_variants(service_id))
    to_remove = [k for k in obj if k in variants]
    if not to_remove:
        return False
    for k in to_remove:
        del obj[k]
    write_json(path, catalog, indent=2)
    return True


def _remove_from_dict_key_by_value_catalog(
    path: Path, service_id: str, list_key: str, id_field: str
) -> bool:
    """Remove dict entries where value[id_field] == service_id (e.g. image-catalog)."""
    if not path.is_file():
        return False
    catalog = load_json(path)
    obj = catalog.get(list_key)
    if not isinstance(obj, dict):
        return False
    to_remove = [k for k, v in obj.items() if isinstance(v, dict) and v.get(id_field) == service_id]
    if not to_remove:
        return False
    for k in to_remove:
        del obj[k]
    write_json(path, catalog, indent=2)
    return True


def _remove_from_workflow_dict(path: Path, service_id: str, list_key: str) -> bool:
    """Remove workflow entries whose key contains any service variant."""
    if not path.is_file():
        return False
    catalog = load_json(path)
    obj = catalog.get(list_key)
    if not isinstance(obj, dict):
        return False
    variants = _service_name_variants(service_id)
    to_remove = [k for k in obj if any(v in k for v in variants)]
    if not to_remove:
        return False
    for k in to_remove:
        del obj[k]
    write_json(path, catalog, indent=2)
    return True


def _remove_from_dep_graph(path: Path, service_id: str, nodes_key: str, edges_key: str) -> bool:
    """Remove nodes (by id) and edges (by from/to) from a dependency graph JSON."""
    if not path.is_file():
        return False
    catalog = load_json(path)
    if not isinstance(catalog, dict):
        return False
    variants = set(_service_name_variants(service_id))
    changed = False

    nodes = catalog.get(nodes_key)
    if isinstance(nodes, list):
        before = len(nodes)
        catalog[nodes_key] = [
            n for n in nodes
            if not (isinstance(n, dict) and (n.get("id") in variants or n.get("service") in variants))
        ]
        if len(catalog[nodes_key]) != before:
            changed = True

    edges = catalog.get(edges_key)
    if isinstance(edges, list):
        before = len(edges)
        catalog[edges_key] = [
            e for e in edges
            if not (isinstance(e, dict) and (e.get("from") in variants or e.get("to") in variants))
        ]
        if len(catalog[edges_key]) != before:
            changed = True

    if changed:
        write_json(path, catalog, indent=2)
    return changed


def _remove_from_partitions_catalog(path: Path, service_id: str) -> bool:
    """Remove service_id from all partition services[] string arrays."""
    if not path.is_file():
        return False
    catalog = load_json(path)
    partitions = catalog.get("partitions")
    if not isinstance(partitions, dict):
        return False
    variants = set(_service_name_variants(service_id))
    changed = False
    for partition in partitions.values():
        if not isinstance(partition, dict):
            continue
        services_list = partition.get("services")
        if isinstance(services_list, list):
            before = len(services_list)
            partition["services"] = [s for s in services_list if s not in variants]
            if len(partition["services"]) != before:
                changed = True
    if changed:
        write_json(path, catalog, indent=2)
    return changed


def _remove_from_yaml_dict_key(path: Path, service_id: str, list_key: str) -> bool:
    """Remove YAML dict entries whose key contains any service variant.

    Handles files like ansible-role-idempotency.yml where role names contain the service_id.
    Uses PyYAML when available, falls back to line-based removal.
    """
    if not path.is_file():
        return False
    variants = _service_name_variants(service_id)
    try:
        import yaml  # optional dependency
        content = path.read_text()
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or list_key not in data:
            return False
        obj = data[list_key]
        if not isinstance(obj, dict):
            return False
        to_remove = [k for k in obj if any(v in str(k) for v in variants)]
        if not to_remove:
            return False
        for k in to_remove:
            del obj[k]
        path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
        return True
    except ImportError:
        # Fall back to line-based block removal under list_key
        return _remove_yaml_block(path, service_id)


def _remove_from_yaml_topology_block(path: Path, list_key: str, service_id: str) -> bool:
    """Remove a service key block from within a YAML dict section, preserving all comments.

    Operates line-by-line to avoid clobbering comments and surrounding content.
    Scoped to the ``list_key`` section so only the service entry inside it is removed.

    Used for ``lv3_service_topology`` in ``inventory/host_vars/proxmox_florin.yml``.
    """
    if not path.is_file():
        return False
    try:
        lines = path.read_text().splitlines(keepends=True)
    except (UnicodeDecodeError, ValueError):
        return False

    variants = set(_service_name_variants(service_id))
    new_lines: list[str] = []

    in_topology = False
    in_service_block = False
    topology_key_indent = -1
    service_key_indent = -1
    changed = False

    for line in lines:
        raw = line.rstrip("\n").rstrip("\r")
        stripped = raw.lstrip()

        # Blank or comment: keep unless we're inside a removed block
        if not stripped or stripped.startswith("#"):
            if in_service_block:
                continue
            new_lines.append(line)
            continue

        current_indent = len(raw) - len(stripped)
        # Key = text before the first ':'
        key_part = stripped.split(":")[0].strip() if ":" in stripped else stripped.split()[0]

        # Transition: exiting the topology section (back to same or lower indent)
        if in_topology and current_indent <= topology_key_indent:
            in_topology = False
            in_service_block = False

        # Transition: end of the service block (next sibling or end of topology)
        if in_service_block and current_indent <= service_key_indent:
            in_service_block = False

        # Detect topology section header
        if not in_topology and key_part == list_key:
            in_topology = True
            topology_key_indent = current_indent
            new_lines.append(line)
            continue

        if in_topology and not in_service_block:
            if key_part in variants:
                in_service_block = True
                service_key_indent = current_indent
                changed = True
                continue  # skip — don't append

        if in_service_block:
            continue  # skip lines inside removed block

        new_lines.append(line)

    if changed:
        path.write_text("".join(new_lines))
    return changed


def _remove_yaml_block_markers(path: Path, service_id: str) -> bool:
    """Remove content between # BEGIN SERVICE: <variant> and # END SERVICE: <variant> markers.

    This is the primary removal strategy for generated YAML files (SLO config, etc.)
    that have block markers written by generate_slo_config.py.
    """
    if not path.is_file():
        return False
    try:
        content = path.read_text()
    except (UnicodeDecodeError, ValueError):
        return False
    variants = _service_name_variants(service_id)
    changed = False
    for variant in variants:
        pattern = re.compile(
            rf'^ *# BEGIN SERVICE: {re.escape(variant)}\n.*?^ *# END SERVICE: {re.escape(variant)}\n',
            re.MULTILINE | re.DOTALL,
        )
        new_content, n = pattern.subn("", content)
        if n:
            content = new_content
            changed = True
    if changed:
        path.write_text(content)
    return changed


def _remove_from_json_array_flat(path: Path, service_id: str, id_field: str) -> bool:
    """Remove entries from a JSON file whose root IS a bare array (no list_key wrapper).

    Used for config/uptime-kuma/monitors.json where the root is ``[{...}, ...]``.
    Entries are removed when item[id_field] matches any service variant.
    """
    if not path.is_file():
        return False
    try:
        data = load_json(path)
    except Exception:
        return False
    if not isinstance(data, list):
        return False
    variants = set(_service_name_variants(service_id))
    filtered = [
        item for item in data
        if not (isinstance(item, dict) and item.get(id_field) in variants)
    ]
    if len(filtered) == len(data):
        return False
    write_json(path, filtered, indent=2)
    return True


def _remove_from_yaml_var_prefix(path: Path, parent_key: str, service_id: str) -> bool:
    """Remove lines under parent_key whose YAML key starts with any service variant.

    Operates line-by-line to preserve all comments and surrounding structure.
    Used to clean up standalone ``<service_id>_port: N`` entries under
    ``platform_port_assignments`` in inventory/host_vars/proxmox_florin.yml.
    """
    if not path.is_file():
        return False
    try:
        lines = path.read_text().splitlines(keepends=True)
    except (UnicodeDecodeError, ValueError):
        return False
    variants = set(_service_name_variants(service_id))
    new_lines: list[str] = []
    in_parent = False
    parent_indent = -1
    changed = False

    for line in lines:
        raw = line.rstrip("\n").rstrip("\r")
        stripped = raw.lstrip()
        if not stripped:
            new_lines.append(line)
            continue
        current_indent = len(raw) - len(stripped)
        key_part = stripped.split(":")[0].strip() if ":" in stripped else stripped.split()[0]

        if not in_parent and key_part == parent_key:
            in_parent = True
            parent_indent = current_indent
            new_lines.append(line)
            continue

        if in_parent and current_indent <= parent_indent and key_part != parent_key:
            in_parent = False

        if in_parent and not stripped.startswith("#"):
            if any(key_part == v or key_part.startswith(f"{v}_") for v in variants):
                changed = True
                continue

        new_lines.append(line)

    if changed:
        path.write_text("".join(new_lines))
    return changed


def _remove_service_test_functions(path: Path, service_id: str) -> bool:
    """Remove Python test functions whose names contain any service_id variant.

    Uses the AST module for exact start/end line numbers — safe for multi-line
    functions, decorators, and nested functions.  Returns True if any functions
    were removed.
    """
    if not path.is_file():
        return False
    try:
        source = path.read_text()
    except (UnicodeDecodeError, ValueError):
        return False
    try:
        import ast as _ast
        tree = _ast.parse(source)
    except SyntaxError:
        return False
    variants = _service_name_variants(service_id)
    lines_to_remove: set[int] = set()

    for node in _ast.walk(tree):
        if not isinstance(node, _ast.FunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        name_lower = node.name.lower()
        if not any(v.replace("-", "_") in name_lower for v in variants):
            continue
        start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
        for lineno in range(start, node.end_lineno + 1):
            lines_to_remove.add(lineno)

    if not lines_to_remove:
        return False

    source_lines = source.splitlines(keepends=True)
    # Also absorb a single blank line immediately before each function start
    for lineno in sorted(lines_to_remove):
        preceding = lineno - 1
        if preceding > 0 and preceding not in lines_to_remove:
            if not source_lines[preceding - 1].strip():
                lines_to_remove.add(preceding)

    new_lines = [
        line for i, line in enumerate(source_lines, start=1)
        if i not in lines_to_remove
    ]
    path.write_text("".join(new_lines))
    return True


def _remove_inline_service_markers(path: Path, service_id: str) -> bool:
    """Remove lines annotated with ``# SERVICE: <id>`` inline markers.

    Handles two annotation styles:
    - Single-line: ``var: value  # SERVICE: service_id — ...``
    - Jinja2 block: ``{# BEGIN SERVICE: service_id #}`` ... ``{# END SERVICE: service_id #}``
    """
    if not path.is_file():
        return False
    try:
        content = path.read_text()
    except (UnicodeDecodeError, ValueError):
        return False

    variants = _service_name_variants(service_id)
    original = content

    # Remove Jinja2 block markers (multi-line)
    for variant in variants:
        pattern = re.compile(
            rf'\{{#\s*BEGIN SERVICE:\s*{re.escape(variant)}\s*#\}}.*?\{{#\s*END SERVICE:\s*{re.escape(variant)}\s*#\}}',
            re.DOTALL,
        )
        content = pattern.sub("", content)

    # Remove lines with inline ``# SERVICE: <variant>`` annotations
    lines = content.splitlines(keepends=True)
    new_lines = [
        line for line in lines
        if not any(f"# SERVICE: {v}" in line for v in variants)
    ]
    content = "".join(new_lines)

    if content != original:
        path.write_text(content)
        return True
    return False


def _remove_role_inline_markers(service_id: str) -> list[str]:
    """Scan all role defaults/main.yml and Jinja2 templates for ``# SERVICE:`` markers.

    Returns a list of relative paths that were modified.
    """
    modified: list[str] = []
    if not ROLES_ROOT.is_dir():
        return modified

    for candidate in ROLES_ROOT.rglob("*.yml"):
        # Try both annotation styles: inline # SERVICE: markers AND # BEGIN/END SERVICE: blocks
        changed = _remove_inline_service_markers(candidate, service_id)
        changed = _remove_yaml_block_markers(candidate, service_id) or changed
        if changed:
            modified.append(str(candidate.relative_to(repo_path())))
    for candidate in ROLES_ROOT.rglob("*.j2"):
        if _remove_inline_service_markers(candidate, service_id):
            modified.append(str(candidate.relative_to(repo_path())))

    return modified


def _apply_catalog_registry_entry(entry: dict[str, str], service_id: str) -> bool:
    """Dispatch to the right handler based on the catalog type."""
    path = repo_path(*entry["path"].split("/"))
    kind = entry["type"]

    if kind == "array":
        return _remove_from_json_catalog(path, service_id, entry["list_key"], entry["id_field"])
    elif kind == "dict_key":
        return _remove_from_dict_key_catalog(path, service_id, entry["list_key"])
    elif kind == "top_level_key":
        return _remove_top_level_key(path, service_id)
    elif kind == "dict_key_by_value":
        return _remove_from_dict_key_by_value_catalog(path, service_id, entry["list_key"], entry["id_field"])
    elif kind in ("workflow_dict", "secrets_dict"):
        return _remove_from_workflow_dict(path, service_id, entry["list_key"])
    elif kind == "dep_graph":
        return _remove_from_dep_graph(path, service_id, entry["nodes_key"], entry["edges_key"])
    elif kind == "partitions":
        return _remove_from_partitions_catalog(path, service_id)
    elif kind == "yaml_dict_key":
        return _remove_from_yaml_dict_key(path, service_id, entry["list_key"])
    elif kind == "yaml_topology_block":
        return _remove_from_yaml_topology_block(path, entry["list_key"], service_id)
    elif kind == "yaml_marker_block":
        return _remove_yaml_block_markers(path, service_id)
    elif kind == "json_array_flat":
        return _remove_from_json_array_flat(path, service_id, entry["id_field"])
    elif kind == "yaml_var_prefix":
        return _remove_from_yaml_var_prefix(path, entry.get("parent_key", ""), service_id)
    return False


def _remove_yaml_block(path: Path, service_id: str) -> bool:
    """Remove a top-level YAML key matching the service_id (simple line-based removal)."""
    if not path.is_file():
        return False
    try:
        lines = path.read_text().splitlines(keepends=True)
    except (UnicodeDecodeError, ValueError):
        return False  # skip binary files
    variants = _service_name_variants(service_id)
    new_lines: list[str] = []
    skip_block = False
    changed = False
    for line in lines:
        stripped = line.lstrip()
        # Check if this line starts a top-level or indented key matching service variants
        if not skip_block:
            key_match = False
            for variant in variants:
                if stripped.startswith(f"{variant}:") or stripped.startswith(f"{variant} :"):
                    key_match = True
                    break
            if key_match:
                skip_block = True
                changed = True
                continue
        else:
            # Continue skipping indented continuation lines
            if stripped and not stripped.startswith("#") and not stripped[0].isspace() and line[0] != " " and line[0] != "\t":
                # New top-level key — stop skipping
                skip_block = False
            elif stripped == "" or stripped.startswith("#"):
                # Blank or comment inside block — skip
                continue
            else:
                continue
        if not skip_block:
            new_lines.append(line)
    if changed:
        path.write_text("".join(new_lines))
    return changed


def _remove_line_references(path: Path, service_id: str) -> bool:
    """Remove individual lines referencing the service from a file."""
    if not path.is_file():
        return False
    try:
        variants = _service_name_variants(service_id)
        lines = path.read_text().splitlines(keepends=True)
    except (UnicodeDecodeError, ValueError):
        return False  # skip binary files
    filtered = [line for line in lines if not any(v in line for v in variants)]
    if len(filtered) == len(lines):
        return False
    path.write_text("".join(filtered))
    return True


def _deprecate_adrs(service_id: str, removing_adr: str | None = None) -> list[str]:
    """Find ADRs mentioning the service and mark them Deprecated.

    Handles both bold (**Status:** Accepted) and list-item (- Status: Accepted) formats.
    """
    if not DOCS_ADR_DIR.is_dir():
        return []
    deprecated: list[str] = []
    variants = _service_name_variants(service_id)
    removing_ref = f"ADR {removing_adr}" if removing_adr else "service removal ADR"
    for adr_file in sorted(DOCS_ADR_DIR.glob("*.md")):
        content = adr_file.read_text()
        # Only deprecate ADRs primarily about this service (in the title)
        first_line = content.split("\n", 1)[0].lower()
        if not any(v.replace("_", " ") in first_line or v in first_line for v in variants):
            continue
        already_deprecated = (
            "**Status:** Deprecated" in content
            or "- Status: Deprecated" in content
        )
        if already_deprecated:
            continue
        # Handle bold format: **Status:** Accepted
        content = re.sub(
            r"\*\*Status:\*\*\s*\w+",
            "**Status:** Deprecated",
            content,
            count=1,
        )
        # Handle list-item format: - Status: Accepted
        content = re.sub(
            r"^(- Status:)\s*\w+",
            r"\1 Deprecated",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        # Add cross-reference comment if not already present
        if removing_ref not in content:
            content = content.replace(
                "**Status:** Deprecated",
                f"**Status:** Deprecated (see {removing_ref} — service removed from platform)",
                1,
            ).replace(
                "- Status: Deprecated",
                f"- Status: Deprecated (see {removing_ref} — service removed from platform)",
                1,
            )
        adr_file.write_text(content)
        deprecated.append(adr_file.name)
    return deprecated


def _remove_from_stack_yaml(service_id: str) -> bool:
    """Remove the service receipt from versions/stack.yaml."""
    stack_path = VERSIONS_DIR / "stack.yaml"
    return _remove_line_references(stack_path, service_id)


def _validate_modified_files(paths: list[Path]) -> list[str]:
    """Parse every modified JSON/YAML file and return error messages for any that are corrupt.

    Called at the end of ``execute_code_purge`` to catch parser-visible corruption
    immediately (orphaned commas, broken PromQL expressions, etc.) rather than at
    pre-commit time (Amendment 6).

    For each failure the error message includes the ``git checkout HEAD -- <path>``
    recovery command.
    """
    errors: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            if path.suffix == ".json":
                with path.open() as fh:
                    json.load(fh)
            elif path.suffix in (".yml", ".yaml"):
                try:
                    import yaml
                    with path.open() as fh:
                        yaml.safe_load(fh)
                except ImportError:
                    pass  # yaml not available — skip YAML validation
        except Exception as exc:
            rel = str(path.relative_to(repo_path())) if repo_path() in path.parents else str(path)
            errors.append(
                f"CORRUPT: {rel}: {exc}\n"
                f"  Recovery: git checkout HEAD -- {rel}"
            )
    return errors


def build_code_purge_plan(service_id: str) -> dict[str, Any]:
    """Build a plan showing exactly what code purge would do."""
    deletable_dirs = _discover_deletable_dirs(service_id)
    deletable_files = _discover_deletable_files(service_id)
    variants = _service_name_variants(service_id)

    # Structured catalog entries to clean — uses CATALOG_REGISTRY for comprehensive coverage
    registry_hits: list[dict[str, str]] = []
    variants_set = set(variants)
    for entry in CATALOG_REGISTRY:
        full = repo_path(*entry["path"].split("/"))
        if not full.is_file():
            continue
        kind = entry["type"]
        hit = False
        try:
            if kind == "array":
                catalog = load_json(full)
                items = catalog.get(entry["list_key"], [])
                hit = isinstance(items, list) and any(
                    isinstance(i, dict) and i.get(entry["id_field"]) == service_id for i in items
                )
            elif kind == "dict_key":
                catalog = load_json(full)
                obj = catalog.get(entry["list_key"], {})
                hit = isinstance(obj, dict) and bool(variants_set & set(obj.keys()))
            elif kind == "dict_key_by_value":
                catalog = load_json(full)
                obj = catalog.get(entry["list_key"], {})
                hit = isinstance(obj, dict) and any(
                    isinstance(v, dict) and v.get(entry["id_field"]) == service_id
                    for v in obj.values()
                )
            elif kind in ("workflow_dict", "secrets_dict"):
                catalog = load_json(full)
                obj = catalog.get(entry["list_key"], {})
                hit = isinstance(obj, dict) and any(
                    any(v in k for v in variants_set) for k in obj
                )
            elif kind == "dep_graph":
                catalog = load_json(full)
                nodes = catalog.get(entry["nodes_key"], [])
                edges = catalog.get(entry["edges_key"], [])
                hit = any(isinstance(n, dict) and n.get("id") in variants_set for n in nodes) or \
                      any(isinstance(e, dict) and (e.get("from") in variants_set or e.get("to") in variants_set) for e in edges)
            elif kind == "partitions":
                catalog = load_json(full)
                parts = catalog.get("partitions", {})
                hit = any(
                    s in variants_set
                    for p in parts.values()
                    if isinstance(p, dict)
                    for s in p.get("services", [])
                )
            elif kind == "top_level_key":
                catalog = load_json(full)
                hit = isinstance(catalog, dict) and bool(variants_set & set(catalog.keys()))
            elif kind == "yaml_dict_key":
                try:
                    import yaml
                    data = yaml.safe_load(full.read_text()) or {}
                    obj = data.get(entry["list_key"], {})
                    hit = isinstance(obj, dict) and any(any(v in str(k) for v in variants_set) for k in obj)
                except Exception:
                    hit = any(v in full.read_text() for v in variants_set)
            elif kind == "yaml_topology_block":
                try:
                    import yaml
                    data = yaml.safe_load(full.read_text()) or {}
                    topology = data.get(entry.get("list_key", ""), {})
                    hit = isinstance(topology, dict) and bool(variants_set & set(topology.keys()))
                except Exception:
                    hit = any(v in full.read_text() for v in variants_set)
            elif kind == "yaml_marker_block":
                content = full.read_text()
                hit = any(f"# BEGIN SERVICE: {v}" in content for v in variants_set)
            elif kind == "json_array_flat":
                data = load_json(full)
                hit = isinstance(data, list) and any(
                    isinstance(i, dict) and i.get(entry["id_field"]) in variants_set for i in data
                )
            elif kind == "yaml_var_prefix":
                try:
                    import yaml
                    data = yaml.safe_load(full.read_text()) or {}
                    port_map = data.get(entry.get("parent_key", ""), {})
                    hit = isinstance(port_map, dict) and any(
                        any(k == v or k.startswith(f"{v}_") for v in variants_set)
                        for k in port_map
                    )
                except Exception:
                    hit = any(v in full.read_text() for v in variants_set)
        except Exception:
            pass
        if hit:
            registry_hits.append(entry)

    json_catalogs = registry_hits  # for plan output compatibility

    # YAML/JSON files with line-level references
    search_dirs = [CONFIG_DIR, INVENTORY_DIR, repo_path("scripts")]
    ref_files = _grep_files(variants, search_dirs, exclude_dirs=[
        ".git", "receipts", "docs/release-notes", "changelog.md", "RELEASE.md",
    ])
    # Exclude files already covered by dir/file deletion or JSON catalogs
    covered = set(str(f) for f in deletable_files)
    for d in deletable_dirs:
        covered.update(str(f) for f in d.rglob("*"))
    catalog_paths = set(c["path"] for c in json_catalogs)
    ref_files = [
        f for f in ref_files
        if str(f) not in covered
        and not any(str(f).endswith(cp) for cp in catalog_paths)
    ]

    return {
        "service_id": service_id,
        "variants": variants,
        "delete_directories": [str(d.relative_to(repo_path())) for d in deletable_dirs],
        "delete_files": [str(f.relative_to(repo_path())) for f in deletable_files],
        "json_catalogs_to_clean": json_catalogs,
        "files_with_references": [str(f.relative_to(repo_path())) for f in ref_files],
        "adr_deprecation": "will scan docs/adr/ for service-specific ADRs (handles both bold and list-item Status: formats)",
        "stack_yaml": "will remove receipt entry",
        "regenerate": [
            "python scripts/platform_manifest.py --write",
            "python scripts/generate_discovery_artifacts.py --write",
            "python3 scripts/workstream_registry.py --write",
        ],
    }


def execute_code_purge(plan: dict[str, Any]) -> dict[str, Any]:
    """Execute the code purge plan. Deterministic, CPU-only."""
    results: dict[str, Any] = {
        "directories_deleted": [],
        "files_deleted": [],
        "catalogs_cleaned": [],
        "reference_files_cleaned": [],
        "inline_marker_files_cleaned": [],
        "test_functions_removed": [],
        "adrs_deprecated": [],
        "stack_yaml_cleaned": False,
        "regeneration_commands": [],
        "integrity_errors": [],
    }
    service_id = plan["service_id"]
    modified_paths: list[Path] = []  # track for post-purge validation

    # 1. Delete directories
    for rel_dir in plan["delete_directories"]:
        full = repo_path() / rel_dir
        if full.is_dir():
            shutil.rmtree(full)
            results["directories_deleted"].append(rel_dir)

    # 2. Delete files
    for rel_file in plan["delete_files"]:
        full = repo_path() / rel_file
        if full.is_file():
            full.unlink()
            results["files_deleted"].append(rel_file)

    # 3. Clean catalogs using the registry (structured, schema-aware)
    for entry in plan["json_catalogs_to_clean"]:
        path = repo_path(*entry["path"].split("/"))
        if _apply_catalog_registry_entry(entry, service_id):
            results["catalogs_cleaned"].append(entry["path"])
            modified_paths.append(path)

    # 4. Remove service blocks from generated YAML files (marker-based)
    generated_yaml_files = [
        repo_path("config", "prometheus", "rules", "slo_alerts.yml"),
        repo_path("config", "prometheus", "rules", "slo_rules.yml"),
        repo_path("config", "prometheus", "file_sd", "slo_targets.yml"),
        repo_path("config", "prometheus", "rules", "https_tls_alerts.yml"),
        repo_path("config", "prometheus", "file_sd", "https_tls_targets.yml"),
        repo_path("config", "dependency-graph.yaml"),
    ]
    for yaml_file in generated_yaml_files:
        if _remove_yaml_block_markers(yaml_file, service_id):
            results["reference_files_cleaned"].append(str(yaml_file.relative_to(repo_path())))
            modified_paths.append(yaml_file)

    # 4b. Remove line-level references from remaining files (fallback for non-catalog, non-marker files)
    for rel_file in plan["files_with_references"]:
        full = repo_path() / rel_file
        # Skip files already handled by catalog registry or markers
        if any(str(full).endswith(e["path"]) for e in CATALOG_REGISTRY):
            continue
        if _remove_line_references(full, service_id):
            results["reference_files_cleaned"].append(rel_file)
            modified_paths.append(full)

    # 4c. Remove inline # SERVICE: markers from role defaults and Jinja2 templates (Amendment 4)
    inline_modified = _remove_role_inline_markers(service_id)
    results["inline_marker_files_cleaned"] = inline_modified
    modified_paths.extend(repo_path() / f for f in inline_modified)

    # 4d. Remove service-specific test functions using AST (Gap 6 — ADR 0402 postmortem)
    test_files_modified: list[str] = []
    if TESTS_DIR.is_dir():
        for test_file in sorted(TESTS_DIR.glob("test_*.py")):
            if _remove_service_test_functions(test_file, service_id):
                test_files_modified.append(str(test_file.relative_to(repo_path())))
                modified_paths.append(test_file)
    results["test_functions_removed"] = test_files_modified

    # 5. Deprecate ADRs
    results["adrs_deprecated"] = _deprecate_adrs(service_id)

    # 6. Clean stack.yaml
    results["stack_yaml_cleaned"] = _remove_from_stack_yaml(service_id)

    # 7. Regenerate artifacts
    for cmd_str in plan.get("regenerate", []):
        try:
            subprocess.run(cmd_str.split(), cwd=str(repo_path()), capture_output=True, timeout=60)
            results["regeneration_commands"].append({"command": cmd_str, "status": "ok"})
        except Exception as exc:
            results["regeneration_commands"].append({"command": cmd_str, "status": f"error: {exc}"})

    # 8. Post-purge integrity validation (Amendment 6) — parse every modified JSON/YAML
    integrity_errors = _validate_modified_files(modified_paths)
    results["integrity_errors"] = integrity_errors
    if integrity_errors:
        print("\n".join(integrity_errors), file=sys.stderr)

    return results


# ============================================================================
# ADR Generation — templated, zero AI involvement
# ============================================================================

def _next_adr_number() -> int:
    """Find the next available ADR number by scanning docs/adr/."""
    highest = 0
    if DOCS_ADR_DIR.is_dir():
        for f in DOCS_ADR_DIR.glob("*.md"):
            match = re.match(r"^(\d+)-", f.name)
            if match:
                num = int(match.group(1))
                if num > highest:
                    highest = num
    return highest + 1


def _format_file_list(files: list[str], label: str) -> str:
    if not files:
        return ""
    lines = [f"| {label} | {len(files)} |"]
    return "\n".join(lines)


def generate_removal_adr(
    service_id: str,
    code_plan: dict[str, Any],
    runtime_plan: dict[str, Any],
    *,
    reason: str = "The service is no longer needed.",
    replacement: str = "None.",
    adr_number: int | None = None,
) -> tuple[Path, str]:
    """Generate a complete service-removal ADR from the dry-run plan. Pure template, no AI."""
    if adr_number is None:
        adr_number = _next_adr_number()

    hyphen_name = service_id.replace("_", "-")
    service_name = runtime_plan.get("service_name", service_id)
    today = __import__("datetime").date.today().isoformat()

    n_dirs = len(code_plan.get("delete_directories", []))
    n_files = len(code_plan.get("delete_files", []))
    n_catalogs = len(code_plan.get("json_catalogs_to_clean", []))
    n_refs = len(code_plan.get("files_with_references", []))
    total = n_dirs + n_files + n_catalogs + n_refs

    dir_list = "\n".join(f"- `{d}`" for d in code_plan.get("delete_directories", []))
    file_list = "\n".join(f"- `{f}`" for f in code_plan.get("delete_files", []))
    catalog_list = "\n".join(
        f"- `{c['path']}` (remove from `{c['list_key']}`)"
        for c in code_plan.get("json_catalogs_to_clean", [])
    )
    ref_list = "\n".join(f"- `{f}`" for f in code_plan.get("files_with_references", []))

    db_section = ""
    if runtime_plan.get("database_name"):
        db_section = f"- Drop PostgreSQL database: `{runtime_plan['database_name']}`"

    content = f"""# ADR {adr_number:04d}: Remove {service_name} from the Platform

**Status:** Accepted
**Decision Date:** {today}
**Concern:** Service Lifecycle, Operational Simplification
**Depends on:** ADR 0389 (Service Decommissioning Procedure)

---

## Context

{reason}

**Replacement:** {replacement}

### Removal scope (auto-generated from dry-run)

| Surface | Count |
|---------|-------|
| Directories to delete | {n_dirs} |
| Files to delete | {n_files} |
| JSON catalogs to clean | {n_catalogs} |
| Files with line references | {n_refs} |
| **Total surfaces** | **{total}** |

---

## Decision

Remove {service_name} following ADR 0389.

### Phase 1: Production Teardown

```bash
ssh docker-runtime-lv3 "cd /opt/lv3/{hyphen_name} && docker compose down --remove-orphans"
```
{db_section}
- Remove Keycloak OIDC client: `{runtime_plan.get("keycloak_client_id", service_id)}`
- Remove OpenBao policy: `{runtime_plan.get("openbao_policy_name", "")}`

### Phase 2: Code Removal

```bash
# Dry-run
python3 scripts/decommission_service.py --service {service_id}

# Execute
python3 scripts/decommission_service.py --service {service_id} \\
  --purge-code --confirm {service_id}
```

<details>
<summary>Directories to delete ({n_dirs})</summary>

{dir_list or "_None_"}
</details>

<details>
<summary>Files to delete ({n_files})</summary>

{file_list or "_None_"}
</details>

<details>
<summary>JSON catalogs to clean ({n_catalogs})</summary>

{catalog_list or "_None_"}
</details>

<details>
<summary>Files with line references to clean ({n_refs})</summary>

{ref_list or "_None_"}
</details>

### Phase 3: Reconverge affected services

- `public-edge` — remove NGINX upstream/server blocks
- `database-dns` — remove DNS records
- `keycloak` — remove OIDC client
- `monitoring-stack` — reload alert rules and dashboards

---

## Validation

```bash
grep -ri "{service_id}\\|{hyphen_name}" \\
  collections/ansible_collections/lv3/platform/roles/*/defaults/ \\
  collections/ansible_collections/lv3/platform/roles/*/tasks/ \\
  inventory/ config/ tests/ scripts/ \\
  | grep -v "docs/\\|changelog\\|receipts/\\|release-notes/" | wc -l
# Expected: 0
```

---

## Consequences

**Positive:**
- Reduces operational surface (containers, monitoring, backups, OIDC, database)
- {total} fewer active configuration surfaces

**Negative / Trade-offs:**
- Historical references remain in changelog, release notes, and receipts

---

## Related

- ADR 0389 — Service Decommissioning Procedure
"""

    filename = f"{adr_number:04d}-remove-{hyphen_name}.md"
    out_path = DOCS_ADR_DIR / filename
    return out_path, content


def validate_catalog_registry(probe_service_id: str) -> list[str]:
    """Check each CATALOG_REGISTRY entry for the probe service and warn on zero matches.

    A zero-match on an entry that *should* have the service is a registry
    misconfiguration (wrong ``id_field``, wrong ``list_key``, etc.) — Amendment 1.

    Returns a list of warning strings. An empty list means the registry is healthy
    for this service.
    """
    warnings: list[str] = []
    variants_set = set(_service_name_variants(probe_service_id))

    for entry in CATALOG_REGISTRY:
        full = repo_path(*entry["path"].split("/"))
        if not full.is_file():
            continue
        kind = entry["type"]
        found = False
        try:
            if kind == "array":
                catalog = load_json(full)
                items = catalog.get(entry["list_key"], [])
                found = isinstance(items, list) and any(
                    isinstance(i, dict) and i.get(entry["id_field"]) == probe_service_id for i in items
                )
            elif kind == "dict_key":
                catalog = load_json(full)
                obj = catalog.get(entry["list_key"], {})
                found = isinstance(obj, dict) and bool(variants_set & set(obj.keys()))
            elif kind == "top_level_key":
                catalog = load_json(full)
                found = isinstance(catalog, dict) and bool(variants_set & set(catalog.keys()))
            elif kind == "dict_key_by_value":
                catalog = load_json(full)
                obj = catalog.get(entry["list_key"], {})
                found = isinstance(obj, dict) and any(
                    isinstance(v, dict) and v.get(entry["id_field"]) == probe_service_id
                    for v in obj.values()
                )
            elif kind in ("workflow_dict", "secrets_dict"):
                catalog = load_json(full)
                obj = catalog.get(entry["list_key"], {})
                found = isinstance(obj, dict) and any(
                    any(v in k for v in variants_set) for k in obj
                )
            elif kind == "dep_graph":
                catalog = load_json(full)
                nodes = catalog.get(entry["nodes_key"], [])
                found = any(isinstance(n, dict) and n.get("id") in variants_set for n in nodes)
            elif kind == "partitions":
                catalog = load_json(full)
                parts = catalog.get("partitions", {})
                found = any(
                    s in variants_set
                    for p in parts.values()
                    if isinstance(p, dict)
                    for s in p.get("services", [])
                )
            elif kind == "yaml_dict_key":
                try:
                    import yaml
                    data = yaml.safe_load(full.read_text()) or {}
                    obj = data.get(entry["list_key"], {})
                    found = isinstance(obj, dict) and any(any(v in str(k) for v in variants_set) for k in obj)
                except Exception:
                    pass
            elif kind == "yaml_topology_block":
                try:
                    import yaml
                    data = yaml.safe_load(full.read_text()) or {}
                    topology = data.get(entry.get("list_key", ""), {})
                    found = isinstance(topology, dict) and bool(variants_set & set(topology.keys()))
                except Exception:
                    pass
            elif kind == "yaml_marker_block":
                content = full.read_text()
                found = any(f"# BEGIN SERVICE: {v}" in content for v in variants_set)
            elif kind == "json_array_flat":
                data = load_json(full)
                found = isinstance(data, list) and any(
                    isinstance(i, dict) and i.get(entry["id_field"]) in variants_set for i in data
                )
            elif kind == "yaml_var_prefix":
                try:
                    import yaml
                    data = yaml.safe_load(full.read_text()) or {}
                    port_map = data.get(entry.get("parent_key", ""), {})
                    found = isinstance(port_map, dict) and any(
                        any(k == v or k.startswith(f"{v}_") for v in variants_set)
                        for k in port_map
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # Only warn on entries we'd expect to have this service (optional catalogs
        # might legitimately be absent for a given service)
        OPTIONAL_CATALOG_TYPES = {
            "dep_graph", "partitions", "yaml_topology_block",
            "yaml_marker_block",  # platform_services.yml — only docker-compose services; VMs are absent
            "json_array_flat",    # monitors.json — not all services have uptime monitors
            "yaml_var_prefix",    # proxmox_florin.yml — not all services have port assignments
        }
        if not found and kind not in OPTIONAL_CATALOG_TYPES:
            warnings.append(
                f"WARN registry: {entry['path']} ({kind}) — zero matches for '{probe_service_id}'. "
                f"Check id_field/list_key in CATALOG_REGISTRY."
            )

    return warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan or execute service decommission — runtime teardown and/or code purge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--service", required=True, help="Service id from config/service-capability-catalog.json.")
    parser.add_argument("--execute", action="store_true", help="Execute runtime teardown (databases, secrets, OIDC).")
    parser.add_argument("--purge-code", action="store_true", help="Execute code purge (delete files, clean catalogs, regenerate).")
    parser.add_argument("--validate-registry", action="store_true", help="Check CATALOG_REGISTRY entries for zero-match misconfigurations before any mutation.")
    parser.add_argument("--generate-adr", action="store_true", help="Generate a templated removal ADR from the dry-run plan (no AI needed).")
    parser.add_argument("--reason", default="The service is no longer needed.", help="Why the service is being removed (used in generated ADR).")
    parser.add_argument("--replacement", default="None.", help="What replaces the service (used in generated ADR).")
    parser.add_argument(
        "--confirm",
        help="Repeat the service id to confirm destructive execution.",
    )
    parser.add_argument("--postgres-admin-dsn", help="Superuser DSN for PostgreSQL cleanup.")
    parser.add_argument("--loki-url", help="Loki base URL with admin deletion enabled.")
    parser.add_argument("--openbao-addr", help="OpenBao base URL.")
    parser.add_argument("--keycloak-url", help="Keycloak admin base URL, for example https://sso.localhost.")
    parser.add_argument("--keycloak-realm", default="lv3", help="Keycloak realm containing the service client.")
    args = parser.parse_args(argv)

    try:
        payload: dict[str, Any] = {"executed": False, "code_purged": False}

        # Registry self-validation (Amendment 1) — runs before any mutation
        if args.validate_registry:
            registry_warnings = validate_catalog_registry(args.service)
            payload["registry_warnings"] = registry_warnings
            if registry_warnings:
                for w in registry_warnings:
                    print(w, file=sys.stderr)
            else:
                print(f"Registry OK — all entries matched '{args.service}'.")

        # Runtime plan (always computed for context)
        try:
            plan = build_plan(args.service)
            payload["plan"] = plan
        except ValueError:
            # Service may already be removed from catalog during code purge
            payload["plan"] = {"service_id": args.service, "note": "not found in service catalog (may already be removed)"}

        # Code purge plan (always computed when requested or for dry-run)
        code_plan = build_code_purge_plan(args.service)
        payload["code_purge_plan"] = code_plan

        # Execute runtime teardown
        if args.execute:
            if args.confirm != args.service:
                raise ValueError("--confirm must exactly match --service when --execute or --purge-code is used")
            payload["results"] = execute_plan(
                payload["plan"],
                postgres_admin_dsn=args.postgres_admin_dsn or os.environ.get(DEFAULT_POSTGRES_ADMIN_DSN_ENV),
                loki_url=args.loki_url,
                openbao_addr=args.openbao_addr or os.environ.get(DEFAULT_OPENBAO_ADDR_ENV),
                openbao_token=os.environ.get(DEFAULT_OPENBAO_TOKEN_ENV),
                keycloak_url=args.keycloak_url,
                keycloak_token=os.environ.get(DEFAULT_KEYCLOAK_TOKEN_ENV),
                keycloak_realm=args.keycloak_realm,
            )
            payload["executed"] = True

        # Execute code purge
        if args.purge_code:
            if args.confirm != args.service:
                raise ValueError("--confirm must exactly match --service when --execute or --purge-code is used")
            payload["code_purge_results"] = execute_code_purge(code_plan)
            payload["code_purged"] = True

        # Generate ADR
        if args.generate_adr:
            runtime_plan = payload.get("plan", {"service_id": args.service})
            adr_path, adr_content = generate_removal_adr(
                args.service,
                code_plan,
                runtime_plan,
                reason=args.reason,
                replacement=args.replacement,
            )
            adr_path.write_text(adr_content)
            payload["generated_adr"] = str(adr_path.relative_to(repo_path()))

    except (OSError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Service decommission", exc)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
