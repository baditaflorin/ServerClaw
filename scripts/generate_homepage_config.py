#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from controller_automation_toolkit import load_json, load_yaml, repo_path


SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
STACK_PATH = repo_path("versions", "stack.yaml")

CATEGORY_LABELS = {
    "access": "Access & Identity",
    "automation": "Automation & AI",
    "communication": "Communication",
    "data": "Data",
    "infrastructure": "Infrastructure",
    "observability": "Observability",
    "security": "Security",
}

SERVICE_ICONS = {
    "alertmanager": "si-prometheus",
    "api_gateway": "mdi-api",
    "backup_pbs": "mdi-backup-restore",
    "docker_build": "mdi-hammer-wrench",
    "docker_runtime": "mdi-docker",
    "docs_portal": "mdi-file-document-multiple",
    "grafana": "si-grafana",
    "homepage": "mdi-view-dashboard",
    "keycloak": "si-keycloak",
    "mail_platform": "mdi-email-fast",
    "mattermost": "si-mattermost",
    "netbox": "si-netbox",
    "nginx_edge": "si-nginx",
    "ntfy": "mdi-bell-badge",
    "ntopng": "mdi-chart-areaspline",
    "ollama": "mdi-head-snowflake-outline",
    "openbao": "mdi-vault",
    "ops_portal": "mdi-console-network",
    "platform_context_api": "mdi-database-search",
    "portainer": "si-portainer",
    "postgres": "si-postgresql",
    "proxmox_ui": "si-proxmox",
    "status_page": "mdi-list-status",
    "step_ca": "mdi-certificate-outline",
    "uptime_kuma": "si-uptimekuma",
    "windmill": "si-windmill",
}

BOOKMARK_GROUPS = [
    {
        "Quick Actions": [
            {"name": "Ops Portal", "abbr": "OP", "href": "https://ops.localhost"},
            {"name": "Grafana", "abbr": "GR", "href": "https://grafana.localhost"},
            {"name": "Status", "abbr": "ST", "href": "https://status.localhost"},
            {"name": "Docs", "abbr": "DO", "href": "https://docs.localhost"},
        ]
    },
    {
        "Control Plane": [
            {"name": "Proxmox", "abbr": "PV", "href": "https://proxmox.localhost"},
            {"name": "Windmill", "abbr": "WM", "href": "http://100.118.189.95:8005"},
            {"name": "NetBox", "abbr": "NB", "href": "http://100.118.189.95:8004"},
            {"name": "Portainer", "abbr": "PT", "href": "https://100.118.189.95:9444"},
        ]
    },
]


def yaml_dump(payload: Any) -> str:
    class IndentedSafeDumper(yaml.SafeDumper):
        def increase_indent(self, flow: bool = False, indentless: bool = False):
            return super().increase_indent(flow, False)

    return yaml.dump(payload, Dumper=IndentedSafeDumper, sort_keys=False)


def load_service_catalog() -> dict[str, Any]:
    payload = load_json(SERVICE_CATALOG_PATH)
    services = payload.get("services")
    if not isinstance(services, list):
        raise ValueError(f"{SERVICE_CATALOG_PATH} must define a services list")
    return payload


def load_subdomain_catalog() -> dict[str, Any]:
    payload = load_json(SUBDOMAIN_CATALOG_PATH)
    subdomains = payload.get("subdomains")
    if not isinstance(subdomains, list):
        raise ValueError(f"{SUBDOMAIN_CATALOG_PATH} must define a subdomains list")
    return payload


