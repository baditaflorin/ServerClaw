#!/usr/bin/env python3
"""Nightly wrapper for the ADR 0111 integration suite."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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


def maybe_read_secret_path(repo_root: Path, secret_id: str) -> str | None:
    manifest_path = repo_root / "config" / "controller-local-secrets.json"
    if not manifest_path.exists():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    secret = payload.get("secrets", {}).get(secret_id)
    if secret is None or secret.get("kind") != "file":
        return None
    secret_path = Path(secret["path"]).expanduser()
    if not secret_path.exists():
        return None
    return secret_path.read_text(encoding="utf-8").strip()


def build_summary(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    return (
        f"ADR 0111 nightly integration tests [{payload['status']}]: "
        f"{summary['passed']} passed, {summary['failed']} failed, {summary['skipped']} skipped "
        f"in {payload.get('duration_seconds', 0):.3f}s "
        f"({payload['environment']} / {payload['mode']})"
    )


def execute_suite(repo_root: Path, environment: str, report_file: Path) -> dict[str, Any]:
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import integration_suite

    try:
        _, payload = integration_suite.run_suite(
            repo_root=repo_root,
            mode="nightly",
            environment=environment,
            report_file=report_file,
        )
        return payload
    except ModuleNotFoundError as exc:
        if exc.name != "pytest":
            raise

    command = [
        "uv",
        "run",
        "--with-requirements",
        str(repo_root / "requirements" / "integration-tests.txt"),
        "python",
        str(repo_root / "scripts" / "integration_suite.py"),
        "--mode",
        "nightly",
        "--environment",
        environment,
        "--report-file",
        str(report_file),
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if report_file.exists():
        return json.loads(report_file.read_text(encoding="utf-8"))
    raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "nightly integration suite failed")


def publish_notifications(repo_root: Path, payload: dict[str, Any]) -> None:
    mattermost_url = (
        os.environ.get("LV3_MATTERMOST_INTEGRATION_TEST_WEBHOOK_URL")
        or maybe_read_secret_path(repo_root, "mattermost_platform_findings_webhook_url")
    )
    if mattermost_url:
        post_json_webhook(mattermost_url, {"text": build_summary(payload)})

    if payload["status"] == "passed":
        return

    glitchtip_url = (
        os.environ.get("LV3_GLITCHTIP_INTEGRATION_EVENT_URL")
        or maybe_read_secret_path(repo_root, "glitchtip_platform_findings_event_url")
    )
    if glitchtip_url:
        post_json_webhook(
            glitchtip_url,
            {
                "message": "ADR 0111 nightly integration suite failed",
                "level": "error",
                "tags": {
                    "workflow": "nightly-integration-tests",
                    "environment": payload["environment"],
                    "mode": payload["mode"],
                },
                "extra": {
                    "summary": payload["summary"],
                    "failed_tests": [
                        test["nodeid"]
                        for test in payload["tests"]
                        if test.get("outcome") == "failed"
                    ],
                },
            },
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0111 nightly integration suite wrapper.")
    parser.add_argument(
        "--repo-path",
        default="/srv/proxmox_florin_server",
        help="Path to the repo checkout mounted on the worker.",
    )
    parser.add_argument(
        "--environment",
        default="production",
        choices=("production", "staging"),
        help="Environment selection forwarded to scripts/integration_suite.py.",
    )
    return parser


def main(repo_path: str = "/srv/proxmox_florin_server", environment: str = "production") -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    report_file = repo_root / ".local" / "integration-tests" / "nightly-last-run.json"
    payload = execute_suite(repo_root, environment, report_file)
    publish_notifications(repo_root, payload)
    return payload


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(json.dumps(main(repo_path=args.repo_path, environment=args.environment), indent=2, sort_keys=True))
