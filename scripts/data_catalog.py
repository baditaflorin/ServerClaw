#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_bool, require_list, require_mapping, require_str, require_string_list

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


DATA_CATALOG_PATH = repo_path("config", "data-catalog.json")
DATA_CATALOG_SCHEMA_PATH = repo_path("docs", "schema", "data-catalog.schema.json")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
ALLOWED_CLASSES = {"secret", "confidential", "internal", "public"}
ALLOWED_PII_RISKS = {"none", "low", "medium", "high"}


def require_identifier(value: Any, path: str) -> str:
    value = require_str(value, path)
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if value[0] not in "abcdefghijklmnopqrstuvwxyz0123456789":
        raise ValueError(f"{path} must start with a lowercase letter or number")
    if any(char not in allowed for char in value):
        raise ValueError(f"{path} must use lowercase letters, numbers, hyphens, or underscores")
    return value


def load_data_catalog(path=DATA_CATALOG_PATH) -> dict[str, Any]:
    return require_mapping(load_json(path), str(path))


def validate_data_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("$schema") != "docs/schema/data-catalog.schema.json":
        raise ValueError("config/data-catalog.json.$schema must reference docs/schema/data-catalog.schema.json")
    if catalog.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"config/data-catalog.json.schema_version must be {SUPPORTED_SCHEMA_VERSION}")

    data_stores = require_list(catalog.get("data_stores"), "config/data-catalog.json.data_stores")
    if not data_stores:
        raise ValueError("config/data-catalog.json.data_stores must not be empty")

    seen_ids: set[str] = set()
    for index, store in enumerate(data_stores):
        path = f"config/data-catalog.json.data_stores[{index}]"
        store = require_mapping(store, path)
        store_id = require_identifier(store.get("id"), f"{path}.id")
        if store_id in seen_ids:
            raise ValueError(f"duplicate data store id: {store_id}")
        seen_ids.add(store_id)

        require_identifier(store.get("service"), f"{path}.service")
        require_str(store.get("name"), f"{path}.name")

        data_class = require_str(store.get("class"), f"{path}.class")
        if data_class not in ALLOWED_CLASSES:
            raise ValueError(f"{path}.class must be one of {sorted(ALLOWED_CLASSES)}")

        retention_days = store.get("retention_days")
        if retention_days is not None:
            if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 1:
                raise ValueError(f"{path}.retention_days must be null or an integer >= 1")

        require_bool(store.get("backup_included"), f"{path}.backup_included")
        access_role = require_str(store.get("access_role"), f"{path}.access_role")
        pii_risk = require_str(store.get("pii_risk"), f"{path}.pii_risk")
        if pii_risk not in ALLOWED_PII_RISKS:
            raise ValueError(f"{path}.pii_risk must be one of {sorted(ALLOWED_PII_RISKS)}")

        locations = require_string_list(store.get("locations"), f"{path}.locations")
        if not locations:
            raise ValueError(f"{path}.locations must not be empty")

        retention_paths = store.get("retention_paths")
        if retention_paths is not None:
            require_string_list(retention_paths, f"{path}.retention_paths")
            if retention_days is None:
                raise ValueError(f"{path}.retention_paths requires {path}.retention_days to be set")

        require_str(store.get("notes"), f"{path}.notes")

        if data_class == "public" and access_role != "public":
            raise ValueError(f"{path}.access_role must be public for public data stores")
        if data_class == "secret" and access_role == "public":
            raise ValueError(f"{path}.access_role must not be public for secret data stores")


def validate_data_catalog_schema(catalog: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError(
            "Missing dependency: jsonschema. Run via 'uv run --with pyyaml --with jsonschema python ...'."
        ) from exc

    jsonschema.validate(instance=catalog, schema=load_json(DATA_CATALOG_SCHEMA_PATH))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the platform data catalog.")
    parser.add_argument("--validate", action="store_true", help="Validate config/data-catalog.json.")
    args = parser.parse_args(argv)

    if not args.validate:
        parser.print_help()
        return 0

    try:
        catalog = load_data_catalog()
        validate_data_catalog(catalog)
        validate_data_catalog_schema(catalog)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Data catalog", exc)

    print("Data catalog OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
