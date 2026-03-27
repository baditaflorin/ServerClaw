#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


RENOVATE_CONFIG_PATH = repo_path("config", "renovate.json")
RENOVATE_CONFIG_SCHEMA_PATH = repo_path("docs", "schema", "renovate-config.schema.json")
REQUIRED_MANAGERS = {"ansible", "custom.regex", "github-actions", "pip_requirements"}
PATCH_AUTOMERGE_TYPES = {"digest", "patch", "pin", "pinDigest"}


def load_renovate_config(path: Path | None = None) -> dict[str, Any]:
    path = path or RENOVATE_CONFIG_PATH
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object")
    return payload


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def validate_renovate_config_schema(config: dict[str, Any]) -> None:
    try:
        import jsonschema
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing dependency: jsonschema. Run via 'uv run --with jsonschema python ...'."
        ) from exc

    jsonschema.validate(instance=config, schema=load_json(RENOVATE_CONFIG_SCHEMA_PATH))


def validate_renovate_config(config: dict[str, Any]) -> None:
    validate_renovate_config_schema(config)

    schema_url = _require_str(config.get("$schema"), "config/renovate.json.$schema")
    if schema_url != "https://docs.renovatebot.com/renovate-schema.json":
        raise ValueError("config/renovate.json.$schema must reference the Renovate schema URL")

    enabled_managers = {
        _require_str(value, f"config/renovate.json.enabledManagers[{index}]")
        for index, value in enumerate(_require_list(config.get("enabledManagers"), "config/renovate.json.enabledManagers"))
    }
    missing_managers = sorted(REQUIRED_MANAGERS - enabled_managers)
    if missing_managers:
        raise ValueError(
            f"config/renovate.json.enabledManagers is missing required managers {missing_managers}"
        )

    custom_managers = _require_list(config.get("customManagers"), "config/renovate.json.customManagers")
    image_catalog_manager = None
    for index, manager in enumerate(custom_managers):
        manager = _require_mapping(manager, f"config/renovate.json.customManagers[{index}]")
        manager_patterns = _require_list(
            manager.get("managerFilePatterns"),
            f"config/renovate.json.customManagers[{index}].managerFilePatterns",
        )
        if "/^config\\/image-catalog\\.json$/" in manager_patterns:
            image_catalog_manager = manager
            break
    if image_catalog_manager is None:
        raise ValueError(
            "config/renovate.json.customManagers must include a regex manager for config/image-catalog.json"
        )
    if image_catalog_manager.get("customType") != "regex":
        raise ValueError("config/renovate.json image catalog manager must use customType 'regex'")
    if image_catalog_manager.get("datasourceTemplate") != "docker":
        raise ValueError("config/renovate.json image catalog manager must use datasourceTemplate 'docker'")
    auto_replace = _require_str(
        image_catalog_manager.get("autoReplaceStringTemplate"),
        "config/renovate.json custom image-catalog manager.autoReplaceStringTemplate",
    )
    for token in ("{{{newValue}}}", "{{{newDigest}}}", "{{{depName}}}"):
        if token not in auto_replace:
            raise ValueError(
                "config/renovate.json image catalog autoReplaceStringTemplate must rewrite depName, tag, and digest"
            )

    package_rules = _require_list(config.get("packageRules"), "config/renovate.json.packageRules")
    found_patch_automerge = False
    found_manual_minor_major = False
    found_pip_range_replace = False
    for index, rule in enumerate(package_rules):
        rule = _require_mapping(rule, f"config/renovate.json.packageRules[{index}]")
        update_types = {
            _require_str(value, f"config/renovate.json.packageRules[{index}].matchUpdateTypes[{subindex}]")
            for subindex, value in enumerate(rule.get("matchUpdateTypes", []))
        }
        if update_types == PATCH_AUTOMERGE_TYPES and rule.get("automerge") is True:
            if rule.get("automergeType") != "pr":
                raise ValueError(
                    "config/renovate.json patch automerge rule must use automergeType 'pr'"
                )
            found_patch_automerge = True
        if update_types == {"major", "minor"} and rule.get("automerge") is False:
            found_manual_minor_major = True
        match_managers = set(rule.get("matchManagers", []))
        if match_managers == {"pip_requirements"} and rule.get("rangeStrategy") == "replace":
            found_pip_range_replace = True

    if not found_patch_automerge:
        raise ValueError(
            "config/renovate.json.packageRules must include a patch/digest automerge rule"
        )
    if not found_manual_minor_major:
        raise ValueError(
            "config/renovate.json.packageRules must include a non-automerge rule for minor and major updates"
        )
    if not found_pip_range_replace:
        raise ValueError(
            "config/renovate.json.packageRules must include a pip_requirements rangeStrategy replace rule"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the repo-managed Renovate configuration.")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate config/renovate.json against the local schema and policy checks.",
    )
    args = parser.parse_args()

    if not args.validate:
        parser.print_help()
        return 0

    try:
        validate_renovate_config(load_renovate_config())
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Renovate config", exc)

    print(f"Renovate config OK: {RENOVATE_CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
