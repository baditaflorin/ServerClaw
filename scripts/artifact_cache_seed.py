#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def normalize_registry_host(ref: str) -> str:
    first = ref.split("/", 1)[0]
    if "." not in first and ":" not in first and first != "localhost":
        return "docker.io"
    return first


def strip_registry_host(ref: str) -> str:
    host = normalize_registry_host(ref)
    prefix = f"{host}/"
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return ref


def normalize_mirror_registry(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme:
        return parsed.netloc.rstrip("/")
    return value.rstrip("/")


def iter_image_refs(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"image", "ref"} and isinstance(value, str):
                found.append(value)
            else:
                found.extend(iter_image_refs(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(iter_image_refs(item))
    return found


def collect_image_refs(catalog_paths: list[Path]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in catalog_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for ref in iter_image_refs(payload):
            if ref not in seen:
                seen.add(ref)
                ordered.append(ref)
    return ordered


def build_seed_plan(catalog_paths: list[Path], mirrors: dict[str, str]) -> dict[str, Any]:
    seed_images: list[dict[str, str]] = []
    unsupported_images: list[dict[str, str]] = []

    for ref in collect_image_refs(catalog_paths):
        registry_host = normalize_registry_host(ref)
        entry = {
            "registry_host": registry_host,
            "source_ref": ref,
        }
        mirror_registry = mirrors.get(registry_host)
        if mirror_registry:
            entry["mirror_ref"] = f"{normalize_mirror_registry(mirror_registry)}/{strip_registry_host(ref)}"
            seed_images.append(entry)
        else:
            unsupported_images.append(entry)

    return {
        "seed_images": seed_images,
        "unsupported_images": unsupported_images,
    }


def parse_mirror(arg: str) -> tuple[str, str]:
    if "=" not in arg:
        raise argparse.ArgumentTypeError("mirrors must use REGISTRY_HOST=host:port format")
    host, registry = arg.split("=", 1)
    host = host.strip()
    registry = registry.strip()
    if not host or not registry:
        raise argparse.ArgumentTypeError("mirrors must use REGISTRY_HOST=host:port format")
    return host, registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive the artifact cache warm set from repo-managed catalogs.")
    parser.add_argument(
        "--catalog",
        action="append",
        dest="catalogs",
        required=True,
        help="JSON catalog file that may contain image refs.",
    )
    parser.add_argument(
        "--mirror",
        action="append",
        dest="mirrors",
        default=[],
        type=parse_mirror,
        help="Registry mirror mapping in REGISTRY_HOST=host:port form; URL schemes are also accepted and normalized.",
    )
    args = parser.parse_args()

    catalog_paths = [Path(item).resolve() for item in args.catalogs]
    mirrors = dict(args.mirrors)
    plan = build_seed_plan(catalog_paths, mirrors)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
