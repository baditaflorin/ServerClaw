#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSTREAMS_PATH = REPO_ROOT / "workstreams.yaml"
MUTABLE_SURFACE_MODES = {"exclusive", "shared_contract"}
ALL_SURFACE_MODES = MUTABLE_SURFACE_MODES | {"generated", "read_only"}
TERMINAL_WORKSTREAM_STATUSES = {"merged", "live_applied"}


@dataclass(frozen=True)
class SurfaceClaim:
    surface_id: str
    paths: tuple[str, ...]
    mode: str
    contract: str | None = None


@dataclass(frozen=True)
class WorkstreamOwnership:
    workstream_id: str
    status: str
    branch: str
    doc: str
    owned_surfaces: tuple[SurfaceClaim, ...]

    @property
    def is_active(self) -> bool:
        return self.status not in TERMINAL_WORKSTREAM_STATUSES


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _normalized_repo_pattern(pattern: str, path: str) -> str:
    pattern = _require_str(pattern, path).replace("\\", "/").strip()
    if pattern.startswith("/"):
        raise ValueError(f"{path} must be repository-relative, not absolute")
    return pattern


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _require_mapping(payload, str(path))


def load_registry(path: Path = WORKSTREAMS_PATH) -> dict[str, Any]:
    return _load_yaml(path)


def _parse_surface_claim(entry: dict[str, Any], path: str) -> SurfaceClaim:
    surface_id = _require_str(entry.get("id"), f"{path}.id")
    mode = _require_str(entry.get("mode"), f"{path}.mode")
    if mode not in ALL_SURFACE_MODES:
        raise ValueError(f"{path}.mode must be one of {sorted(ALL_SURFACE_MODES)}")

    patterns = tuple(
        _normalized_repo_pattern(item, f"{path}.paths[{index}]")
        for index, item in enumerate(_require_list(entry.get("paths"), f"{path}.paths"))
    )
    if not patterns:
        raise ValueError(f"{path}.paths must not be empty")

    contract = entry.get("contract")
    if mode == "shared_contract":
        contract = _require_str(contract, f"{path}.contract")
    elif contract is not None:
        raise ValueError(f"{path}.contract is only allowed when mode is shared_contract")

    return SurfaceClaim(surface_id=surface_id, paths=patterns, mode=mode, contract=contract)


def parse_workstream_ownerships(registry: dict[str, Any]) -> list[WorkstreamOwnership]:
    workstreams = _require_list(registry.get("workstreams"), "workstreams.yaml.workstreams")
    ownerships: list[WorkstreamOwnership] = []

    for index, item in enumerate(workstreams):
        path = f"workstreams.yaml.workstreams[{index}]"
        entry = _require_mapping(item, path)
        workstream_id = _require_str(entry.get("id"), f"{path}.id")
        status = _require_str(entry.get("status"), f"{path}.status")
        branch = _require_str(entry.get("branch"), f"{path}.branch")
        doc = _require_str(entry.get("doc"), f"{path}.doc")
        manifest = entry.get("ownership_manifest")

        is_active = status not in TERMINAL_WORKSTREAM_STATUSES
        if manifest is None:
            if is_active:
                raise ValueError(f"{path}.ownership_manifest is required for active workstreams")
            ownerships.append(
                WorkstreamOwnership(
                    workstream_id=workstream_id,
                    status=status,
                    branch=branch,
                    doc=doc,
                    owned_surfaces=(),
                )
            )
            continue

        manifest = _require_mapping(manifest, f"{path}.ownership_manifest")
        owned_surfaces = tuple(
            _parse_surface_claim(surface, f"{path}.ownership_manifest.owned_surfaces[{surface_index}]")
            for surface_index, surface in enumerate(
                _require_list(manifest.get("owned_surfaces"), f"{path}.ownership_manifest.owned_surfaces")
            )
        )
        if is_active and not owned_surfaces:
            raise ValueError(f"{path}.ownership_manifest.owned_surfaces must not be empty for active workstreams")

        seen_surface_ids: set[str] = set()
        seen_patterns: dict[str, str] = {}
        for surface in owned_surfaces:
            if surface.surface_id in seen_surface_ids:
                raise ValueError(f"{path}.ownership_manifest duplicates surface id '{surface.surface_id}'")
            seen_surface_ids.add(surface.surface_id)
            for pattern in surface.paths:
                existing_mode = seen_patterns.get(pattern)
                if existing_mode is not None and existing_mode != surface.mode:
                    raise ValueError(
                        f"{path}.ownership_manifest reuses path pattern '{pattern}' across incompatible modes"
                    )
                seen_patterns[pattern] = surface.mode

        ownerships.append(
            WorkstreamOwnership(
                workstream_id=workstream_id,
                status=status,
                branch=branch,
                doc=doc,
                owned_surfaces=owned_surfaces,
            )
        )

    return ownerships


