#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from validation_toolkit import require_list, require_str

from platform.events import load_event_taxonomy, load_topic_index
from controller_automation_toolkit import REPO_ROOT, emit_cli_error, load_json, load_yaml, repo_path


CONTROL_PLANE_LANES_PATH = repo_path("config", "control-plane-lanes.json")
NTFY_SERVER_PATH = repo_path("config", "ntfy", "server.yml")
NTFY_TOPIC_REGISTRY_PATH = repo_path("config", "ntfy", "topics.yaml")
SOURCE_ROOTS = (
    repo_path("platform"),
    repo_path("scripts"),
    repo_path("config", "windmill", "scripts"),
)
TOPIC_PATTERN = re.compile(r"""["'](platform\.[a-z0-9-]+(?:\.[a-z0-9_.-]+)+)["']""")
NTFY_TOPIC_PATTERN = re.compile(r"""\b(platform\.[a-z0-9-]+(?:\.[a-z0-9_.-]+)+)\b""")


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def iter_python_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "*.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    files = []
    for line in result.stdout.splitlines():
        path = REPO_ROOT / line.strip()
        if any(root in path.parents or path == root for root in SOURCE_ROOTS):
            files.append(path)
    return files


def extract_code_topics() -> dict[str, set[str]]:
    findings: dict[str, set[str]] = {}
    for path in iter_python_files():
        text = path.read_text(encoding="utf-8")
        matches: set[str] = set()
        for line in text.splitlines():
            # Private ntfy topic names share the platform.* namespace but are not
            # canonical NATS subjects and should be tracked by ntfy-specific
            # configuration, not the event-bus validator.
            if "ntfy" in line.lower():
                continue
            matches.update(TOPIC_PATTERN.findall(line))
        if matches:
            findings[str(path.relative_to(REPO_ROOT))] = matches
    return findings


def extract_ntfy_topics() -> set[str]:
    topics = set(NTFY_TOPIC_PATTERN.findall(NTFY_SERVER_PATH.read_text(encoding="utf-8")))
    payload = load_yaml(NTFY_TOPIC_REGISTRY_PATH)
    if not isinstance(payload, dict):
        raise ValueError(f"{NTFY_TOPIC_REGISTRY_PATH} must be a mapping")
    configured_topics = payload.get("topics", {})
    if not isinstance(configured_topics, dict):
        raise ValueError(f"{NTFY_TOPIC_REGISTRY_PATH}.topics must be a mapping")
    topics.update(topic for topic in configured_topics if isinstance(topic, str) and topic.startswith("platform."))
    return topics


def iter_event_lane_endpoints() -> list[tuple[str, str]]:
    catalog = require_mapping(load_json(CONTROL_PLANE_LANES_PATH), str(CONTROL_PLANE_LANES_PATH))
    lanes = require_mapping(catalog.get("lanes"), "control-plane-lanes.lanes")
    event_lane = require_mapping(lanes.get("event"), "control-plane-lanes.lanes.event")
    surfaces = require_list(event_lane.get("current_surfaces"), "control-plane-lanes.lanes.event.current_surfaces")
    endpoints = []
    for index, surface_value in enumerate(surfaces):
        surface = require_mapping(surface_value, f"control-plane-lanes.lanes.event.current_surfaces[{index}]")
        if require_str(surface.get("kind"), f"event surface {index}.kind") != "event_subject":
            continue
        endpoints.append(
            (
                require_str(surface.get("id"), f"event surface {index}.id"),
                require_str(surface.get("endpoint"), f"event surface {index}.endpoint"),
            )
        )
    return endpoints


def matches_endpoint(endpoint: str, topic: str) -> bool:
    pattern = endpoint.replace(">", "*").replace("*", "*")
    return fnmatch.fnmatchcase(topic, pattern)


def validate_topic_usage() -> dict[str, Any]:
    taxonomy = load_event_taxonomy()
    topic_index = load_topic_index()
    active_topics = sorted(name for name, spec in topic_index.items() if spec["status"] == "active")
    code_topics = extract_code_topics()
    ntfy_topics = extract_ntfy_topics()

    unknown_topics: list[str] = []
    for path, topics in code_topics.items():
        for topic in sorted(topics):
            if topic not in topic_index and topic not in ntfy_topics:
                unknown_topics.append(f"{path}: {topic}")

    endpoint_matches: dict[str, list[str]] = {}
    uncovered_topics = set(active_topics)
    for surface_id, endpoint in iter_event_lane_endpoints():
        matched_topics = [topic for topic in active_topics if matches_endpoint(endpoint, topic)]
        endpoint_matches[surface_id] = matched_topics
        uncovered_topics -= set(matched_topics)

    return {
        "taxonomy_schema_version": taxonomy["schema_version"],
        "active_topics": active_topics,
        "code_topics": {path: sorted(values) for path, values in sorted(code_topics.items())},
        "ntfy_topics": sorted(ntfy_topics),
        "endpoint_matches": endpoint_matches,
        "unknown_topics": unknown_topics,
        "uncovered_topics": sorted(uncovered_topics),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical NATS topics and event-lane routing.")
    parser.add_argument("--validate", action="store_true", help="Validate the taxonomy, code topics, and lane routing.")
    parser.add_argument("--json", action="store_true", help="Emit the validation result as JSON.")
    args = parser.parse_args()

    try:
        result = validate_topic_usage()
        if result["unknown_topics"]:
            raise ValueError("unknown NATS topics detected: " + ", ".join(result["unknown_topics"]))
        if result["uncovered_topics"]:
            raise ValueError(
                "active taxonomy topics are not routed by config/control-plane-lanes.json: "
                + ", ".join(result["uncovered_topics"])
            )
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError, subprocess.CalledProcessError) as exc:
        return emit_cli_error("NATS topic validation", exc)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.validate:
        print("NATS topic taxonomy and routing OK")
        return 0
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
