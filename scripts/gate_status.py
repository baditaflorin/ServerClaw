#!/usr/bin/env python3
"""Show the configured validation gate checks and the most recent gate outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path("config/validation-gate.json")
DEFAULT_LAST_RUN = Path(".local/validation-gate/last-run.json")
DEFAULT_REMOTE_VALIDATE_RUN = Path(".local/validation-gate/remote-validate-last-run.json")
DEFAULT_POST_MERGE_RUN = Path(".local/validation-gate/post-merge-last-run.json")
DEFAULT_BYPASS_DIR = Path("receipts/gate-bypasses")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show repository validation gate status.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--last-run", type=Path, default=DEFAULT_LAST_RUN)
    parser.add_argument("--remote-validate-run", type=Path, default=DEFAULT_REMOTE_VALIDATE_RUN)
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
    remote_validate_run_path: Path,
    post_merge_run_path: Path,
    bypass_dir: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    last_run = load_optional_json(last_run_path)
    remote_validate_run = load_optional_json(remote_validate_run_path)
    post_merge_run = load_optional_json(post_merge_run_path)
    bypass = latest_bypass_receipt(bypass_dir)

    payload = {
        "manifest_path": str(manifest_path),
        "enabled_checks": [
            {
                "id": check_id,
                "severity": config.get("severity", "error"),
                "description": config.get("description", ""),
            }
            for check_id, config in sorted(manifest.items())
        ],
        "last_run": last_run,
        "remote_validate_run": remote_validate_run,
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
    runner = payload.get("runner") or {}
    runner_id = runner.get("id")
    runner_suffix = f" on runner {runner_id}" if runner_id else ""
    print(
        f"{label}: {payload.get('status', 'unknown')} at {payload.get('executed_at', 'unknown')} "
        f"via {payload.get('source', 'unknown')}{runner_suffix}"
    )


def print_status_text(payload: dict[str, Any]) -> None:
    print(f"Validation gate manifest: {payload['manifest_path']}")
    print("Enabled checks:")
    for check in payload["enabled_checks"]:
        print(f"  - {check['id']} [{check['severity']}]: {check['description']}")

    print_run_summary("Last gate run", payload.get("last_run"))
    print_run_summary("Last remote validate run", payload.get("remote_validate_run"))
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
        remote_validate_run_path=args.remote_validate_run,
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
