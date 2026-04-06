#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_list, require_mapping, require_str, require_string_list

from controller_automation_toolkit import emit_cli_error, load_yaml, repo_path


CATALOG_PATH = repo_path("config", "provider-boundary-catalog.yaml")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def require_identifier(value: Any, path: str) -> str:
    candidate = require_str(value, path)
    if not IDENTIFIER_PATTERN.fullmatch(candidate):
        raise ValueError(f"{path} must match {IDENTIFIER_PATTERN.pattern}")
    return candidate


def require_str_int_mapping(value: Any, path: str) -> dict[str, int]:
    mapping = require_mapping(value, path)
    normalized: dict[str, int] = {}
    for key, item in mapping.items():
        pattern = require_str(key, f"{path} key")
        if not isinstance(item, int) or item < 0:
            raise ValueError(f"{path}.{pattern} must be a non-negative integer")
        normalized[pattern] = item
    return normalized


def _resolve_repo_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise ValueError(f"provider-boundary paths must stay repository-relative: {relative_path}")
    return repo_path(*path.parts)


def validate_provider_boundary_catalog(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    schema_version = require_str(catalog.get("schema_version"), "provider-boundary-catalog.schema_version")
    if schema_version != "1.0.0":
        raise ValueError("provider-boundary-catalog.schema_version must be '1.0.0'")

    boundaries = require_list(catalog.get("provider_boundaries"), "provider-boundary-catalog.provider_boundaries")
    if not boundaries:
        raise ValueError("provider-boundary-catalog.provider_boundaries must not be empty")

    normalized: list[dict[str, Any]] = []
    seen_boundary_ids: set[str] = set()
    for index, entry in enumerate(boundaries):
        path = f"provider-boundary-catalog.provider_boundaries[{index}]"
        entry = require_mapping(entry, path)
        boundary_id = require_identifier(entry.get("boundary_id"), f"{path}.boundary_id")
        if boundary_id in seen_boundary_ids:
            raise ValueError(f"duplicate provider boundary id '{boundary_id}'")
        seen_boundary_ids.add(boundary_id)

        provider = require_identifier(entry.get("provider"), f"{path}.provider")
        concern = require_identifier(entry.get("concern"), f"{path}.concern")
        criticality = require_str(entry.get("criticality"), f"{path}.criticality")
        if criticality not in {"critical", "supporting"}:
            raise ValueError(f"{path}.criticality must be 'critical' or 'supporting'")

        implementation_paths = require_string_list(entry.get("implementation_paths"), f"{path}.implementation_paths")
        translation_tasks = require_string_list(entry.get("translation_tasks"), f"{path}.translation_tasks")
        raw_pattern_counts = require_str_int_mapping(entry.get("raw_pattern_counts"), f"{path}.raw_pattern_counts")
        canonical_patterns = require_string_list(entry.get("canonical_patterns"), f"{path}.canonical_patterns")

        resolved_paths = [_resolve_repo_path(item) for item in implementation_paths]
        contents: list[str] = []
        for file_path in resolved_paths:
            if not file_path.exists():
                raise ValueError(f"{path}.implementation_paths references a missing file: {file_path}")
            contents.append(file_path.read_text(encoding="utf-8"))
        aggregate = "\n".join(contents)

        for task_name in translation_tasks:
            if task_name not in aggregate:
                raise ValueError(f"{path}.translation_tasks references a missing task name: {task_name}")

        for raw_pattern, expected_count in raw_pattern_counts.items():
            actual_count = sum(content.count(raw_pattern) for content in contents)
            if actual_count != expected_count:
                raise ValueError(
                    f"{path}.raw_pattern_counts['{raw_pattern}'] expected {expected_count} occurrence(s), found {actual_count}"
                )

        for canonical_pattern in canonical_patterns:
            if canonical_pattern not in aggregate:
                raise ValueError(f"{path}.canonical_patterns references a missing literal: {canonical_pattern}")

        normalized.append(
            {
                "boundary_id": boundary_id,
                "provider": provider,
                "concern": concern,
                "criticality": criticality,
                "implementation_paths": implementation_paths,
                "translation_tasks": translation_tasks,
            }
        )

    return normalized


def load_provider_boundary_catalog(path: Path = CATALOG_PATH) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    catalog = require_mapping(load_yaml(path), str(path))
    normalized = validate_provider_boundary_catalog(catalog)
    return catalog, normalized


def list_provider_boundaries(normalized: list[dict[str, Any]]) -> int:
    print(f"Provider boundary catalog: {CATALOG_PATH}")
    for boundary in normalized:
        print(
            f"  - {boundary['boundary_id']} [{boundary['provider']}, {boundary['criticality']}]: "
            f"{', '.join(boundary['implementation_paths'])}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the provider-boundary anti-corruption catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and exit silently on success.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _catalog, normalized = load_provider_boundary_catalog()
    if args.validate:
        return 0
    return list_provider_boundaries(normalized)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        raise SystemExit(emit_cli_error("Provider boundary catalog", exc))