def load_stack() -> dict[str, Any]:
    payload = load_yaml(STACK_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{STACK_PATH} must define a mapping")
    return payload


def build_subdomain_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in payload["subdomains"]:
        if isinstance(entry, dict) and isinstance(entry.get("service_id"), str):
            index[entry["service_id"]] = entry
    return index


def candidate_service_url(service: dict[str, Any]) -> str:
    for key in ("public_url", "internal_url"):
        value = service.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    raise ValueError(f"service {service.get('id', '<unknown>')} does not define a browser-usable URL")


def candidate_site_monitor(service: dict[str, Any], subdomain_entry: dict[str, Any] | None) -> str | None:
    internal_url = service.get("internal_url")
    if isinstance(internal_url, str) and internal_url.startswith(("http://", "https://")):
        return internal_url
    if subdomain_entry and subdomain_entry.get("status") == "active":
        public_url = service.get("public_url")
        if isinstance(public_url, str) and public_url.startswith(("http://", "https://")):
            return public_url
    return None


def include_service(service: dict[str, Any]) -> bool:
    if service.get("lifecycle_status") != "active":
        return False
    try:
        candidate_service_url(service)
    except ValueError:
        return False
    return True


def build_service_tile(service: dict[str, Any], subdomain_entry: dict[str, Any] | None) -> dict[str, Any]:
    tile: dict[str, Any] = {
        "href": candidate_service_url(service),
        "description": service["description"],
        "icon": SERVICE_ICONS.get(service["id"], "mdi-application-outline"),
    }
    site_monitor = candidate_site_monitor(service, subdomain_entry)
    if site_monitor:
        tile["siteMonitor"] = site_monitor
        tile["statusStyle"] = "dot"
    return {service["name"]: tile}


def build_services_payload() -> list[dict[str, list[dict[str, Any]]]]:
    catalog = load_service_catalog()
    subdomain_index = build_subdomain_index(load_subdomain_catalog())
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for service in sorted(catalog["services"], key=lambda item: (item["category"], item["name"])):
        if not include_service(service):
            continue
        label = CATEGORY_LABELS.get(service["category"], service["category"].title())
        grouped[label].append(build_service_tile(service, subdomain_index.get(service["id"])))

    payload: list[dict[str, list[dict[str, Any]]]] = []
    for category in CATEGORY_LABELS.values():
        items = grouped.get(category)
        if items:
            payload.append({category: items})
    return payload


def build_bookmarks_payload() -> list[dict[str, list[dict[str, str]]]]:
    payload: list[dict[str, list[dict[str, str]]]] = []
    for group in BOOKMARK_GROUPS:
        group_name, bookmarks = next(iter(group.items()))
        payload.append(
            {
                group_name: [
                    {
                        bookmark["name"]: [
                            {
                                "abbr": bookmark["abbr"],
                                "href": bookmark["href"],
                            }
                        ]
                    }
                    for bookmark in bookmarks
                ]
            }
        )
    return payload


def build_widgets_payload() -> list[dict[str, Any]]:
    return [
        {
            "search": {
                "provider": "duckduckgo",
                "target": "_blank",
                "focus": False,
            }
        },
        {
            "datetime": {
                "text_size": "xl",
                "format": {
                    "dateStyle": "medium",
                    "timeStyle": "short",
                },
            }
        },
    ]


def build_settings_payload() -> dict[str, Any]:
    stack = load_stack()
    return {
        "title": "LV3 Unified Dashboard",
        "description": (
            f"Platform service dashboard generated from repo version {stack['repo_version']} "
            f"and platform version {stack['platform_version']}."
        ),
        "theme": "light",
        "color": "slate",
        "headerStyle": "boxed",
        "statusStyle": "dot",
        "hideVersion": True,
        "disableUpdateCheck": True,
        "disableIndexing": True,
        "useEqualHeights": True,
        "quicklaunch": {
            "searchDescriptions": True,
            "provider": "duckduckgo",
        },
        "layout": {
            "Access & Identity": {"style": "row", "columns": 3},
            "Automation & AI": {"style": "row", "columns": 3},
            "Observability": {"style": "row", "columns": 3},
            "Infrastructure": {"style": "row", "columns": 3},
            "Data": {"style": "row", "columns": 2},
            "Security": {"style": "row", "columns": 2},
            "Communication": {"style": "row", "columns": 2},
            "Quick Actions": {"style": "row", "columns": 4, "header": False},
            "Control Plane": {"style": "row", "columns": 4, "header": False},
        },
    }


def build_custom_css() -> str:
    return (
        ":root {\n"
        "  --card-radius: 1rem;\n"
        "}\n\n"
        ".service-card, .bookmark-card {\n"
        "  border-radius: var(--card-radius);\n"
        "  box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);\n"
        "}\n\n"
        ".information-widget {\n"
        "  border-radius: var(--card-radius);\n"
        "}\n\n"
        "/* ADR 0395: ensure all text is selectable for operator copy-paste */\n"
        "*, *::before, *::after {\n"
        "  -webkit-user-select: text !important;\n"
        "  user-select: text !important;\n"
        "}\n\n"
        "a, button, input, [role=\"button\"] {\n"
        "  cursor: pointer;\n"
        "}\n"
    )


def render_outputs() -> dict[str, str]:
    return {
        "services.yaml": yaml_dump(build_services_payload()),
        "bookmarks.yaml": yaml_dump(build_bookmarks_payload()),
        "widgets.yaml": yaml_dump(build_widgets_payload()),
        "settings.yaml": yaml_dump(build_settings_payload()),
        "custom.css": build_custom_css(),
    }


def write_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in render_outputs().items():
        (output_dir / name).write_text(content, encoding="utf-8")


def outputs_match(output_dir: Path) -> bool:
    expected = render_outputs()
    return all((output_dir / name).exists() and (output_dir / name).read_text(encoding="utf-8") == content for name, content in expected.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Homepage configuration from the canonical LV3 service catalogs.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory where Homepage config files will be written or checked.")
    parser.add_argument("--write", action="store_true", help="Write generated files to the output directory.")
    parser.add_argument("--check", action="store_true", help="Fail if generated files differ from the current output directory.")
    args = parser.parse_args(argv)

    if not args.write and not args.check:
        parser.error("one of --write or --check is required")

    try:
        if args.write:
            write_outputs(args.output_dir)
            return 0
        if outputs_match(args.output_dir):
            return 0
        print(f"{args.output_dir} is stale; run scripts/generate_homepage_config.py --output-dir {args.output_dir} --write")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
