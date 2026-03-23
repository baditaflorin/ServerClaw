#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.environ.get("LV3_REPO_ROOT", Path(__file__).resolve().parent.parent))
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
HEALTH_PROBE_CATALOG_PATH = REPO_ROOT / "config" / "health-probe-catalog.json"
SUBDOMAIN_CATALOG_PATH = REPO_ROOT / "config" / "subdomain-catalog.json"
SECRET_CATALOG_PATH = REPO_ROOT / "config" / "secret-catalog.json"
API_GATEWAY_CATALOG_PATH = REPO_ROOT / "config" / "api-gateway-catalog.json"
DEPENDENCY_GRAPH_PATH = REPO_ROOT / "config" / "dependency-graph.json"
SLO_CATALOG_PATH = REPO_ROOT / "config" / "slo-catalog.json"
DATA_CATALOG_PATH = REPO_ROOT / "config" / "data-catalog.json"
SERVICE_COMPLETENESS_PATH = REPO_ROOT / "config" / "service-completeness.json"

CHECKLIST = [
    ("adr", "ADR"),
    ("ansible_role", "Ansible role"),
    ("service_catalog", "Service capability catalog"),
    ("health_probe", "Health probe definition"),
    ("subdomain", "Subdomain entry"),
    ("api_gateway", "API gateway registration"),
    ("dependency_graph", "Dependency graph node"),
    ("keycloak_client", "Keycloak client scaffold"),
    ("secret_definition", "Secret definition"),
    ("grafana_dashboard", "Grafana dashboard"),
    ("slo_definition", "SLO definition"),
    ("compose_secrets", "Compose secrets injection"),
    ("data_catalog", "Data catalog entry"),
    ("alert_rules", "Alert rules"),
    ("runbook", "Runbook"),
]
CHECKLIST_IDS = [item_id for item_id, _label in CHECKLIST]


@dataclass(frozen=True)
class ItemResult:
    item_id: str
    label: str
    required: bool
    present: bool
    grandfathered_until: str | None
    detail: str

    @property
    def passing(self) -> bool:
        return (not self.required) or self.present or self.grandfathered_until is not None


@dataclass(frozen=True)
class ServiceResult:
    service_id: str
    items: list[ItemResult]

    @property
    def failing_items(self) -> list[ItemResult]:
        return [item for item in self.items if item.required and not item.present and item.grandfathered_until is None]

    @property
    def passing(self) -> bool:
        return not self.failing_items


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_date(value: Any, path: str) -> str:
    value = require_string(value, path)
    dt.date.fromisoformat(value)
    return value


def slugify_service_id(service_id: str) -> str:
    return service_id.replace("_", "-")


