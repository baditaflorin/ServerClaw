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


# ============================================================================
# Phase 2: Code Purge — deterministic file removal and catalog rewriting
# ============================================================================

def _service_name_variants(service_id: str) -> list[str]:
    """Return all naming variants for grep patterns."""
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
    hyphen = service_id.replace("_", "-")

    # Ansible roles: <service>_runtime, <service>_postgres
    for suffix in ("_runtime", "_postgres"):
        role_dir = ROLES_ROOT / f"{underscore}{suffix}"
        if role_dir.is_dir():
            dirs.append(role_dir)

    return dirs


def _discover_deletable_files(service_id: str) -> list[Path]:
    """Find individual files to delete entirely."""
    files: list[Path] = []
    underscore = service_id
    hyphen = service_id.replace("_", "-")

    # Collection playbook
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = COLLECTION_PLAYBOOKS / name
        if candidate.is_file():
            files.append(candidate)

    # Collection services playbook
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = COLLECTION_PLAYBOOKS / "services" / name
        if candidate.is_file():
            files.append(candidate)

    # Root playbooks
    for name in (f"{hyphen}.yml", f"{underscore}.yml"):
        candidate = ROOT_PLAYBOOKS / name
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

    # Tests
    for pattern in (f"test_{underscore}_*.py", f"test_{hyphen}_*.py"):
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


def _deprecate_adrs(service_id: str) -> list[str]:
    """Find ADRs mentioning the service and mark them Deprecated."""
    if not DOCS_ADR_DIR.is_dir():
        return []
    deprecated: list[str] = []
    variants = _service_name_variants(service_id)
    for adr_file in sorted(DOCS_ADR_DIR.glob("*.md")):
        content = adr_file.read_text()
        # Only deprecate ADRs that are primarily about this service (in the title)
        first_line = content.split("\n", 1)[0].lower()
        if not any(v.replace("_", " ") in first_line or v in first_line for v in variants):
            continue
        if "**Status:** Deprecated" in content:
            continue
        content = re.sub(
            r"\*\*Status:\*\*\s*\w+",
            "**Status:** Deprecated",
            content,
            count=1,
        )
        if "Deprecated by ADR 0390" not in content:
            content = content.replace(
                "**Status:** Deprecated",
                "**Status:** Deprecated (see ADR 0390 — service removed from platform)",
            )
        adr_file.write_text(content)
        deprecated.append(adr_file.name)
    return deprecated


def _remove_from_stack_yaml(service_id: str) -> bool:
    """Remove the service receipt from versions/stack.yaml."""
    stack_path = VERSIONS_DIR / "stack.yaml"
    return _remove_line_references(stack_path, service_id)


def build_code_purge_plan(service_id: str) -> dict[str, Any]:
    """Build a plan showing exactly what code purge would do."""
    deletable_dirs = _discover_deletable_dirs(service_id)
    deletable_files = _discover_deletable_files(service_id)
    variants = _service_name_variants(service_id)

    # JSON catalogs to clean
    json_catalogs: list[dict[str, str]] = []
    catalog_specs = [
        ("config/service-capability-catalog.json", "services", "id"),
        ("config/subdomain-catalog.json", "subdomains", "service"),
        ("config/service-redundancy-catalog.json", "groups", "id"),
        ("config/service-completeness.json", "services", "id"),
    ]
    for rel_path, list_key, id_key in catalog_specs:
        full = repo_path(*rel_path.split("/"))
        if full.is_file():
            catalog = load_json(full)
            if isinstance(catalog, dict) and list_key in catalog:
                items = catalog[list_key]
                if isinstance(items, list) and any(
                    isinstance(i, dict) and i.get(id_key) == service_id for i in items
                ):
                    json_catalogs.append({"path": rel_path, "list_key": list_key, "id_key": id_key})

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
        "adr_deprecation": "will scan docs/adr/ for service-specific ADRs",
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
        "adrs_deprecated": [],
        "stack_yaml_cleaned": False,
        "regeneration_commands": [],
    }
    service_id = plan["service_id"]

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

    # 3. Clean JSON catalogs
    for spec in plan["json_catalogs_to_clean"]:
        full = repo_path(*spec["path"].split("/"))
        if _remove_from_json_catalog(full, service_id, spec["list_key"], spec["id_key"]):
            results["catalogs_cleaned"].append(spec["path"])

    # 4. Remove line-level references from remaining files
    for rel_file in plan["files_with_references"]:
        full = repo_path() / rel_file
        if _remove_line_references(full, service_id):
            results["reference_files_cleaned"].append(rel_file)

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan or execute service decommission — runtime teardown and/or code purge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--service", required=True, help="Service id from config/service-capability-catalog.json.")
    parser.add_argument("--execute", action="store_true", help="Execute runtime teardown (databases, secrets, OIDC).")
    parser.add_argument("--purge-code", action="store_true", help="Execute code purge (delete files, clean catalogs, regenerate).")
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
