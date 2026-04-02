from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


UTC = timezone.utc

try:
    from workbench_information_architecture import (
        DEFAULT_PERSONAS_BY_TASK_LANE,
        TASK_LANE_IDS,
        TASK_LANE_LABELS,
        TASK_LANE_ORDER,
        TASK_LANE_QUESTIONS,
        default_personas_for_task_lane,
        normalize_task_lane,
        normalize_task_lane_list,
    )
except ImportError:  # pragma: no cover - repo checkout import path
    from scripts.workbench_information_architecture import (
        DEFAULT_PERSONAS_BY_TASK_LANE,
        TASK_LANE_IDS,
        TASK_LANE_LABELS,
        TASK_LANE_ORDER,
        TASK_LANE_QUESTIONS,
        default_personas_for_task_lane,
        normalize_task_lane,
        normalize_task_lane_list,
    )

try:
    from publication_contract import registry_entries
except ImportError:  # pragma: no cover - repo checkout import path
    from scripts.publication_contract import registry_entries

try:
    from search_fabric.collectors import available_collections
except ImportError:  # pragma: no cover - repo checkout import path
    from scripts.search_fabric.collectors import available_collections

try:
    from .runtime_assurance import build_runtime_assurance_models
except ImportError:  # pragma: no cover - direct module or repo checkout import path
    try:
        from runtime_assurance import build_runtime_assurance_models
    except ImportError:  # pragma: no cover - repo checkout import path
        from scripts.ops_portal.runtime_assurance import build_runtime_assurance_models

try:
    from .contextual_help import build_ops_portal_help
except ImportError:  # pragma: no cover - direct module or repo checkout import path
    try:
        from contextual_help import build_ops_portal_help
    except ImportError:  # pragma: no cover - repo checkout import path
        from scripts.ops_portal.contextual_help import build_ops_portal_help


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def humanize_timestamp(value: str | None) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return "Not recorded"
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or is_macos_metadata_file(path):
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def is_macos_metadata_file(path: Path) -> bool:
    return path.name == ".DS_Store" or path.name.startswith("._")


def load_optional_json_document(path: Path) -> Any | None:
    if is_macos_metadata_file(path):
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


TONE_META = {
    "ok": {"label": "Healthy", "color": "#2a6f4f"},
    "warn": {"label": "Needs attention", "color": "#b26a00"},
    "danger": {"label": "Critical", "color": "#a3302c"},
    "neutral": {"label": "Unknown", "color": "#314467"},
}

EDGE_META = {
    "hard": {"color": "#14213d", "line_type": "solid", "width": 2.6},
    "startup_only": {"color": "#d97706", "line_type": "dashed", "width": 2.1},
    "soft": {"color": "#7d8597", "line_type": "dotted", "width": 1.6},
}
DEFAULT_PERSONA_CATALOG = {
    "personas": [
        {
            "id": "operator",
            "name": "Operator",
            "description": "Day-to-day runtime operations and service switching.",
            "default": True,
            "focus_lanes": ["start", "observe", "change"],
            "default_favorites": [
                "service:ops_portal",
                "service:homepage",
                "service:grafana",
                "service:docs_portal",
                "workflow:gate-status",
            ],
        },
        {
            "id": "observer",
            "name": "Observer",
            "description": "Monitoring, drift, assurance, and incident triage.",
            "default": False,
            "focus_lanes": ["observe", "recover", "change"],
            "default_favorites": [
                "service:grafana",
                "service:realtime",
                "service:dozzle",
                "service:status_page",
                "workflow:continuous-drift-detection",
            ],
        },
        {
            "id": "planner",
            "name": "Planner",
            "description": "Planning work, reviewing docs, and coordinating changes.",
            "default": False,
            "focus_lanes": ["start", "learn", "change"],
            "default_favorites": [
                "service:plane",
                "service:outline",
                "service:docs_portal",
                "service:netbox",
                "service:gitea",
            ],
        },
        {
            "id": "administrator",
            "name": "Administrator",
            "description": "Identity, secrets, control-plane, and platform administration.",
            "default": False,
            "focus_lanes": ["recover", "change", "observe"],
            "default_favorites": [
                "service:keycloak",
                "service:openbao",
                "service:proxmox_ui",
                "service:portainer",
                "workflow:converge-ops-portal",
            ],
        },
    ]
}
LAUNCHER_RECENT_LIMIT = 6
LAUNCHER_FAVORITE_LIMIT = 8
LIVE_APPLY_RECEIPT_EXCLUDED_PARTS = {"evidence", "preview"}

DEFAULT_SERVICE_CATEGORY_NAVIGATION = {
    "automation": {
        "primary_lane": "change",
        "secondary_lanes": ["observe"],
        "next_success_lane": "observe",
        "next_failure_lane": "recover",
    },
    "communication": {
        "primary_lane": "learn",
        "secondary_lanes": ["change"],
        "next_success_lane": "change",
        "next_failure_lane": "recover",
    },
    "data": {
        "primary_lane": "learn",
        "secondary_lanes": ["observe"],
        "next_success_lane": "change",
        "next_failure_lane": "recover",
    },
    "infrastructure": {
        "primary_lane": "change",
        "secondary_lanes": ["recover"],
        "next_success_lane": "observe",
        "next_failure_lane": "recover",
    },
    "observability": {
        "primary_lane": "observe",
        "secondary_lanes": ["recover"],
        "next_success_lane": "change",
        "next_failure_lane": "recover",
    },
    "security": {
        "primary_lane": "recover",
        "secondary_lanes": ["observe"],
        "next_success_lane": "change",
        "next_failure_lane": "recover",
    },
    "access": {
        "primary_lane": "start",
        "secondary_lanes": ["learn"],
        "next_success_lane": "observe",
        "next_failure_lane": "recover",
    },
}


