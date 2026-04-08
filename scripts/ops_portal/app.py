from __future__ import annotations

import asyncio
import base64
import hashlib
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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


UTC = timezone.utc

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


def normalize_boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_collection_claim(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    candidate = value.strip()
    if not candidate:
        return []
    if candidate.startswith("[") and candidate.endswith("]"):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item).strip()]
    normalized = candidate.replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def decode_unverified_jwt_claims(token: str | None) -> dict[str, Any]:
    if not isinstance(token, str) or token.count(".") < 2:
        return {}
    payload = token.split(".", 2)[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii")).decode("utf-8")
        claims = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}


def normalize_claim_roles(claims: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        roles.extend(parse_collection_claim(realm_access.get("roles")))
    roles.extend(parse_collection_claim(claims.get("roles")))
    normalized: list[str] = []
    for role in roles:
        if role not in normalized:
            normalized.append(role)
    return normalized


def resolve_operator_role(groups: list[str], roles: list[str]) -> str:
    group_set = {group.strip() for group in groups if group.strip()}
    role_set = {role.strip() for role in roles if role.strip()}
    for role_name, known_groups, known_roles in WORKBENCH_ROLE_GROUP_PRIORITY:
        if group_set.intersection(known_groups) or role_set.intersection(known_roles):
            return role_name
    return "viewer"


def append_query_param(url: str, key: str, value: str) -> str:
    parsed = urlsplit(url)
    query_items = [(name, item) for name, item in parse_qsl(parsed.query, keep_blank_values=True) if name != key]
    query_items.append((key, value))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query_items), parsed.fragment))


