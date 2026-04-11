#!/usr/bin/env python3
"""Windmill wrapper for ADR 0171 fault injection."""

from __future__ import annotations

import os

import argparse
import json
import subprocess
from pathlib import Path


def _parse_json(stdout: str) -> dict:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("fault injection wrapper expected a JSON object")
    return payload


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    scenario_names: str = "",
    schedule_guard: str = "",
    dry_run: bool = False,
) -> dict:
    repo_root = Path(repo_path)
    report_script = repo_root / "scripts" / "fault_injection.py"
    if not report_script.exists():
        return {
            "status": "blocked",
            "reason": "fault injection script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(report_script),
        "--repo-path",
        str(repo_root),
    ]
    if scenario_names.strip():
        command.extend(["--scenario-names", scenario_names])
    if schedule_guard.strip():
        command.extend(["--schedule-guard", schedule_guard])
    if dry_run:
        command.append("--dry-run")

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return {
            "status": "error",
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    payload = _parse_json(result.stdout)
    _publish_to_outline(payload, repo_root)
    return payload


def _publish_to_outline(payload: dict, repo_root: Path) -> None:
    import os, sys as _sys

    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = repo_root / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = repo_root / "scripts" / "outline_tool.py"
    if not outline_tool.exists():
        return
    from datetime import datetime, timezone

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    status = payload.get("status", "unknown")
    scenarios = payload.get("scenarios", []) if isinstance(payload.get("scenarios"), list) else []
    lines = [
        f"# Fault Injection Run — {date}",
        "",
        f"**Status:** {status}",
        "",
    ]
    if scenarios:
        lines += ["## Scenarios", "", "| Scenario | Result | Duration |", "|---|---|---|"]
        for sc in scenarios:
            name = str(sc.get("name", "")).replace("|", "\\|")
            res = str(sc.get("result", "")).replace("|", "\\|")
            dur = str(sc.get("duration_seconds", "")).replace("|", "\\|")
            lines.append(f"| {name} | {res} | {dur} |")
        lines.append("")
    title = f"fault-injection-{date}"[:100]
    markdown = "\n".join(lines)
    try:
        subprocess.run(
            [
                _sys.executable,
                str(outline_tool),
                "document.publish",
                "--collection",
                "Automation Runs",
                "--title",
                title,
            ],
            input=markdown,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ADR 0171 fault injection from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--scenario-names", default="")
    parser.add_argument("--schedule-guard", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                scenario_names=args.scenario_names,
                schedule_guard=args.schedule_guard,
                dry_run=args.dry_run,
            ),
            indent=2,
            sort_keys=True,
        )
    )
