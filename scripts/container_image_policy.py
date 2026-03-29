#!/usr/bin/env python3

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


IMAGE_CATALOG_PATH = repo_path("config", "image-catalog.json")
IMAGE_SCAN_RECEIPTS_DIR = repo_path("receipts", "image-scans")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]*$")
ALLOWED_KINDS = {"runtime", "build_base"}
ALLOWED_SCAN_STATUSES = {"pass_no_critical", "exception_open"}


def require_mapping(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_string_list(value: Any, path: str) -> list[str]:
    items = require_list(value, path)
    if not items:
        raise ValueError(f"{path} must not be empty")
    output: list[str] = []
    for index, item in enumerate(items):
        output.append(require_str(item, f"{path}[{index}]"))
    return output


def require_date(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not DATE_PATTERN.match(value):
        raise ValueError(f"{path} must use YYYY-MM-DD format")
    return value


def optional_mapping(value: Any, path: str) -> dict | None:
    if value is None:
        return None
    return require_mapping(value, path)


def require_digest(value: Any, path: str) -> str:
    value = require_str(value, path)
    if not DIGEST_PATTERN.match(value):
        raise ValueError(f"{path} must be a sha256 digest")
    return value


def load_image_catalog() -> dict:
    return load_json(IMAGE_CATALOG_PATH)


def validate_exception_metadata(exception: dict, path: str) -> None:
    require_str(exception.get("owner"), f"{path}.owner")
    if exception.get("justification") is not None:
        require_str(exception.get("justification"), f"{path}.justification")
    elif exception.get("reason") is not None:
        require_str(exception.get("reason"), f"{path}.reason")
    else:
        raise ValueError(f"{path}.justification must be a non-empty string")
    if exception.get("compensating_controls") is not None:
        require_string_list(exception.get("compensating_controls"), f"{path}.compensating_controls")
    approved_on = require_date(exception.get("approved_on"), f"{path}.approved_on")
    expires_on_key = "expires_on" if exception.get("expires_on") is not None else "review_by"
    expires_on = require_date(exception.get(expires_on_key), f"{path}.{expires_on_key}")
    if exception.get("remediation_plan") is not None:
        require_str(exception.get("remediation_plan"), f"{path}.remediation_plan")
    if expires_on < approved_on:
        raise ValueError(f"{path}.expires_on must be on or after approved_on")


def validate_image_catalog(catalog: dict) -> None:
    if catalog.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"image catalog must declare schema_version '{SUPPORTED_SCHEMA_VERSION}'"
        )

    images = require_mapping(catalog.get("images"), "images")
    if not images:
        raise ValueError("images must not be empty")

    seen_refs = set()
    for image_id, entry in sorted(images.items()):
        if not IDENTIFIER_PATTERN.match(image_id):
            raise ValueError(f"image id '{image_id}' must use lowercase snake_case")

        entry = require_mapping(entry, f"images.{image_id}")
        kind = require_str(entry.get("kind"), f"images.{image_id}.kind")
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"images.{image_id}.kind must be one of {sorted(ALLOWED_KINDS)}")

        registry_ref = require_str(entry.get("registry_ref"), f"images.{image_id}.registry_ref")
        if "@" in registry_ref:
            raise ValueError(f"images.{image_id}.registry_ref must not include a digest")

        tag = require_str(entry.get("tag"), f"images.{image_id}.tag")
        if tag == "latest":
            raise ValueError(f"images.{image_id}.tag must not use 'latest'")

        digest = require_digest(entry.get("digest"), f"images.{image_id}.digest")
        expected_ref = f"{registry_ref}:{tag}@{digest}"
        ref = require_str(entry.get("ref"), f"images.{image_id}.ref")
        if ref != expected_ref:
            raise ValueError(f"images.{image_id}.ref must equal '{expected_ref}'")
        if ref in seen_refs:
            raise ValueError(f"images.{image_id}.ref duplicates another catalog entry")
        seen_refs.add(ref)

        platform = require_str(entry.get("platform"), f"images.{image_id}.platform")
        if platform != "linux/amd64":
            raise ValueError(f"images.{image_id}.platform must be linux/amd64 for this platform")

        require_date(entry.get("pinned_on"), f"images.{image_id}.pinned_on")
        scan_status = require_str(entry.get("scan_status"), f"images.{image_id}.scan_status")
        if scan_status not in ALLOWED_SCAN_STATUSES:
            raise ValueError(
                f"images.{image_id}.scan_status must be one of {sorted(ALLOWED_SCAN_STATUSES)}"
            )

        receipt_rel = require_str(entry.get("scan_receipt"), f"images.{image_id}.scan_receipt")
        receipt_path = repo_path(*Path(receipt_rel).parts)
        if not receipt_path.is_file():
            raise ValueError(f"images.{image_id}.scan_receipt references missing file '{receipt_rel}'")

        consumers = require_list(entry.get("consumers"), f"images.{image_id}.consumers")
        if not consumers:
            raise ValueError(f"images.{image_id}.consumers must not be empty")
        for index, consumer in enumerate(consumers):
            consumer = require_str(consumer, f"images.{image_id}.consumers[{index}]")
            if not repo_path(*Path(consumer).parts).exists():
                raise ValueError(
                    f"images.{image_id}.consumers[{index}] references missing path '{consumer}'"
                )

        apply_targets = require_list(entry.get("apply_targets"), f"images.{image_id}.apply_targets")
        if not apply_targets:
            raise ValueError(f"images.{image_id}.apply_targets must not be empty")
        for index, target in enumerate(apply_targets):
            require_str(target, f"images.{image_id}.apply_targets[{index}]")

        receipt = load_json(receipt_path)
        validate_scan_receipt(receipt, receipt_path, image_id, ref)

        exception = optional_mapping(entry.get("exception"), f"images.{image_id}.exception")
        critical_count = receipt["summary"]["critical"]
        if exception is None:
            if critical_count > 0:
                raise ValueError(f"images.{image_id}.exception is required when critical findings are present")
            if scan_status != "pass_no_critical":
                raise ValueError(
                    f"images.{image_id}.scan_status must be 'pass_no_critical' when no active exception is recorded"
                )
            continue

        validate_exception_metadata(exception, f"images.{image_id}.exception")
        if scan_status != "exception_open":
            raise ValueError(
                f"images.{image_id}.scan_status must be 'exception_open' when an exception is recorded"
            )