def load_context() -> dict[str, Any]:
    service_catalog = require_mapping(load_json(SERVICE_CATALOG_PATH), str(SERVICE_CATALOG_PATH))
    services = require_list(service_catalog.get("services"), "config/service-capability-catalog.json.services")
    service_map = {
        require_string(service.get("id"), f"config/service-capability-catalog.json.services[{index}].id"): require_mapping(
            service,
            f"config/service-capability-catalog.json.services[{index}]",
        )
        for index, service in enumerate(services)
    }

    completeness = require_mapping(load_json(SERVICE_COMPLETENESS_PATH), str(SERVICE_COMPLETENESS_PATH))
    service_profiles = require_mapping(completeness.get("services"), "config/service-completeness.json.services")
    suppression_presets = require_mapping(
        completeness.get("suppression_presets"),
        "config/service-completeness.json.suppression_presets",
    )

    if set(service_profiles) != set(service_map):
        missing = sorted(set(service_map) - set(service_profiles))
        extra = sorted(set(service_profiles) - set(service_map))
        problems = []
        if missing:
            problems.append(f"missing profiles for {', '.join(missing)}")
        if extra:
            problems.append(f"unexpected profiles for {', '.join(extra)}")
        raise ValueError("config/service-completeness.json.services must match the service catalog: " + "; ".join(problems))

    for preset_name, preset in suppression_presets.items():
        preset = require_mapping(preset, f"config/service-completeness.json.suppression_presets.{preset_name}")
        for item_id, value in preset.items():
            if item_id not in CHECKLIST_IDS:
                raise ValueError(
                    f"config/service-completeness.json.suppression_presets.{preset_name}.{item_id} is not a known checklist id"
                )
            require_date(value, f"config/service-completeness.json.suppression_presets.{preset_name}.{item_id}")

    for service_id, profile in service_profiles.items():
        profile = require_mapping(profile, f"config/service-completeness.json.services.{service_id}")
        require_string(profile.get("service_type"), f"config/service-completeness.json.services.{service_id}.service_type")
        require_bool(profile.get("requires_subdomain"), f"config/service-completeness.json.services.{service_id}.requires_subdomain")
        require_bool(profile.get("requires_oidc"), f"config/service-completeness.json.services.{service_id}.requires_oidc")
        require_bool(profile.get("requires_secrets"), f"config/service-completeness.json.services.{service_id}.requires_secrets")
        require_bool(
            profile.get("requires_compose_secrets"),
            f"config/service-completeness.json.services.{service_id}.requires_compose_secrets",
        )
        if "suppression_preset" in profile:
            preset_name = require_string(
                profile.get("suppression_preset"),
                f"config/service-completeness.json.services.{service_id}.suppression_preset",
            )
            if preset_name not in suppression_presets:
                raise ValueError(
                    f"config/service-completeness.json.services.{service_id}.suppression_preset references unknown preset '{preset_name}'"
                )
        suppressed_checks = profile.get("suppressed_checks", {})
        suppressed_checks = require_mapping(
            suppressed_checks,
            f"config/service-completeness.json.services.{service_id}.suppressed_checks",
        )
        for item_id, value in suppressed_checks.items():
            if item_id not in CHECKLIST_IDS:
                raise ValueError(
                    f"config/service-completeness.json.services.{service_id}.suppressed_checks.{item_id} is not a known checklist id"
                )
            require_date(
                value,
                f"config/service-completeness.json.services.{service_id}.suppressed_checks.{item_id}",
            )
        if "dashboard_file" in profile:
            require_string(profile.get("dashboard_file"), f"config/service-completeness.json.services.{service_id}.dashboard_file")
        if "alert_rule_file" in profile:
            require_string(profile.get("alert_rule_file"), f"config/service-completeness.json.services.{service_id}.alert_rule_file")
        if "keycloak_client_generated" in profile:
            require_bool(
                profile.get("keycloak_client_generated"),
                f"config/service-completeness.json.services.{service_id}.keycloak_client_generated",
            )

    health_probe_catalog = require_mapping(load_json(HEALTH_PROBE_CATALOG_PATH), str(HEALTH_PROBE_CATALOG_PATH))
    health_services = require_mapping(health_probe_catalog.get("services"), "config/health-probe-catalog.json.services")

    subdomain_catalog = require_mapping(load_json(SUBDOMAIN_CATALOG_PATH), str(SUBDOMAIN_CATALOG_PATH))
    require_list(subdomain_catalog.get("subdomains"), "config/subdomain-catalog.json.subdomains")

    secret_catalog = require_mapping(load_json(SECRET_CATALOG_PATH), str(SECRET_CATALOG_PATH))
    require_list(secret_catalog.get("secrets"), "config/secret-catalog.json.secrets")

    api_gateway_catalog = require_mapping(load_json(API_GATEWAY_CATALOG_PATH), str(API_GATEWAY_CATALOG_PATH))
    gateway_services = require_list(api_gateway_catalog.get("services"), "config/api-gateway-catalog.json.services")
    seen_gateway_services: set[str] = set()
    for index, entry in enumerate(gateway_services):
        entry = require_mapping(entry, f"config/api-gateway-catalog.json.services[{index}]")
        service_id = require_string(entry.get("service_id"), f"config/api-gateway-catalog.json.services[{index}].service_id")
        if service_id in seen_gateway_services:
            raise ValueError(f"duplicate API gateway service entry for {service_id}")
        seen_gateway_services.add(service_id)
        require_string(entry.get("gateway_prefix"), f"config/api-gateway-catalog.json.services[{index}].gateway_prefix")
        require_string(entry.get("upstream"), f"config/api-gateway-catalog.json.services[{index}].upstream")
        require_string(entry.get("auth"), f"config/api-gateway-catalog.json.services[{index}].auth")
        timeout_seconds = entry.get("timeout_seconds")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1:
            raise ValueError(f"config/api-gateway-catalog.json.services[{index}].timeout_seconds must be >= 1")
        require_bool(entry.get("strip_prefix"), f"config/api-gateway-catalog.json.services[{index}].strip_prefix")

    dependency_graph = require_mapping(load_json(DEPENDENCY_GRAPH_PATH), str(DEPENDENCY_GRAPH_PATH))
    nodes = require_list(dependency_graph.get("nodes"), "config/dependency-graph.json.nodes")
    edges = require_list(dependency_graph.get("edges"), "config/dependency-graph.json.edges")
    seen_nodes: set[str] = set()
    for index, node in enumerate(nodes):
        node = require_mapping(node, f"config/dependency-graph.json.nodes[{index}]")
        node_id = require_string(node.get("id"), f"config/dependency-graph.json.nodes[{index}].id")
        if node_id in seen_nodes:
            raise ValueError(f"duplicate dependency graph node '{node_id}'")
        seen_nodes.add(node_id)
        require_string(node.get("service"), f"config/dependency-graph.json.nodes[{index}].service")
        require_string(node.get("vm"), f"config/dependency-graph.json.nodes[{index}].vm")
        tier = node.get("tier")
        if isinstance(tier, bool) or not isinstance(tier, int) or tier < 0:
            raise ValueError(f"config/dependency-graph.json.nodes[{index}].tier must be >= 0")
    for index, edge in enumerate(edges):
        edge = require_mapping(edge, f"config/dependency-graph.json.edges[{index}]")
        require_string(edge.get("from"), f"config/dependency-graph.json.edges[{index}].from")
        require_string(edge.get("to"), f"config/dependency-graph.json.edges[{index}].to")
        require_string(edge.get("type"), f"config/dependency-graph.json.edges[{index}].type")
        require_string(edge.get("description"), f"config/dependency-graph.json.edges[{index}].description")

    slo_catalog = require_mapping(load_json(SLO_CATALOG_PATH), str(SLO_CATALOG_PATH))
    slos = require_list(slo_catalog.get("slos"), "config/slo-catalog.json.slos")
    seen_slo_ids: set[str] = set()
    for index, slo in enumerate(slos):
        slo = require_mapping(slo, f"config/slo-catalog.json.slos[{index}]")
        slo_id = require_string(slo.get("id"), f"config/slo-catalog.json.slos[{index}].id")
        if slo_id in seen_slo_ids:
            raise ValueError(f"duplicate SLO id '{slo_id}'")
        seen_slo_ids.add(slo_id)
        require_string(slo.get("service"), f"config/slo-catalog.json.slos[{index}].service")

    data_catalog = require_mapping(load_json(DATA_CATALOG_PATH), str(DATA_CATALOG_PATH))
    data_stores = require_list(data_catalog.get("data_stores"), "config/data-catalog.json.data_stores")
    seen_data_ids: set[str] = set()
    for index, store in enumerate(data_stores):
        store = require_mapping(store, f"config/data-catalog.json.data_stores[{index}]")
        store_id = require_string(store.get("id"), f"config/data-catalog.json.data_stores[{index}].id")
        if store_id in seen_data_ids:
            raise ValueError(f"duplicate data catalog id '{store_id}'")
        seen_data_ids.add(store_id)
        require_string(store.get("service"), f"config/data-catalog.json.data_stores[{index}].service")

    return {
        "service_map": service_map,
        "profiles": service_profiles,
        "suppression_presets": suppression_presets,
        "health_services": health_services,
        "subdomains": subdomain_catalog["subdomains"],
        "secret_entries": secret_catalog["secrets"],
        "api_gateway_services": gateway_services,
        "dependency_nodes": nodes,
        "slos": slos,
        "data_stores": data_stores,
    }


