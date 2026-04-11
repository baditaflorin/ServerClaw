#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, repo_path


ENVIRONMENT_TOPOLOGY_PATH = repo_path("config", "environment-topology.json")
DEFAULT_ENVIRONMENTS = ("production", "staging")
DEFAULT_PRIMARY_ENVIRONMENT = "production"
RECEIPT_ONLY_ENVIRONMENTS = ("preview",)


def _ordered_environment_ids(environment_ids: set[str]) -> tuple[str, ...]:
    tail = sorted(environment_id for environment_id in environment_ids if environment_id != DEFAULT_PRIMARY_ENVIRONMENT)
    if DEFAULT_PRIMARY_ENVIRONMENT in environment_ids:
        return (DEFAULT_PRIMARY_ENVIRONMENT, *tail)
    return tuple(tail)


def load_environment_topology(path: Path | None = None) -> dict[str, Any]:
    return load_json(path or ENVIRONMENT_TOPOLOGY_PATH)


def configured_environment_ids(
    path: Path | None = None,
    *,
    include_planned: bool = True,
    fallback: tuple[str, ...] = DEFAULT_ENVIRONMENTS,
) -> tuple[str, ...]:
    try:
        payload = load_environment_topology(path)
    except Exception:
        return fallback

    environments = payload.get("environments")
    if not isinstance(environments, list):
        return fallback

    collected: set[str] = set()
    for item in environments:
        if not isinstance(item, dict):
            continue
        environment_id = item.get("id")
        status = item.get("status")
        if not isinstance(environment_id, str) or not environment_id.strip():
            continue
        if not include_planned and status != "active":
            continue
        collected.add(environment_id)

    if not collected:
        return fallback
    return _ordered_environment_ids(collected)


def active_environment_ids(path: Path | None = None) -> tuple[str, ...]:
    return configured_environment_ids(path, include_planned=False)


def environment_choices(path: Path | None = None) -> tuple[str, ...]:
    return configured_environment_ids(path)


def primary_environment(path: Path | None = None) -> str:
    choices = configured_environment_ids(path)
    return choices[0] if choices else DEFAULT_PRIMARY_ENVIRONMENT


def receipt_environment_ids(path: Path | None = None) -> tuple[str, ...]:
    configured = list(configured_environment_ids(path))
    for environment in RECEIPT_ONLY_ENVIRONMENTS:
        if environment not in configured:
            configured.append(environment)
    return tuple(configured)


def receipt_subdirectory_environments(path: Path | None = None) -> set[str]:
    return set(receipt_environment_ids(path)) - {primary_environment(path)}
