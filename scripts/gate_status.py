#!/usr/bin/env python3
"""Show the configured validation gate checks and the most recent gate outcomes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts import validation_lanes
except ModuleNotFoundError as exc:
    if exc.name != "yaml" or os.environ.get("LV3_GATE_STATUS_PYYAML_BOOTSTRAPPED") == "1":
        raise
    helper_path = Path(__file__).resolve().with_name("run_python_with_packages.sh")
    if not helper_path.is_file():
        raise
    os.environ["LV3_GATE_STATUS_PYYAML_BOOTSTRAPPED"] = "1"
    os.execv(
        str(helper_path),
        [str(helper_path), "pyyaml", "--", str(Path(__file__).resolve()), *sys.argv[1:]],
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "config" / "validation-gate.json"
DEFAULT_LANE_CATALOG = REPO_ROOT / "config" / "validation-lanes.yaml"
DEFAULT_LAST_RUN = REPO_ROOT / ".local" / "validation-gate" / "last-run.json"
DEFAULT_POST_MERGE_RUN = REPO_ROOT / ".local" / "validation-gate" / "post-merge-last-run.json"
DEFAULT_BYPASS_DIR = REPO_ROOT / "receipts" / "gate-bypasses"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show repository validation gate status.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--last-run", type=Path, default=DEFAULT_LAST_RUN)
    parser.add_argument("--post-merge-run", type=Path, default=DEFAULT_POST_MERGE_RUN)
    parser.add_argument("--bypass-dir", type=Path, default=DEFAULT_BYPASS_DIR)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_bypass_receipt(directory: Path) -> tuple[Path, dict[str, Any]] | None:
    if not directory.is_dir():
        return None
    receipts = sorted(path for path in directory.glob("*.json") if path.is_file())
    if not receipts:
        return None
    latest = receipts[-1]
    return latest, json.loads(latest.read_text(encoding="utf-8"))


def build_status_payload(
    *,
    manifest_path: Path,
    last_run_path: Path,
    post_merge_run_path: Path,
    bypass_dir: Path,
    lane_catalog_path: Path | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    last_run = load_optional_json(last_run_path)
    post_merge_run = load_optional_json(post_merge_run_path)
    bypass = latest_bypass_receipt(bypass_dir)
    resolved_lane_catalog_path = lane_catalog_path or manifest_path.parent / DEFAULT_LANE_CATALOG.name
    enabled_lanes: list[dict[str, Any]] = []
    if resolved_lane_catalog_path.is_file():
        catalog = validation_lanes.load_catalog(
            catalog_path=resolved_lane_catalog_path,
            manifest_checks=set(manifest),
        )
        enabled_lanes = [
            {
                "id": lane_id,
                "title": lane.title,
                "checks": list(lane.checks),
            }
            for lane_id, lane in catalog.lanes.items()
        ]

    payload = {
        "manifest_path": str(manifest_path),
        "lane_catalog_path": str(resolved_lane_catalog_path) if resolved_lane_catalog_path.is_file() else None,
        "enabled_lanes": enabled_lanes,
        "enabled_checks": [
            {
                "id": check_id,
                "severity": config.get("severity", "error"),
                "description": config.get("description", ""),
            }
            for check_id, config in sorted(manifest.items())
        ],
        "last_run": last_run,
        "post_merge_run": post_merge_run,
        "latest_bypass": None,
    }
    if bypass is not None:
        path, bypass_payload = bypass
        payload["latest_bypass"] = {
            "path": str(path),
            "payload": bypass_payload,
        }
    return payload


def print_run_summary(label: str, payload: dict[str, Any] | None) -> None:
    if payload is None:
        print(f"{label}: none recorded")
        return
    print(
        f"{label}: {payload.get('status', 'unknown')} at {payload.get('executed_at', 'unknown')} "
        f"via {payload.get('source', 'unknown')}"
    )
    lane_selection = payload.get("lane_selection")
    if isinstance(lane_selection, dict):
        selected_lanes = lane_selection.get("selected_lanes", [])
        if isinstance(selected_lanes, list) and selected_lanes:
            print(f"  selected lanes: {', '.join(str(item) for item in selected_lanes)}")


def print_status_text(payload: dict[str, Any]) -> None:
    print(f"Validation gate manifest: {payload['manifest_path']}")
    if payload.get("enabled_lanes"):
        print("Validation lanes:")
        for lane in payload["enabled_lanes"]:
            checks = ", ".join(lane.get("checks", []))
            print(f"  - {lane['id']}: {lane['title']} [{checks}]")
    print("Enabled checks:")
    for check in payload["enabled_checks"]:
        print(f"  - {check['id']} [{check['severity']}]: {check['description']}")

    print_run_summary("Last gate run", payload.get("last_run"))
    print_run_summary("Last post-merge gate run", payload.get("post_merge_run"))

    latest_bypass = payload.get("latest_bypass")
    if latest_bypass is None:
        print("Latest bypass receipt: none recorded")
    else:
        path = latest_bypass["path"]
        bypass_payload = latest_bypass["payload"]
        print(
            "Latest bypass receipt: "
            f"{path} ({bypass_payload.get('bypass', 'unknown')} at {bypass_payload.get('created_at', 'unknown')})"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    payload = build_status_payload(
        manifest_path=args.manifest,
        last_run_path=args.last_run,
        post_merge_run_path=args.post_merge_run,
        bypass_dir=args.bypass_dir,
    )
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_status_text(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