def merged_suppressions(profile: dict[str, Any], presets: dict[str, Any]) -> dict[str, str]:
    suppressions: dict[str, str] = {}
    preset_name = profile.get("suppression_preset")
    if isinstance(preset_name, str) and preset_name:
        suppressions.update(presets[preset_name])
    suppressed_checks = profile.get("suppressed_checks", {})
    if isinstance(suppressed_checks, dict):
        suppressions.update({str(key): str(value) for key, value in suppressed_checks.items()})
    return suppressions


def suppression_for(item_id: str, suppressions: dict[str, str], today: dt.date) -> str | None:
    value = suppressions.get(item_id)
    if value is None:
        return None
    suppressed_until = dt.date.fromisoformat(value)
    if suppressed_until < today:
        return None
    return suppressed_until.isoformat()


def find_adr_path(adr_id: str) -> Path | None:
    matches = sorted((REPO_ROOT / "docs" / "adr").glob(f"{adr_id}-*.md"))
    return matches[0] if matches else None


def role_dir_for(service_id: str, context: dict[str, Any], profile: dict[str, Any]) -> Path | None:
    probe_entry = context["health_services"].get(service_id)
    if isinstance(probe_entry, dict):
        role_name = probe_entry.get("role")
        if isinstance(role_name, str) and role_name.strip():
            return REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / role_name
    if profile.get("service_type") == "compose":
        return (
            REPO_ROOT
            / "collections"
            / "ansible_collections"
            / "lv3"
            / "platform"
            / "roles"
            / f"{service_id}_runtime"
        )
    return None


