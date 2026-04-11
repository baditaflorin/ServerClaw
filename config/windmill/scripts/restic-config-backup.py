#!/usr/bin/env python3
"""Windmill wrapper for ADR 0302 restic config backups."""

from __future__ import annotations

import os

import argparse
import json
import subprocess
from pathlib import Path

DEFAULT_FALLBACK_SCRIPT_PATH = Path("/opt/api-gateway/service/scripts/restic_config_backup.py")
DEFAULT_FALLBACK_CATALOG_PATH = Path("/etc/lv3/restic-config-backup/restic-file-backup-catalog.json")


def extract_report_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("REPORT_JSON="):
            return json.loads(line.removeprefix("REPORT_JSON="))
    return None


def resolve_script_path(
    repo_root: Path,
    *,
    fallback_script_path: Path | None = None,
) -> Path | None:
    fallback = fallback_script_path or DEFAULT_FALLBACK_SCRIPT_PATH
    primary_script_path = repo_root / "scripts" / "restic_config_backup.py"
    if primary_script_path.exists():
        return primary_script_path
    if fallback.exists():
        return fallback
    return None


def resolve_catalog_path(
    repo_root: Path,
    *,
    fallback_catalog_path: Path | None = None,
) -> Path | None:
    fallback = fallback_catalog_path or DEFAULT_FALLBACK_CATALOG_PATH
    primary_catalog_path = repo_root / "config" / "restic-file-backup-catalog.json"
    if primary_catalog_path.exists():
        return primary_catalog_path
    if fallback.exists():
        return fallback
    return None


def build_command(
    repo_root: Path,
    *,
    mode: str,
    triggered_by: str,
    live_apply_trigger: bool,
    script_path: Path | None = None,
    catalog_path: Path | None = None,
) -> list[str]:
    target_script_path = script_path or (repo_root / "scripts" / "restic_config_backup.py")
    target_catalog_path = catalog_path or (repo_root / "config" / "restic-file-backup-catalog.json")
    command = [
        "python3",
        str(target_script_path),
        "--repo-root",
        str(repo_root),
        "--catalog",
        str(target_catalog_path),
        "--backup-receipts-dir",
        str(repo_root / "receipts" / "restic-backups"),
        "--latest-snapshot-receipt",
        str(repo_root / "receipts" / "restic-snapshots-latest.json"),
        "--restore-verification-dir",
        str(repo_root / "receipts" / "restic-restore-verifications"),
        "--mode",
        mode,
        "--triggered-by",
        triggered_by,
        "--print-report-json",
    ]
    if live_apply_trigger:
        command.append("--live-apply-trigger")
    return command


def main(
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    mode: str = "backup",
    triggered_by: str = "windmill-schedule",
    live_apply_trigger: bool = False,
) -> dict[str, object]:
    repo_root = Path(repo_path)
    script_path = resolve_script_path(repo_root)
    catalog_path = resolve_catalog_path(repo_root)
    if script_path is None or catalog_path is None:
        return {
            "status": "blocked",
            "reason": "restic backup surfaces are missing from both the worker checkout and the deployed runtime fallbacks",
            "expected_repo_path": str(repo_root),
            "fallback_script_path": str(DEFAULT_FALLBACK_SCRIPT_PATH),
            "fallback_catalog_path": str(DEFAULT_FALLBACK_CATALOG_PATH),
        }

    command = build_command(
        repo_root,
        mode=mode,
        triggered_by=triggered_by,
        live_apply_trigger=live_apply_trigger,
        script_path=script_path,
        catalog_path=catalog_path,
    )
    result = subprocess.run(command, cwd=repo_root, text=True, capture_output=True, check=False)
    report = extract_report_json(result.stdout)
    payload: dict[str, object] = {
        "status": "ok" if result.returncode == 0 else "error",
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
    if report is not None:
        payload["report"] = report
        if isinstance(report, dict):
            payload["summary"] = report.get("summary") or ((report.get("report") or {}).get("summary"))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0302 restic workflow from Windmill.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--mode", choices=["backup", "restore-verify"], default="backup")
    parser.add_argument("--triggered-by", default="windmill-schedule")
    parser.add_argument("--live-apply-trigger", action="store_true")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                mode=args.mode,
                triggered_by=args.triggered_by,
                live_apply_trigger=args.live_apply_trigger,
            ),
            indent=2,
            sort_keys=True,
        )
    )
