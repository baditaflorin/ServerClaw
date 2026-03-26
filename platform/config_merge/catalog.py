from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
MERGE_ELIGIBLE_PATH = REPO_ROOT / "config" / "merge-eligible-files.yaml"
ALLOWED_FORMATS = {"json", "yaml"}
ALLOWED_COLLECTION_TYPES = {"list", "mapping"}
ALLOWED_CONFLICT_RESOLUTIONS = {"reject_duplicate_key", "last_write_wins"}
ALLOWED_OPERATIONS = {"append", "update", "delete"}


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


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _require_string_list(value: Any, path: str) -> list[str]:
    items = _require_list(value, path)
    return [_require_str(item, f"{path}[{index}]") for index, item in enumerate(items)]


@dataclass(frozen=True)
class MergeEligibleFileSpec:
    file_path: str
    format: str
    collection_path: tuple[str, ...]
    collection_type: str
    key_field: str
    conflict_resolution: str
    allowed_operations: tuple[str, ...]
    value_field: str | None = None
    drop_key_field_on_write: bool = False


def _normalize_spec(payload: dict[str, Any], *, path: str) -> MergeEligibleFileSpec:
    file_path = _require_str(payload.get("file"), f"{path}.file")
    format_name = _require_str(payload.get("format"), f"{path}.format")
    if format_name not in ALLOWED_FORMATS:
        raise ValueError(f"{path}.format must be one of {sorted(ALLOWED_FORMATS)}")

    collection_path = tuple(_require_string_list(payload.get("collection_path"), f"{path}.collection_path"))
    collection_type = _require_str(payload.get("collection_type"), f"{path}.collection_type")
    if collection_type not in ALLOWED_COLLECTION_TYPES:
        raise ValueError(f"{path}.collection_type must be one of {sorted(ALLOWED_COLLECTION_TYPES)}")

    key_field = _require_str(payload.get("key_field"), f"{path}.key_field")
    conflict_resolution = _require_str(payload.get("conflict_resolution"), f"{path}.conflict_resolution")
    if conflict_resolution not in ALLOWED_CONFLICT_RESOLUTIONS:
        raise ValueError(f"{path}.conflict_resolution must be one of {sorted(ALLOWED_CONFLICT_RESOLUTIONS)}")

    allowed_operations = tuple(_require_string_list(payload.get("allowed_operations"), f"{path}.allowed_operations"))
    unknown_operations = sorted(set(allowed_operations) - ALLOWED_OPERATIONS)
    if unknown_operations:
        raise ValueError(
            f"{path}.allowed_operations references unknown operations: {', '.join(unknown_operations)}"
        )

    value_field = payload.get("value_field")
    if value_field is not None:
        value_field = _require_str(value_field, f"{path}.value_field")
    drop_key_field_on_write = payload.get("drop_key_field_on_write", False)
    _require_bool(drop_key_field_on_write, f"{path}.drop_key_field_on_write")

    if collection_type == "mapping" and value_field is not None:
        raise ValueError(f"{path}.value_field is not supported for mapping collections")

    return MergeEligibleFileSpec(
        file_path=file_path,
        format=format_name,
        collection_path=collection_path,
        collection_type=collection_type,
        key_field=key_field,
        conflict_resolution=conflict_resolution,
        allowed_operations=allowed_operations,
        value_field=value_field,
        drop_key_field_on_write=drop_key_field_on_write,
    )


def load_merge_eligible_catalog(path: str | Path | None = None) -> dict[str, MergeEligibleFileSpec]:
    catalog_path = Path(path) if path is not None else MERGE_ELIGIBLE_PATH
    payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    payload = _require_mapping(payload, str(catalog_path))
    if _require_str(payload.get("schema_version"), f"{catalog_path}.schema_version") != "1.0.0":
        raise ValueError(f"{catalog_path}.schema_version must be '1.0.0'")

    entries = _require_list(payload.get("merge_eligible"), f"{catalog_path}.merge_eligible")
    if not entries:
        raise ValueError(f"{catalog_path}.merge_eligible must not be empty")

    result: dict[str, MergeEligibleFileSpec] = {}
    for index, raw in enumerate(entries):
        spec = _normalize_spec(_require_mapping(raw, f"{catalog_path}.merge_eligible[{index}]"), path=f"{catalog_path}.merge_eligible[{index}]")
        if spec.file_path in result:
            raise ValueError(f"duplicate merge-eligible file entry '{spec.file_path}'")
        result[spec.file_path] = spec
    return result


def validate_merge_eligible_catalog(path: str | Path | None = None) -> dict[str, MergeEligibleFileSpec]:
    return load_merge_eligible_catalog(path)
