#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
STACK_PATH = REPO_ROOT / "versions" / "stack.yaml"
IMAGE_CATALOG_PATH = REPO_ROOT / "config" / "image-catalog.json"

STACK_IMAGE_LINKS = (
    {
        "stack_path": ("ollama", "api_version"),
        "image_catalog_key": "ollama_runtime",
        "friendly_name": "ollama",
    },
)


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_git_object(ref: str, relative_path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{ref}:{relative_path}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def nested_get(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def docker_tag(ref: str) -> str | None:
    if ":" not in ref:
        return None
    without_digest = ref.split("@", 1)[0]
    return without_digest.rsplit(":", 1)[1]


def validate_against_base(base_ref: str) -> None:
    base_stack_text = load_git_object(base_ref, "versions/stack.yaml")
    base_catalog_text = load_git_object(base_ref, "config/image-catalog.json")
    if base_stack_text is None or base_catalog_text is None:
        return

    current_stack = load_yaml(STACK_PATH)
    current_catalog = load_json(IMAGE_CATALOG_PATH)
    base_stack = yaml.safe_load(base_stack_text)
    base_catalog = json.loads(base_catalog_text)

    failures: list[str] = []
    for link in STACK_IMAGE_LINKS:
        stack_path = tuple(link["stack_path"])
        image_catalog_key = str(link["image_catalog_key"])
        friendly_name = str(link["friendly_name"])

        current_version = nested_get(current_stack, stack_path)
        base_version = nested_get(base_stack, stack_path)
        current_ref = current_catalog["images"][image_catalog_key]["ref"]
        base_ref_value = base_catalog["images"][image_catalog_key]["ref"]

        if current_version == base_version:
            continue

        if current_ref == base_ref_value:
            failures.append(
                f"{friendly_name} changed {'.'.join(stack_path)} from {base_version} to {current_version} "
                f"without updating config/image-catalog.json:{image_catalog_key}"
            )
            continue

        current_tag = docker_tag(current_ref)
        if current_tag != str(current_version):
            failures.append(
                f"{friendly_name} changed {'.'.join(stack_path)} to {current_version} but "
                f"config/image-catalog.json:{image_catalog_key} still points to tag {current_tag}"
            )

    if failures:
        raise ValueError("\n".join(failures))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guard stack version changes that require an image-catalog digest update."
    )
    parser.add_argument("--base-ref", default="origin/main")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    validate_against_base(args.base_ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
