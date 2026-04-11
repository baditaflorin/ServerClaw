#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0271 backup coverage ledger."""

from __future__ import annotations

import os

import argparse
import json
import subprocess
from pathlib import Path


def extract_report_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("REPORT_JSON="):
            return json.loads(line.removeprefix("REPORT_JSON="))
    return None


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    strict: bool = False,
    write_receipt: bool = True,
):
    repo_root = Path(repo_path)
    script_path = repo_root / "scripts" / "backup_coverage_ledger.py"
    if not script_path.exists():
        return {
            "status": "blocked",
            "reason": "backup coverage ledger surfaces are missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        "uv",
        "run",
        "--with",
        "pyyaml",
        "python",
        str(script_path),
        "--format",
        "json",
        "--print-report-json",
    ]
    if write_receipt:
        command.append("--write-receipt")
    if strict:
        command.append("--strict")

    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    report = extract_report_json(result.stdout)
    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if report is not None:
        payload["report"] = report
        payload["summary"] = report.get("summary", {})
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0271 backup coverage ledger from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--no-write-receipt",
        action="store_true",
        help="Do not persist the generated report under receipts/backup-coverage.",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                strict=args.strict,
                write_receipt=not args.no_write_receipt,
            ),
            indent=2,
            sort_keys=True,
        )
    )