def item_result(
    item_id: str,
    label: str,
    *,
    required: bool,
    present: bool,
    detail: str,
    suppressions: dict[str, str],
    today: dt.date,
) -> ItemResult:
    return ItemResult(
        item_id=item_id,
        label=label,
        required=required,
        present=present,
        grandfathered_until=None if present or not required else suppression_for(item_id, suppressions, today),
        detail=detail,
    )


def evaluate_service(service_id: str, *, today: dt.date | None = None, context: dict[str, Any] | None = None) -> ServiceResult:
    context = context or load_context()
    today = today or dt.date.today()
    service = context["service_map"].get(service_id)
    if service is None:
        raise ValueError(f"unknown service '{service_id}'")
    profile = context["profiles"][service_id]
    suppressions = merged_suppressions(profile, context["suppression_presets"])
    role_dir = role_dir_for(service_id, context, profile)
    role_compose_path = None if role_dir is None else role_dir / "templates" / "docker-compose.yml.j2"
    slug = slugify_service_id(service_id)
    dashboard_path = REPO_ROOT / profile.get("dashboard_file", f"config/grafana/dashboards/{slug}.json")
    alert_rule_path = REPO_ROOT / profile.get("alert_rule_file", f"config/alertmanager/rules/{slug}.yml")
    adr_id = require_string(service.get("adr"), f"service {service_id}.adr")
    adr_path = find_adr_path(adr_id)
    service_secret_ids = {
        require_string(secret_id, "service.secret_catalog_ids[]")
        for secret_id in service.get("secret_catalog_ids", [])
        if isinstance(secret_id, str)
    }
    secret_entries = [secret for secret in context["secret_entries"] if secret.get("owner_service") == service_id]
    subdomain_entries = [entry for entry in context["subdomains"] if entry.get("service_id") == service_id]
    api_gateway_entries = [entry for entry in context["api_gateway_services"] if entry.get("service_id") == service_id]
    dependency_nodes = [node for node in context["dependency_nodes"] if node.get("id") == service_id]
    slo_entries = [entry for entry in context["slos"] if entry.get("service") == service_id]
    data_entries = [entry for entry in context["data_stores"] if entry.get("service") == service_id]

    compose_secrets_present = False
    if role_compose_path is not None and role_compose_path.exists():
        compose_template = role_compose_path.read_text(encoding="utf-8")
        compose_secrets_present = "openbao-agent" in compose_template and "env_file:" in compose_template

    items = [
        item_result(
            "adr",
            "ADR",
            required=True,
            present=adr_path is not None,
            detail=str(adr_path.relative_to(REPO_ROOT)) if adr_path else f"missing docs/adr/{adr_id}-*.md",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "ansible_role",
            "Ansible role",
            required=True,
            present=role_dir is not None and role_dir.is_dir(),
            detail=str(role_dir.relative_to(REPO_ROOT)) if role_dir and role_dir.is_dir() else "missing role directory",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "service_catalog",
            "Service capability catalog",
            required=True,
            present=True,
            detail="config/service-capability-catalog.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "health_probe",
            "Health probe definition",
            required=True,
            present=service_id in context["health_services"],
            detail="config/health-probe-catalog.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "subdomain",
            "Subdomain entry",
            required=bool(profile["requires_subdomain"]),
            present=bool(subdomain_entries),
            detail="config/subdomain-catalog.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "api_gateway",
            "API gateway registration",
            required=True,
            present=bool(api_gateway_entries),
            detail="config/api-gateway-catalog.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "dependency_graph",
            "Dependency graph node",
            required=True,
            present=bool(dependency_nodes),
            detail="config/dependency-graph.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "keycloak_client",
            "Keycloak client scaffold",
            required=bool(profile["requires_oidc"]),
            present=bool(profile.get("keycloak_client_generated", False)),
            detail="config/service-completeness.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "secret_definition",
            "Secret definition",
            required=bool(profile["requires_secrets"]),
            present=bool(secret_entries) or bool(service_secret_ids),
            detail="config/secret-catalog.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "grafana_dashboard",
            "Grafana dashboard",
            required=True,
            present=dashboard_path.exists(),
            detail=str(dashboard_path.relative_to(REPO_ROOT)),
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "slo_definition",
            "SLO definition",
            required=True,
            present=bool(slo_entries),
            detail="config/slo-catalog.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "compose_secrets",
            "Compose secrets injection",
            required=bool(profile["requires_compose_secrets"]),
            present=compose_secrets_present,
            detail=str(role_compose_path.relative_to(REPO_ROOT)) if role_compose_path else "not a compose service",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "data_catalog",
            "Data catalog entry",
            required=True,
            present=bool(data_entries),
            detail="config/data-catalog.json",
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "alert_rules",
            "Alert rules",
            required=True,
            present=alert_rule_path.exists(),
            detail=str(alert_rule_path.relative_to(REPO_ROOT)),
            suppressions=suppressions,
            today=today,
        ),
        item_result(
            "runbook",
            "Runbook",
            required=True,
            present=isinstance(service.get("runbook"), str) and (REPO_ROOT / service["runbook"]).exists(),
            detail=str(service.get("runbook", "missing runbook path")),
            suppressions=suppressions,
            today=today,
        ),
    ]
    return ServiceResult(service_id=service_id, items=items)


