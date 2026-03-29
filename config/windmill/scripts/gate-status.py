#!/usr/bin/env python3
"""Windmill wrapper for the repository validation gate status."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Any


def gate_status_command(repo_root: Path) -> list[str]:
    return [
        "python3",
        str(repo_root / "scripts" / "gate_status.py"),
        "--manifest",
        str(repo_root / "config" / "validation-gate.json"),
        "--last-run",
        str(repo_root / ".local" / "validation-gate" / "last-run.json"),
        "--post-merge-run",
        str(repo_root / ".local" / "validation-gate" / "post-merge-last-run.json"),
        "--bypass-dir",
        str(repo_root / "receipts" / "gate-bypasses"),
        "--format",
        "json",
    ]


def decode_gate_status_payload(stdout: str) -> dict[str, Any]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError("gate status payload must be a JSON object")
    return payload


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict:
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "gate_status.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "gate status script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = gate_status_command(repo_root)
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=dict(os.environ),
    )
    if completed.returncode != 0:
        return {
            "status": "error",
            "reason": completed.stderr.strip() or "gate status command failed",
            "command": completed.args,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }

    payload = decode_gate_status_payload(completed.stdout)
    return {
        "status": "ok",
        "gate_status": payload,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show repository validation gate status from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