def safe_requested_url(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    parsed = urlsplit(candidate)
    if parsed.scheme != "https":
        return None
    host = parsed.hostname or ""
    if host == "lv3.org" or host.endswith(".lv3.org"):
        return candidate
    return None


def safe_local_redirect(value: str | None, default: str = "/entry?neutral=1") -> str:
    candidate = safe_requested_url(value)
    if candidate and candidate.startswith("/"):
        return candidate
    return default


def activation_steps_from_request(request: Request) -> list[str]:
    allowed_steps = {step["id"] for step in WORKBENCH_ACTIVATION_STEPS}
    return [
        step_id
        for step_id in parse_collection_claim(request.cookies.get(WORKBENCH_ACTIVATION_STEPS_COOKIE))
        if step_id in allowed_steps
    ]


def activation_skipped_from_request(request: Request) -> bool:
    return normalize_boolish(request.cookies.get(WORKBENCH_ACTIVATION_SKIP_COOKIE))


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

WORKBENCH_HOME_COOKIE = "lv3_workbench_home"
WORKBENCH_ACTIVATION_STEPS_COOKIE = "lv3_workbench_activation_steps"
WORKBENCH_ACTIVATION_SKIP_COOKIE = "lv3_workbench_activation_skip"
WORKBENCH_PREFERENCE_COOKIE_MAX_AGE = 180 * 24 * 60 * 60
WORKBENCH_HOME_CANDIDATE_IDS = (
    "service:homepage",
    "service:ops_portal",
    "service:docs_portal",
    "service:changelog_portal",
)
WORKBENCH_DEFAULT_HOME_BY_ROLE = {
    "viewer": "service:homepage",
    "operator": "service:ops_portal",
    "admin": "service:ops_portal",
}
WORKBENCH_ROLE_HOME_META = {
    "viewer": {
        "role_label": "Viewer",
        "entry_mode": "observe-first",
        "mode_label": "Observe-first home",
        "mode_description": "Start from the Homepage so status, discovery, and read-only references are the first things you see.",
    },
    "operator": {
        "role_label": "Operator",
        "entry_mode": "operate-first",
        "mode_label": "Operate-first home",
        "mode_description": "Start from the ops portal so governed actions, drift, and live operations are front and center.",
    },
    "admin": {
        "role_label": "Admin",
        "entry_mode": "govern-and-change",
        "mode_label": "Govern-and-change home",
        "mode_description": "Start from the ops portal with the administration lane in view for identity, control-plane, and change-heavy work.",
    },
}
WORKBENCH_HOME_DESCRIPTIONS = {
    "service:homepage": "Discovery dashboard for observe-first entry and broad service orientation.",
    "service:ops_portal": "Governed control surface for operations, drift review, and bounded platform change.",
    "service:docs_portal": "Reference-first home for ADRs, runbooks, and repo-governed explanations.",
    "service:changelog_portal": "Change-history home for deployment review, receipts, and recent platform movement.",
}
WORKBENCH_ACTIVATION_STEPS = (
    {
        "id": "compare-home-surfaces",
        "title": "Compare the available home surfaces",
        "description": "Review Homepage, Ops Portal, Docs, and Changelog before you pin a preferred home.",
    },
    {
        "id": "verify-launcher-path",
        "title": "Verify the shared launcher path",
        "description": "Use the shared application launcher so switching surfaces stays one click away after sign-in.",
    },
    {
        "id": "open-orientation-runbook",
        "title": "Open the orientation runbook",
        "description": "Keep the authoritative onboarding and portal guidance one click away while you settle on a home surface.",
    },
)
WORKBENCH_ROLE_GROUP_PRIORITY = (
    ("admin", {"/lv3-platform-admins", "lv3-platform-admins"}, {"platform-admin"}),
    ("operator", {"/lv3-platform-operators", "lv3-platform-operators"}, {"platform-operator"}),
    (
        "viewer",
        {"/lv3-platform-viewers", "lv3-platform-viewers", "/grafana-viewers", "grafana-viewers"},
        {"platform-read"},
    ),
)

LAUNCHER_PURPOSE_ORDER = ("operate", "observe", "learn", "plan", "administer")
LAUNCHER_PURPOSE_LABELS = {
    "operate": "Operate",
    "observe": "Observe",
    "learn": "Learn",
    "plan": "Plan",
    "administer": "Administer",
}
LAUNCHER_PURPOSE_BY_CATEGORY = {
    "automation": "operate",
    "communication": "plan",
    "data": "learn",
    "infrastructure": "administer",
    "observability": "observe",
    "security": "administer",
    "access": "administer",
}
LAUNCHER_PURPOSE_OVERRIDES = {
    "changelog_portal": "learn",
    "coolify": "operate",
    "coolify_apps": "operate",
    "docs_portal": "learn",
    "gitea": "plan",
    "grafana": "observe",
    "headscale": "administer",
    "homepage": "operate",
    "keycloak": "administer",
    "langfuse": "observe",
    "netbox": "plan",
    "ops_portal": "operate",
    "outline": "learn",
    "plane": "plan",
    "portainer": "administer",
    "proxmox_ui": "administer",
    "realtime": "observe",
    "status_page": "observe",
    "uptime_kuma": "observe",
    "windmill": "operate",
}
LAUNCHER_PERSONAS_BY_PURPOSE = {
    "operate": ["operator", "administrator"],
    "observe": ["observer", "operator"],
    "learn": ["planner", "operator"],
    "plan": ["planner", "operator"],
    "administer": ["administrator", "operator"],
}
DEFAULT_PERSONA_CATALOG = {
    "personas": [
        {
            "id": "operator",
            "name": "Operator",
            "description": "Day-to-day runtime operations and service switching.",
            "default": True,
            "focus_purposes": ["operate", "observe", "learn"],
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
            "focus_purposes": ["observe", "operate", "administer"],
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
            "focus_purposes": ["plan", "learn", "operate"],
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
            "focus_purposes": ["administer", "operate", "observe"],
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
ACTIVATION_SESSION_KEY = "activation_checklist"
ACTIVATION_STATUS_ORDER = {"todo": 0, "skipped": 1, "completed": 2}
DEFAULT_ACTIVATION_CHECKLIST = {
    "schema_version": "1.0.0",
    "stages": [],
    "progressive_reveal": {
        "advanced_stage_id": "",
        "required_stage_ids": [],
        "locked_launcher_purposes": [],
        "locked_service_actions": [],
        "locked_runbook_execution_classes": [],
    },
}


def browser_usable_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate.startswith(("http://", "https://")):
        return candidate
    return None


def include_live_apply_receipt_path(path: Path) -> bool:
    return not any(part in LIVE_APPLY_RECEIPT_EXCLUDED_PARTS for part in path.parts)


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


def normalize_navigation_contract(payload: Any, *, default_lane: str = "start") -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    primary_lane = normalize_task_lane(payload.get("primary_lane"), default=default_lane)
    secondary_lanes = [
        lane for lane in normalize_task_lane_list(payload.get("secondary_lanes", [])) if lane != primary_lane
    ]
    next_success_lane = normalize_task_lane(payload.get("next_success_lane"), default=primary_lane)
    next_failure_lane = normalize_task_lane(payload.get("next_failure_lane"), default="recover")
    return {
        "primary_lane": primary_lane,
        "primary_lane_label": TASK_LANE_LABELS[primary_lane],
        "secondary_lanes": secondary_lanes,
        "secondary_lanes_csv": ",".join(secondary_lanes),
        "next_success_lane": next_success_lane,
        "next_success_lane_label": TASK_LANE_LABELS[next_success_lane],
        "next_failure_lane": next_failure_lane,
        "next_failure_lane_label": TASK_LANE_LABELS[next_failure_lane],
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
            payload.get("service_category_defaults", {})
            if isinstance(payload.get("service_category_defaults"), dict)
            else {}
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
                normalize_navigation_contract(
                    {"primary_lane": "observe", "secondary_lanes": ["learn"]},
                    default_lane="observe",
                ),
            ),
            "mutation": workflow_defaults.get(
                "mutation",
                normalize_navigation_contract(
                    {"primary_lane": "change", "secondary_lanes": ["observe"]},
                    default_lane="change",
                ),
            ),
        },
        "workflow_overrides": index_contracts(payload.get("workflow_overrides"), "workflow_id", default_lane="change"),
        "runbook_defaults": {
            "diagnostic": runbook_defaults.get(
                "diagnostic",
                normalize_navigation_contract(
                    {"primary_lane": "learn", "secondary_lanes": ["observe"]},
                    default_lane="learn",
                ),
            ),
            "mutation": runbook_defaults.get(
                "mutation",
                normalize_navigation_contract(
                    {"primary_lane": "change", "secondary_lanes": ["recover"]},
                    default_lane="change",
                ),
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


def launcher_purpose_for_service(service: dict[str, Any]) -> str:
    service_id = str(service.get("id", ""))
    if service_id in LAUNCHER_PURPOSE_OVERRIDES:
        return LAUNCHER_PURPOSE_OVERRIDES[service_id]
    category = str(service.get("category", ""))
    return LAUNCHER_PURPOSE_BY_CATEGORY.get(category, "operate")


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
        focus_lanes = normalize_task_lane_list(item.get("focus_lanes", item.get("focus_purposes", [])))
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


def normalize_activation_catalog(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = DEFAULT_ACTIVATION_CHECKLIST
    stages = payload.get("stages")
    if not isinstance(stages, list):
        stages = []
    progressive_reveal = payload.get("progressive_reveal")
    if not isinstance(progressive_reveal, dict):
        progressive_reveal = {}
    return {
        "schema_version": str(payload.get("schema_version", "1.0.0")),
        "stages": [stage for stage in stages if isinstance(stage, dict)],
        "progressive_reveal": {
            "advanced_stage_id": str(progressive_reveal.get("advanced_stage_id", "")).strip(),
            "required_stage_ids": [
                stage_id
                for stage_id in progressive_reveal.get("required_stage_ids", [])
                if isinstance(stage_id, str) and stage_id.strip()
            ],
            "locked_launcher_purposes": [
                purpose
                for purpose in progressive_reveal.get("locked_launcher_purposes", [])
                if isinstance(purpose, str) and purpose.strip()
            ],
            "locked_service_actions": [
                action
                for action in progressive_reveal.get("locked_service_actions", [])
                if isinstance(action, str) and action.strip()
            ],
            "locked_runbook_execution_classes": [
                item
                for item in progressive_reveal.get("locked_runbook_execution_classes", [])
                if isinstance(item, str) and item.strip()
            ],
        },
    }


def service_href_from_catalog(service_id: str, services: list[dict[str, Any]]) -> str | None:
    for service in services:
        if str(service.get("id", "")) != service_id:
            continue
        href = browser_usable_url(service.get("public_url")) or browser_usable_url(service.get("internal_url"))
        if href:
            return "/" if service_id == "ops_portal" else href
    return None


def resolve_activation_link(
    link: dict[str, Any],
    *,
    services: list[dict[str, Any]],
    docs_base_url: str,
) -> dict[str, str] | None:
    link_type = str(link.get("type", "")).strip()
    label = str(link.get("label", "")).strip()
    value = str(link.get("value", "")).strip()
    if not link_type or not label or not value:
        return None
    if link_type == "docs":
        href = f"{docs_base_url}/{value.lstrip('/')}"
    elif link_type == "portal_anchor":
        href = f"/#{value.lstrip('#')}"
    elif link_type == "service":
        href = service_href_from_catalog(value, services)
        if href is None:
            return None
    elif link_type == "url":
        href = value
    else:
        return None
    return {"label": label, "href": href}


def activation_item_catalog(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for stage in catalog.get("stages", []):
        for item in stage.get("items", []):
            item_id = str(item.get("id", "")).strip()
            if item_id:
                items[item_id] = item
    return items


def normalize_activation_session_state(session: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    valid_item_ids = set(activation_item_catalog(catalog))
    raw_state = session.get(ACTIVATION_SESSION_KEY)
    if not isinstance(raw_state, dict):
        raw_state = {}
    raw_items = raw_state.get("items")
    items: dict[str, dict[str, str]] = {}
    if isinstance(raw_items, dict):
        for item_id, payload in raw_items.items():
            if item_id not in valid_item_ids or not isinstance(payload, dict):
                continue
            status = str(payload.get("status", "")).strip()
            if status not in {"todo", "completed", "skipped"}:
                continue
            items[item_id] = {
                "status": status,
                "updated_at": str(payload.get("updated_at", "")).strip(),
            }

    override = bool(raw_state.get("advanced_override"))
    override_updated_at = str(raw_state.get("advanced_override_updated_at", "")).strip()
    normalized = {
        "items": items,
        "advanced_override": override,
        "advanced_override_updated_at": override_updated_at,
    }
    session[ACTIVATION_SESSION_KEY] = normalized
    return normalized


def write_activation_item_state(
    session: dict[str, Any],
    catalog: dict[str, Any],
    *,
    item_id: str,
    status: str,
) -> dict[str, Any]:
    state = normalize_activation_session_state(session, catalog)
    if item_id not in activation_item_catalog(catalog):
        return state
    if status == "todo":
        state["items"].pop(item_id, None)
    elif status in {"completed", "skipped"}:
        state["items"][item_id] = {"status": status, "updated_at": isoformat(utc_now())}
    session[ACTIVATION_SESSION_KEY] = state
    return state


def set_activation_override(session: dict[str, Any], catalog: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
    state = normalize_activation_session_state(session, catalog)
    state["advanced_override"] = enabled
    state["advanced_override_updated_at"] = isoformat(utc_now()) if enabled else ""
    session[ACTIVATION_SESSION_KEY] = state
    return state


def build_activation_context(
    catalog: dict[str, Any],
    state: dict[str, Any],
    *,
    services: list[dict[str, Any]],
    docs_base_url: str,
) -> dict[str, Any]:
    stage_models: list[dict[str, Any]] = []
    item_catalog = activation_item_catalog(catalog)
    required_stage_ids = set(catalog.get("progressive_reveal", {}).get("required_stage_ids", []))
    required_item_ids: set[str] = set()
    completed_required_items = 0

    for stage in catalog.get("stages", []):
        stage_id = str(stage.get("id", "")).strip()
        stage_items = stage.get("items", [])
        item_models: list[dict[str, Any]] = []
        completed_items = 0
        for item in stage_items:
            item_id = str(item.get("id", "")).strip()
            item_state = state.get("items", {}).get(item_id, {})
            item_status = str(item_state.get("status", "todo")) or "todo"
            links = [
                resolved
                for resolved in (
                    resolve_activation_link(link, services=services, docs_base_url=docs_base_url)
                    for link in item.get("links", [])
                )
                if resolved is not None
            ]
            is_done = item_status in {"completed", "skipped"}
            if is_done:
                completed_items += 1
            if stage_id in required_stage_ids:
                required_item_ids.add(item_id)
                if is_done:
                    completed_required_items += 1
            item_models.append(
                {
                    "id": item_id,
                    "title": str(item.get("title", item_id)),
                    "description": str(item.get("description", "")),
                    "status": item_status,
                    "status_label": (
                        "Completed"
                        if item_status == "completed"
                        else "Skipped"
                        if item_status == "skipped"
                        else "To do"
                    ),
                    "updated_at": item_state.get("updated_at"),
                    "links": links,
                }
            )

        stage_models.append(
            {
                "id": stage_id,
                "title": str(stage.get("title", stage_id)),
                "description": str(stage.get("description", "")),
                "items": item_models,
                "item_count": len(item_models),
                "completed_items": completed_items,
                "required": stage_id in required_stage_ids,
                "status": (
                    "completed"
                    if item_models and completed_items == len(item_models)
                    else "in_progress"
                    if completed_items
                    else "todo"
                ),
                "status_label": (
                    "Complete"
                    if item_models and completed_items == len(item_models)
                    else "In progress"
                    if completed_items
                    else "To do"
                ),
            }
        )

    required_complete = completed_required_items >= len(required_item_ids) if required_item_ids else True
    advanced_override = bool(state.get("advanced_override"))
    advanced_unlocked = required_complete or advanced_override
    advanced_stage_id = str(catalog.get("progressive_reveal", {}).get("advanced_stage_id", "")).strip()
    for stage in stage_models:
        if stage["id"] == advanced_stage_id:
            stage["status"] = "completed" if advanced_unlocked else "todo"
            stage["status_label"] = (
                "Revealed for this session"
                if advanced_override
                else "Ready"
                if advanced_unlocked
                else "Locked"
            )
            break

    return {
        "stages": stage_models,
        "required_item_total": len(required_item_ids),
        "required_item_completed": completed_required_items,
        "required_complete": required_complete,
        "advanced_unlocked": advanced_unlocked,
        "advanced_override": advanced_override,
        "advanced_override_updated_at": state.get("advanced_override_updated_at", ""),
        "locked_launcher_purposes": set(
            catalog.get("progressive_reveal", {}).get("locked_launcher_purposes", [])
        ),
        "locked_service_actions": set(
            catalog.get("progressive_reveal", {}).get("locked_service_actions", [])
        ),
        "locked_runbook_execution_classes": set(
            catalog.get("progressive_reveal", {}).get("locked_runbook_execution_classes", [])
        ),
    }


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
        purpose = launcher_purpose_for_service(service)
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
                "purpose": purpose,
                "purpose_label": LAUNCHER_PURPOSE_LABELS[purpose],
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
        purpose = str(launcher.get("purpose", "")).strip()
        if purpose not in LAUNCHER_PURPOSE_LABELS:
            purpose = {
                "start": "plan",
                "observe": "observe",
                "change": "operate",
                "learn": "learn",
                "recover": "administer",
            }.get(navigation["primary_lane"], "operate")
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
                "purpose": purpose,
                "purpose_label": LAUNCHER_PURPOSE_LABELS[purpose],
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


def journey_redirect_url(entry: dict[str, Any], role: str) -> str:
    href = str(entry.get("href", "/")).strip() or "/"
    role_meta = WORKBENCH_ROLE_HOME_META.get(role, WORKBENCH_ROLE_HOME_META["viewer"])
    if entry.get("id") == "service:ops_portal":
        return append_query_param(href, "entry_mode", str(role_meta["entry_mode"]))
    return href


def build_workbench_context(
    request: Request,
    *,
    entry_index: dict[str, dict[str, Any]],
    docs_base_url: str,
) -> dict[str, Any]:
    role = str(request.session.get("operator_role", "viewer"))
    if role not in WORKBENCH_ROLE_HOME_META:
        role = "viewer"
    role_meta = WORKBENCH_ROLE_HOME_META[role]
    completed_steps = activation_steps_from_request(request)
    completed_set = set(completed_steps)
    skipped = activation_skipped_from_request(request)
    activation_ready = skipped or len(completed_set) == len(WORKBENCH_ACTIVATION_STEPS)

    activation_steps: list[dict[str, Any]] = []
    for step in WORKBENCH_ACTIVATION_STEPS:
        activation_steps.append(
            {
                **step,
                "completed": step["id"] in completed_set,
            }
        )

    default_home_id = WORKBENCH_DEFAULT_HOME_BY_ROLE.get(role, WORKBENCH_DEFAULT_HOME_BY_ROLE["viewer"])
    default_home = entry_index.get(default_home_id)
    saved_home_id = request.cookies.get(WORKBENCH_HOME_COOKIE, "").strip()
    saved_home = entry_index.get(saved_home_id) if saved_home_id in WORKBENCH_HOME_CANDIDATE_IDS else None

    home_destinations: list[dict[str, Any]] = []
    for entry_id in WORKBENCH_HOME_CANDIDATE_IDS:
        entry = entry_index.get(entry_id)
        if entry is None:
            continue
        model = dict(entry)
        model["entry_url"] = f"/entry?item_id={entry_id}"
        model["pin_allowed"] = activation_ready
        model["is_saved_home"] = saved_home is not None and saved_home.get("id") == entry_id
        model["is_default_home"] = default_home is not None and default_home.get("id") == entry_id
        model["home_description"] = WORKBENCH_HOME_DESCRIPTIONS.get(entry_id, model.get("description", ""))
        home_destinations.append(model)

    runbook_url = f"{docs_base_url}/runbooks/operator-onboarding/"
    portal_runbook_url = f"{docs_base_url}/runbooks/platform-operations-portal/"

    return {
        "role": role,
        "role_label": role_meta["role_label"],
        "mode_label": role_meta["mode_label"],
        "mode_description": role_meta["mode_description"],
        "activation_steps": activation_steps,
        "activation_completed_steps": completed_steps,
        "activation_completed_count": len(completed_set),
        "activation_remaining_count": max(len(WORKBENCH_ACTIVATION_STEPS) - len(completed_set), 0),
        "activation_total_steps": len(WORKBENCH_ACTIVATION_STEPS),
        "activation_skipped": skipped,
        "activation_ready": activation_ready,
        "default_home": default_home,
        "default_home_redirect": journey_redirect_url(default_home, role) if default_home else "/",
        "saved_home": saved_home,
        "saved_home_redirect": journey_redirect_url(saved_home, role) if saved_home else None,
        "home_destinations": home_destinations,
        "neutral_entry_url": "/entry?neutral=1",
        "runbook_url": runbook_url,
        "portal_runbook_url": portal_runbook_url,
        "saved_home_label": saved_home.get("name") if isinstance(saved_home, dict) else None,
        "default_home_label": default_home.get("name") if isinstance(default_home, dict) else None,
    }


def set_preference_cookie(response: HTMLResponse | RedirectResponse, request: Request, key: str, value: str) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=WORKBENCH_PREFERENCE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


def delete_preference_cookie(response: HTMLResponse | RedirectResponse, key: str) -> None:
    response.delete_cookie(key=key, path="/")


def launcher_entry_locked(entry: dict[str, Any], activation: dict[str, Any]) -> bool:
    return not activation.get("advanced_unlocked", True) and entry.get("purpose") in activation.get(
        "locked_launcher_purposes",
        set(),
    )


def split_launcher_entries(
    entries: list[dict[str, Any]],
    *,
    activation: dict[str, Any],
    persona_id: str,
    query: str,
    favorite_ids: set[str],
    recent_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visible_entries: list[dict[str, Any]] = []
    locked_entries: list[dict[str, Any]] = []
    for entry in entries:
        if not launcher_entry_visible(entry, persona_id, query):
            continue
        if launcher_entry_locked(entry, activation):
            locked_entries.append(decorate_launcher_entry(entry, favorite_ids, recent_ids))
            continue
        visible_entries.append(entry)
    locked_entries.sort(key=lambda item: (item["kind"], item["name"]))
    return visible_entries, locked_entries


def runbook_locked(runbook: dict[str, Any], activation: dict[str, Any]) -> bool:
    return (
        not activation.get("advanced_unlocked", True)
        and str(runbook.get("execution_class", "workflow")) in activation.get("locked_runbook_execution_classes", set())
    )


def action_locked(action_id: str, activation: dict[str, Any]) -> bool:
    return not activation.get("advanced_unlocked", True) and action_id in activation.get("locked_service_actions", set())


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
    promotions_dir: Path
    drift_receipts_dir: Path
    attention_state_path: Path
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
            promotions_dir=Path(
                os.getenv("OPS_PORTAL_PROMOTIONS_DIR", data_root / "receipts" / "promotions")
            ),
            drift_receipts_dir=Path(
                os.getenv("OPS_PORTAL_DRIFT_RECEIPTS_DIR", data_root / "receipts" / "drift-reports")
            ),
            attention_state_path=Path(
                os.getenv("OPS_PORTAL_ATTENTION_STATE_FILE", "/srv/ops-portal/state/attention-state.json")
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

    async def fetch_runbook_task(self, run_id: str, *, token: str | None = None) -> dict[str, Any]:
        return await self._request("GET", f"/v1/platform/runbooks/{run_id}", token=token)

    async def resume_runbook_task(self, run_id: str, *, token: str | None = None) -> dict[str, Any]:
        return await self._request("POST", f"/v1/platform/runbooks/{run_id}/approve", token=token)

    async def fetch_runbook_tasks(
        self,
        *,
        token: str | None = None,
        delivery_surface: str = "ops_portal",
        limit: int = 12,
        statuses: list[str] | None = None,
    ) -> dict[str, Any]:
        params: list[tuple[str, str]] = [("delivery_surface", delivery_surface), ("limit", str(limit))]
        for item in statuses or []:
            params.append(("status", item))
        return await self._request("GET", f"/v1/platform/runbook-tasks?{httpx.QueryParams(params)}", token=token)

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

    def load_activation_checklist(self) -> dict[str, Any]:
        activation_path = self.settings.service_catalog_path.parent / "activation-checklist.json"
        payload = load_json_file(activation_path, DEFAULT_ACTIVATION_CHECKLIST)
        return normalize_activation_catalog(payload)

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
                    "execution_class": workflow.get("execution_class", "workflow"),
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
            verification = [item for item in receipt.get("verification", []) if isinstance(item, dict)]
            verification_results = [str(item.get("result", "")).strip().lower() for item in verification]
            if any(result == "fail" for result in verification_results):
                receipt["_outcome"] = "failure"
            elif any(result == "partial" for result in verification_results):
                receipt["_outcome"] = "partial"
            else:
                receipt["_outcome"] = "success"
            receipt["_environment"] = (
                str(receipt.get("environment", "")).strip().lower()
                or ("staging" if "staging" in receipt_path.parts else "production")
            )
            receipts.append(receipt)
        return receipts

    def load_promotion_receipts(self, services: list[dict[str, Any]]) -> list[dict[str, Any]]:
        service_keywords = self._service_keywords(services)
        receipts: list[dict[str, Any]] = []
        for receipt_path in sorted(self.settings.promotions_dir.rglob("*.json"), reverse=True):
            receipt = load_optional_json_document(receipt_path)
            if not isinstance(receipt, dict):
                continue
            text = normalize_text(json.dumps(receipt, sort_keys=True))
            matched = []
            for service_id, keywords in service_keywords.items():
                if any(keyword and keyword in text for keyword in keywords):
                    matched.append(service_id)
            branch = str(receipt.get("branch", "")).strip()
            playbook = str(receipt.get("playbook", "")).strip()
            gate_decision = str(receipt.get("gate_decision", "")).strip().lower()
            title_parts = [f"Promoted {branch or 'unknown branch'}"]
            if playbook:
                title_parts.append(f"via {playbook}")
            summary = " ".join(title_parts)
            if gate_decision:
                summary = f"{summary}; gate {gate_decision}"
            receipts.append(
                {
                    "promotion_id": str(receipt.get("promotion_id", receipt_path.stem)),
                    "summary": summary,
                    "recorded_on": receipt.get("ts"),
                    "recorded_by": (
                        str(receipt.get("gate_actor", {}).get("id", "")).strip()
                        if isinstance(receipt.get("gate_actor"), dict)
                        else ""
                    )
                    or "promotion-gate",
                    "services": sorted(set(matched)),
                    "path": str(receipt_path),
                    "outcome": "success" if gate_decision == "approved" else "partial",
                    "branch": branch,
                    "playbook": playbook,
                }
            )
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
                    "outcome": str(receipt.get("_outcome", "success")),
                    "source": "live_apply",
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


def stable_token(*parts: Any) -> str:
    raw = "||".join(str(part) for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


class AttentionStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _default_state(self) -> dict[str, Any]:
        return {"version": 1, "items": {}}

    def load(self) -> dict[str, Any]:
        payload = load_optional_json_document(self.path)
        if not isinstance(payload, dict):
            return self._default_state()
        items = payload.get("items")
        if not isinstance(items, dict):
            payload["items"] = {}
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, self.path)

    def current_by_item(self) -> dict[str, dict[str, Any]]:
        current: dict[str, dict[str, Any]] = {}
        payload = self.load()
        for item_id, record in payload.get("items", {}).items():
            if not isinstance(record, dict):
                continue
            entry = record.get("current")
            if isinstance(entry, dict):
                current[str(item_id)] = entry
        return current

    def apply(
        self,
        item_id: str,
        *,
        action: str,
        actor_id: str,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        if action not in {"acknowledged", "dismissed", "reopened"}:
            return
        payload = self.load()
        items = payload.setdefault("items", {})
        record = items.setdefault(item_id, {"history": []})
        if snapshot:
            record["snapshot"] = snapshot
        history = record.setdefault("history", [])
        if not isinstance(history, list):
            history = []
            record["history"] = history
        event = {"action": action, "actor_id": actor_id or "operator", "ts": isoformat(utc_now())}
        history.append(event)
        if action == "reopened":
            record.pop("current", None)
        else:
            record["current"] = {
                "action": action,
                "actor_id": actor_id or "operator",
                "updated_at": event["ts"],
            }
        self._write(payload)

    def history_events(self, *, limit: int = 20) -> list[dict[str, Any]]:
        payload = self.load()
        events: list[dict[str, Any]] = []
        for item_id, record in payload.get("items", {}).items():
            if not isinstance(record, dict):
                continue
            snapshot = record.get("snapshot") if isinstance(record.get("snapshot"), dict) else {}
            history = record.get("history")
            if not isinstance(history, list):
                continue
            for index, entry in enumerate(history):
                if not isinstance(entry, dict):
                    continue
                events.append(
                    {
                        "id": f"attention-action:{item_id}:{index}",
                        "item_id": item_id,
                        "action": str(entry.get("action", "")),
                        "actor_id": str(entry.get("actor_id", "operator")),
                        "occurred_at": entry.get("ts"),
                        "snapshot": snapshot,
                    }
                )
        events.sort(
            key=lambda item: parse_timestamp(item.get("occurred_at")) or datetime(1970, 1, 1, tzinfo=UTC),
            reverse=True,
        )
        return events[:limit]


def docs_href(base_url: str, path: Any) -> str | None:
    if not isinstance(path, str):
        return None
    candidate = path.strip()
    if not candidate:
        return None
    if candidate.startswith(("http://", "https://", "#", "/")):
        return candidate
    normalized = candidate.removeprefix("./")
    return f"{base_url}/{normalized}"


def notification_sort_key(item: dict[str, Any]) -> tuple[int, int, float, str]:
    state_rank = {"active": 0, "acknowledged": 1, "dismissed": 2}
    tone_rank = {"danger": 0, "warn": 1, "ok": 2, "neutral": 3}
    parsed = parse_timestamp(item.get("occurred_at")) or datetime(1970, 1, 1, tzinfo=UTC)
    return (
        state_rank.get(str(item.get("state", "active")), 3),
        tone_rank.get(str(item.get("tone", "neutral")), 4),
        -parsed.timestamp(),
        str(item.get("title", "")),
    )


def build_attention_notifications(
    *,
    services: list[dict[str, Any]],
    runtime_assurance: dict[str, Any],
    coordination: dict[str, Any],
    drift_report: dict[str, Any],
    maintenance_windows: list[dict[str, Any]],
    live_apply_receipts: list[dict[str, Any]],
    docs_base_url: str,
    state_by_item: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    service_index = {str(service.get("id")): service for service in services if isinstance(service, dict)}
    items: list[dict[str, Any]] = []

    for window in maintenance_windows:
        service_id = str(window.get("service_id", "all")).strip() or "all"
        service = service_index.get(service_id, {})
        reason = str(window.get("reason") or "A maintenance window is currently open.")
        item_id = f"maintenance:{stable_token(service_id, window.get('opened_at'), reason)}"
        links = [{"label": "Open overview", "href": "#overview"}]
        runbook_href = docs_href(docs_base_url, service.get("runbook"))
        if runbook_href:
            links.append({"label": "Runbook", "href": runbook_href})
        items.append(
            {
                "id": item_id,
                "title": f"Maintenance window open for {service.get('name', service_id)}",
                "summary": reason,
                "detail": str(window.get("service_id", "all")),
                "occurred_at": window.get("opened_at"),
                "tone": "warn",
                "source_label": "Maintenance window",
                "links": links,
            }
        )

    for entry in runtime_assurance.get("entries", []):
        if not isinstance(entry, dict):
            continue
        overall_status = str(entry.get("overall_status", "unknown"))
        if overall_status == "pass":
            continue
        exception_titles = entry.get("exception_titles")
        detail = (
            ", ".join(str(title) for title in exception_titles[:3])
            if isinstance(exception_titles, list) and exception_titles
            else "Fresh governed evidence is still missing for this surface."
        )
        links = [{"label": "Open runtime assurance", "href": "#runtime-assurance"}]
        runbook_href = docs_href(docs_base_url, entry.get("runbook"))
        if runbook_href:
            links.append({"label": "Runbook", "href": runbook_href})
        if browser_usable_url(entry.get("primary_url")):
            links.append({"label": "Surface", "href": str(entry.get("primary_url"))})
        item_id = f"runtime-assurance:{stable_token(entry.get('service_id'), entry.get('environment'), entry.get('profile_id'))}"
        items.append(
            {
                "id": item_id,
                "title": f"{entry.get('service_name', entry.get('service_id', 'surface'))} needs runtime follow-up",
                "summary": f"{entry.get('profile_title', 'Runtime assurance')} is {overall_status}.",
                "detail": detail,
                "occurred_at": runtime_assurance.get("generated_at"),
                "tone": status_tone(overall_status),
                "source_label": "Runtime assurance",
                "links": links,
            }
        )

    for entry in coordination.get("entries", []):
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "unknown"))
        if status not in {"blocked", "escalated"}:
            continue
        blocked_reason = str(entry.get("blocked_reason") or "This session needs human follow-up.")
        item_id = f"coordination:{stable_token(entry.get('agent_id'), entry.get('current_phase'), status)}"
        items.append(
            {
                "id": item_id,
                "title": f"{entry.get('session_label', entry.get('agent_id', 'agent session'))} is {status}",
                "summary": blocked_reason,
                "detail": str(entry.get("current_target") or entry.get("current_workflow_id") or "No target recorded"),
                "occurred_at": entry.get("last_heartbeat") or entry.get("started_at"),
                "tone": status_tone(status),
                "source_label": "Agent coordination",
                "links": [{"label": "Open agent coordination", "href": "#agents"}],
            }
        )

    drift_summary = drift_report.get("summary", {}) if isinstance(drift_report, dict) else {}
    drift_generated_at = drift_report.get("generated_at") if isinstance(drift_report, dict) else None
    for record in drift_report.get("records", []) if isinstance(drift_report, dict) else []:
        if not isinstance(record, dict):
            continue
        service_id = str(record.get("service") or record.get("resource") or "platform")
        service = service_index.get(service_id, {})
        severity = str(record.get("severity") or drift_summary.get("status") or "warn")
        links = [{"label": "Open drift panel", "href": "#drift"}]
        runbook_href = docs_href(docs_base_url, service.get("runbook"))
        if runbook_href:
            links.append({"label": "Runbook", "href": runbook_href})
        item_id = f"drift:{stable_token(service_id, record.get('source'), record.get('detail'))}"
        items.append(
            {
                "id": item_id,
                "title": f"Drift detected for {service.get('name', service_id)}",
                "summary": str(record.get("detail") or "Repo and live state diverged."),
                "detail": str(record.get("source") or "drift report"),
                "occurred_at": drift_generated_at,
                "tone": status_tone(severity),
                "source_label": "Drift report",
                "links": links,
            }
        )

    for receipt in live_apply_receipts:
        if str(receipt.get("_outcome", "success")) == "success":
            continue
        matched_services = receipt.get("_matched_services")
        if not isinstance(matched_services, list):
            matched_services = []
        item_id = f"live-apply:{stable_token(receipt.get('receipt_id'), receipt.get('_path'))}"
        items.append(
            {
                "id": item_id,
                "title": str(receipt.get("summary") or "Live apply needs review"),
                "summary": f"Latest recorded outcome: {receipt.get('_outcome', 'unknown')}.",
                "detail": ", ".join(str(service_id) for service_id in matched_services) or "Affected services not inferred.",
                "occurred_at": receipt.get("recorded_on") or receipt.get("applied_on"),
                "tone": "danger" if receipt.get("_outcome") == "failure" else "warn",
                "source_label": "Live apply receipt",
                "links": [{"label": "Open activity timeline", "href": "#changelog"}],
            }
        )

    for item in items:
        state = state_by_item.get(item["id"], {})
        action = str(state.get("action", "")).strip().lower()
        if action == "acknowledged":
            item["state"] = "acknowledged"
        elif action == "dismissed":
            item["state"] = "dismissed"
        else:
            item["state"] = "active"
        item["updated_at"] = state.get("updated_at")
        item["updated_by"] = state.get("actor_id")

    ordered = sorted(items, key=notification_sort_key)
    groups = {
        "active": [item for item in ordered if item["state"] == "active"],
        "acknowledged": [item for item in ordered if item["state"] == "acknowledged"],
        "dismissed": [item for item in ordered if item["state"] == "dismissed"],
    }
    return {
        "all": ordered,
        "groups": groups,
        "summary": {
            "active_count": len(groups["active"]),
            "acknowledged_count": len(groups["acknowledged"]),
            "dismissed_count": len(groups["dismissed"]),
        },
    }


def build_activity_items(
    *,
    deployments: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    attention_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for deployment in deployments:
        services = deployment.get("services")
        if not isinstance(services, list):
            services = []
        items.append(
            {
                "id": f"activity:deployment:{deployment.get('id')}",
                "title": str(deployment.get("summary") or deployment.get("id") or "Live apply"),
                "summary": ", ".join(str(service_id) for service_id in services) or "Service inference unavailable.",
                "occurred_at": deployment.get("recorded_on"),
                "tone": "danger" if deployment.get("outcome") == "failure" else status_tone(str(deployment.get("outcome", "success"))),
                "source_label": "Live apply",
                "meta": str(deployment.get("recorded_by", "unknown")),
                "links": [{"label": "Open activity timeline", "href": "#changelog"}],
            }
        )

    for promotion in promotions:
        items.append(
            {
                "id": f"activity:promotion:{promotion.get('promotion_id')}",
                "title": str(promotion.get("summary") or promotion.get("promotion_id") or "Promotion"),
                "summary": ", ".join(str(service_id) for service_id in promotion.get("services", []))
                or "Promotion metadata did not resolve a concrete service set.",
                "occurred_at": promotion.get("recorded_on"),
                "tone": status_tone(str(promotion.get("outcome", "partial"))),
                "source_label": "Promotion",
                "meta": str(promotion.get("recorded_by", "promotion-gate")),
                "links": [{"label": "Open activity timeline", "href": "#changelog"}],
            }
        )

    for history in attention_history:
        snapshot = history.get("snapshot") if isinstance(history.get("snapshot"), dict) else {}
        action = str(history.get("action", "updated"))
        title = str(snapshot.get("title") or "Notification state changed")
        actor = str(history.get("actor_id", "operator"))
        items.append(
            {
                "id": str(history.get("id")),
                "title": f"{title} was {action}",
                "summary": str(snapshot.get("summary") or "Notification center state changed without deleting the source event."),
                "occurred_at": history.get("occurred_at"),
                "tone": "warn" if action == "dismissed" else "ok" if action == "acknowledged" else "neutral",
                "source_label": "Notification center",
                "meta": actor,
                "links": [{"label": "Open notification center", "href": str(snapshot.get("href") or "#attention")}],
            }
        )

    items.sort(
        key=lambda item: parse_timestamp(item.get("occurred_at")) or datetime(1970, 1, 1, tzinfo=UTC),
        reverse=True,
    )
    return items[:16]


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
    activation: dict[str, Any],
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
                "actions_locked": not activation.get("advanced_unlocked", True),
                "locked_actions": sorted(activation.get("locked_service_actions", set())),
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
    operator_id = request.headers.get("x-auth-request-user", "").strip()
    operator_email = request.headers.get("x-auth-request-email", "").strip()
    if operator_id:
        session["operator_id"] = operator_id
    elif "operator_id" not in session:
        session["operator_id"] = "operator"
    if operator_email:
        session["operator_email"] = operator_email
    elif "operator_email" not in session:
        session["operator_email"] = ""

    forwarded_token = request.headers.get("x-forwarded-access-token") or request.headers.get("authorization", "")
    if forwarded_token.startswith("Bearer "):
        forwarded_token = forwarded_token.removeprefix("Bearer ").strip()
    if forwarded_token:
        session["api_token"] = forwarded_token

    claims = decode_unverified_jwt_claims(session.get("api_token", ""))
    groups = parse_collection_claim(request.headers.get("x-auth-request-groups"))
    if not groups:
        groups = parse_collection_claim(claims.get("groups"))
    roles = normalize_claim_roles(claims)
    session["operator_groups"] = groups
    session["operator_role"] = resolve_operator_role(groups, roles)
    return {
        "operator_id": session.get("operator_id", "operator"),
        "operator_email": session.get("operator_email", ""),
        "api_token": session.get("api_token", ""),
        "operator_role": session.get("operator_role", "viewer"),
    }


def read_api_token(session: dict[str, str], settings: PortalSettings) -> str | None:
    return session.get("api_token") or settings.static_api_token


@lru_cache(maxsize=1)
def template_root() -> Path:
    return Path(__file__).resolve().parent


def build_runbook_models(
    runbooks: list[dict[str, Any]],
    activation: dict[str, Any],
    workbench_ia: dict[str, Any],
    latest_tasks_by_runbook: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
    task_index = latest_tasks_by_runbook or {}
    visible: list[dict[str, Any]] = []
    locked: list[dict[str, Any]] = []
    for item in combined[:6]:
        model = dict(item)
        latest_task = task_index.get(str(model.get("id", "")))
        if latest_task is not None:
            model["latest_task"] = latest_task
        if runbook_locked(model, activation):
            locked.append(model)
        else:
            visible.append(model)
    return visible, locked


def enrich_runbook_metadata(
    runbooks: list[dict[str, Any]],
    workflows: dict[str, Any],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in runbooks:
        if not isinstance(item, dict):
            continue
        runbook = dict(item)
        runbook_id = str(runbook.get("id", "")).strip()
        workflow = workflows.get(runbook_id, {}) if runbook_id else {}
        if not isinstance(workflow, dict):
            workflow = {}
        for field in ("description", "owner_runbook", "execution_class", "live_impact"):
            if not runbook.get(field) and workflow.get(field):
                runbook[field] = workflow[field]
        enriched.append(runbook)
    return enriched


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_task_step_reference(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    label = str(value.get("label") or value.get("id") or "").strip()
    if not label:
        return None
    normalized = {"label": label}
    if value.get("id"):
        normalized["id"] = str(value["id"])
    if value.get("type"):
        normalized["type"] = str(value["type"])
    if value.get("workflow_id"):
        normalized["workflow_id"] = str(value["workflow_id"])
    return normalized


def default_task_headline(runbook_title: str, *, status: str, attention_required: bool) -> str:
    if attention_required:
        return f"Paused {runbook_title}"
    if status == "completed":
        return f"Completed {runbook_title}"
    if status == "running":
        return f"In progress at {runbook_title}"
    return f"Task summary for {runbook_title}"


def normalize_task_model(task: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(task)
    run_id = str(task.get("run_id") or "").strip()
    runbook_id = str(task.get("runbook_id") or "").strip() or "unknown-runbook"
    runbook_title = str(task.get("runbook_title") or runbook_id or "Runbook task").strip() or "Runbook task"
    status = str(task.get("status") or "unknown").strip() or "unknown"
    attention_required = bool(task.get("attention_required")) or status == "escalated"
    portal_path = str(task.get("portal_path") or f"/tasks/runbooks/{run_id}").strip() or "/tasks/runbooks"

    progress = task.get("progress") if isinstance(task.get("progress"), dict) else {}
    completed_steps = max(coerce_int(progress.get("completed_steps"), 0), 0)
    total_steps = max(coerce_int(progress.get("total_steps"), completed_steps), completed_steps)
    percent = coerce_int(progress.get("percent"), 0)
    if total_steps == 0 and completed_steps > 0:
        total_steps = completed_steps
    percent = min(max(percent, 0), 100)
    if percent == 0 and total_steps > 0 and completed_steps >= total_steps:
        percent = 100

    summary = task.get("summary") if isinstance(task.get("summary"), dict) else {}
    last_safe_resume_point = (
        summary.get("last_safe_resume_point") if isinstance(summary.get("last_safe_resume_point"), dict) else {}
    )
    next_step = normalize_task_step_reference(summary.get("next_step"))
    next_irreversible_step = normalize_task_step_reference(summary.get("next_irreversible_step"))

    if attention_required:
        default_next_human_action = "Review the saved evidence, then resume when you are ready."
    elif status == "completed":
        default_next_human_action = "Review the saved evidence or launch a fresh run when you need another pass."
    elif status == "running":
        default_next_human_action = "Reopen this task to inspect the latest committed progress."
    else:
        default_next_human_action = "Open the task summary to inspect the saved evidence."

    normalized["run_id"] = run_id
    normalized["runbook_id"] = runbook_id
    normalized["runbook_title"] = runbook_title
    normalized["status"] = status
    normalized["attention_required"] = attention_required
    normalized["resume_available"] = bool(task.get("resume_available")) or attention_required
    normalized["portal_path"] = portal_path
    normalized["progress"] = {
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "percent": percent,
    }
    normalized["params"] = task.get("params") if isinstance(task.get("params"), dict) else {}
    normalized["summary"] = {
        "headline": str(
            summary.get("headline")
            or default_task_headline(runbook_title, status=status, attention_required=attention_required)
        ),
        "what_happened": str(
            summary.get("what_happened")
            or f"{runbook_title} state is available for reentry, but the detailed summary has not been recorded yet."
        ),
        "next_human_action": str(summary.get("next_human_action") or default_next_human_action),
        "last_safe_resume_point": {
            "step_id": last_safe_resume_point.get("step_id"),
            "label": str(last_safe_resume_point.get("label") or "Saved state"),
            "timestamp": last_safe_resume_point.get("timestamp"),
            "message": str(
                last_safe_resume_point.get("message")
                or "Saved run state is available, but the last safe resume point was not recorded."
            ),
        },
        "next_step": next_step,
        "next_irreversible_step": next_irreversible_step,
        "mutation_state": str(summary.get("mutation_state") or "Mutation state is not available for this task yet."),
    }

    evidence = task.get("evidence") if isinstance(task.get("evidence"), list) else []
    normalized["evidence"] = [
        {
            "label": str(item.get("label") or item.get("step_id") or "Recorded evidence"),
            "status": str(item.get("status") or "unknown"),
            "finished_at": item.get("finished_at"),
            "detail": str(item.get("detail") or ""),
        }
        for item in evidence
        if isinstance(item, dict)
    ]

    activity = task.get("activity") if isinstance(task.get("activity"), list) else []
    normalized["activity"] = [
        {
            "title": str(item.get("title") or "Task update"),
            "detail": str(item.get("detail") or "Saved task state updated."),
            "timestamp": item.get("timestamp"),
            "status": str(item.get("status") or "unknown"),
            "portal_path": str(item.get("portal_path") or portal_path),
            "runbook_title": str(item.get("runbook_title") or runbook_title),
        }
        for item in activity
        if isinstance(item, dict)
    ]
    normalized["steps"] = task.get("steps") if isinstance(task.get("steps"), list) else []
    return normalized


def build_task_panel_model(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [normalize_task_model(item) for item in tasks if isinstance(item, dict)]
    attention = [item for item in normalized if item.get("attention_required")]
    latest_by_runbook: dict[str, dict[str, Any]] = {}
    for item in normalized:
        runbook_id = str(item.get("runbook_id", "")).strip()
        if runbook_id and runbook_id not in latest_by_runbook:
            latest_by_runbook[runbook_id] = item

    activity: list[dict[str, Any]] = []
    seen_activity: set[tuple[str, str, str]] = set()
    for item in normalized:
        for event in item.get("activity", []):
            if not isinstance(event, dict):
                continue
            key = (
                str(item.get("run_id", "")),
                str(event.get("timestamp", "")),
                str(event.get("title", "")),
            )
            if key in seen_activity:
                continue
            seen_activity.add(key)
            activity.append(
                {
                    "run_id": item.get("run_id"),
                    "runbook_id": item.get("runbook_id"),
                    "runbook_title": item.get("runbook_title"),
                    "portal_path": event.get("portal_path") or item.get("portal_path"),
                    "title": event.get("title"),
                    "detail": event.get("detail"),
                    "timestamp": event.get("timestamp"),
                    "status": event.get("status"),
                }
            )
    activity.sort(key=lambda entry: str(entry.get("timestamp") or ""), reverse=True)

    return {
        "attention": attention[:4],
        "recent": normalized[:6],
        "activity": activity[:8],
        "attention_count": len(attention),
        "recent_count": len(normalized),
        "latest_by_runbook": latest_by_runbook,
    }


async def build_launcher_panel_context(request: Request, *, query: str = "") -> dict[str, Any]:
    operator = await ensure_session(request)
    repository: PortalRepository = request.app.state.repository

    services = repository.load_service_catalog()
    publications = repository.load_publication_registry()
    workflows = repository.load_workflow_definitions()
    workbench_ia = repository.load_workbench_information_architecture()
    personas = repository.load_persona_catalog()
    activation_catalog = repository.load_activation_checklist()
    activation_state = normalize_activation_session_state(request.session, activation_catalog)
    activation = build_activation_context(
        activation_catalog,
        activation_state,
        services=services,
        docs_base_url=request.app.state.settings.docs_base_url,
    )

    entries = build_launcher_entries(services, publications, workflows, workbench_ia)
    valid_entry_ids = {entry["id"] for entry in entries}
    preferences = ensure_launcher_preferences(request.session, personas, valid_entry_ids)
    selected_persona = preferences["selected_persona"]
    favorite_ids = set(preferences["favorite_ids"])
    recent_ids = set(preferences["recent_ids"])
    visible_entries, locked_entries = split_launcher_entries(
        entries,
        activation=activation,
        persona_id=str(selected_persona["id"]),
        query=query,
        favorite_ids=favorite_ids,
        recent_ids=recent_ids,
    )
    entry_index = {entry["id"]: entry for entry in visible_entries}

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
        visible_entries,
        persona=selected_persona,
        favorite_ids=favorite_ids,
        recent_ids=recent_ids,
        query=query,
    )
    journey = build_workbench_context(
        request,
        entry_index=entry_index,
        docs_base_url=request.app.state.settings.docs_base_url,
    )

    return {
        "request": request,
        "operator": operator,
        "services": [],
        "deployments": [],
        "runbooks": [],
        "changelog_notes": [],
        "coordination": {"summary": {"count": 0}},
        "generated_at": isoformat(utc_now()),
        "docs_base_url": request.app.state.settings.docs_base_url,
        "maintenance_count": 0,
        "drift_summary": {"unsuppressed_count": 0},
        "attention_summary": {
            "active_count": 0,
            "acknowledged_count": 0,
            "dismissed_count": 0,
            "activity_count": 0,
        },
        "task_panel": {
            "attention": [],
            "recent": [],
            "activity": [],
            "attention_count": 0,
            "recent_count": 0,
            "latest_by_runbook": {},
        },
        "contextual_help": build_ops_portal_help(request.app.state.settings.docs_base_url),
        "search_collections": available_collections(),
        "launcher": {
            "query": query,
            "personas": personas,
            "selected_persona": selected_persona,
            "favorites": favorites,
            "recents": recents,
            "groups": groups,
            "locked_entries": locked_entries,
            "locked_count": len(locked_entries),
            "advanced_unlocked": activation["advanced_unlocked"],
            "match_count": sum(len(group["entries"]) for group in groups) + len(locked_entries),
            "entry_index": entry_index,
            "page_lane": workbench_ia["pages_by_id"].get("ops_portal_launcher"),
        },
        "journey": journey,
        "activation": activation,
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
    attention_store: AttentionStateStore = request.app.state.attention_store
    launcher_context = await build_launcher_panel_context(request)
    activation = launcher_context["activation"]

    services = repository.load_service_catalog()
    publications = repository.load_publication_registry()
    workflows = repository.load_workflow_definitions()
    workbench_ia = repository.load_workbench_information_architecture()

    capability_contracts = repository.load_capability_contract_catalog()
    dependency_graph = repository.load_dependency_graph()
    maintenance_windows = repository.load_maintenance_windows()
    live_apply_receipts = repository.load_live_apply_receipts(services)
    promotion_receipts = repository.load_promotion_receipts(services)
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
        task_payload = await gateway.fetch_runbook_tasks(
            token=read_api_token(session, request.app.state.settings),
            delivery_surface="ops_portal",
        )
    except Exception as exc:  # noqa: BLE001
        task_payload = {"warning": str(exc), "tasks": []}
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
    runbooks = enrich_runbook_metadata(raw_runbooks if isinstance(raw_runbooks, list) else [], workflows)
    raw_tasks = task_payload.get("tasks") if isinstance(task_payload, dict) else []
    tasks = raw_tasks if isinstance(raw_tasks, list) else []
    task_panel = build_task_panel_model(tasks)
    capability_models, capability_summary = build_capability_contract_models(capability_contracts, services)
    service_models = build_service_models(
        services,
        publications,
        health,
        drift_report,
        maintenance_windows,
        deployments,
        request.app.state.settings,
        activation,
    )
    assurance_rows, assurance_summary = build_runtime_assurance_models(
        services,
        publications,
        health_payload if isinstance(health_payload, dict) else {},
        live_apply_receipts,
    )
    active_maintenance = [window for window in maintenance_windows if window.get("service_id")]
    attention_notifications = build_attention_notifications(
        services=service_models,
        runtime_assurance=runtime_assurance,
        coordination=coordination,
        drift_report=drift_report,
        maintenance_windows=active_maintenance,
        live_apply_receipts=live_apply_receipts,
        docs_base_url=request.app.state.settings.docs_base_url,
        state_by_item=attention_store.current_by_item(),
    )
    activity_items = build_activity_items(
        deployments=deployments,
        promotions=promotion_receipts,
        attention_history=attention_store.history_events(),
    )
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
        "runtime-assurance": int(assurance_summary.get("row_count", 0)),
        "drift": int(drift_summary.get("unsuppressed_count", 0) or 0),
        "search": len(available_collections()),
        "runbooks": len(runbooks),
        "changelog": len(changelog_notes),
    }
    shell_navigation = build_shell_navigation(workbench_ia["pages"], section_counts)

    visible_runbooks, locked_runbooks = build_runbook_models(
        runbooks,
        activation,
        workbench_ia,
        task_panel["latest_by_runbook"],
    )

    return {
        "request": request,
        "operator": session,
        "services": service_models,
        "activation": activation,
        "runtime_assurance_rows": assurance_rows,
        "runtime_assurance_summary": assurance_summary,
        "capability_contracts": capability_models,
        "capability_contract_summary": capability_summary,
        "maintenance_windows": active_maintenance,
        "maintenance_count": len(active_maintenance),
        "runbooks": visible_runbooks,
        "locked_runbooks": locked_runbooks,
        "attention": attention_notifications,
        "attention_notification_index": {
            item["id"]: item for item in attention_notifications["all"]
        },
        "attention_summary": {
            **attention_notifications["summary"],
            "activity_count": len(activity_items),
        },
        "activities": activity_items,
        "runbooks": visible_runbooks,
        "locked_runbooks": locked_runbooks,
        "task_panel": task_panel,
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
        "task_warning": task_payload.get("warning") if isinstance(task_payload, dict) else None,
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
        "journey": launcher_context["journey"],
        "contextual_help": build_ops_portal_help(request.app.state.settings.docs_base_url),
        "shell_page": workbench_ia["pages_by_id"].get("ops_portal_shell"),
        "page_sections": workbench_ia["pages_by_section"],
        "shell_navigation": shell_navigation,
    }


async def build_activation_panel_context(request: Request) -> dict[str, Any]:
    launcher_context = await build_launcher_panel_context(request)
    return {
        "request": request,
        "activation": launcher_context["activation"],
        "docs_base_url": request.app.state.settings.docs_base_url,
    }


async def build_task_detail_context(
    request: Request,
    run_id: str,
    *,
    notice: str = "",
    notice_tone: str = "ok",
) -> dict[str, Any]:
    context = await build_dashboard_context(request)
    session = await ensure_session(request)
    gateway: Any = request.app.state.gateway_client
    try:
        payload = await gateway.fetch_runbook_task(
            run_id,
            token=read_api_token(session, request.app.state.settings),
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or f"task {run_id} is unavailable"
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"unable to load task {run_id}: {exc}") from exc

    task = payload.get("reentry") if isinstance(payload, dict) else None
    if not isinstance(task, dict):
        raise HTTPException(status_code=502, detail=f"task {run_id} returned an invalid payload")

    task = normalize_task_model(task)
    context.update(
        {
            "task": task,
            "task_record": payload,
            "task_notice": notice,
            "task_notice_tone": notice_tone,
        }
    )
    return context


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
    app.state.attention_store = AttentionStateStore(settings.attention_state_path)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="index.html", context=context)

    @app.get("/entry", response_class=HTMLResponse)
    async def journey_entry(request: Request, item_id: str = "", neutral: bool = False) -> Response:
        context = await build_launcher_panel_context(request)
        entry_index = context["launcher"]["entry_index"]
        journey = dict(context["journey"])
        requested_url = safe_requested_url(request.query_params.get("next"))
        invalid_requested_url = bool(request.query_params.get("next")) and requested_url is None

        if item_id:
            entry = entry_index.get(item_id)
            if entry is not None:
                record_launcher_recent(request.session, item_id, set(entry_index))
                return RedirectResponse(url=journey_redirect_url(entry, journey["role"]), status_code=303)

        if requested_url:
            return RedirectResponse(url=requested_url, status_code=303)

        if invalid_requested_url:
            journey["invalid_requested_url"] = True
            return templates.TemplateResponse(request=request, name="entry.html", context={**context, "journey": journey})

        if not neutral and not journey["activation_ready"]:
            journey["invalid_requested_url"] = invalid_requested_url
            return templates.TemplateResponse(request=request, name="entry.html", context={**context, "journey": journey})

        if not neutral and journey["saved_home"] is not None:
            saved_home = journey["saved_home"]
            record_launcher_recent(request.session, str(saved_home["id"]), set(entry_index))
            return RedirectResponse(url=str(journey["saved_home_redirect"]), status_code=303)

        if not neutral and journey["default_home"] is not None:
            default_home = journey["default_home"]
            record_launcher_recent(request.session, str(default_home["id"]), set(entry_index))
            return RedirectResponse(url=str(journey["default_home_redirect"]), status_code=303)

        journey["invalid_requested_url"] = invalid_requested_url
        return templates.TemplateResponse(request=request, name="entry.html", context={**context, "journey": journey})

    @app.get("/tasks/runbooks/{run_id}", response_class=HTMLResponse)
    async def runbook_task_detail(
        request: Request,
        run_id: str,
        notice: str = "",
        notice_tone: str = "ok",
    ) -> HTMLResponse:
        context = await build_task_detail_context(request, run_id, notice=notice, notice_tone=notice_tone)
        return templates.TemplateResponse(request=request, name="task_detail.html", context=context)

    @app.get("/partials/launcher", response_class=HTMLResponse)
    async def launcher_partial(request: Request, query: str = "") -> HTMLResponse:
        context = await build_launcher_panel_context(request, query=query)
        context["page_lane"] = context["launcher"].get("page_lane")
        return templates.TemplateResponse(request=request, name="partials/launcher.html", context=context)

    @app.get("/partials/activation", response_class=HTMLResponse)
    async def activation_partial(request: Request) -> HTMLResponse:
        context = await build_activation_panel_context(request)
        return templates.TemplateResponse(request=request, name="partials/activation.html", context=context)

    @app.get("/partials/overview", response_class=HTMLResponse)
    async def overview_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["page_lane"] = context["page_sections"].get("overview")
        return templates.TemplateResponse(request=request, name="partials/overview.html", context=context)

    @app.get("/partials/attention", response_class=HTMLResponse)
    async def attention_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/attention.html", context=context)

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

    @app.get("/partials/tasks", response_class=HTMLResponse)
    async def tasks_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/tasks.html", context=context)

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

    @app.post("/actions/journey/home/clear")
    async def clear_saved_home_action(
        request: Request,
        redirect_to: str = Form(default="/entry?neutral=1"),
    ) -> RedirectResponse:
        response = RedirectResponse(url=safe_local_redirect(redirect_to), status_code=303)
        delete_preference_cookie(response, WORKBENCH_HOME_COOKIE)
        return response

    @app.post("/actions/journey/home/{item_id}")
    async def select_saved_home_action(
        request: Request,
        item_id: str,
        redirect_to: str = Form(default="/entry?neutral=1"),
    ) -> RedirectResponse:
        context = await build_launcher_panel_context(request)
        journey = context["journey"]
        response = RedirectResponse(url=safe_local_redirect(redirect_to), status_code=303)
        candidate_ids = {str(entry["id"]) for entry in journey["home_destinations"]}
        if journey["activation_ready"] and item_id in candidate_ids:
            set_preference_cookie(response, request, WORKBENCH_HOME_COOKIE, item_id)
        return response

    @app.post("/actions/journey/activation/skip")
    async def skip_activation_action(
        request: Request,
        redirect_to: str = Form(default="/entry?neutral=1"),
    ) -> RedirectResponse:
        response = RedirectResponse(url=safe_local_redirect(redirect_to), status_code=303)
        set_preference_cookie(response, request, WORKBENCH_ACTIVATION_SKIP_COOKIE, "1")
        return response

    @app.post("/actions/journey/activation/reset")
    async def reset_activation_action(
        request: Request,
        redirect_to: str = Form(default="/entry?neutral=1"),
    ) -> RedirectResponse:
        response = RedirectResponse(url=safe_local_redirect(redirect_to), status_code=303)
        delete_preference_cookie(response, WORKBENCH_ACTIVATION_STEPS_COOKIE)
        delete_preference_cookie(response, WORKBENCH_ACTIVATION_SKIP_COOKIE)
        return response

    @app.post("/actions/journey/activation/steps/{step_id}")
    async def complete_activation_step_action(
        request: Request,
        step_id: str,
        redirect_to: str = Form(default="/entry?neutral=1"),
    ) -> RedirectResponse:
        response = RedirectResponse(url=safe_local_redirect(redirect_to), status_code=303)
        allowed_steps = {step["id"] for step in WORKBENCH_ACTIVATION_STEPS}
        if step_id not in allowed_steps:
            return response
        completed_steps = activation_steps_from_request(request)
        if step_id not in completed_steps:
            completed_steps.append(step_id)
        set_preference_cookie(response, request, WORKBENCH_ACTIVATION_STEPS_COOKIE, ",".join(completed_steps))
        delete_preference_cookie(response, WORKBENCH_ACTIVATION_SKIP_COOKIE)
        return response

    @app.post("/actions/activation/items/{item_id}", response_class=HTMLResponse)
    async def activation_item_action(
        request: Request,
        item_id: str,
        status: str = Form(default="completed"),
    ) -> HTMLResponse:
        repository: PortalRepository = request.app.state.repository
        activation_catalog = repository.load_activation_checklist()
        write_activation_item_state(request.session, activation_catalog, item_id=item_id, status=status)
        context = await build_activation_panel_context(request)
        return templates.TemplateResponse(request=request, name="partials/activation.html", context=context)

    @app.post("/actions/activation/override", response_class=HTMLResponse)
    async def activation_override_action(
        request: Request,
        enabled: bool = Form(default=True),
    ) -> HTMLResponse:
        repository: PortalRepository = request.app.state.repository
        activation_catalog = repository.load_activation_checklist()
        set_activation_override(request.session, activation_catalog, enabled=enabled)
        context = await build_activation_panel_context(request)
        return templates.TemplateResponse(request=request, name="partials/activation.html", context=context)

    @app.post("/actions/attention/{item_id}", response_class=HTMLResponse)
    async def attention_action(
        request: Request,
        item_id: str,
        action: str = Form(default="acknowledged"),
    ) -> HTMLResponse:
        context = await build_dashboard_context(request)
        item = context["attention_notification_index"].get(item_id)
        normalized_action = action.strip().lower()
        if item and normalized_action in {"acknowledged", "dismissed", "reopened"}:
            request.app.state.attention_store.apply(
                item_id,
                action=normalized_action,
                actor_id=str(context["operator"].get("operator_id") or "operator"),
                snapshot={
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "href": item.get("links", [{}])[0].get("href") if item.get("links") else "#attention",
                },
            )
            context = await build_dashboard_context(request)
        return templates.TemplateResponse(request=request, name="partials/attention.html", context=context)

    @app.get("/launcher/go/{item_id}")
    async def launcher_go(request: Request, item_id: str) -> RedirectResponse:
        context = await build_launcher_panel_context(request)
        entry = context["launcher"]["entry_index"].get(item_id)
        if entry is None:
            return RedirectResponse(url="/#activation", status_code=303)
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
        activation_context = (await build_activation_panel_context(request))["activation"]
        action_id = "restart" if restart_only else "deploy"
        if action_locked(action_id, activation_context):
            context = {
                "request": request,
                "result": {
                    "title": f"{'Restart' if restart_only else 'Deploy'}: {service_id}",
                    "status": "blocked",
                    "detail": "Complete the activation checklist or explicitly reveal advanced tools for this session before launching mutating service actions.",
                    "tone": "warn",
                    "timestamp": isoformat(utc_now()),
                },
            }
            return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)
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
        activation_context = (await build_activation_panel_context(request))["activation"]
        if action_locked("rotate_secret", activation_context):
            context = {
                "request": request,
                "result": {
                    "title": f"Rotate secret: {service_id}",
                    "status": "blocked",
                    "detail": "Complete the activation checklist or explicitly reveal advanced tools for this session before rotating production secrets.",
                    "tone": "warn",
                    "timestamp": isoformat(utc_now()),
                },
            }
            return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)
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
        dashboard_context = await build_dashboard_context(request)
        runbook_lookup = {
            str(item.get("id")): item
            for item in [*dashboard_context.get("runbooks", []), *dashboard_context.get("locked_runbooks", [])]
            if isinstance(item, dict)
        }
        runbook_model = runbook_lookup.get(runbook_id, {})
        if runbook_locked(runbook_model, dashboard_context["activation"]):
            context = {
                "request": request,
                "result": {
                    "title": f"Runbook: {runbook_id}",
                    "status": "blocked",
                    "detail": "This mutating runbook stays disabled until the activation checklist is complete or advanced tools are explicitly revealed for the session.",
                    "tone": "warn",
                    "timestamp": isoformat(utc_now()),
                },
            }
            return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)
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
            task_link = str(result.get("task_path") or f"/tasks/runbooks/{result.get('run_id', '')}").strip()
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            tone = "danger"
            status = "failed"
            task_link = ""

        context = {
            "request": request,
            "result": {
                "title": f"Runbook: {runbook_id}",
                "status": status,
                "detail": detail,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
                "link_url": task_link if task_link and status != "failed" else "",
                "link_label": (
                    "Review task summary"
                    if task_link and status == "escalated"
                    else "Open task details"
                    if task_link
                    else ""
                ),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/tasks/runbooks/{run_id}/resume")
    async def resume_runbook_task(request: Request, run_id: str) -> RedirectResponse:
        session = await ensure_session(request)
        gateway = request.app.state.gateway_client
        try:
            result = await gateway.resume_runbook_task(
                run_id,
                token=read_api_token(session, request.app.state.settings),
            )
            notice = str(result.get("message") or f"Runbook task {run_id} resumed successfully.")
            notice_tone = "ok" if str(result.get("status") or "") == "completed" else "warn"
        except Exception as exc:  # noqa: BLE001
            notice = str(exc)
            notice_tone = "danger"
        query = httpx.QueryParams({"notice": notice, "notice_tone": notice_tone})
        return RedirectResponse(url=f"/tasks/runbooks/{run_id}?{query}", status_code=303)

    # ---------------------------------------------------------------------------
    # ADR 0224: Self-service repo intake — GUI + secure JSON API
    # ---------------------------------------------------------------------------

    def _load_repo_deploy_catalog() -> list[dict[str, Any]]:
        catalog_path = Path(os.getenv("OPS_PORTAL_REPO_DEPLOY_CATALOG", "")).expanduser()
        if not catalog_path.is_file():
            # Fall back to repo-relative path when running from source
            candidates = [
                Path(__file__).resolve().parents[2] / "config" / "repo-deploy-catalog.json",
                Path("/srv/ops-portal/data/config/repo-deploy-catalog.json"),
            ]
            catalog_path = next((p for p in candidates if p.is_file()), Path(""))
        if not catalog_path.is_file():
            return []
        try:
            data = json.loads(catalog_path.read_text())
            return data.get("profiles", []) if isinstance(data, dict) else []
        except Exception:  # noqa: BLE001
            return []

    @app.get("/partials/repo-intake", response_class=HTMLResponse)
    async def repo_intake_partial(request: Request) -> HTMLResponse:
        context = await build_dashboard_context(request)
        context["catalog_profiles"] = _load_repo_deploy_catalog()
        context["intake_error"] = ""
        context["page_lane"] = context["page_sections"].get("repo-intake")
        return templates.TemplateResponse(request=request, name="partials/repo_intake.html", context=context)

    @app.post("/actions/repo-intake/profile/{profile_id}", response_class=HTMLResponse)
    async def deploy_catalog_profile_action(request: Request, profile_id: str) -> HTMLResponse:
        session = await ensure_session(request)
        broker: EventBroker = request.app.state.event_broker
        activation_context = (await build_activation_panel_context(request))["activation"]
        if action_locked("deploy", activation_context):
            context = {
                "request": request,
                "result": {
                    "title": f"Repo deploy: {profile_id}",
                    "status": "blocked",
                    "detail": "Complete the activation checklist or reveal advanced tools before triggering repo deployments.",
                    "tone": "warn",
                    "timestamp": isoformat(utc_now()),
                },
            }
            return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)
        profiles = _load_repo_deploy_catalog()
        profile = next((p for p in profiles if str(p.get("id", "")) == profile_id), None)
        if profile is None:
            context = {
                "request": request,
                "result": {
                    "title": f"Repo deploy: {profile_id}",
                    "status": "failed",
                    "detail": f"Profile '{profile_id}' not found in the repo-deploy catalog.",
                    "tone": "danger",
                    "timestamp": isoformat(utc_now()),
                },
            }
            return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)
        try:
            import subprocess  # noqa: PLC0415 - lazy import
            compose_domain_args: list[str] = []
            for cd in profile.get("compose_domains") or []:
                compose_domain_args.extend(["--compose-domain", f"{cd['service']}:{cd['domain']}"])
            args = [
                "python3", "-m", "scripts.lv3_cli", "deploy-repo-profile",
                "--profile-id", profile_id,
            ]
            result = subprocess.run(  # noqa: S603
                args,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).resolve().parents[2]),
            )
            if result.returncode == 0:
                status = "queued"
                detail = result.stdout.strip() or f"Profile '{profile_id}' deploy queued via Coolify."
                tone = "ok"
            else:
                status = "failed"
                detail = result.stderr.strip() or result.stdout.strip() or "Deploy command exited non-zero."
                tone = "danger"
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            detail = str(exc)
            tone = "danger"
        await broker.publish(
            f"repo-intake profile {profile_id}: {detail}",
            event_type="deploy",
            metadata={"profile_id": profile_id, "status": status},
        )
        context = {
            "request": request,
            "result": {
                "title": f"Repo deploy: {profile.get('app_name', profile_id)}",
                "status": status,
                "detail": detail,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/actions/repo-intake/custom", response_class=HTMLResponse)
    async def deploy_custom_repo_action(
        request: Request,
        repo: str = Form(default=""),
        branch: str = Form(default="main"),
        app_name: str = Form(default=""),
        project: str = Form(default="LV3 Apps"),
        environment: str = Form(default="production"),
        build_pack: str = Form(default="dockercompose"),
        source: str = Form(default="auto"),
        domain: str = Form(default=""),
        ports: str = Form(default="80"),
        llm_assistance: str = Form(default="prohibited"),
        docker_compose_location: str = Form(default=""),
    ) -> HTMLResponse:
        session = await ensure_session(request)
        broker: EventBroker = request.app.state.event_broker
        activation_context = (await build_activation_panel_context(request))["activation"]
        if action_locked("deploy", activation_context):
            context = {
                "request": request,
                "result": {
                    "title": "Custom repo intake",
                    "status": "blocked",
                    "detail": "Complete the activation checklist or reveal advanced tools before triggering repo deployments.",
                    "tone": "warn",
                    "timestamp": isoformat(utc_now()),
                },
            }
            return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)
        # Validate required fields
        repo = repo.strip()
        app_name = app_name.strip()
        valid_sources = {"auto", "public", "private-deploy-key"}
        valid_build_packs = {"nixpacks", "static", "dockerfile", "dockercompose"}
        valid_llm = {"allowed", "required", "prohibited"}
        errors = []
        if not repo:
            errors.append("Repository URL is required.")
        if not app_name:
            errors.append("Application name is required.")
        if source not in valid_sources:
            errors.append(f"Source must be one of: {', '.join(sorted(valid_sources))}.")
        if build_pack not in valid_build_packs:
            errors.append(f"Build pack must be one of: {', '.join(sorted(valid_build_packs))}.")
        if llm_assistance not in valid_llm:
            errors.append(f"LLM assistance must be one of: {', '.join(sorted(valid_llm))}.")
        if errors:
            context = {
                "request": request,
                "result": {
                    "title": "Custom repo intake",
                    "status": "failed",
                    "detail": " ".join(errors),
                    "tone": "danger",
                    "timestamp": isoformat(utc_now()),
                },
            }
            return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)
        try:
            import subprocess  # noqa: PLC0415
            args = [
                "python3", "-m", "scripts.lv3_cli", "deploy-repo",
                "--repo", repo,
                "--branch", branch.strip() or "main",
                "--source", source,
                "--app-name", app_name,
                "--project", project.strip() or "LV3 Apps",
                "--environment", environment.strip() or "production",
                "--build-pack", build_pack,
                "--ports", ports.strip() or "80",
            ]
            if domain.strip():
                args.extend(["--domain", domain.strip()])
            if docker_compose_location.strip():
                args.extend(["--docker-compose-location", docker_compose_location.strip()])
            result = subprocess.run(  # noqa: S603
                args,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).resolve().parents[2]),
            )
            if result.returncode == 0:
                status = "queued"
                detail = result.stdout.strip() or f"Custom repo '{app_name}' deploy queued via Coolify."
                tone = "ok"
            else:
                status = "failed"
                detail = result.stderr.strip() or result.stdout.strip() or "Deploy command exited non-zero."
                tone = "danger"
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            detail = str(exc)
            tone = "danger"
        await broker.publish(
            f"repo-intake custom {app_name}: {detail}",
            event_type="deploy",
            metadata={"app_name": app_name, "repo": repo, "status": status},
        )
        context = {
            "request": request,
            "result": {
                "title": f"Custom repo intake: {app_name}",
                "status": status,
                "detail": detail,
                "tone": tone,
                "timestamp": isoformat(utc_now()),
            },
        }
        return templates.TemplateResponse(request=request, name="partials/action_result.html", context=context)

    @app.post("/api/v1/repo-intake", response_class=JSONResponse)
    async def api_repo_intake(request: Request) -> JSONResponse:
        """Secure JSON API endpoint for programmatic self-service repo intake (ADR 0224).

        Accepts Bearer token or OPS_PORTAL_STATIC_API_TOKEN.
        Request body: JSON with same fields as the custom intake form.
        Returns: {"ok": true/false, "status": "...", "detail": "..."}
        """
        # Token auth — accept Bearer header or static token
        auth_header = request.headers.get("Authorization", "")
        bearer_token: str | None = None
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header[7:].strip()
        static_token = request.app.state.settings.static_api_token
        if not bearer_token and not static_token:
            return JSONResponse({"ok": False, "error": "Authentication required."}, status_code=401)
        if bearer_token and static_token and bearer_token != static_token:
            # If both present, require match; if only static configured, allow unauthenticated internal callers
            session_dict: dict[str, str] = {}
            session = request.session
            session_token = session.get("api_token", "")
            if bearer_token != session_token:
                return JSONResponse({"ok": False, "error": "Invalid token."}, status_code=403)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "Request body must be valid JSON."}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "error": "Request body must be a JSON object."}, status_code=400)
        repo = str(body.get("repo", "")).strip()
        app_name = str(body.get("app_name", "")).strip()
        branch = str(body.get("branch", "main")).strip() or "main"
        project = str(body.get("project", "LV3 Apps")).strip() or "LV3 Apps"
        environment = str(body.get("environment", "production")).strip() or "production"
        build_pack = str(body.get("build_pack", "dockercompose")).strip()
        source = str(body.get("source", "auto")).strip()
        domain = str(body.get("domain", "")).strip()
        ports = str(body.get("ports", "80")).strip() or "80"
        llm_assistance = str(body.get("llm_assistance", "prohibited")).strip()
        docker_compose_location = str(body.get("docker_compose_location", "")).strip()
        profile_id = str(body.get("profile_id", "")).strip()

        # Profile-based shortcut
        if profile_id:
            profiles = _load_repo_deploy_catalog()
            profile = next((p for p in profiles if str(p.get("id", "")) == profile_id), None)
            if profile is None:
                return JSONResponse({"ok": False, "error": f"Profile '{profile_id}' not found."}, status_code=404)
            try:
                import subprocess  # noqa: PLC0415
                args = [
                    "python3", "-m", "scripts.lv3_cli", "deploy-repo-profile",
                    "--profile-id", profile_id,
                ]
                result = subprocess.run(  # noqa: S603
                    args, capture_output=True, text=True, timeout=30,
                    cwd=str(Path(__file__).resolve().parents[2]),
                )
                if result.returncode == 0:
                    return JSONResponse({"ok": True, "status": "queued", "detail": result.stdout.strip() or "Deploy queued."})
                return JSONResponse({"ok": False, "status": "failed", "detail": result.stderr.strip() or "Deploy failed."}, status_code=502)
            except Exception as exc:  # noqa: BLE001
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

        valid_sources = {"auto", "public", "private-deploy-key"}
        valid_build_packs = {"nixpacks", "static", "dockerfile", "dockercompose"}
        errors = []
        if not repo:
            errors.append("'repo' is required.")
        if not app_name:
            errors.append("'app_name' is required.")
        if source not in valid_sources:
            errors.append(f"'source' must be one of {sorted(valid_sources)}.")
        if build_pack not in valid_build_packs:
            errors.append(f"'build_pack' must be one of {sorted(valid_build_packs)}.")
        if errors:
            return JSONResponse({"ok": False, "error": " ".join(errors)}, status_code=422)
        try:
            import subprocess  # noqa: PLC0415
            args = [
                "python3", "-m", "scripts.lv3_cli", "deploy-repo",
                "--repo", repo, "--branch", branch,
                "--source", source, "--app-name", app_name,
                "--project", project, "--environment", environment,
                "--build-pack", build_pack, "--ports", ports,
            ]
            if domain:
                args.extend(["--domain", domain])
            if docker_compose_location:
                args.extend(["--docker-compose-location", docker_compose_location])
            result = subprocess.run(  # noqa: S603
                args, capture_output=True, text=True, timeout=30,
                cwd=str(Path(__file__).resolve().parents[2]),
            )
            if result.returncode == 0:
                return JSONResponse({"ok": True, "status": "queued", "detail": result.stdout.strip() or "Deploy queued."})
            return JSONResponse({"ok": False, "status": "failed", "detail": result.stderr.strip() or "Deploy failed."}, status_code=502)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    # ---------------------------------------------------------------------------
    # End ADR 0224
    # ---------------------------------------------------------------------------

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
