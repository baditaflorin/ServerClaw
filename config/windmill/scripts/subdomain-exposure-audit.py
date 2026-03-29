#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict[str, Any]:
    repo_root = Path(repo_path)
    audit_script = repo_root / "scripts" / "subdomain_exposure_audit.py"

    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }
    if not audit_script.exists():
        return {
            "status": "blocked",
            "reason": "subdomain exposure audit script is missing from the worker checkout",
            "expected_script_path": str(audit_script),
        }

    command = [
        "uvx",
        "--from",
        "pyyaml",
        "python",
        str(audit_script),
        "--check-registry",
        "--include-live-dns",
        "--include-http-auth",
        "--include-private-routes",
        "--include-tls",
        "--include-hetzner-zone",
        "--write-receipt",
        "--print-report-json",
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    payload: dict[str, Any]
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "ok" if completed.returncode == 0 else "error",
            "stdout": completed.stdout.strip(),
        }

    payload["returncode"] = completed.returncode
    payload["command"] = " ".join(shlex.quote(part) for part in command)
    if completed.stderr.strip():
        payload["stderr"] = completed.stderr.strip()
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the subdomain exposure audit from a worker checkout.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
