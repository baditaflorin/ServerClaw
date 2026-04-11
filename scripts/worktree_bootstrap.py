#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
from typing import Any

from controller_automation_toolkit import REPO_ROOT, load_json, resolve_repo_local_path


WORKTREE_BOOTSTRAP_MANIFEST_PATH = REPO_ROOT / "config" / "worktree-bootstrap-manifests.json"
ALLOWED_BOOTSTRAP_ENTRY_KINDS = {"file", "directory", "env"}


def load_bootstrap_catalog() -> dict[str, Any]:
    return load_json(WORKTREE_BOOTSTRAP_MANIFEST_PATH)


def _require_non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_manifest_id_list(value: object, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    manifest_ids: list[str] = []
    for index, manifest_id in enumerate(value):
        manifest_ids.append(_require_non_empty_string(manifest_id, f"{path}[{index}]"))
    return manifest_ids


def _validate_bootstrap_input(entry: object, path: str, *, generated: bool) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{path} must be a mapping")
    _require_non_empty_string(entry.get("id"), f"{path}.id")
    kind = _require_non_empty_string(entry.get("kind"), f"{path}.kind")
    if kind not in ALLOWED_BOOTSTRAP_ENTRY_KINDS:
        raise ValueError(f"{path}.kind must be one of {sorted(ALLOWED_BOOTSTRAP_ENTRY_KINDS)}")
    _require_non_empty_string(entry.get("description"), f"{path}.description")
    if kind == "env":
        _require_non_empty_string(entry.get("name"), f"{path}.name")
        if "path" in entry:
            raise ValueError(f"{path}.path is not valid for env bootstrap entries")
    else:
        _require_non_empty_string(entry.get("path"), f"{path}.path")
    resolve_repo_local = entry.get("resolve_repo_local")
    if resolve_repo_local is not None and not isinstance(resolve_repo_local, bool):
        raise ValueError(f"{path}.resolve_repo_local must be boolean when present")
    if generated:
        if kind == "env":
            raise ValueError(f"{path}.kind cannot be 'env' for generated artifacts")
        _require_non_empty_string(entry.get("materialize_command"), f"{path}.materialize_command")


def validate_bootstrap_catalog(catalog: dict[str, Any]) -> None:
    if not isinstance(catalog, dict):
        raise ValueError("worktree bootstrap catalog must be a mapping")
    manifests = catalog.get("manifests")
    if not isinstance(manifests, dict) or not manifests:
        raise ValueError("worktree bootstrap catalog must define a non-empty manifests mapping")

    defaults = catalog.get("defaults", {})
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ValueError("worktree bootstrap catalog defaults must be a mapping")
    default_manifest_ids = _require_manifest_id_list(
        defaults.get("workflow_manifest_ids", []), "defaults.workflow_manifest_ids"
    )

    for manifest_id, manifest in manifests.items():
        if not isinstance(manifest, dict):
            raise ValueError(f"manifest '{manifest_id}' must be a mapping")
        _require_non_empty_string(manifest.get("description"), f"manifests.{manifest_id}.description")
        generated_artifacts = manifest.get("generated_artifacts", [])
        required_local_inputs = manifest.get("required_local_inputs", [])
        optional_read_only_caches = manifest.get("optional_read_only_caches", [])
        if not isinstance(generated_artifacts, list):
            raise ValueError(f"manifests.{manifest_id}.generated_artifacts must be a list")
        if not isinstance(required_local_inputs, list):
            raise ValueError(f"manifests.{manifest_id}.required_local_inputs must be a list")
        if not isinstance(optional_read_only_caches, list):
            raise ValueError(f"manifests.{manifest_id}.optional_read_only_caches must be a list")
        for index, entry in enumerate(generated_artifacts):
            _validate_bootstrap_input(entry, f"manifests.{manifest_id}.generated_artifacts[{index}]", generated=True)
        for index, entry in enumerate(required_local_inputs):
            _validate_bootstrap_input(entry, f"manifests.{manifest_id}.required_local_inputs[{index}]", generated=False)
        for index, entry in enumerate(optional_read_only_caches):
            _validate_bootstrap_input(
                entry, f"manifests.{manifest_id}.optional_read_only_caches[{index}]", generated=False
            )

    for manifest_id in default_manifest_ids:
        if manifest_id not in manifests:
            raise ValueError(f"defaults.workflow_manifest_ids references unknown manifest '{manifest_id}'")


def resolve_workflow_manifest_ids(catalog: dict[str, Any], workflow: dict[str, Any]) -> list[str]:
    manifests = catalog.get("manifests", {})
    defaults = catalog.get("defaults", {})
    default_ids = defaults.get("workflow_manifest_ids", []) if isinstance(defaults, dict) else []
    preflight = workflow.get("preflight", {})
    explicit_ids = preflight.get("bootstrap_manifest_ids", []) if isinstance(preflight, dict) else []
    manifest_ids: list[str] = []
    for manifest_id in [*default_ids, *explicit_ids]:
        if manifest_id not in manifest_ids:
            manifest_ids.append(manifest_id)
    for manifest_id in manifest_ids:
        if manifest_id not in manifests:
            raise ValueError(f"workflow references unknown bootstrap manifest '{manifest_id}'")
    return manifest_ids


def resolve_entry_path(entry: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> Path:
    path_value = _require_non_empty_string(entry.get("path"), "bootstrap entry path")
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    if bool(entry.get("resolve_repo_local")):
        return resolve_repo_local_path(path, repo_root=repo_root)
    return path
