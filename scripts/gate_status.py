#!/usr/bin/env python3
"""Show the configured validation gate checks and the most recent gate outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path("config/validation-gate.json")
DEFAULT_LAST_RUN = Path(".local/validation-gate/last-run.json")
DEFAULT_POST_MERGE_RUN = Path(".local/validation-gate/post-merge-last-run.json")
DEFAULT_BYPASS_DIR = Path("receipts/gate-bypasses")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show repository validation gate status.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--last-run", type=Path, default=DEFAULT_LAST_RUN)
    parser.add_argument("--post-merge-run", type=Path, default=DEFAULT_POST_MERGE_RUN)
    parser.add_argument("--bypass-dir", type=Path, default=DEFAULT_BYPASS_DIR)
    return parser.parse_args()


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


def print_run_summary(label: str, payload: dict[str, Any] | None) -> None:
    if payload is None:
        print(f"{label}: none recorded")
        return
    print(
        f"{label}: {payload.get('status', 'unknown')} at {payload.get('executed_at', 'unknown')} "
        f"via {payload.get('source', 'unknown')}"
    )


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    last_run = load_optional_json(args.last_run)
    post_merge_run = load_optional_json(args.post_merge_run)
    bypass = latest_bypass_receipt(args.bypass_dir)

    print(f"Validation gate manifest: {args.manifest}")
    print("Enabled checks:")
    for check_id in sorted(manifest):
        config = manifest[check_id]
        print(f"  - {check_id} [{config.get('severity', 'error')}]: {config.get('description', '')}")

    print_run_summary("Last gate run", last_run)
    print_run_summary("Last post-merge gate run", post_merge_run)

    if bypass is None:
        print("Latest bypass receipt: none recorded")
    else:
        path, payload = bypass
        print(
            "Latest bypass receipt: "
            f"{path} ({payload.get('bypass', 'unknown')} at {payload.get('created_at', 'unknown')})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