def validate_registry(registry: dict[str, Any]) -> list[WorkstreamOwnership]:
    ownerships = parse_workstream_ownerships(registry)
    active = [ownership for ownership in ownerships if ownership.is_active]

    exclusive_ids: dict[str, str] = {}
    exclusive_patterns: dict[str, str] = {}
    shared_contracts: dict[str, str] = {}

    for ownership in active:
        for surface in ownership.owned_surfaces:
            if surface.mode == "exclusive":
                prior_owner = exclusive_ids.get(surface.surface_id)
                if prior_owner and prior_owner != ownership.workstream_id:
                    raise ValueError(
                        f"surface '{surface.surface_id}' is claimed as exclusive by both '{prior_owner}' and '{ownership.workstream_id}'"
                    )
                exclusive_ids[surface.surface_id] = ownership.workstream_id
                for pattern in surface.paths:
                    prior_pattern_owner = exclusive_patterns.get(pattern)
                    if prior_pattern_owner and prior_pattern_owner != ownership.workstream_id:
                        raise ValueError(
                            f"path pattern '{pattern}' is claimed as exclusive by both '{prior_pattern_owner}' and '{ownership.workstream_id}'"
                        )
                    exclusive_patterns[pattern] = ownership.workstream_id
            elif surface.mode == "shared_contract":
                prior_contract = shared_contracts.get(surface.surface_id)
                if prior_contract and prior_contract != surface.contract:
                    raise ValueError(
                        f"shared_contract surface '{surface.surface_id}' must use a single contract across active workstreams"
                    )
                shared_contracts[surface.surface_id] = surface.contract or ""

    return ownerships


def _run_git(repo_root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def detect_current_branch(repo_root: Path) -> str:
    return _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")


def resolve_base_ref(repo_root: Path, registry: dict[str, Any], explicit_base_ref: str | None) -> str:
    if explicit_base_ref:
        return explicit_base_ref

    delivery_model = registry.get("delivery_model")
    registry_owner = "main"
    if isinstance(delivery_model, dict):
        owner = delivery_model.get("registry_owner")
        if isinstance(owner, str) and owner.strip():
            registry_owner = owner

    remote_candidate = f"origin/{registry_owner}"
    remote_exists = subprocess.run(
        ["git", "-C", str(repo_root), "show-ref", "--verify", "--quiet", f"refs/remotes/{remote_candidate}"],
        check=False,
    )
    if remote_exists.returncode == 0:
        return remote_candidate
    return registry_owner


def _collect_changed_files(repo_root: Path, base_ref: str) -> list[str]:
    merge_base = _run_git(repo_root, "merge-base", base_ref, "HEAD")
    changed: set[str] = set()
    commands = (
        ("diff", "--name-only", f"{merge_base}..HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    for args in commands:
        output = _run_git(repo_root, *args)
        if not output:
            continue
        for line in output.splitlines():
            normalized = line.strip().replace("\\", "/")
            if normalized:
                changed.add(normalized)
    return sorted(changed)


def _matches_any_pattern(repo_path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(repo_path, pattern) for pattern in patterns)


def validate_branch_ownership(
    *,
    repo_root: Path = REPO_ROOT,
    registry: dict[str, Any] | None = None,
    current_branch: str | None = None,
    base_ref: str | None = None,
) -> list[str]:
    repo_root = repo_root.resolve()
    registry = registry or load_registry(repo_root / "workstreams.yaml")
    ownerships = validate_registry(registry)
    current_branch = current_branch or detect_current_branch(repo_root)

    if current_branch in {"main", "HEAD"}:
        return []

    ownership = next((item for item in ownerships if item.branch == current_branch), None)
    if ownership is None:
        raise ValueError(f"branch '{current_branch}' is not registered in workstreams.yaml")
    if not ownership.is_active:
        raise ValueError(f"branch '{current_branch}' maps to terminal workstream '{ownership.workstream_id}'")

    resolved_base_ref = resolve_base_ref(repo_root, registry, base_ref)
    changed_files = _collect_changed_files(repo_root, resolved_base_ref)
    if not changed_files:
        return []

    mutable_surfaces = [surface for surface in ownership.owned_surfaces if surface.mode in MUTABLE_SURFACE_MODES]
    immutable_surfaces = [surface for surface in ownership.owned_surfaces if surface.mode not in MUTABLE_SURFACE_MODES]
    failures: list[str] = []

    for changed_file in changed_files:
        matched_mutable = [surface for surface in mutable_surfaces if _matches_any_pattern(changed_file, surface.paths)]
        matched_immutable = [surface for surface in immutable_surfaces if _matches_any_pattern(changed_file, surface.paths)]
        if matched_mutable:
            continue
        if matched_immutable:
            labels = ", ".join(f"{surface.surface_id} ({surface.mode})" for surface in matched_immutable)
            failures.append(f"{changed_file}: direct edits are not allowed for {labels}")
            continue
        failures.append(f"{changed_file}: outside declared owned surfaces for {ownership.workstream_id}")

    if failures:
        raise ValueError(
            "workstream surface ownership validation failed:\n- " + "\n- ".join(failures)
        )
    return changed_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate workstream surface ownership manifests and branch edits.")
    parser.add_argument("--validate-registry", action="store_true", help="Validate the ownership manifest registry.")
    parser.add_argument("--validate-branch", action="store_true", help="Validate the current branch against its manifest.")
    parser.add_argument("--base-ref", help="Git base ref to diff against when validating a branch.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root to validate.")
    args = parser.parse_args(argv)

    if not args.validate_registry and not args.validate_branch:
        parser.print_help()
        return 0

    try:
        registry = load_registry(args.repo_root / "workstreams.yaml")
        if args.validate_registry:
            validate_registry(registry)
            print("Workstream surface ownership registry OK")
        if args.validate_branch:
            validate_branch_ownership(repo_root=args.repo_root, registry=registry, base_ref=args.base_ref)
            print("Workstream branch ownership OK")
        return 0
    except (OSError, subprocess.CalledProcessError, ValueError, yaml.YAMLError) as exc:
        print(f"Workstream surface ownership validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
