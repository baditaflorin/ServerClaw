#!/usr/bin/env python3
"""Inspect and resolve the ADR 0264 validation-lane catalog."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = REPO_ROOT / "config" / "validation-lanes.yaml"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "config" / "validation-gate.json"
ALL_LANES_POLICY = "all_lanes"


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
    return value.strip()


def _normalized_pattern(value: Any, path: str) -> str:
    pattern = _require_str(value, path).replace("\\", "/")
    if pattern.startswith("/"):
        raise ValueError(f"{path} must be repository-relative, not absolute")
    return pattern


def _unique_in_order(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _require_mapping(payload, str(path))


def load_manifest_checks(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> set[str]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = _require_mapping(payload, str(manifest_path))
    return {check_id for check_id in manifest}


@dataclass(frozen=True)
class ValidationLane:
    lane_id: str
    title: str
    description: str
    checks: tuple[str, ...]


@dataclass(frozen=True)
class ValidationSurfaceClass:
    surface_id: str
    title: str
    paths: tuple[str, ...]
    required_lanes: tuple[str, ...]


@dataclass(frozen=True)
class ValidationLaneCatalog:
    schema_version: str
    primary_branch: str
    unknown_surface_policy: str
    fast_global_checks: tuple[str, ...]
    lanes: dict[str, ValidationLane]
    surface_classes: tuple[ValidationSurfaceClass, ...]

    @property
    def lane_ids(self) -> tuple[str, ...]:
        return tuple(self.lanes)

    def all_checks(self) -> tuple[str, ...]:
        checks: list[str] = list(self.fast_global_checks)
        for lane in self.lanes.values():
            checks.extend(lane.checks)
        return _unique_in_order(checks)


@dataclass(frozen=True)
class MatchedSurfaceClass:
    surface_id: str
    title: str
    required_lanes: tuple[str, ...]
    matched_files: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "title": self.title,
            "required_lanes": list(self.required_lanes),
            "matched_files": list(self.matched_files),
        }


@dataclass(frozen=True)
class ValidationLaneSelection:
    mode: str
    branch: str
    base_ref: str | None
    changed_files: tuple[str, ...]
    selected_lanes: tuple[str, ...]
    blocking_checks: tuple[str, ...]
    fast_global_checks: tuple[str, ...]
    skipped_checks: tuple[str, ...]
    matched_surfaces: tuple[MatchedSurfaceClass, ...]
    unknown_files: tuple[str, ...]
    widened_to_all_lanes: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "branch": self.branch,
            "base_ref": self.base_ref,
            "changed_files": list(self.changed_files),
            "selected_lanes": list(self.selected_lanes),
            "blocking_checks": list(self.blocking_checks),
            "fast_global_checks": list(self.fast_global_checks),
            "skipped_checks": list(self.skipped_checks),
            "matched_surfaces": [surface.as_dict() for surface in self.matched_surfaces],
            "unknown_files": list(self.unknown_files),
            "widened_to_all_lanes": self.widened_to_all_lanes,
        }


def load_catalog(
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    manifest_checks: set[str] | None = None,
) -> ValidationLaneCatalog:
    payload = _load_yaml(catalog_path)
    schema_version = _require_str(payload.get("schema_version"), f"{catalog_path}.schema_version")
    primary_branch = _require_str(payload.get("primary_branch", "main"), f"{catalog_path}.primary_branch")
    unknown_surface_policy = _require_str(
        payload.get("unknown_surface_policy", ALL_LANES_POLICY),
        f"{catalog_path}.unknown_surface_policy",
    )
    if unknown_surface_policy != ALL_LANES_POLICY:
        raise ValueError(f"{catalog_path}.unknown_surface_policy must be '{ALL_LANES_POLICY}'")

    fast_global_checks = tuple(
        _require_str(check_id, f"{catalog_path}.fast_global_checks[{index}]")
        for index, check_id in enumerate(_require_list(payload.get("fast_global_checks"), f"{catalog_path}.fast_global_checks"))
    )
    if not fast_global_checks:
        raise ValueError(f"{catalog_path}.fast_global_checks must not be empty")
    if len(set(fast_global_checks)) != len(fast_global_checks):
        raise ValueError(f"{catalog_path}.fast_global_checks must not contain duplicates")

    lanes_payload = _require_mapping(payload.get("lanes"), f"{catalog_path}.lanes")
    lanes: dict[str, ValidationLane] = {}
    for lane_id, raw_lane in lanes_payload.items():
        lane_path = f"{catalog_path}.lanes.{lane_id}"
        lane = _require_mapping(raw_lane, lane_path)
        checks = tuple(
            _require_str(check_id, f"{lane_path}.checks[{index}]")
            for index, check_id in enumerate(_require_list(lane.get("checks"), f"{lane_path}.checks"))
        )
        if not checks:
            raise ValueError(f"{lane_path}.checks must not be empty")
        if len(set(checks)) != len(checks):
            raise ValueError(f"{lane_path}.checks must not contain duplicates")
        lanes[lane_id] = ValidationLane(
            lane_id=lane_id,
            title=_require_str(lane.get("title"), f"{lane_path}.title"),
            description=_require_str(lane.get("description"), f"{lane_path}.description"),
            checks=checks,
        )

    surface_classes_payload = _require_list(payload.get("surface_classes"), f"{catalog_path}.surface_classes")
    surface_classes: list[ValidationSurfaceClass] = []
    surface_ids: set[str] = set()
    for index, raw_surface in enumerate(surface_classes_payload):
        surface_path = f"{catalog_path}.surface_classes[{index}]"
        surface = _require_mapping(raw_surface, surface_path)
        surface_id = _require_str(surface.get("surface_id"), f"{surface_path}.surface_id")
        if surface_id in surface_ids:
            raise ValueError(f"{catalog_path}.surface_classes duplicates surface_id '{surface_id}'")
        surface_ids.add(surface_id)
        required_lanes = tuple(
            _require_str(lane_id, f"{surface_path}.required_lanes[{lane_index}]")
            for lane_index, lane_id in enumerate(
                _require_list(surface.get("required_lanes"), f"{surface_path}.required_lanes")
            )
        )
        if not required_lanes:
            raise ValueError(f"{surface_path}.required_lanes must not be empty")
        for lane_id in required_lanes:
            if lane_id not in lanes:
                raise ValueError(f"{surface_path}.required_lanes references unknown lane '{lane_id}'")
        paths = tuple(
            _normalized_pattern(pattern, f"{surface_path}.paths[{path_index}]")
            for path_index, pattern in enumerate(_require_list(surface.get("paths"), f"{surface_path}.paths"))
        )
        if not paths:
            raise ValueError(f"{surface_path}.paths must not be empty")
        surface_classes.append(
            ValidationSurfaceClass(
                surface_id=surface_id,
                title=_require_str(surface.get("title"), f"{surface_path}.title"),
                paths=paths,
                required_lanes=required_lanes,
            )
        )

    catalog = ValidationLaneCatalog(
        schema_version=schema_version,
        primary_branch=primary_branch,
        unknown_surface_policy=unknown_surface_policy,
        fast_global_checks=fast_global_checks,
        lanes=lanes,
        surface_classes=tuple(surface_classes),
    )
    if manifest_checks is not None:
        validate_catalog_against_manifest(catalog, manifest_checks)
    return catalog


def validate_catalog_against_manifest(catalog: ValidationLaneCatalog, manifest_checks: set[str]) -> None:
    catalog_checks = set(catalog.all_checks())
    missing_checks = sorted(catalog_checks - manifest_checks)
    if missing_checks:
        raise ValueError(
            "validation lane catalog references unknown manifest checks: " + ", ".join(missing_checks)
        )
    unassigned_checks = sorted(manifest_checks - catalog_checks)
    if unassigned_checks:
        raise ValueError(
            "validation gate manifest contains checks with no lane assignment: " + ", ".join(unassigned_checks)
        )


def _run_git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def detect_current_branch(repo_root: Path = REPO_ROOT) -> str:
    result = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch else "HEAD"


def resolve_base_ref(
    repo_root: Path = REPO_ROOT,
    *,
    primary_branch: str = "main",
    explicit_base_ref: str | None = None,
) -> str:
    if explicit_base_ref:
        return explicit_base_ref
    remote_candidate = f"origin/{primary_branch}"
    remote_exists = _run_git(repo_root, "show-ref", "--verify", "--quiet", f"refs/remotes/{remote_candidate}", check=False)
    if remote_exists.returncode == 0:
        return remote_candidate
    return primary_branch


def collect_changed_files(repo_root: Path = REPO_ROOT, *, base_ref: str) -> tuple[str, ...]:
    merge_base_result = _run_git(repo_root, "merge-base", base_ref, "HEAD", check=False)
    if merge_base_result.returncode != 0:
        return ()
    merge_base = merge_base_result.stdout.strip()
    if not merge_base:
        return ()

    changed: set[str] = set()
    commands = (
        ("diff", "--name-only", f"{merge_base}..HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    for args in commands:
        result = _run_git(repo_root, *args, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        for line in result.stdout.splitlines():
            normalized = line.strip().replace("\\", "/")
            if normalized:
                changed.add(normalized)
    return tuple(sorted(changed))


def _matches_any_pattern(repo_path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(repo_path, pattern) for pattern in patterns)


def resolve_selection_from_changed_files(
    catalog: ValidationLaneCatalog,
    manifest_checks: set[str],
    *,
    changed_files: tuple[str, ...] | list[str],
    branch: str,
    base_ref: str | None,
    explicit_checks: tuple[str, ...] | list[str] = (),
    explicit_lanes: tuple[str, ...] | list[str] = (),
    force_all_lanes: bool = False,
) -> ValidationLaneSelection:
    validate_catalog_against_manifest(catalog, manifest_checks)
    ordered_lane_ids = catalog.lane_ids
    changed_files = tuple(changed_files)
    explicit_checks = tuple(explicit_checks)
    explicit_lanes = tuple(explicit_lanes)
    selected_lanes: tuple[str, ...]
    matched_surfaces: tuple[MatchedSurfaceClass, ...] = ()
    unknown_files: tuple[str, ...] = ()
    widened = False

    if explicit_checks:
        unknown_checks = sorted(set(explicit_checks) - manifest_checks)
        if unknown_checks:
            raise ValueError("explicit checks reference unknown manifest ids: " + ", ".join(unknown_checks))
        selected_lanes = tuple(
            lane_id for lane_id in ordered_lane_ids if any(check in catalog.lanes[lane_id].checks for check in explicit_checks)
        )
        blocking_checks = _unique_in_order(list(catalog.fast_global_checks) + list(explicit_checks))
        skipped_checks = tuple(sorted(manifest_checks - set(blocking_checks)))
        return ValidationLaneSelection(
            mode="explicit_checks",
            branch=branch,
            base_ref=base_ref,
            changed_files=changed_files,
            selected_lanes=selected_lanes,
            blocking_checks=blocking_checks,
            fast_global_checks=catalog.fast_global_checks,
            skipped_checks=skipped_checks,
            matched_surfaces=matched_surfaces,
            unknown_files=unknown_files,
            widened_to_all_lanes=False,
        )

    if explicit_lanes:
        for lane_id in explicit_lanes:
            if lane_id not in catalog.lanes:
                raise ValueError(f"explicit lanes reference unknown lane '{lane_id}'")
        selected_lanes = _unique_in_order(list(explicit_lanes))
        blocking_checks = _unique_in_order(
            list(catalog.fast_global_checks)
            + [check_id for lane_id in selected_lanes for check_id in catalog.lanes[lane_id].checks]
        )
        skipped_checks = tuple(sorted(manifest_checks - set(blocking_checks)))
        return ValidationLaneSelection(
            mode="explicit_lanes",
            branch=branch,
            base_ref=base_ref,
            changed_files=changed_files,
            selected_lanes=selected_lanes,
            blocking_checks=blocking_checks,
            fast_global_checks=catalog.fast_global_checks,
            skipped_checks=skipped_checks,
            matched_surfaces=matched_surfaces,
            unknown_files=unknown_files,
            widened_to_all_lanes=False,
        )

    if force_all_lanes or branch in {catalog.primary_branch, "HEAD"} or not changed_files:
        mode = "all_lanes" if force_all_lanes else ("primary_branch" if branch in {catalog.primary_branch, "HEAD"} else "no_changes")
        selected_lanes = ordered_lane_ids
        blocking_checks = _unique_in_order(
            list(catalog.fast_global_checks)
            + [check_id for lane_id in selected_lanes for check_id in catalog.lanes[lane_id].checks]
        )
        skipped_checks = tuple(sorted(manifest_checks - set(blocking_checks)))
        return ValidationLaneSelection(
            mode=mode,
            branch=branch,
            base_ref=base_ref,
            changed_files=changed_files,
            selected_lanes=selected_lanes,
            blocking_checks=blocking_checks,
            fast_global_checks=catalog.fast_global_checks,
            skipped_checks=skipped_checks,
            matched_surfaces=matched_surfaces,
            unknown_files=unknown_files,
            widened_to_all_lanes=False,
        )

    matched: list[MatchedSurfaceClass] = []
    known_files: set[str] = set()
    selected_lane_set: set[str] = set()
    for surface in catalog.surface_classes:
        surface_matches = tuple(sorted(file_path for file_path in changed_files if _matches_any_pattern(file_path, surface.paths)))
        if not surface_matches:
            continue
        known_files.update(surface_matches)
        matched.append(
            MatchedSurfaceClass(
                surface_id=surface.surface_id,
                title=surface.title,
                required_lanes=surface.required_lanes,
                matched_files=surface_matches,
            )
        )
        selected_lane_set.update(surface.required_lanes)

    unknown_files = tuple(sorted(file_path for file_path in changed_files if file_path not in known_files))
    if unknown_files and catalog.unknown_surface_policy == ALL_LANES_POLICY:
        selected_lanes = ordered_lane_ids
        widened = True
    elif selected_lane_set:
        selected_lanes = tuple(lane_id for lane_id in ordered_lane_ids if lane_id in selected_lane_set)
    else:
        selected_lanes = ordered_lane_ids
        widened = True

    blocking_checks = _unique_in_order(
        list(catalog.fast_global_checks)
        + [check_id for lane_id in selected_lanes for check_id in catalog.lanes[lane_id].checks]
    )
    skipped_checks = tuple(sorted(manifest_checks - set(blocking_checks)))
    return ValidationLaneSelection(
        mode="auto",
        branch=branch,
        base_ref=base_ref,
        changed_files=changed_files,
        selected_lanes=selected_lanes,
        blocking_checks=blocking_checks,
        fast_global_checks=catalog.fast_global_checks,
        skipped_checks=skipped_checks,
        matched_surfaces=tuple(matched),
        unknown_files=unknown_files,
        widened_to_all_lanes=widened,
    )


def resolve_selection_for_repo(
    catalog: ValidationLaneCatalog,
    manifest_checks: set[str],
    *,
    repo_root: Path = REPO_ROOT,
    base_ref: str | None = None,
    explicit_checks: tuple[str, ...] | list[str] = (),
    explicit_lanes: tuple[str, ...] | list[str] = (),
    force_all_lanes: bool = False,
) -> ValidationLaneSelection:
    repo_root = repo_root.resolve()
    branch = detect_current_branch(repo_root)
    resolved_base_ref = resolve_base_ref(repo_root, primary_branch=catalog.primary_branch, explicit_base_ref=base_ref)
    changed_files = collect_changed_files(repo_root, base_ref=resolved_base_ref) if not force_all_lanes else ()
    return resolve_selection_from_changed_files(
        catalog,
        manifest_checks,
        changed_files=changed_files,
        branch=branch,
        base_ref=resolved_base_ref,
        explicit_checks=explicit_checks,
        explicit_lanes=explicit_lanes,
        force_all_lanes=force_all_lanes,
    )


def render_selection_summary(selection: ValidationLaneSelection) -> str:
    changed_preview = ", ".join(selection.changed_files[:6])
    if len(selection.changed_files) > 6:
        changed_preview += ", ..."
    lines = [
        "Validation lane selection",
        f"  mode: {selection.mode}",
        f"  branch: {selection.branch}",
        f"  selected lanes: {', '.join(selection.selected_lanes) if selection.selected_lanes else 'none'}",
        f"  blocking checks: {', '.join(selection.blocking_checks) if selection.blocking_checks else 'none'}",
    ]
    if selection.changed_files:
        lines.append(f"  changed files: {changed_preview}")
    if selection.unknown_files:
        lines.append(
            "  widened to all lanes because of unknown surfaces: " + ", ".join(selection.unknown_files)
        )
    return "\n".join(lines)


def _list_lanes(catalog: ValidationLaneCatalog) -> int:
    print(f"Validation lane catalog: {DEFAULT_CATALOG_PATH}")
    for lane_id, lane in catalog.lanes.items():
        print(f"  - {lane_id}: {lane.title} [{', '.join(lane.checks)}]")
    return 0


def _show_lane(catalog: ValidationLaneCatalog, lane_id: str) -> int:
    lane = catalog.lanes.get(lane_id)
    if lane is None:
        print(f"Unknown validation lane: {lane_id}", file=sys.stderr)
        return 1
    print(f"Lane: {lane.lane_id}")
    print(f"Title: {lane.title}")
    print(f"Description: {lane.description}")
    print("Checks:")
    for check_id in lane.checks:
        print(f"  - {check_id}")
    print("Surface classes:")
    for surface in catalog.surface_classes:
        if lane_id in surface.required_lanes:
            print(f"  - {surface.surface_id}: {', '.join(surface.paths)}")
    return 0


def _resolve_and_print(args: argparse.Namespace) -> int:
    manifest_checks = load_manifest_checks(args.manifest)
    catalog = load_catalog(catalog_path=args.catalog, manifest_checks=manifest_checks)
    selection = resolve_selection_for_repo(
        catalog,
        manifest_checks,
        repo_root=args.repo_root,
        base_ref=args.base_ref,
        explicit_checks=tuple(args.check or ()),
        explicit_lanes=tuple(args.select_lane or ()),
        force_all_lanes=args.all_lanes,
    )
    print(json.dumps(selection.as_dict(), indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or validate the ADR 0264 validation-lane catalog.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH, help="Path to the validation-lane catalog.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH, help="Path to the validation-gate manifest.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root for lane resolution.")
    parser.add_argument("--base-ref", help="Explicit git base ref to diff against.")
    parser.add_argument("--validate", action="store_true", help="Validate the lane catalog against the gate manifest.")
    parser.add_argument("--list", action="store_true", help="List available lanes.")
    parser.add_argument("--lane", help="Show one lane from the catalog.")
    parser.add_argument("--resolve", action="store_true", help="Resolve the selected lanes for the current checkout.")
    parser.add_argument("--all-lanes", action="store_true", help="Resolve all lanes regardless of changed surfaces.")
    parser.add_argument("--check", action="append", help="Resolve using explicit check ids instead of changed files.")
    parser.add_argument("--select-lane", action="append", help="Resolve using explicit lane ids instead of changed files.")
    args = parser.parse_args(argv)

    try:
        manifest_checks = load_manifest_checks(args.manifest)
        catalog = load_catalog(catalog_path=args.catalog, manifest_checks=manifest_checks)
        if args.validate:
            print(f"Validation lanes OK: {args.catalog}")
            return 0
        if args.list:
            return _list_lanes(catalog)
        if args.lane:
            return _show_lane(catalog, args.lane)
        if args.resolve:
            return _resolve_and_print(args)
        parser.print_help()
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError, yaml.YAMLError) as exc:
        print(f"Validation lanes failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
