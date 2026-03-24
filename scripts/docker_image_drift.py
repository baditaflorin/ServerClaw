#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from controller_automation_toolkit import load_json, repo_path
from drift_lib import (
    build_guest_ssh_command,
    drift_event_topic,
    load_controller_context,
    normalize_image_reference,
    run_command,
)


IMAGE_CATALOG_PATH = repo_path("config", "image-catalog.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")


def iter_runtime_images() -> list[dict[str, Any]]:
    payload = load_json(IMAGE_CATALOG_PATH)
    images = payload.get("images", {})
    normalized: list[dict[str, Any]] = []
    if isinstance(images, dict):
        for image_id, image in images.items():
            if not isinstance(image, dict) or image.get("kind") != "runtime":
                continue
            if not image.get("runtime_host") or not image.get("container_name"):
                continue
            normalized.append(
                {
                    "image_id": image_id,
                    "service_id": image.get("service_id", image_id),
                    "runtime_host": image["runtime_host"],
                    "container_name": image["container_name"],
                    "expected_digest": str(image.get("digest", "")),
                    "expected_reference": str(image.get("ref", "")),
                }
            )
    return sorted(normalized, key=lambda item: item["image_id"])


def parse_inspect_output(stdout: str) -> dict[str, Any]:
    repo_digests_raw, _, configured_ref = stdout.partition("|")
    repo_digests = json.loads(repo_digests_raw) if repo_digests_raw else []
    digests = [digest.split("@", 1)[1] for digest in repo_digests if "@" in digest]
    return {
        "repo_digests": repo_digests,
        "running_reference": configured_ref.strip(),
        "running_digest": digests[0] if digests else "",
    }


def inspect_runtime_image(context: dict[str, Any], runtime_host: str, container_name: str) -> dict[str, Any]:
    remote_command = (
        "docker inspect --format "
        "'{{json .RepoDigests}}|{{.Config.Image}}' "
        f"{container_name}"
    )
    result = run_command(build_guest_ssh_command(context, runtime_host, remote_command))
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"docker inspect failed for {container_name}")
    return parse_inspect_output(result.stdout)


def evaluate_image(image: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    try:
        actual = inspect_runtime_image(context, image["runtime_host"], image["container_name"])
    except Exception as exc:  # noqa: BLE001
        return {
            "source": "docker-image",
            "event": drift_event_topic("critical"),
            "severity": "critical",
            "service": image["service_id"],
            "host": image["runtime_host"],
            "resource": image["container_name"],
            "image_id": image["image_id"],
            "detail": str(exc),
            "shared_surfaces": [image["service_id"], image["runtime_host"], image["container_name"], image["image_id"]],
        }

    expected_digest = image["expected_digest"]
    running_digest = actual["running_digest"]
    if expected_digest and running_digest == expected_digest:
        return None
    expected_ref = normalize_image_reference(image["expected_reference"])
    running_ref = normalize_image_reference(actual["running_reference"])
    if not expected_digest and expected_ref and running_ref == expected_ref:
        return None
    return {
        "source": "docker-image",
        "event": drift_event_topic("warn"),
        "severity": "warn",
        "service": image["service_id"],
        "host": image["runtime_host"],
        "resource": image["container_name"],
        "image_id": image["image_id"],
        "detail": f"expected {image['expected_reference'] or expected_digest}, running {actual['running_reference'] or running_digest}",
        "expected_digest": expected_digest,
        "running_digest": running_digest,
        "expected_reference": image["expected_reference"],
        "running_reference": actual["running_reference"],
        "shared_surfaces": [image["service_id"], image["runtime_host"], image["container_name"], image["image_id"]],
    }


def collect_drift(context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    controller_context = context or load_controller_context()
    images = iter_runtime_images()
    with ThreadPoolExecutor(max_workers=min(4, len(images) or 1)) as executor:
        results = list(executor.map(lambda item: evaluate_image(item, controller_context), images))
    return [record for record in results if record is not None]


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="Detect runtime Docker image drift from the image catalog.")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print(json.dumps(collect_drift(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
