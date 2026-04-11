#!/usr/bin/env python3
"""Weekly calibration wrapper for ADR 0114 triage rules."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any


def post_json_webhook(url: str, payload: dict[str, Any]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f"Webhook POST failed with HTTP {response.status}")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_summary(payload: dict[str, Any]) -> str:
    if payload["status"] != "ok":
        return f"ADR 0114 calibration [{payload['status']}]: {payload.get('reason', 'unknown')}"
    reviewed = payload["summary"]["reports_reviewed"]
    cases = payload["summary"]["cases_reviewed"]
    if cases == 0:
        return f"ADR 0114 calibration [insufficient_data]: reviewed {reviewed} reports and found no resolved cases yet."
    return (
        "ADR 0114 calibration [ok]: "
        f"reviewed {reviewed} reports, {cases} resolved cases, "
        f"{payload['summary']['rules_with_data']} rules with calibration data."
    )


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    cases_path: str | None = None,
    mattermost_webhook_url: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "triage_calibration.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    triage_calibration = load_module("triage_calibration_worker", script_path)

    payload = triage_calibration.calibrate(cases_path=Path(cases_path) if cases_path else None)
    webhook = mattermost_webhook_url or os.environ.get("LV3_TRIAGE_CALIBRATION_WEBHOOK_URL", "").strip()
    if webhook:
        post_json_webhook(webhook, {"text": build_summary(payload)})
        payload["mattermost_posted"] = True
    else:
        payload["mattermost_posted"] = False
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0114 triage calibration wrapper.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--cases-path", help="Optional resolved-case JSON or JSONL file.")
    parser.add_argument("--mattermost-webhook-url", help="Optional Mattermost webhook override.")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                cases_path=args.cases_path,
                mattermost_webhook_url=args.mattermost_webhook_url,
            ),
            indent=2,
            sort_keys=True,
        )
    )
