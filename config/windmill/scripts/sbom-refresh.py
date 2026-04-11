#!/usr/bin/env python3

import os
import argparse
import json
import shlex
import subprocess
from pathlib import Path


def main(repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server")):
    repo_root = Path(repo_path)
    refresh_script = repo_root / "scripts" / "sbom_refresh.py"
    if not refresh_script.exists():
        return {
            "status": "blocked",
            "reason": "SBOM refresh script is missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }
    required_paths = [
        repo_root / "config" / "image-catalog.json",
        repo_root / "config" / "sbom-scanner.json",
    ]
    missing_paths = [str(path) for path in required_paths if not path.exists()]
    if missing_paths:
        return {
            "status": "blocked",
            "reason": "SBOM refresh worker checkout is missing required repo paths",
            "missing_paths": missing_paths,
            "expected_repo_path": str(repo_root),
        }
    for output_dir in (repo_root / "receipts" / "sbom", repo_root / "receipts" / "cve"):
        output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "uv",
        "run",
        "--with",
        "nats-py",
        "--with",
        "pyyaml",
        "python",
        str(refresh_script),
        "--publish-nats",
        "--send-ntfy-alerts",
        "--print-report-json",
    ]
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    has_report_json = "REPORT_JSON=" in stdout
    return {
        "status": "ok" if result.returncode == 0 and has_report_json else "error",
        "command": " ".join(shlex.quote(part) for part in command),
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the ADR 0298 SBOM refresh workflow from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2))
