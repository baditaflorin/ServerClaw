from __future__ import annotations

from pathlib import Path
from typing import Any

from .repo import load_json, repo_path


CORRECTION_LOOP_CATALOG_PATH = repo_path("config", "correction-loops.json")


def load_correction_loop_catalog(path: Path = CORRECTION_LOOP_CATALOG_PATH) -> dict[str, Any]:
    return load_json(path)


def _require_mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return dict(value)


def workflow_matches_loop(loop: dict[str, Any], workflow_id: str) -> bool:
    selectors = _require_mapping(loop.get("applies_to"), f"correction loop '{loop.get('id', '<unknown>')}'.applies_to")
    for candidate in selectors.get("workflow_ids", []):
        if candidate == workflow_id:
            return True
    for prefix in selectors.get("workflow_id_prefixes", []):
        if workflow_id.startswith(prefix):
            return True
    return False


def matching_workflow_correction_loops(catalog: dict[str, Any], workflow_id: str) -> list[dict[str, Any]]:
    loops = catalog.get("loops")
    if not isinstance(loops, list):
        raise ValueError("config/correction-loops.json.loops must be a list")
    return [loop for loop in loops if isinstance(loop, dict) and workflow_matches_loop(loop, workflow_id)]


def resolve_workflow_correction_loop(catalog: dict[str, Any], workflow_id: str) -> dict[str, Any] | None:
    matches = matching_workflow_correction_loops(catalog, workflow_id)
    if not matches:
        return None
    if len(matches) > 1:
        match_ids = ", ".join(sorted(str(loop.get("id")) for loop in matches))
        raise ValueError(f"workflow '{workflow_id}' matches multiple correction loops: {match_ids}")
    return matches[0]
