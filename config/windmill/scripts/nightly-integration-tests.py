#!/usr/bin/env python3
"""Nightly wrapper for the ADR 0111 integration suite."""

from __future__ import annotations

import argparse
import importlib.util
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


def _load_environment_catalog(repo_root: Path):
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import environment_catalog

    return environment_catalog


def emit_glitchtip_notification(repo_root: Path, target_url: str, payload: dict[str, Any]) -> None:
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from glitchtip_event import emit_glitchtip_event

    emit_glitchtip_event(target_url, payload)


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

    overrides = load_integration_env_overrides(repo_root)
    for name, value in overrides.items():
        os.environ.setdefault(name, value)

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
        env={**os.environ, **overrides},
    )
    if report_file.exists():
        return json.loads(report_file.read_text(encoding="utf-8"))
    raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "nightly integration suite failed")


def load_integration_env_overrides(repo_root: Path) -> dict[str, str]:
    helper_path = repo_root / "config" / "windmill" / "scripts" / "windmill_integration_env.py"
    if not helper_path.exists():
        return {}
    spec = importlib.util.spec_from_file_location("lv3_windmill_integration_env", helper_path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolver = getattr(module, "integration_env_overrides", None)
    if not callable(resolver):
        return {}
    overrides = resolver(repo_root)
    return overrides if isinstance(overrides, dict) else {}


def publish_to_outline(repo_root: Path, payload: dict[str, Any]) -> None:
    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        return
    outline_tool = repo_root / "scripts" / "outline_tool.py"
    if not outline_tool.exists():
        return
    date = payload.get("executed_at", "")[:10] or __import__("datetime").date.today().isoformat()
    title = f"nightly-tests-{date}"
    status = payload.get("status", "unknown")
    summary = payload.get("summary", {})
    tests = payload.get("tests", [])
    failed_tests = [t.get("nodeid", "") for t in tests if t.get("outcome") == "failed"]
    icon = "✅" if status == "passed" else "❌"
    md_lines = [
        f"# Nightly Integration Tests: {date}\n\n",
        f"| Field | Value |\n|---|---|\n",
        f"| Status | {icon} {status} |\n",
        f"| Environment | {payload.get('environment', '?')} |\n",
        f"| Mode | {payload.get('mode', 'nightly')} |\n",
        f"| Duration | {payload.get('duration_seconds', 0):.1f}s |\n\n",
        f"## Summary\n\n",
        f"| Metric | Count |\n|---|---|\n",
        f"| Passed | {summary.get('passed', 0)} |\n",
        f"| Failed | {summary.get('failed', 0)} |\n",
        f"| Skipped | {summary.get('skipped', 0)} |\n\n",
    ]
    if failed_tests:
        md_lines.append("## Failed Tests\n\n")
        for t in failed_tests:
            md_lines.append(f"- `{t}`\n")
        md_lines.append("\n")
    md_content = "".join(md_lines)
    try:
        subprocess.run(
            [
                sys.executable,
                str(outline_tool),
                "document.publish",
                "--collection",
                "Automation Runs",
                "--title",
                title,
                "--stdin",
            ],
            input=md_content,
            text=True,
            capture_output=True,
            check=False,
            cwd=repo_root,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


def publish_notifications(repo_root: Path, payload: dict[str, Any]) -> None:
    mattermost_url = os.environ.get("LV3_MATTERMOST_INTEGRATION_TEST_WEBHOOK_URL") or maybe_read_secret_path(
        repo_root, "mattermost_platform_findings_webhook_url"
    )
    if mattermost_url:
        post_json_webhook(mattermost_url, {"text": build_summary(payload)})

    if payload["status"] == "passed":
        return

    glitchtip_url = os.environ.get("LV3_GLITCHTIP_INTEGRATION_EVENT_URL") or maybe_read_secret_path(
        repo_root, "glitchtip_platform_findings_event_url"
    )
    if glitchtip_url:
        emit_glitchtip_notification(
            repo_root,
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
                    "failed_tests": [test["nodeid"] for test in payload["tests"] if test.get("outcome") == "failed"],
                },
            },
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0111 nightly integration suite wrapper.")
    parser.add_argument(
        "--repo-path",
        default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
        help="Path to the repo checkout mounted on the worker.",
    )
    parser.add_argument(
        "--environment",
        default="",
        help="Environment selection forwarded to scripts/integration_suite.py.",
    )
    return parser


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"), environment: str = ""
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    environment_catalog = _load_environment_catalog(repo_root)
    effective_environment = environment.strip() or environment_catalog.primary_environment()
    allowed_environments = set(environment_catalog.environment_choices())
    if effective_environment not in allowed_environments:
        return {
            "status": "blocked",
            "reason": "unsupported environment",
            "environment": effective_environment,
            "allowed_environments": sorted(allowed_environments),
        }

    report_file = repo_root / ".local" / "integration-tests" / "nightly-last-run.json"
    payload = execute_suite(repo_root, effective_environment, report_file)
    publish_notifications(repo_root, payload)
    publish_to_outline(repo_root, payload)
    return payload


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(json.dumps(main(repo_path=args.repo_path, environment=args.environment), indent=2, sort_keys=True))