def normalize_navigation_contract(
    payload: Any,
    *,
    default_lane: str = "start",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    primary_lane = normalize_task_lane(payload.get("primary_lane"), default=default_lane)
    secondary_lanes = [
        lane for lane in normalize_task_lane_list(payload.get("secondary_lanes", [])) if lane != primary_lane
    ]
    next_success_lane = normalize_task_lane(payload.get("next_success_lane"), default=primary_lane)
    next_failure_lane = normalize_task_lane(payload.get("next_failure_lane"), default="recover")
    return {
        "primary_lane": primary_lane,
        "secondary_lanes": secondary_lanes,
        "next_success_lane": next_success_lane,
        "next_failure_lane": next_failure_lane,
        "primary_lane_label": TASK_LANE_LABELS[primary_lane],
        "secondary_lane_labels": [TASK_LANE_LABELS[lane] for lane in secondary_lanes],
        "next_success_lane_label": TASK_LANE_LABELS[next_success_lane],
        "next_failure_lane_label": TASK_LANE_LABELS[next_failure_lane],
        "primary_question": TASK_LANE_QUESTIONS[primary_lane],
    }


def normalize_workbench_information_architecture(payload: Any) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    lanes = [
        {
            "id": lane,
            "label": TASK_LANE_LABELS[lane],
            "question": TASK_LANE_QUESTIONS[lane],
        }
        for lane in TASK_LANE_ORDER
    ]
    category_defaults = {
        category: normalize_navigation_contract(definition, default_lane=definition.get("primary_lane", "start"))
        for category, definition in (
            payload.get("service_category_defaults", {}) if isinstance(payload.get("service_category_defaults"), dict) else {}
        ).items()
    }
    for category, definition in DEFAULT_SERVICE_CATEGORY_NAVIGATION.items():
        category_defaults.setdefault(
            category,
            normalize_navigation_contract(definition, default_lane=definition["primary_lane"]),
        )

    def index_contracts(entries: Any, key_name: str, *, default_lane: str = "start") -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        if not isinstance(entries, list):
            return indexed
        for item in entries:
            if not isinstance(item, dict):
                continue
            entry_id = item.get(key_name)
            if not isinstance(entry_id, str) or not entry_id.strip():
                continue
            indexed[entry_id.strip()] = {
                key_name: entry_id.strip(),
                **normalize_navigation_contract(item, default_lane=default_lane),
            }
        return indexed

    workflow_defaults = {}
    raw_workflow_defaults = payload.get("workflow_defaults")
    if isinstance(raw_workflow_defaults, dict):
        for key, value in raw_workflow_defaults.items():
            if key in {"diagnostic", "mutation"}:
                workflow_defaults[key] = normalize_navigation_contract(value, default_lane="change")
    runbook_defaults = {}
    raw_runbook_defaults = payload.get("runbook_defaults")
    if isinstance(raw_runbook_defaults, dict):
        for key, value in raw_runbook_defaults.items():
            if key in {"diagnostic", "mutation"}:
                runbook_defaults[key] = normalize_navigation_contract(value, default_lane="learn")

    pages: list[dict[str, Any]] = []
    pages_by_id: dict[str, dict[str, Any]] = {}
    pages_by_section: dict[str, dict[str, Any]] = {}
    for item in payload.get("pages", []) if isinstance(payload.get("pages"), list) else []:
        if not isinstance(item, dict):
            continue
        page_id = item.get("id")
        section_id = item.get("section_id")
        route = item.get("route")
        title = item.get("title")
        if not all(isinstance(value, str) and value.strip() for value in (page_id, section_id, route, title)):
            continue
        page = {
            "id": page_id.strip(),
            "title": title.strip(),
            "surface": str(item.get("surface", "ops_portal")).strip() or "ops_portal",
            "route": route.strip(),
            "section_id": section_id.strip(),
            "fragment": str(item.get("fragment", section_id)).strip() or section_id.strip(),
            "nav_label": str(item.get("nav_label", title)).strip() or title.strip(),
            "nav_visible": bool(item.get("nav_visible")),
            "nav_order": int(item.get("nav_order", len(pages) + 1)),
            **normalize_navigation_contract(item),
        }
        page["secondary_lanes_csv"] = ",".join(page["secondary_lanes"])
        pages.append(page)
        pages_by_id[page["id"]] = page
        pages_by_section[page["section_id"]] = page

    return {
        "lanes": lanes,
        "service_category_defaults": category_defaults,
        "service_overrides": index_contracts(payload.get("service_overrides"), "service_id"),
        "workflow_defaults": {
            "diagnostic": workflow_defaults.get(
                "diagnostic",
                normalize_navigation_contract({"primary_lane": "observe", "secondary_lanes": ["learn"]}, default_lane="observe"),
            ),
            "mutation": workflow_defaults.get(
                "mutation",
                normalize_navigation_contract({"primary_lane": "change", "secondary_lanes": ["observe"]}, default_lane="change"),
            ),
        },
        "workflow_overrides": index_contracts(payload.get("workflow_overrides"), "workflow_id", default_lane="change"),
        "runbook_defaults": {
            "diagnostic": runbook_defaults.get(
                "diagnostic",
                normalize_navigation_contract({"primary_lane": "learn", "secondary_lanes": ["observe"]}, default_lane="learn"),
            ),
            "mutation": runbook_defaults.get(
                "mutation",
                normalize_navigation_contract({"primary_lane": "change", "secondary_lanes": ["recover"]}, default_lane="change"),
            ),
        },
        "runbook_overrides": index_contracts(payload.get("runbook_overrides"), "runbook_id", default_lane="learn"),
        "pages": sorted(pages, key=lambda item: item["nav_order"]),
        "pages_by_id": pages_by_id,
        "pages_by_section": pages_by_section,
    }


def build_shell_navigation(
    pages: list[dict[str, Any]],
    section_counts: dict[str, int],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    visible_pages = [page for page in pages if page.get("nav_visible")]
    for lane in TASK_LANE_ORDER:
        entries: list[dict[str, Any]] = []
        for page in visible_pages:
            if lane != page["primary_lane"] and lane not in page["secondary_lanes"]:
                continue
            entries.append(
                {
                    "id": page["id"],
                    "label": page["nav_label"],
                    "href": f"#{page['fragment']}",
                    "count": section_counts.get(page["section_id"]),
                    "is_primary": lane == page["primary_lane"],
                }
            )
        if not entries:
            continue
        groups.append(
            {
                "id": lane,
                "label": TASK_LANE_LABELS[lane],
                "question": TASK_LANE_QUESTIONS[lane],
                "entries": entries,
            }
        )
    return groups


def browser_usable_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate.startswith(("http://", "https://")):
        return candidate
    return None


def include_live_apply_receipt_path(path: Path) -> bool:
    return not any(part in LIVE_APPLY_RECEIPT_EXCLUDED_PARTS for part in path.parts)


def service_navigation_contract(
    service: dict[str, Any],
    workbench_ia: dict[str, Any],
) -> dict[str, Any]:
    service_id = str(service.get("id", "")).strip()
    category = str(service.get("category", "")).strip()
    override = workbench_ia.get("service_overrides", {}).get(service_id, {})
    default = workbench_ia.get("service_category_defaults", {}).get(
        category,
        normalize_navigation_contract(DEFAULT_SERVICE_CATEGORY_NAVIGATION.get("access", {})),
    )
    return {**default, **override}


def workflow_navigation_contract(
    workflow_id: str,
    workflow: dict[str, Any],
    workbench_ia: dict[str, Any],
) -> dict[str, Any]:
    override = workbench_ia.get("workflow_overrides", {}).get(workflow_id)
    if override:
        return dict(override)
    execution_class = str(workflow.get("execution_class", "mutation")).strip().lower()
    return dict(workbench_ia.get("workflow_defaults", {}).get(execution_class, {}))


def runbook_navigation_contract(runbook: dict[str, Any], workbench_ia: dict[str, Any]) -> dict[str, Any]:
    runbook_id = str(runbook.get("id", "")).strip()
    override = workbench_ia.get("runbook_overrides", {}).get(runbook_id)
    if override:
        return dict(override)
    execution_class = str(runbook.get("execution_class", "diagnostic")).strip().lower()
    return dict(workbench_ia.get("runbook_defaults", {}).get(execution_class, {}))


def default_launcher_personas(primary_lane: str) -> list[str]:
    return default_personas_for_task_lane(primary_lane)


def normalize_persona_catalog(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        payload = DEFAULT_PERSONA_CATALOG
    raw_personas = payload.get("personas")
    if not isinstance(raw_personas, list) or not raw_personas:
        raw_personas = DEFAULT_PERSONA_CATALOG["personas"]

    personas: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in raw_personas:
        if not isinstance(item, dict):
            continue
        persona_id = item.get("id")
        name = item.get("name")
        description = item.get("description")
        if not isinstance(persona_id, str) or not persona_id.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        if persona_id in seen_ids:
            continue
        seen_ids.add(persona_id)
        focus_lanes = normalize_task_lane_list(
            item.get("focus_lanes", item.get("focus_purposes", [])),
        )
        default_favorites = [
            favorite
            for favorite in item.get("default_favorites", [])
            if isinstance(favorite, str) and favorite.strip()
        ]
        personas.append(
            {
                "id": persona_id.strip(),
                "name": name.strip(),
                "description": description.strip()
                if isinstance(description, str) and description.strip()
                else "No description recorded.",
                "default": bool(item.get("default")),
                "focus_lanes": focus_lanes,
                "default_favorites": default_favorites,
            }
        )

    if not personas:
        return normalize_persona_catalog(DEFAULT_PERSONA_CATALOG)
    if not any(persona["default"] for persona in personas):
        personas[0]["default"] = True
    return personas


def default_persona_id(personas: list[dict[str, Any]]) -> str:
    for persona in personas:
        if persona.get("default"):
            return str(persona["id"])
    return str(personas[0]["id"]) if personas else "operator"


def launcher_matches_query(entry: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = normalize_text(" ".join(str(item) for item in entry.get("search_tokens", []) if item))
    return all(token in haystack for token in normalize_text(query).split())


def launcher_entry_visible(entry: dict[str, Any], persona_id: str, query: str) -> bool:
    personas = entry.get("personas", [])
    return persona_id in personas and launcher_matches_query(entry, query)


def decorate_launcher_entry(
    entry: dict[str, Any],
    favorite_ids: set[str],
    recent_ids: set[str],
) -> dict[str, Any]:
    model = dict(entry)
    model["is_favorite"] = entry["id"] in favorite_ids
    model["is_recent"] = entry["id"] in recent_ids
    return model


def build_launcher_groups(
    entries: list[dict[str, Any]],
    *,
    persona: dict[str, Any],
    favorite_ids: set[str],
    recent_ids: set[str],
    query: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {lane: [] for lane in TASK_LANE_ORDER}
    for entry in entries:
        if not launcher_entry_visible(entry, str(persona["id"]), query):
            continue
        grouped[entry["primary_lane"]].append(decorate_launcher_entry(entry, favorite_ids, recent_ids))

    ordered_lanes: list[str] = []
    for lane in persona.get("focus_lanes", []):
        if lane not in ordered_lanes:
            ordered_lanes.append(lane)
    for lane in TASK_LANE_ORDER:
        if lane not in ordered_lanes:
            ordered_lanes.append(lane)

    groups: list[dict[str, Any]] = []
    for lane in ordered_lanes:
        items = sorted(grouped.get(lane, []), key=lambda item: (item["kind"], item["name"]))
        if not items:
            continue
        groups.append(
            {
                "lane": lane,
                "label": TASK_LANE_LABELS[lane],
                "question": TASK_LANE_QUESTIONS[lane],
                "entries": items,
            }
        )
    return groups


def normalize_session_item_ids(value: Any, valid_entry_ids: set[str], *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        if item not in valid_entry_ids:
            continue
        if item in normalized:
            continue
        normalized.append(item)
        if len(normalized) >= limit:
            break
    return normalized


def ensure_launcher_preferences(
    session: dict[str, Any],
    personas: list[dict[str, Any]],
    valid_entry_ids: set[str],
) -> dict[str, Any]:
    persona_index = {str(persona["id"]): persona for persona in personas}
    selected_persona = session.get("launcher_persona")
    if selected_persona not in persona_index:
        selected_persona = default_persona_id(personas)
        session["launcher_persona"] = selected_persona

    seeded = bool(session.get("launcher_preferences_seeded"))
    favorites = normalize_session_item_ids(
        session.get("launcher_favorites"),
        valid_entry_ids,
        limit=LAUNCHER_FAVORITE_LIMIT,
    )
    recents = normalize_session_item_ids(
        session.get("launcher_recent"),
        valid_entry_ids,
        limit=LAUNCHER_RECENT_LIMIT,
    )

    if not seeded and not favorites:
        favorites = normalize_session_item_ids(
            persona_index[selected_persona].get("default_favorites", []),
            valid_entry_ids,
            limit=LAUNCHER_FAVORITE_LIMIT,
        )
        session["launcher_preferences_seeded"] = True

    session["launcher_favorites"] = favorites
    session["launcher_recent"] = recents
    return {
        "selected_persona": persona_index[selected_persona],
        "favorite_ids": favorites,
        "recent_ids": recents,
    }


def toggle_launcher_favorite(session: dict[str, Any], item_id: str, valid_entry_ids: set[str]) -> None:
    favorites = normalize_session_item_ids(
        session.get("launcher_favorites"),
        valid_entry_ids,
        limit=LAUNCHER_FAVORITE_LIMIT,
    )
    if item_id in favorites:
        favorites = [favorite for favorite in favorites if favorite != item_id]
    elif item_id in valid_entry_ids:
        favorites = [item_id, *favorites]
    session["launcher_favorites"] = favorites[:LAUNCHER_FAVORITE_LIMIT]
    session["launcher_preferences_seeded"] = True


def record_launcher_recent(session: dict[str, Any], item_id: str, valid_entry_ids: set[str]) -> None:
    if item_id not in valid_entry_ids:
        return
    recents = normalize_session_item_ids(
        session.get("launcher_recent"),
        valid_entry_ids,
        limit=LAUNCHER_RECENT_LIMIT,
    )
    recents = [item_id, *[recent for recent in recents if recent != item_id]]
    session["launcher_recent"] = recents[:LAUNCHER_RECENT_LIMIT]


def build_launcher_entries(
    services: list[dict[str, Any]],
    publications: list[dict[str, Any]],
    workflows: dict[str, Any],
    workbench_ia: dict[str, Any],
) -> list[dict[str, Any]]:
    publications_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for publication in publications:
        service_id = publication.get("service_id")
        if isinstance(service_id, str) and service_id:
            publications_by_service[service_id].append(publication)

    entries: list[dict[str, Any]] = []

    for service in services:
        if service.get("lifecycle_status") != "active":
            continue
        href = browser_usable_url(service.get("public_url")) or browser_usable_url(service.get("internal_url"))
        if href is None:
            continue
        service_id = str(service.get("id", "")).strip()
        if not service_id:
            continue
        navigation = service_navigation_contract(service, workbench_ia)
        publications_for_service = publications_by_service.get(service_id, [])
        primary_publication = next(
            (
                publication
                for publication in sorted(publications_for_service, key=lambda item: item.get("fqdn", ""))
                if publication.get("status") == "active"
            ),
            publications_for_service[0] if publications_for_service else {},
        )
        publication_payload = primary_publication.get("publication", {})
        access_model = publication_payload.get("access_model", service.get("exposure", "unknown"))
        audience = publication_payload.get("audience", "operator")
        fqdn = primary_publication.get("fqdn") or service.get("subdomain") or ""
        description = str(service.get("description", "")).strip()
        tags = service.get("tags") if isinstance(service.get("tags"), list) else []
        entries.append(
            {
                "id": f"service:{service_id}",
                "kind": "service",
                "kind_label": "Service",
                "name": str(service.get("name", service_id)),
                "description": description,
                "href": "/" if service_id == "ops_portal" else href,
                **navigation,
                "personas": default_launcher_personas(navigation["primary_lane"]),
                "summary_line": " / ".join(str(item) for item in (fqdn, audience, access_model) if item),
                "badges": [
                    str(service.get("category", "uncategorized")),
                    navigation["primary_lane_label"],
                    str(audience),
                    str(access_model),
                ],
                "search_tokens": [
                    service_id,
                    service.get("name", ""),
                    description,
                    fqdn,
                    access_model,
                    audience,
                    *tags,
                ],
            }
        )

    for workflow_id, workflow in workflows.items():
        if not isinstance(workflow, dict):
            continue
        human_navigation = workflow.get("human_navigation")
        if not isinstance(human_navigation, dict):
            continue
        launcher = human_navigation.get("launcher")
        if not isinstance(launcher, dict) or not launcher.get("enabled"):
            continue
        href = browser_usable_url(launcher.get("href")) or (
            str(launcher.get("href", "")).strip() if isinstance(launcher.get("href"), str) else ""
        )
        if not href:
            continue
        navigation = workflow_navigation_contract(workflow_id, workflow, workbench_ia)
        declared_lane = normalize_task_lane(launcher.get("lane", launcher.get("purpose")), default="")
        if declared_lane in TASK_LANE_IDS:
            navigation = {
                **navigation,
                **normalize_navigation_contract(
                    {
                        "primary_lane": declared_lane,
                        "secondary_lanes": navigation.get("secondary_lanes", []),
                        "next_success_lane": navigation.get("next_success_lane"),
                        "next_failure_lane": navigation.get("next_failure_lane"),
                    },
                    default_lane=declared_lane,
                ),
            }
        personas = [
            persona_id
            for persona_id in launcher.get("personas", [])
            if isinstance(persona_id, str) and persona_id.strip()
        ] or default_launcher_personas(navigation["primary_lane"])
        label = str(launcher.get("label") or workflow.get("description") or workflow_id)
        description = str(launcher.get("description") or workflow.get("description") or "").strip()
        tags = workflow.get("tags") if isinstance(workflow.get("tags"), list) else []
        entries.append(
            {
                "id": f"workflow:{workflow_id}",
                "kind": "workflow",
                "kind_label": "Workflow",
                "name": label,
                "description": description,
                "href": href,
                **navigation,
                "personas": personas,
                "summary_line": str(workflow.get("owner_runbook", "")).strip(),
                "badges": [
                    "workflow",
                    navigation["primary_lane_label"],
                    str(workflow.get("execution_class", "unknown")),
                    str(workflow.get("live_impact", "unknown")),
                ],
                "search_tokens": [
                    workflow_id,
                    label,
                    description,
                    workflow.get("owner_runbook", ""),
                    *tags,
                ],
            }
        )

    return sorted(entries, key=lambda item: (TASK_LANE_ORDER.index(item["primary_lane"]), item["kind"], item["name"]))


@dataclass(frozen=True)
class PortalSettings:
    gateway_url: str
    session_secret: str
    static_api_token: str | None
    service_catalog_path: Path
    persona_catalog_path: Path
    workbench_ia_path: Path
    publication_registry_path: Path
    workflow_catalog_path: Path
    changelog_path: Path
    live_applies_dir: Path
    drift_receipts_dir: Path
    maintenance_windows_path: Path | None
    docs_base_url: str
    grafana_logs_url: str

    @classmethod
    def from_env(cls) -> PortalSettings:
        data_root = Path(os.getenv("OPS_PORTAL_DATA_ROOT", "/srv/ops-portal/data"))
        maintenance_file = os.getenv("OPS_PORTAL_MAINTENANCE_WINDOWS_FILE", "").strip()
        return cls(
            gateway_url=os.getenv("GATEWAY_URL", "http://api-gateway:8080").rstrip("/"),
            session_secret=os.getenv("OPS_PORTAL_SESSION_SECRET", "development-secret-change-me"),
            static_api_token=os.getenv("OPS_PORTAL_STATIC_API_TOKEN") or None,
            service_catalog_path=Path(
                os.getenv("OPS_PORTAL_SERVICE_CATALOG", data_root / "config" / "service-capability-catalog.json")
            ),
            persona_catalog_path=Path(
                os.getenv("OPS_PORTAL_PERSONA_CATALOG", data_root / "config" / "persona-catalog.json")
            ),
            workbench_ia_path=Path(
                os.getenv(
                    "OPS_PORTAL_WORKBENCH_IA_CATALOG",
                    data_root / "config" / "workbench-information-architecture.json",
                )
            ),
            publication_registry_path=Path(
                os.getenv(
                    "OPS_PORTAL_PUBLICATION_REGISTRY",
                    data_root / "config" / "subdomain-exposure-registry.json",
                )
            ),
            workflow_catalog_path=Path(
                os.getenv("OPS_PORTAL_WORKFLOW_CATALOG", data_root / "config" / "workflow-catalog.json")
            ),
            changelog_path=Path(os.getenv("OPS_PORTAL_CHANGELOG_FILE", data_root / "changelog.md")),
            live_applies_dir=Path(
                os.getenv("OPS_PORTAL_LIVE_APPLIES_DIR", data_root / "receipts" / "live-applies")
            ),
            drift_receipts_dir=Path(
                os.getenv("OPS_PORTAL_DRIFT_RECEIPTS_DIR", data_root / "receipts" / "drift-reports")
            ),
            maintenance_windows_path=Path(maintenance_file) if maintenance_file else None,
            docs_base_url=os.getenv("OPS_PORTAL_DOCS_BASE_URL", "https://docs.lv3.org").rstrip("/"),
            grafana_logs_url=os.getenv(
                "OPS_PORTAL_GRAFANA_LOGS_URL",
                "https://grafana.lv3.org/explore?left=%7B%22queries%22:%5B%5D%7D",
            ),
        )


class EventBroker:
    def __init__(self, limit: int = 200) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=limit)
        self._condition = asyncio.Condition()

    async def publish(self, message: str, *, event_type: str = "log", metadata: dict[str, Any] | None = None) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "type": event_type,
            "message": message,
            "metadata": metadata or {},
            "ts": isoformat(utc_now()),
        }
        async with self._condition:
            self._events.append(event)
            self._condition.notify_all()

    async def stream(self):
        last_seen = 0
        while True:
            async with self._condition:
                if last_seen >= len(self._events):
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=15)
                    except TimeoutError:
                        yield {"event": "heartbeat", "data": {"ts": isoformat(utc_now())}}
                        continue
                snapshot = list(self._events)
            for event in snapshot[last_seen:]:
                yield {"event": event["type"], "data": event}
            last_seen = len(snapshot)


class GatewayClient:
    def __init__(self, settings: PortalSettings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=self.settings.gateway_url, timeout=20)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = await self._client.request(method, path, json=payload, headers=headers)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_platform_health(self, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", "/v1/platform/health", token=token)

    async def fetch_agent_coordination(self, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", "/v1/platform/agents", token=token)

    async def fetch_service_health(self, service_id: str, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", f"/v1/platform/health/{service_id}", token=token)

    async def fetch_runtime_assurance(self, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", "/v1/platform/runtime-assurance", token=token)

    async def trigger_deploy(
        self,
        service_id: str,
        *,
        token: str | None = None,
        restart_only: bool = False,
        source: str = "portal",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/platform/deploy",
            token=token,
            payload={"service": service_id, "restart_only": restart_only, "source": source},
        )

    async def rotate_secret(self, service_id: str, *, token: str | None = None) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/platform/secrets/rotate",
            token=token,
            payload={"service": service_id, "source": "portal"},
        )

    async def launch_runbook(
        self,
        runbook_id: str,
        *,
        token: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/platform/runbooks/execute",
            token=token,
            payload={
                "runbook_id": runbook_id,
                "parameters": parameters or {},
                "delivery_surface": "ops_portal",
            },
        )

    async def search(
        self,
        query: str,
        *,
        collection: str | None = None,
        token: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        params = {"q": query, "limit": str(limit)}
        if collection:
            params["collection"] = collection
        return await self._request("GET", f"/v1/search?{httpx.QueryParams(params)}", token=token)

    async def fetch_runbooks(self, *, token: str | None = None, delivery_surface: str = "ops_portal") -> dict[str, Any]:
        params = httpx.QueryParams({"delivery_surface": delivery_surface})
        return await self._request("GET", f"/v1/platform/runbooks?{params}", token=token)


@dataclass
class PortalRepository:
    settings: PortalSettings

    def load_service_catalog(self) -> list[dict[str, Any]]:
        payload = load_json_file(self.settings.service_catalog_path, {"services": []})
        return payload.get("services", [])

    def load_persona_catalog(self) -> list[dict[str, Any]]:
        payload = load_json_file(self.settings.persona_catalog_path, DEFAULT_PERSONA_CATALOG)
        return normalize_persona_catalog(payload)

    def load_workbench_information_architecture(self) -> dict[str, Any]:
        payload = load_json_file(self.settings.workbench_ia_path, {})
        return normalize_workbench_information_architecture(payload)

    def load_publication_registry(self) -> list[dict[str, Any]]:
        payload = load_json_file(self.settings.publication_registry_path, {"publications": []})
        return registry_entries(payload)

    def load_workflow_definitions(self) -> dict[str, Any]:
        payload = load_json_file(self.settings.workflow_catalog_path, {"workflows": {}})
        workflows = payload.get("workflows", {})
        return workflows if isinstance(workflows, dict) else {}

    def load_capability_contract_catalog(self) -> list[dict[str, Any]]:
        contract_path = self.settings.service_catalog_path.parent / "capability-contract-catalog.json"
        payload = load_json_file(contract_path, {"capabilities": []})
        capabilities = payload.get("capabilities", [])
        return capabilities if isinstance(capabilities, list) else []

    def load_workflow_catalog(self) -> list[dict[str, Any]]:
        payload = load_json_file(self.settings.workflow_catalog_path, {"workflows": {}})
        workflows = []
        for workflow_id, workflow in payload.get("workflows", {}).items():
            if workflow.get("lifecycle_status") != "active":
                continue
            if workflow.get("live_impact") == "repo_only":
                continue
            workflows.append(
                {
                    "id": workflow_id,
                    "description": workflow.get("description", workflow_id),
                    "owner_runbook": workflow.get("owner_runbook"),
                    "entrypoint": workflow.get("preferred_entrypoint", {}),
                    "live_impact": workflow.get("live_impact", "unknown"),
                }
            )
        return sorted(workflows, key=lambda item: item["id"])

    def load_dependency_graph(self) -> dict[str, Any]:
        graph_path = self.settings.service_catalog_path.parent / "dependency-graph.json"
        payload = load_json_file(graph_path, {"nodes": [], "edges": []})
        if not isinstance(payload, dict):
            return {"nodes": [], "edges": []}
        nodes = payload.get("nodes")
        edges = payload.get("edges")
        return {
            "nodes": nodes if isinstance(nodes, list) else [],
            "edges": edges if isinstance(edges, list) else [],
        }

    def load_maintenance_windows(self) -> list[dict[str, Any]]:
        if self.settings.maintenance_windows_path is None:
            return []
        payload = load_json_file(self.settings.maintenance_windows_path, {})
        if isinstance(payload, dict):
            values = payload.values()
        else:
            values = payload
        windows = [item for item in values if isinstance(item, dict)]
        return sorted(windows, key=lambda item: item.get("opened_at", ""), reverse=True)

    def latest_drift_report(self) -> dict[str, Any]:
        reports = sorted(self.settings.drift_receipts_dir.glob("*.json"), reverse=True)
        for report in reports:
            payload = load_optional_json_document(report)
            if not isinstance(payload, dict):
                continue
            payload["_path"] = str(report)
            return payload
        return {}

    def _service_keywords(self, services: list[dict[str, Any]]) -> dict[str, set[str]]:
        service_keywords: dict[str, set[str]] = {}
        for service in services:
            keywords = {
                normalize_text(service["id"]),
                normalize_text(service["name"]),
            }
            for field in ("public_url", "internal_url", "subdomain", "vm"):
                if isinstance(service.get(field), str):
                    keywords.add(normalize_text(service[field]))
            environments = service.get("environments")
            if isinstance(environments, dict):
                for binding in environments.values():
                    if not isinstance(binding, dict):
                        continue
                    for field in ("url", "subdomain"):
                        if isinstance(binding.get(field), str):
                            keywords.add(normalize_text(binding[field]))
            service_keywords[service["id"]] = {keyword for keyword in keywords if keyword}
        return service_keywords

    def load_live_apply_receipts(self, services: list[dict[str, Any]]) -> list[dict[str, Any]]:
        service_keywords = self._service_keywords(services)
        receipts: list[dict[str, Any]] = []
        for receipt_path in sorted(self.settings.live_applies_dir.rglob("*.json"), reverse=True):
            if not include_live_apply_receipt_path(receipt_path):
                continue
            receipt = load_optional_json_document(receipt_path)
            if not isinstance(receipt, dict):
                continue
            text = normalize_text(json.dumps(receipt, sort_keys=True))
            matched = []
            for service_id, keywords in service_keywords.items():
                if any(keyword and keyword in text for keyword in keywords):
                    matched.append(service_id)
            receipt["_path"] = str(receipt_path)
            receipt["_normalized_text"] = text
            receipt["_matched_services"] = sorted(set(matched))
            receipt["_environment"] = (
                str(receipt.get("environment", "")).strip().lower()
                or ("staging" if "staging" in receipt_path.parts else "production")
            )
            receipts.append(receipt)
        return receipts

    def recent_deployments(
        self,
        services: list[dict[str, Any]],
        *,
        receipts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        live_apply_receipts = receipts if receipts is not None else self.load_live_apply_receipts(services)

        receipts_out: list[dict[str, Any]] = []
        for receipt in live_apply_receipts:
            receipts_out.append(
                {
                    "id": receipt.get("receipt_id", Path(str(receipt.get("_path", "receipt"))).stem),
                    "summary": receipt.get("summary", Path(str(receipt.get("_path", "receipt"))).stem),
                    "workflow_id": receipt.get("workflow_id", ""),
                    "recorded_on": receipt.get("recorded_on") or receipt.get("applied_on"),
                    "recorded_by": receipt.get("recorded_by", "unknown"),
                    "services": list(receipt.get("_matched_services", [])),
                    "path": str(receipt.get("_path", "")),
                }
            )
        return receipts_out

    def changelog_notes(self) -> list[str]:
        if not self.settings.changelog_path.exists():
            return []
        notes: list[str] = []
        in_unreleased = False
        for line in self.settings.changelog_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped == "## Unreleased":
                in_unreleased = True
                continue
            if in_unreleased and stripped.startswith("## "):
                break
            if in_unreleased and stripped.startswith("- "):
                notes.append(stripped[2:])
        return notes


def normalize_health(payload: dict[str, Any], services: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    health_map = {
        service["id"]: {
            "status": "unknown",
            "detail": "No live health data",
        }
        for service in services
    }
    if not payload:
        return health_map

    raw_services = payload.get("services") if isinstance(payload, dict) else None
    if isinstance(raw_services, list):
        for item in raw_services:
            service_id = item.get("service_id") or item.get("service") or item.get("id")
            if service_id in health_map:
                health_map[service_id] = {
                    "status": str(item.get("status", "unknown")),
                    "detail": str(item.get("detail") or item.get("message") or "No detail"),
                }
    elif isinstance(raw_services, dict):
        for service_id, item in raw_services.items():
            if service_id not in health_map:
                continue
            if isinstance(item, str):
                health_map[service_id] = {"status": item, "detail": item}
                continue
            health_map[service_id] = {
                "status": str(item.get("status", "unknown")),
                "detail": str(item.get("detail") or item.get("message") or "No detail"),
            }
    elif isinstance(payload, dict):
        service_id = payload.get("service_id") or payload.get("service") or payload.get("id")
        if service_id in health_map:
            health_map[service_id] = {
                "status": str(payload.get("status", "unknown")),
                "detail": str(payload.get("detail") or payload.get("message") or "No detail"),
            }
    return health_map


def normalize_runtime_assurance(payload: dict[str, Any] | None, services: list[dict[str, Any]]) -> dict[str, Any]:
    service_lookup = {str(service.get("id")): service for service in services if isinstance(service, dict)}
    if not isinstance(payload, dict):
        return {
            "summary": {"total": 0, "pass": 0, "degraded": 0, "failed": 0, "unknown": 0},
            "entries": [],
            "generated_at": None,
        }

    raw_entries = payload.get("entries")
    entries = raw_entries if isinstance(raw_entries, list) else []
    normalized_entries: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        service_id = str(item.get("service_id", "unknown"))
        service = service_lookup.get(service_id, {})
        dimensions = item.get("dimensions")
        if not isinstance(dimensions, list):
            dimensions = []
        exceptions = [
            dimension
            for dimension in dimensions
            if isinstance(dimension, dict) and dimension.get("status") not in {"pass", "n_a"}
        ]
        exception_titles = [str(dimension.get("title", dimension.get("id", "dimension"))) for dimension in exceptions[:3]]
        normalized_entries.append(
            {
                "service_id": service_id,
                "service_name": str(item.get("service_name") or service.get("name") or service_id),
                "environment": str(item.get("environment", "unknown")),
                "profile_id": str(item.get("profile_id", "unknown")),
                "profile_title": str(item.get("profile_title", item.get("profile_id", "unknown"))),
                "overall_status": str(item.get("overall_status", "unknown")),
                "summary": item.get("summary") if isinstance(item.get("summary"), dict) else {},
                "primary_url": item.get("primary_url") or service.get("public_url") or service.get("internal_url"),
                "runbook": item.get("runbook") or service.get("runbook"),
                "adr": item.get("adr") or service.get("adr"),
                "exception_dimensions": exceptions,
                "exception_titles": exception_titles,
            }
        )

    status_rank = {"failed": 0, "degraded": 1, "unknown": 2, "pass": 3}
    normalized_entries.sort(
        key=lambda item: (
            status_rank.get(item["overall_status"], 4),
            item["environment"],
            item["service_name"],
        )
    )

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {
            "total": len(normalized_entries),
            "pass": sum(1 for item in normalized_entries if item["overall_status"] == "pass"),
            "degraded": sum(1 for item in normalized_entries if item["overall_status"] == "degraded"),
            "failed": sum(1 for item in normalized_entries if item["overall_status"] == "failed"),
            "unknown": sum(1 for item in normalized_entries if item["overall_status"] == "unknown"),
        }

    return {
        "summary": {
            "total": int(summary.get("total", len(normalized_entries))),
            "pass": int(summary.get("pass", 0)),
            "degraded": int(summary.get("degraded", 0)),
            "failed": int(summary.get("failed", 0)),
            "unknown": int(summary.get("unknown", 0)),
        },
        "entries": normalized_entries,
        "generated_at": payload.get("generated_at"),
    }


def build_capability_contract_models(
    capability_contracts: list[dict[str, Any]],
    services: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    service_index = {service.get("id"): service for service in services if isinstance(service.get("id"), str)}
    models: list[dict[str, Any]] = []
    selected = 0
    export_ready = 0

    for capability in sorted(capability_contracts, key=lambda item: str(item.get("id", ""))):
        migration = capability.get("migration_expectations", {})
        selection = capability.get("current_selection", {})
        if not isinstance(migration, dict):
            migration = {}
        if not isinstance(selection, dict):
            selection = {}
        export_formats = migration.get("export_formats", [])
        if not isinstance(export_formats, list):
            export_formats = []
        service = service_index.get(selection.get("service_id"), {})
        if selection:
            selected += 1
        if export_formats:
            export_ready += 1
        models.append(
            {
                "id": capability.get("id", "unknown"),
                "name": capability.get("name", capability.get("id", "Unknown capability")),
                "summary": capability.get("summary", ""),
                "selected_product": selection.get("product_name"),
                "service_name": service.get("name"),
                "service_url": service.get("public_url") or service.get("internal_url"),
                "selection_adr": selection.get("selection_adr"),
                "runbook": selection.get("runbook"),
                "review_cadence": capability.get("review_cadence", "unspecified"),
                "export_format_count": len(export_formats),
                "fallback_behaviour": migration.get("fallback_behaviour", "No fallback recorded."),
            }
        )

    return models, {
        "total": len(models),
        "selected": selected,
        "contract_only": len(models) - selected,
        "export_ready": export_ready,
    }


def status_tone(status: str) -> str:
    value = status.lower()
    if value in {"healthy", "ok", "up", "success", "active", "pass"}:
        return "ok"
    if value in {"warning", "warn", "degraded", "pending", "blocked", "escalated", "maintenance"}:
        return "warn"
    if value in {"critical", "down", "error", "failed"}:
        return "danger"
    return "neutral"


def build_health_mix_chart(services: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {tone: 0 for tone in TONE_META}
    for service in services:
        tone = str(service.get("status_tone", "neutral"))
        counts[tone if tone in counts else "neutral"] += 1

    data = [
        {
            "name": meta["label"],
            "value": counts[tone],
            "itemStyle": {"color": meta["color"]},
        }
        for tone, meta in TONE_META.items()
        if counts[tone] > 0
    ]
    if not data:
        data = [{"name": "Unknown", "value": 1, "itemStyle": {"color": TONE_META["neutral"]["color"]}}]

    return {
        "aria": {
            "enabled": True,
            "description": "Service health mix for the interactive ops portal overview.",
        },
        "animation": False,
        "tooltip": {"trigger": "item"},
        "legend": {
            "bottom": 0,
            "left": "center",
            "icon": "circle",
            "textStyle": {"color": "#314467"},
        },
        "series": [
            {
                "name": "Service health",
                "type": "pie",
                "radius": ["54%", "76%"],
                "center": ["50%", "42%"],
                "avoidLabelOverlap": True,
                "label": {"formatter": "{b}\n{c}", "color": "#14213d"},
                "labelLine": {"length": 14, "length2": 10},
                "data": data,
            }
        ],
    }


def build_coordination_status_chart(coordination: dict[str, Any]) -> dict[str, Any]:
    summary = coordination.get("summary", {}) if isinstance(coordination, dict) else {}
    categories = [
        ("Active", "active", TONE_META["ok"]["color"]),
        ("Blocked", "blocked", TONE_META["warn"]["color"]),
        ("Escalated", "escalated", TONE_META["danger"]["color"]),
        ("Completing", "completing", "#457b9d"),
    ]
    return {
        "aria": {
            "enabled": True,
            "description": "Current agent coordination counts by session state.",
        },
        "animation": False,
        "grid": {"left": 42, "right": 18, "top": 18, "bottom": 34},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {
            "type": "category",
            "data": [label for label, _key, _color in categories],
            "axisLabel": {"color": "#314467"},
            "axisLine": {"lineStyle": {"color": "#c8c0b3"}},
        },
        "yAxis": {
            "type": "value",
            "minInterval": 1,
            "axisLabel": {"color": "#314467"},
            "splitLine": {"lineStyle": {"color": "rgba(20, 33, 61, 0.1)"}},
        },
        "series": [
            {
                "type": "bar",
                "barWidth": "48%",
                "data": [
                    {
                        "value": int(summary.get(key, 0)),
                        "itemStyle": {"color": color, "borderRadius": [10, 10, 0, 0]},
                    }
                    for _label, key, color in categories
                ],
            }
        ],
    }


def build_live_apply_timeline_chart(deployments: list[dict[str, Any]], *, days: int = 14) -> dict[str, Any]:
    today = utc_now().date()
    parsed_dates = [parsed.date() for item in deployments if (parsed := parse_timestamp(item.get("recorded_on")))]
    end_date = max(parsed_dates, default=today)
    start_date = end_date - timedelta(days=max(days - 1, 0))

    timeline: dict[date, dict[str, Any]] = {}
    for offset in range(days):
        current = start_date + timedelta(days=offset)
        timeline[current] = {"receipts": 0, "services": set()}

    for deployment in deployments:
        parsed = parse_timestamp(deployment.get("recorded_on"))
        if parsed is None:
            continue
        current = parsed.date()
        if current not in timeline:
            continue
        timeline[current]["receipts"] += 1
        timeline[current]["services"].update(
            service_id
            for service_id in deployment.get("services", [])
            if isinstance(service_id, str) and service_id
        )

    labels = [current.strftime("%m-%d") for current in timeline]
    receipt_counts = [timeline[current]["receipts"] for current in timeline]
    service_counts = [len(timeline[current]["services"]) for current in timeline]

    return {
        "aria": {
            "enabled": True,
            "description": "Recent live-apply receipt cadence over the last two weeks.",
        },
        "animation": False,
        "grid": {"left": 46, "right": 38, "top": 22, "bottom": 32},
        "tooltip": {"trigger": "axis"},
        "legend": {
            "top": 0,
            "textStyle": {"color": "#314467"},
        },
        "xAxis": {
            "type": "category",
            "data": labels,
            "axisLabel": {"color": "#314467"},
            "axisLine": {"lineStyle": {"color": "#c8c0b3"}},
        },
        "yAxis": [
            {
                "type": "value",
                "name": "Receipts",
                "minInterval": 1,
                "axisLabel": {"color": "#314467"},
                "splitLine": {"lineStyle": {"color": "rgba(20, 33, 61, 0.1)"}},
            },
            {
                "type": "value",
                "name": "Services",
                "minInterval": 1,
                "axisLabel": {"color": "#314467"},
                "splitLine": {"show": False},
            },
        ],
        "series": [
            {
                "name": "Live applies",
                "type": "bar",
                "barWidth": "46%",
                "data": receipt_counts,
                "itemStyle": {"color": "#d97706", "borderRadius": [8, 8, 0, 0]},
            },
            {
                "name": "Unique services",
                "type": "line",
                "yAxisIndex": 1,
                "smooth": True,
                "symbolSize": 7,
                "lineStyle": {"width": 3, "color": "#14213d"},
                "itemStyle": {"color": "#14213d"},
                "data": service_counts,
            },
        ],
    }


def build_dependency_focus_chart(
    dependency_graph: dict[str, Any],
    services: list[dict[str, Any]],
    *,
    focus_service: str = "ops_portal",
) -> dict[str, Any]:
    nodes = dependency_graph.get("nodes", []) if isinstance(dependency_graph, dict) else []
    edges = dependency_graph.get("edges", []) if isinstance(dependency_graph, dict) else []
    node_index = {
        str(node.get("id")): node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    if focus_service not in node_index:
        return {}

    selected = {focus_service}
    frontier = {focus_service}
    traversable_edge_types = {"hard", "startup_only"}

    for _depth in range(3):
        next_frontier: set[str] = set()
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("type") not in traversable_edge_types:
                continue
            source = str(edge.get("from", ""))
            target = str(edge.get("to", ""))
            if source in frontier and target in node_index and target not in selected:
                selected.add(target)
                next_frontier.add(target)
        frontier = next_frontier
        if not frontier:
            break

    service_index = {
        str(service.get("id")): service
        for service in services
        if isinstance(service, dict) and isinstance(service.get("id"), str)
    }
    graph_nodes = []
    for service_id in sorted(selected, key=lambda item: (int(node_index[item].get("tier", 99)), item)):
        node = node_index[service_id]
        service = service_index.get(service_id, {})
        tone = str(service.get("status_tone", "neutral"))
        meta = TONE_META.get(tone, TONE_META["neutral"])
        graph_nodes.append(
            {
                "id": service_id,
                "name": str(node.get("name", service_id)),
                "value": f"{node.get('vm', 'unknown vm')} · tier {node.get('tier', '?')} · {service.get('status', 'unknown')}",
                "symbolSize": 66 if service_id == focus_service else 46,
                "itemStyle": {
                    "color": meta["color"],
                    "borderColor": "#14213d",
                    "borderWidth": 2 if service_id == focus_service else 1,
                },
                "label": {"show": True, "color": "#14213d"},
            }
        )

    graph_links = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        edge_type = str(edge.get("type", "soft"))
        if source not in selected or target not in selected:
            continue
        meta = EDGE_META.get(edge_type, EDGE_META["soft"])
        graph_links.append(
            {
                "source": source,
                "target": target,
                "value": str(edge.get("description", edge_type)),
                "lineStyle": {
                    "color": meta["color"],
                    "type": meta["line_type"],
                    "width": meta["width"],
                    "curveness": 0.12,
                },
            }
        )

    return {
        "aria": {
            "enabled": True,
            "description": "Interactive ops portal dependency focus graph rendered from the canonical dependency graph.",
        },
        "animation": False,
        "tooltip": {"trigger": "item"},
        "series": [
            {
                "type": "graph",
                "layout": "force",
                "roam": True,
                "draggable": True,
                "force": {"repulsion": 260, "edgeLength": [90, 150]},
                "edgeSymbol": ["none", "arrow"],
                "edgeSymbolSize": [0, 9],
                "emphasis": {"focus": "adjacency"},
                "lineStyle": {"opacity": 0.82},
                "label": {"position": "right"},
                "data": graph_nodes,
                "links": graph_links,
            }
        ],
    }


def build_service_models(
    services: list[dict[str, Any]],
    publications: list[dict[str, Any]],
    health: dict[str, dict[str, str]],
    drift_report: dict[str, Any],
    maintenance_windows: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
    settings: PortalSettings,
) -> list[dict[str, Any]]:
    latest_deploy_by_service: dict[str, dict[str, Any]] = {}
    for deployment in deployments:
        for service_id in deployment["services"]:
            latest_deploy_by_service.setdefault(service_id, deployment)

    drift_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in drift_report.get("records", []):
        service_id = item.get("service")
        if service_id:
            drift_by_service[str(service_id)].append(item)

    windows_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for window in maintenance_windows:
        service_id = str(window.get("service_id", ""))
        if service_id:
            windows_by_service[service_id].append(window)

    publications_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for publication in publications:
        service_id = publication.get("service_id")
        if not isinstance(service_id, str) or not service_id:
            continue
        publications_by_service[service_id].append(publication)

    models = []
    for service in sorted(services, key=lambda item: (item.get("category", ""), item["name"])):
        service_id = service["id"]
        deployment = latest_deploy_by_service.get(service_id)
        publication_models = sorted(
            publications_by_service.get(service_id, []),
            key=lambda item: item.get("fqdn", ""),
        )
        models.append(
            {
                "id": service_id,
                "name": service["name"],
                "description": service.get("description", ""),
                "category": service.get("category", "misc"),
                "adr": service.get("adr"),
                "runbook": service.get("runbook"),
                "dashboard_url": service.get("dashboard_url"),
                "public_url": service.get("public_url"),
                "internal_url": service.get("internal_url"),
                "lifecycle_status": service.get("lifecycle_status", "unknown"),
                "status": health.get(service_id, {}).get("status", "unknown"),
                "status_detail": health.get(service_id, {}).get("detail", "No detail"),
                "status_tone": status_tone(health.get(service_id, {}).get("status", "unknown")),
                "drift_items": drift_by_service.get(service_id, []),
                "maintenance_windows": windows_by_service.get(service_id, []) + windows_by_service.get("all", []),
                "last_deployment": deployment,
                "logs_url": build_logs_url(settings.grafana_logs_url, service_id),
                "publications": [
                    {
                        "fqdn": publication["fqdn"],
                        "delivery_model": publication.get("publication", {}).get("delivery_model", "unknown"),
                        "access_model": publication.get("publication", {}).get("access_model", "unknown"),
                        "audience": publication.get("publication", {}).get("audience", "unknown"),
                        "status": publication.get("status", "unknown"),
                    }
                    for publication in publication_models
                ],
            }
        )
    return models


def build_logs_url(base_url: str, service_id: str) -> str:
    if "{service}" in base_url:
        return base_url.format(service=service_id)
    return f"{base_url}&service={service_id}"


def deployment_console_seed() -> list[dict[str, Any]]:
    return [
        {
            "id": "seed",
            "type": "info",
            "message": "Deployment console connected. New portal actions will appear here.",
            "ts": isoformat(utc_now()),
        }
    ]


async def ensure_session(request: Request) -> dict[str, str]:
    session = request.session
    if "operator_id" not in session:
        session["operator_id"] = request.headers.get("x-auth-request-user", "operator")
        session["operator_email"] = request.headers.get("x-auth-request-email", "")
    if "api_token" not in session:
        forwarded_token = request.headers.get("x-forwarded-access-token") or request.headers.get("authorization", "")
        if forwarded_token.startswith("Bearer "):
            forwarded_token = forwarded_token.removeprefix("Bearer ").strip()
        if forwarded_token:
            session["api_token"] = forwarded_token
    return {
        "operator_id": session.get("operator_id", "operator"),
        "operator_email": session.get("operator_email", ""),
        "api_token": session.get("api_token", ""),
    }


def read_api_token(session: dict[str, str], settings: PortalSettings) -> str | None:
    return session.get("api_token") or settings.static_api_token


@lru_cache(maxsize=1)
def template_root() -> Path:
    return Path(__file__).resolve().parent


def build_runbook_models(runbooks: list[dict[str, Any]], workbench_ia: dict[str, Any]) -> list[dict[str, Any]]:
    featured_ids = {"validation-gate-status"}
    normalized: list[dict[str, Any]] = []
    for item in runbooks:
        if not isinstance(item, dict) or "id" not in item:
            continue
        normalized.append(
            {
                **item,
                **runbook_navigation_contract(item, workbench_ia),
            }
        )
    featured = [item for item in normalized if item["id"] in featured_ids]
    remainder = [item for item in normalized if item["id"] not in featured_ids]
    combined = featured + remainder
    return combined[:6]


async def build_launcher_panel_context(request: Request, *, query: str = "") -> dict[str, Any]:
    await ensure_session(request)
    repository: PortalRepository = request.app.state.repository

    services = repository.load_service_catalog()
    publications = repository.load_publication_registry()
    workflows = repository.load_workflow_definitions()
    personas = repository.load_persona_catalog()
    workbench_ia = repository.load_workbench_information_architecture()

    entries = build_launcher_entries(services, publications, workflows, workbench_ia)
    valid_entry_ids = {entry["id"] for entry in entries}
    preferences = ensure_launcher_preferences(request.session, personas, valid_entry_ids)
    selected_persona = preferences["selected_persona"]
    favorite_ids = set(preferences["favorite_ids"])
    recent_ids = set(preferences["recent_ids"])
    entry_index = {entry["id"]: entry for entry in entries}

    favorites = [
        decorate_launcher_entry(entry_index[item_id], favorite_ids, recent_ids)
        for item_id in preferences["favorite_ids"]
        if item_id in entry_index and launcher_entry_visible(entry_index[item_id], str(selected_persona["id"]), query)
    ]
    recents = [
        decorate_launcher_entry(entry_index[item_id], favorite_ids, recent_ids)
        for item_id in preferences["recent_ids"]
        if item_id in entry_index and launcher_entry_visible(entry_index[item_id], str(selected_persona["id"]), query)
    ]
    groups = build_launcher_groups(
        entries,
        persona=selected_persona,
        favorite_ids=favorite_ids,
        recent_ids=recent_ids,
        query=query,
    )

    return {
        "request": request,
        "launcher": {
            "query": query,
            "personas": personas,
            "selected_persona": selected_persona,
            "favorites": favorites,
            "recents": recents,
            "groups": groups,
            "match_count": sum(len(group["entries"]) for group in groups),
            "entry_index": entry_index,
            "page_lane": workbench_ia["pages_by_id"].get("ops_portal_launcher"),
        },
    }


def normalize_agent_coordination(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"summary": {"count": 0, "active": 0, "blocked": 0, "escalated": 0, "completing": 0}, "entries": []}
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        entries = []

    normalized_entries: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        held_locks = item.get("held_locks")
        held_lanes = item.get("held_lanes")
        normalized_entries.append(
            {
                "agent_id": str(item.get("agent_id", "unknown")),
                "session_label": str(item.get("session_label", "session")),
                "current_phase": str(item.get("current_phase", "unknown")),
                "current_target": item.get("current_target"),
                "current_workflow_id": item.get("current_workflow_id"),
                "status": str(item.get("status", "unknown")),
                "blocked_reason": item.get("blocked_reason"),
                "progress_pct": item.get("progress_pct"),
                "held_locks": held_locks if isinstance(held_locks, list) else [],
                "held_lanes": held_lanes if isinstance(held_lanes, list) else [],
                "last_heartbeat": item.get("last_heartbeat"),
                "started_at": item.get("started_at"),
            }
        )

    return {
        "summary": {
            "count": int(summary.get("count", len(normalized_entries))),
            "active": int(summary.get("active", 0)),
            "blocked": int(summary.get("blocked", 0)),
            "escalated": int(summary.get("escalated", 0)),
            "completing": int(summary.get("completing", 0)),
            "generated_at": summary.get("generated_at"),
        },
        "entries": normalized_entries,
    }


async def build_dashboard_context(request: Request) -> dict[str, Any]:
    session = await ensure_session(request)
    repository: PortalRepository = request.app.state.repository
    gateway: Any = request.app.state.gateway_client
    launcher_context = await build_launcher_panel_context(request)

    services = repository.load_service_catalog()
    publications = repository.load_publication_registry()
    workbench_ia = repository.load_workbench_information_architecture()

    capability_contracts = repository.load_capability_contract_catalog()
    dependency_graph = repository.load_dependency_graph()
    maintenance_windows = repository.load_maintenance_windows()
    live_apply_receipts = repository.load_live_apply_receipts(services)
    deployments = repository.recent_deployments(services, receipts=live_apply_receipts)
    drift_report = repository.latest_drift_report()
    changelog_notes = repository.changelog_notes()

    try:
        health_payload = await gateway.fetch_platform_health(
            token=read_api_token(session, request.app.state.settings),
        )
    except Exception as exc:  # noqa: BLE001
        health_payload = {"warning": str(exc)}
    try:
        runbook_payload = await gateway.fetch_runbooks(
            token=read_api_token(session, request.app.state.settings),
            delivery_surface="ops_portal",
        )
    except Exception as exc:  # noqa: BLE001
        runbook_payload = {"warning": str(exc), "runbooks": []}
    try:
        runtime_assurance_payload = await gateway.fetch_runtime_assurance(
            token=read_api_token(session, request.app.state.settings),
        )
    except Exception as exc:  # noqa: BLE001
        runtime_assurance_payload = {"warning": str(exc), "entries": []}
    try:
        coordination_payload = await gateway.fetch_agent_coordination(
            token=read_api_token(session, request.app.state.settings),
        )
    except Exception as exc:  # noqa: BLE001
        coordination_payload = {"warning": str(exc)}

    health = normalize_health(health_payload, services)
    runtime_assurance = normalize_runtime_assurance(runtime_assurance_payload, services)
    coordination = normalize_agent_coordination(coordination_payload)
    raw_runbooks = runbook_payload.get("runbooks") if isinstance(runbook_payload, dict) else []
    runbooks = raw_runbooks if isinstance(raw_runbooks, list) else []
    capability_models, capability_summary = build_capability_contract_models(capability_contracts, services)
    service_models = build_service_models(
        services,
        publications,
        health,
        drift_report,
        maintenance_windows,
        deployments,
        request.app.state.settings,
    )
    assurance_rows, assurance_summary = build_runtime_assurance_models(
        services,
        publications,
        health_payload if isinstance(health_payload, dict) else {},
        live_apply_receipts,
    )
    active_maintenance = [window for window in maintenance_windows if window.get("service_id")]
    drift_summary = drift_report.get("summary", {})
    chart_models = {
        "health_mix": build_health_mix_chart(service_models),
        "coordination_status": build_coordination_status_chart(coordination),
        "live_apply_timeline": build_live_apply_timeline_chart(deployments),
        "dependency_focus": build_dependency_focus_chart(dependency_graph, service_models),
    }
    section_counts = {
        "overview": len(service_models),
        "deployments": len(deployments),
        "agents": int(coordination.get("summary", {}).get("count", 0)),
        "runtime-assurance": int(runtime_assurance_summary.get("row_count", 0)),
        "drift": int(drift_summary.get("unsuppressed_count", 0) or 0),
        "search": len(available_collections()),
        "runbooks": len(runbooks),
        "changelog": len(changelog_notes),
    }
    shell_navigation = build_shell_navigation(workbench_ia["pages"], section_counts)

    return {
        "request": request,
        "operator": session,
        "services": service_models,
        "runtime_assurance_rows": assurance_rows,
        "runtime_assurance_summary": assurance_summary,
        "capability_contracts": capability_models,
        "capability_contract_summary": capability_summary,
        "maintenance_windows": active_maintenance,
        "maintenance_count": len(active_maintenance),
        "runbooks": build_runbook_models(runbooks, workbench_ia),
        "deployments": deployments[:10],
        "changelog_notes": changelog_notes,
        "drift_report": drift_report,
        "drift_summary": drift_summary,
        "health_warning": health_payload.get("warning") if isinstance(health_payload, dict) else None,
        "runtime_assurance": runtime_assurance,
        "runtime_assurance_warning": (
            runtime_assurance_payload.get("warning") if isinstance(runtime_assurance_payload, dict) else None
        ),
        "coordination_warning": coordination_payload.get("warning") if isinstance(coordination_payload, dict) else None,
        "runbook_warning": runbook_payload.get("warning") if isinstance(runbook_payload, dict) else None,
        "coordination": coordination,
        "deployment_events": deployment_console_seed(),
        "charts": chart_models,
        "generated_at": isoformat(utc_now()),
        "docs_base_url": request.app.state.settings.docs_base_url,
        "search_collections": available_collections(),
        "search_results": [],
        "search_query": "",
        "search_collection": "",
        "launcher": launcher_context["launcher"],
        "contextual_help": build_ops_portal_help(request.app.state.settings.docs_base_url),
        "shell_page": workbench_ia["pages_by_id"].get("ops_portal_shell"),
        "page_sections": workbench_ia["pages_by_section"],
        "shell_navigation": shell_navigation,
    }


def sse_encode(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def create_app(
    settings: PortalSettings | None = None,
    *,
    gateway_client: Any | None = None,
) -> FastAPI:
    settings = settings or PortalSettings.from_env()
    portal_gateway_client = gateway_client or GatewayClient(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if isinstance(portal_gateway_client, GatewayClient):
                await portal_gateway_client.close()

    app = FastAPI(title="LV3 Interactive Ops Portal", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="lv3_ops_portal")
    app.mount("/static", StaticFiles(directory=str(template_root() / "static")), name="static")
    templates = Jinja2Templates(directory=str(template_root() / "templates"))
    templates.env.filters["status_tone"] = status_tone
    templates.env.filters["humanize_timestamp"] = humanize_timestamp
    app.state.templates = templates
    app.state.settings = settings
    app.state.repository = PortalRepository(settings)
    app.state.gateway_client = portal_gateway_client
    app.state.event_broker = EventBroker()

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @app.get("/partials/launcher", response_class=HTMLResponse)
    async def launcher_partial(request: Request, query: str = "") -> HTMLResponse:
        context = await build_launcher_panel_context(request, query=query)
        context["page_lane"] = context["launcher"].get("page_lane")
        return templates.TemplateResponse(request=request, name="partials/launcher.html", context=context)

    @app.get("/partials/overview", response_class=HTMLResponse)
    async def overview_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("overview")
        return templates.TemplateResponse(request=request, name="partials/overview.html", context=context)

    @app.get("/partials/drift", response_class=HTMLResponse)
    async def drift_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("drift")
        return templates.TemplateResponse(request=request, name="partials/drift.html", context=context)

    @app.get("/partials/agents", response_class=HTMLResponse)
    async def agents_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("agents")
        return templates.TemplateResponse(request=request, name="partials/agents.html", context=context)

    @app.get("/partials/runtime-assurance", response_class=HTMLResponse)
    async def runtime_assurance_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("runtime-assurance")
        return templates.TemplateResponse(request=request, name="partials/runtime_assurance.html", context=context)

    @app.get("/partials/runbooks", response_class=HTMLResponse)
    async def runbooks_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("runbooks")
        return templates.TemplateResponse(request=request, name="partials/runbooks.html", context=context)

    @app.get("/partials/changelog", response_class=HTMLResponse)
    async def changelog_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("changelog")
        return templates.TemplateResponse(request=request, name="partials/changelog.html", context=context)

    @app.get("/partials/search", response_class=HTMLResponse)
    async def search_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("search")
        return templates.TemplateResponse(request=request, name="partials/search.html", context=context)

    @app.get("/events/deployments")
    async def deployment_events() -> StreamingResponse:
        broker: EventBroker = app.state.event_broker

        async def event_stream():
            async for event in broker.stream():
                yield sse_encode(event["event"], event["data"])

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/actions/launcher/favorites/{item_id}", response_class=HTMLResponse)
    async def toggle_launcher_favorite_action(
        request: Request,
        item_id: str,
        query: str = Form(default=""),
    ) -> HTMLResponse:
        context = await build_launcher_panel_context(request, query=query)
        context["page_lane"] = context["launcher"].get("page_lane")
        entry_index = context["launcher"]["entry_index"]
        if item_id in entry_index:
            toggle_launcher_favorite(request.session, item_id, set(entry_index))
            context = await build_launcher_panel_context(request, query=query)
            context["page_lane"] = context["launcher"].get("page_lane")
        return templates.TemplateResponse(request=request, name="partials/launcher.html", context=context)

    @app.post("/actions/launcher/persona/{persona_id}", response_class=HTMLResponse)
    async def select_launcher_persona_action(
        request: Request,
        persona_id: str,
        query: str = Form(default=""),
    ) -> HTMLResponse:
        context = await build_launcher_panel_context(request, query=query)
        context["page_lane"] = context["launcher"].get("page_lane")
        personas = context["launcher"]["personas"]
        if any(str(persona["id"]) == persona_id for persona in personas):
            request.session["launcher_persona"] = persona_id
            context = await build_launcher_panel_context(request, query=query)
            context["page_lane"] = context["launcher"].get("page_lane")
        return templates.TemplateResponse(request=request, name="partials/launcher.html", context=context)

    @app.get("/launcher/go/{item_id}")
    async def launcher_go(request: Request, item_id: str) -> RedirectResponse:
        context = await build_launcher_panel_context(request)
        entry = context["launcher"]["entry_index"].get(item_id)
        if entry is None:
            return RedirectResponse(url="/", status_code=303)
        record_launcher_recent(request.session, item_id, set(context["launcher"]["entry_index"]))
        return RedirectResponse(url=str(entry["href"]), status_code=303)

    @app.post("/actions/services/{service_id}/health-check", response_class=HTMLResponse)
    async def health_check_action(request: Request, service_id: str) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        try:
            result = await gateway.fetch_service_health(
                service_id,
                token=read_api_token(session, request.app.state.settings),
            )
            status = result.get("status", "unknown")
            detail = result.get("detail") or result.get("message") or "Health check completed."
            tone = status_tone(status)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            detail = str(exc)
            tone = "danger"

        context = {
            "request": request,
            "result": {
                "title": f"Health check: {service_id}",
                "status": status,
                "detail": detail,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/services/{service_id}/deploy", response_class=HTMLResponse)
    async def deploy_action(request: Request, service_id: str, restart_only: bool = Form(default=False)) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        broker: EventBroker = request.app.state.event_broker
        try:
            result = await gateway.trigger_deploy(
                service_id,
                token=read_api_token(session, request.app.state.settings),
                restart_only=restart_only,
            )
            job_id = result.get("job_id", "queued")
            summary = result.get("message") or ("Restart queued." if restart_only else "Deployment queued.")
            await broker.publish(
                f"{service_id}: {summary}",
                event_type="deploy",
                metadata={"service": service_id, "job_id": job_id, "restart_only": restart_only},
            )
            tone = "ok"
            status = "queued"
        except Exception as exc:  # noqa: BLE001
            job_id = ""
            summary = str(exc)
            tone = "danger"
            status = "failed"
            await broker.publish(f"{service_id}: deployment failed - {summary}", event_type="deploy")

        context = {
            "request": request,
            "result": {
                "title": f"{'Restart' if restart_only else 'Deploy'}: {service_id}",
                "status": status,
                "detail": summary,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
                "job_id": job_id,
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/services/{service_id}/rotate-secret", response_class=HTMLResponse)
    async def rotate_secret_action(request: Request, service_id: str) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        broker: EventBroker = request.app.state.event_broker
        try:
            result = await gateway.rotate_secret(
                service_id,
                token=read_api_token(session, request.app.state.settings),
            )
            summary = result.get("message") or "Secret rotation queued."
            tone = "ok"
            status = "queued"
            await broker.publish(f"{service_id}: {summary}", event_type="secret", metadata={"service": service_id})
        except Exception as exc:  # noqa: BLE001
            summary = str(exc)
            tone = "danger"
            status = "failed"
        context = {
            "request": request,
            "result": {
                "title": f"Rotate secret: {service_id}",
                "status": status,
                "detail": summary,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/runbooks/{runbook_id}", response_class=HTMLResponse)
    async def launch_runbook_action(
        request: Request,
        runbook_id: str,
        parameters: str = Form(default="{}"),
    ) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        broker: EventBroker = request.app.state.event_broker
        try:
            parsed_parameters = json.loads(parameters) if parameters.strip() else {}
            if not isinstance(parsed_parameters, dict):
                raise ValueError("Runbook parameters must be a JSON object.")
            result = await gateway.launch_runbook(
                runbook_id,
                token=read_api_token(session, request.app.state.settings),
                parameters=parsed_parameters,
            )
            status = str(result.get("status") or "completed")
            detail = result.get("message") or f"Runbook {runbook_id} finished with status {status}."
            tone = "ok" if status == "completed" else "danger" if status == "failed" else "warn"
            await broker.publish(
                f"{runbook_id}: {detail}",
                event_type="runbook",
                metadata={"runbook_id": runbook_id, "status": status},
            )
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            tone = "danger"
            status = "failed"

        context = {
            "request": request,
            "result": {
                "title": f"Runbook: {runbook_id}",
                "status": status,
                "detail": detail,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/search", response_class=HTMLResponse)
    async def search_action(
        request: Request,
        query: str = Form(default=""),
        collection: str = Form(default=""),
    ) -> HTMLResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        context = await build_dashboard_context(request)
        context["search_query"] = query
        context["search_collection"] = collection
        context["page_lane"] = context["page_sections"].get("search")
        if not query.strip():
            context["search_error"] = "Enter a query to search the platform corpus."
            return templates.TemplateResponse(request=request, name="partials/search.html", context=context)
        try:
            payload = await gateway.search(
                query,
                collection=collection or None,
                token=read_api_token(session, request.app.state.settings),
            )
            context["search_results"] = payload.get("results", [])
            context["search_expanded_query"] = payload.get("expanded_query", query)
        except Exception as exc:  # noqa: BLE001
            context["search_error"] = str(exc)
        return templates.TemplateResponse(request=request, name="partials/search.html", context=context)

    return app


app = create_app()
