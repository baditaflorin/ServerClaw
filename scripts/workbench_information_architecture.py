from __future__ import annotations

from typing import Any


TASK_LANE_ORDER = ("start", "observe", "change", "learn", "recover")
TASK_LANE_IDS = set(TASK_LANE_ORDER)
TASK_LANE_LABELS = {
    "start": "Start",
    "observe": "Observe",
    "change": "Change",
    "learn": "Learn",
    "recover": "Recover",
}
TASK_LANE_QUESTIONS = {
    "start": "Where do I begin and what needs my attention?",
    "observe": "What is happening right now?",
    "change": "How do I make a safe governed change?",
    "learn": "Where is the explanation, runbook, or reference?",
    "recover": "How do I restore, repair, or escalate?",
}
DEFAULT_PERSONAS_BY_TASK_LANE = {
    "start": ["operator", "planner"],
    "observe": ["observer", "operator"],
    "change": ["operator", "planner"],
    "learn": ["planner", "operator"],
    "recover": ["administrator", "operator"],
}
LEGACY_TASK_LANE_ALIASES = {
    "operate": "change",
    "plan": "start",
    "administer": "recover",
}


def normalize_task_lane(value: Any, *, default: str = "start") -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    lane = value.strip().lower()
    lane = LEGACY_TASK_LANE_ALIASES.get(lane, lane)
    return lane if lane in TASK_LANE_IDS else default


def normalize_task_lane_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        lane = normalize_task_lane(item, default="")
        if lane and lane not in normalized:
            normalized.append(lane)
    return normalized


def task_lane_label(lane: str) -> str:
    return TASK_LANE_LABELS[normalize_task_lane(lane)]


def default_personas_for_task_lane(lane: str) -> list[str]:
    return list(DEFAULT_PERSONAS_BY_TASK_LANE.get(normalize_task_lane(lane), ["operator"]))


# ADR 0307: Platform Workbench — cohesive surface class declarations
# Every human-facing surface must declare one of these roles:
#   "home"          — orients the user, shows attention items, routes to next task
#   "task"          — lets the user complete a governed action or operational job
#   "reference"     — explains how the platform works, hosts runbooks and ADRs
#   "product_native" — third-party product with best-in-class UX, enters/exits via workbench

WORKBENCH_SURFACE_ROLES = ("home", "task", "reference", "product_native")

WORKBENCH_SURFACE_ROLE_LABELS = {
    "home": "Home",
    "task": "Task",
    "reference": "Reference",
    "product_native": "Product",
}


def normalize_surface_role(value: Any, *, default: str = "product_native") -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    role = value.strip().lower()
    return role if role in WORKBENCH_SURFACE_ROLES else default