def validate_scan_receipt(receipt: dict, path: Path, image_id: str, ref: str) -> None:
    if receipt.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"{path}: schema_version must be '{SUPPORTED_SCHEMA_VERSION}'")
    if receipt.get("image_id") != image_id:
        raise ValueError(f"{path}: image_id must equal '{image_id}'")
    if receipt.get("image_ref") != ref:
        raise ValueError(f"{path}: image_ref must equal '{ref}'")
    if receipt.get("scanner") != "trivy":
        raise ValueError(f"{path}: scanner must be 'trivy'")

    require_date(receipt.get("scanned_on"), f"{path}.scanned_on")
    summary = require_mapping(receipt.get("summary"), f"{path}.summary")
    critical = summary.get("critical", None)
    high = summary.get("high", None)
    if not isinstance(critical, int) or critical < 0:
        raise ValueError(f"{path}.summary.critical must be a non-negative integer")
    if not isinstance(high, int) or high < 0:
        raise ValueError(f"{path}.summary.high must be a non-negative integer")


def split_image_reference(registry_ref: str) -> tuple[str, str]:
    if registry_ref.startswith("docker.io/"):
        return "registry-1.docker.io", registry_ref.removeprefix("docker.io/")
    if registry_ref.startswith("ghcr.io/"):
        return "ghcr.io", registry_ref.removeprefix("ghcr.io/")
    first_segment = registry_ref.split("/", 1)[0]
    if "." in first_segment or ":" in first_segment:
        return first_segment, registry_ref.split("/", 1)[1]
    raise ValueError(f"unsupported registry in '{registry_ref}'")


def fetch_bearer_token(registry: str, repository: str) -> str | None:
    if registry == "ghcr.io":
        url = f"https://ghcr.io/token?scope=repository:{repository}:pull"
    elif registry == "registry-1.docker.io":
        query = urllib.parse.urlencode(
            {"service": "registry.docker.io", "scope": f"repository:{repository}:pull"}
        )
        url = f"https://auth.docker.io/token?{query}"
    else:
        return None

    with urllib.request.urlopen(url) as response:
        payload = json.load(response)
    return payload["token"]


def fetch_registry_json(url: str, token: str | None, *, accept: str | None = None) -> dict:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def fetch_registry_payload(url: str, token: str | None, *, accept: str | None = None) -> tuple[dict, str | None]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        payload = json.load(response)
        return payload, response.headers.get("Docker-Content-Digest")


def resolve_remote_digest(registry_ref: str, tag: str, platform: str = "linux/amd64") -> str:
    registry, repository = split_image_reference(registry_ref)
    token = fetch_bearer_token(registry, repository)
    manifest, manifest_digest = fetch_registry_payload(
        f"https://{registry}/v2/{repository}/manifests/{tag}",
        token,
        accept=(
            "application/vnd.oci.image.index.v1+json, "
            "application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.oci.image.manifest.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json"
        ),
    )

    manifests = manifest.get("manifests")
    if not manifests:
        return require_digest(manifest_digest, "remote digest")

    arch = platform.split("/", 1)[1]
    for item in manifests:
        item_platform = item.get("platform", {})
        if item_platform.get("os") == "linux" and item_platform.get("architecture") == arch:
            return require_digest(item.get("digest"), "remote digest")
    raise ValueError(f"no manifest for platform '{platform}' under '{registry_ref}:{tag}'")


def check_freshness(catalog: dict) -> int:
    images = catalog["images"]
    drift_count = 0
    for image_id, entry in sorted(images.items()):
        remote_digest = resolve_remote_digest(entry["registry_ref"], entry["tag"], entry["platform"])
        status = "current" if remote_digest == entry["digest"] else "drifted"
        print(f"{image_id}: {status}")
        if status == "drifted":
            drift_count += 1
            print(f"  catalog: {entry['digest']}")
            print(f"  remote:  {remote_digest}")

    print(f"Summary: {len(images) - drift_count} current, {drift_count} drifted")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and inspect the managed container image policy catalog."
    )
    parser.add_argument("--validate", action="store_true", help="Validate the catalog and receipts.")
    parser.add_argument(
        "--check-freshness",
        action="store_true",
        help="Compare pinned digests against current upstream digests.",
    )
    args = parser.parse_args()

    try:
        catalog = load_image_catalog()
        validate_image_catalog(catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit_cli_error("Container image policy", exc)

    if args.validate:
        print(f"Container image policy OK: {IMAGE_CATALOG_PATH}")
        return 0

    if args.check_freshness:
        try:
            return check_freshness(catalog)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return emit_cli_error("Container image freshness", exc)

    print(f"Container image catalog: {IMAGE_CATALOG_PATH}")
    for image_id, entry in sorted(catalog["images"].items()):
        print(f"  - {image_id}: {entry['ref']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
