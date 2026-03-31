#!/usr/bin/env python3
"""Run the ADR 0302 restic workflow on docker-runtime-lv3 through the managed SSH path."""

from __future__ import annotations

import argparse
import json
import shlex

from controller_automation_toolkit import emit_cli_error
from drift_lib import build_guest_ssh_command, load_controller_context, run_command


DEFAULT_REMOTE_REPO_ROOT = "/srv/proxmox_florin_server"
DEFAULT_REMOTE_CATALOG_PATH = f"{DEFAULT_REMOTE_REPO_ROOT}/config/restic-file-backup-catalog.json"
DEFAULT_REMOTE_BACKUP_RECEIPTS_DIR = f"{DEFAULT_REMOTE_REPO_ROOT}/receipts/restic-backups"
DEFAULT_REMOTE_LATEST_SNAPSHOT_RECEIPT = f"{DEFAULT_REMOTE_REPO_ROOT}/receipts/restic-snapshots-latest.json"
DEFAULT_REMOTE_RESTORE_VERIFY_DIR = f"{DEFAULT_REMOTE_REPO_ROOT}/receipts/restic-restore-verifications"
DEFAULT_REMOTE_RUNTIME_STATE_DIR = "/var/lib/lv3/restic-config-backup"
DEFAULT_REMOTE_CACHE_DIR = f"{DEFAULT_REMOTE_RUNTIME_STATE_DIR}/cache"
DEFAULT_RUNTIME_CREDENTIAL_FILE = "/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json"
DEFAULT_FALLBACK_REMOTE_SCRIPT_PATH = "/opt/api-gateway/service/scripts/restic_config_backup.py"
DEFAULT_FALLBACK_REMOTE_CATALOG_PATH = "/etc/lv3/restic-config-backup/restic-file-backup-catalog.json"


def extract_report_json(stdout: str) -> dict | None:
    for line in reversed(stdout.splitlines()):
        if line.startswith("REPORT_JSON="):
            return json.loads(line.removeprefix("REPORT_JSON="))
    return None


def build_remote_command(
    *,
    mode: str,
    triggered_by: str,
    repo_root: str,
    credential_file: str,
    live_apply_trigger: bool,
    fallback_script_path: str = DEFAULT_FALLBACK_REMOTE_SCRIPT_PATH,
    fallback_catalog_path: str = DEFAULT_FALLBACK_REMOTE_CATALOG_PATH,
) -> str:
    primary_script_path = f"{repo_root}/scripts/restic_config_backup.py"
    primary_catalog_path = f"{repo_root}/config/restic-file-backup-catalog.json"
    command = [
        "--backup-receipts-dir",
        f"{repo_root}/receipts/restic-backups",
        "--latest-snapshot-receipt",
        f"{repo_root}/receipts/restic-snapshots-latest.json",
        "--restore-verification-dir",
        f"{repo_root}/receipts/restic-restore-verifications",
        "--runtime-state-dir",
        DEFAULT_REMOTE_RUNTIME_STATE_DIR,
        "--cache-dir",
        DEFAULT_REMOTE_CACHE_DIR,
        "--credential-file",
        credential_file,
        "--mode",
        mode,
        "--triggered-by",
        triggered_by,
        "--print-report-json",
    ]
    if live_apply_trigger:
        command.append("--live-apply-trigger")
    rendered_args = " ".join(shlex.quote(item) for item in command)
    shell_script = "\n".join(
        [
            "set -euo pipefail",
            f"script_path={shlex.quote(primary_script_path)}",
            f"fallback_script_path={shlex.quote(fallback_script_path)}",
            f"catalog_path={shlex.quote(primary_catalog_path)}",
            f"fallback_catalog_path={shlex.quote(fallback_catalog_path)}",
            'if [ ! -f "$script_path" ] && [ -f "$fallback_script_path" ]; then',
            '  script_path="$fallback_script_path"',
            "fi",
            'if [ ! -f "$script_path" ]; then',
            '  echo "restic_config_backup.py is missing from both $script_path and $fallback_script_path" >&2',
            "  exit 2",
            "fi",
            'if [ ! -f "$catalog_path" ] && [ -f "$fallback_catalog_path" ]; then',
            '  catalog_path="$fallback_catalog_path"',
            "fi",
            'if [ ! -f "$catalog_path" ]; then',
            '  echo "restic-file-backup-catalog.json is missing from both $catalog_path and $fallback_catalog_path" >&2',
            "  exit 2",
            "fi",
            (
                f'exec python3 "$script_path" --repo-root {shlex.quote(repo_root)} '
                f'--catalog "$catalog_path" {rendered_args}'
            ),
        ]
    )
    return " ".join(
        shlex.quote(item)
        for item in [
            "sudo",
            "/bin/bash",
            "-lc",
            shell_script,
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trigger ADR 0302 live restic workflows on docker-runtime-lv3.")
    parser.add_argument("--env", default="production")
    parser.add_argument("--mode", choices=["backup", "restore-verify"], default="backup")
    parser.add_argument("--repo-root", default=DEFAULT_REMOTE_REPO_ROOT)
    parser.add_argument("--credential-file", default=DEFAULT_RUNTIME_CREDENTIAL_FILE)
    parser.add_argument("--triggered-by", default="manual")
    parser.add_argument("--live-apply-trigger", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.env != "production":
            print(
                json.dumps(
                    {
                        "status": "skipped",
                        "reason": "restic live apply only runs against production",
                        "env": args.env,
                    },
                    indent=2,
                )
            )
            return 0

        context = load_controller_context()
        remote_command = build_remote_command(
            mode=args.mode,
            triggered_by=args.triggered_by,
            repo_root=args.repo_root,
            credential_file=args.credential_file,
            live_apply_trigger=args.live_apply_trigger,
        )
        command = build_guest_ssh_command(context, "docker-runtime-lv3", remote_command)
        outcome = run_command(command)
        report = extract_report_json(outcome.stdout)
        payload = {
            "status": "ok" if outcome.returncode == 0 else "error",
            "target": "docker-runtime-lv3",
            "command": remote_command,
            "returncode": outcome.returncode,
            "stdout": outcome.stdout.strip(),
            "stderr": outcome.stderr.strip(),
        }
        if report is not None:
            payload["report"] = report
            if isinstance(report, dict):
                payload["summary"] = report.get("summary") or ((report.get("report") or {}).get("summary"))
        print(json.dumps(payload, indent=2))
        return 0 if outcome.returncode == 0 else 1
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        return emit_cli_error("Restic live apply trigger", exc)


if __name__ == "__main__":
    raise SystemExit(main())
