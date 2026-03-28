#!/usr/bin/env python3
"""Windmill wrapper for the repo-managed ADR 0251 smoke suites."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path


def main(
    service: str = "windmill",
    environment: str = "production",
    repo_path: str = "/srv/proxmox_florin_server",
    report_file: str = "",
    suite_ids: str = "",
):
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "stage_smoke_suites.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "stage smoke suite runner is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
            "service": service,
            "environment": environment,
        }

    command = [
        "python3",
        str(script_path),
        "--service",
        service,
        "--environment",
        environment,
    ]
    if report_file.strip():
        command.extend(["--report-file", report_file.strip()])
    for suite_id in [item.strip() for item in suite_ids.split(",") if item.strip()]:
        command.extend(["--suite-id", suite_id])

    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = {
        "status": "ok" if completed.returncode == 0 else "error",
        "service": service,
        "environment": environment,
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.stdout.strip():
        try:
            payload["result"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            pass
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run declared stage smoke suites from Windmill.")
    parser.add_argument("--service", default="windmill")
    parser.add_argument("--environment", default="production")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--report-file", default="")
    parser.add_argument("--suite-ids", default="")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                service=args.service,
                environment=args.environment,
                repo_path=args.repo_path,
                report_file=args.report_file,
                suite_ids=args.suite_ids,
            ),
            indent=2,
            sort_keys=True,
        )
    )
