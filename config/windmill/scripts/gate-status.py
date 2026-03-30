#!/usr/bin/env python3
"""Windmill wrapper for the repository validation gate status."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict[str, Any]:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "gate_status.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "gate status script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "python3",
        str(script_path),
        "--format",
        "json",
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload: dict[str, Any] = {
        "status": "ok" if completed.returncode == 0 else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }

    if completed.returncode != 0:
        payload["reason"] = "gate status command failed"
        return payload

    if not stdout:
        payload["status"] = "error"
        payload["reason"] = "gate status command returned no JSON payload"
        return payload

    try:
        gate_status = json.loads(stdout)
    except json.JSONDecodeError:
        payload["status"] = "error"
        payload["reason"] = "gate status command did not return valid JSON"
        return payload

    if not isinstance(gate_status, dict):
        payload["status"] = "error"
        payload["reason"] = "gate status command did not return a JSON object"
        payload["gate_status"] = gate_status
        return payload

    payload["gate_status"] = gate_status
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show repository validation gate status from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