def format_service_result(result: ServiceResult) -> str:
    lines = [f"Service completeness: {result.service_id}", f"Status: {'PASS' if result.passing else 'FAIL'}"]
    for item in result.items:
        if not item.required:
            state = "n/a"
        elif item.present:
            state = "ok"
        elif item.grandfathered_until is not None:
            state = f"grandfathered until {item.grandfathered_until}"
        else:
            state = "missing"
        lines.append(f"- {item.label}: {state} ({item.detail})")
    return "\n".join(lines)


def validate_services(service_ids: list[str] | None = None, *, today: dt.date | None = None) -> tuple[list[ServiceResult], list[str]]:
    context = load_context()
    today = today or dt.date.today()
    requested = service_ids or sorted(context["service_map"])
    results = [evaluate_service(service_id, today=today, context=context) for service_id in requested]
    failures: list[str] = []
    for result in results:
        for item in result.failing_items:
            failures.append(f"{result.service_id}: missing {item.label.lower()} ({item.detail})")
    return results, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate service completeness against the ADR 0107 checklist.")
    parser.add_argument("--service", action="append", help="Validate one specific service id. May be repeated.")
    parser.add_argument("--validate", action="store_true", help="Run repository-wide completeness validation.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text.")
    args = parser.parse_args(argv or sys.argv[1:])

    try:
        results, failures = validate_services(args.service)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "services": [
                {
                    "service_id": result.service_id,
                    "passing": result.passing,
                    "items": [
                        {
                            "id": item.item_id,
                            "label": item.label,
                            "required": item.required,
                            "present": item.present,
                            "grandfathered_until": item.grandfathered_until,
                            "detail": item.detail,
                        }
                        for item in result.items
                    ],
                }
                for result in results
            ]
        }
        print(json.dumps(payload, indent=2))
    else:
        print("\n\n".join(format_service_result(result) for result in results))
        if args.validate and failures:
            print()
            print("Blocking failures:")
            for failure in failures:
                print(f"- {failure}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
