#!/usr/bin/env python3
"""Windmill wrapper for the repository validation gate status."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def build_gate_status_command(repo_root: Path) -> list[str]:
    script_path = repo_root / "scripts" / "gate_status.py"
    helper_path = repo_root / "scripts" / "run_python_with_packages.sh"
    if helper_path.is_file():
        return [str(helper_path), "pyyaml", "--", str(script_path), "--format", "json"]
    return [sys.executable, str(script_path), "--format", "json"]


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict[str, Any]:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "gate_status.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "gate status script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = build_gate_status_command(repo_root)
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=dict(os.environ),
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload: dict[str, Any] = {
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
    if completed.returncode != 0:
        payload.update(
            {
                "status": "error",
                "reason": "gate status command failed",
            }
        )
        return payload
    if not stdout:
        payload.update(
            {
                "status": "error",
                "reason": "gate status command returned empty stdout",
            }
        )
        return payload
    try:
        gate_status = json.loads(stdout)
    except json.JSONDecodeError as exc:
        payload.update(
            {
                "status": "error",
                "reason": "gate status command returned non-JSON stdout",
                "parse_error": str(exc),
            }
        )
        return payload
    if not isinstance(gate_status, dict):
        payload.update(
            {
                "status": "error",
                "reason": "gate status command did not return a JSON object",
                "gate_status": gate_status,
            }
        )
        return payload
    payload.update(
        {
            "status": "ok",
            "gate_status": gate_status,
        }
    )
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show repository validation gate status from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
