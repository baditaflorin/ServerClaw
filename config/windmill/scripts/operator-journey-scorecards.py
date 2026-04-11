#!/usr/bin/env python3
"""Windmill wrapper for ADR 0316 scorecard rendering."""

from __future__ import annotations

import os

import json
import subprocess
from pathlib import Path


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    window_days: int = 30,
    write_latest: bool = True,
) -> dict[str, object]:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "journey_scorecards.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "journey scorecard script is missing from the worker checkout",
            "expected_script_path": str(script_path),
        }

    command = [
        "python3",
        str(script_path),
        "report",
        "--repo-root",
        str(repo_root),
        "--window-days",
        str(window_days),
    ]
    if write_latest:
        command.append("--write-latest")
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    payload: dict[str, object] = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if result.stdout.strip():
        try:
            payload["report"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass
    return payload


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
