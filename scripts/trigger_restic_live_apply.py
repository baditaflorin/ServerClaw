#!/usr/bin/env python3
"""Run the ADR 0302 restic workflow on docker-runtime-lv3 through the managed SSH path."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path, PurePosixPath

import yaml

from controller_automation_toolkit import emit_cli_error
from drift_lib import build_guest_ssh_command, load_controller_context, run_command


LOCAL_REPO_ROOT = Path(__file__).resolve().parents[1]
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
REMOTE_RUNTIME_SUPPORT_FILES = (
    ("scripts/restic_config_backup.py", 0o755),
    ("scripts/script_bootstrap.py", 0o644),
    ("scripts/controller_automation_toolkit.py", 0o644),
    ("config/restic-file-backup-catalog.json", 0o644),
)
SYNCABLE_REPORT_KEYS = ("receipt_path", "latest_snapshot_receipt")


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


def sync_remote_runtime_file(
    context: dict,
    *,
    target: str,
    local_path: Path,
    remote_path: str,
    mode: int,
) -> None:
    remote_parent = str(PurePosixPath(remote_path).parent)
    remote_command = (
        f"sudo install -d -o root -g root -m 0755 {shlex.quote(remote_parent)}"
        f" && sudo tee {shlex.quote(remote_path)} >/dev/null"
        f" && sudo chmod {mode:o} {shlex.quote(remote_path)}"
    )
    command = build_guest_ssh_command(context, target, remote_command)
    completed = subprocess.run(
        command,
        input=local_path.read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "remote sync failed"
        raise RuntimeError(f"{remote_path}: {detail}")


def remote_file_exists(
    context: dict,
    *,
    target: str,
    path: str,
) -> bool:
    remote_command = f"sudo test -s {shlex.quote(path)}"
    command = build_guest_ssh_command(context, target, remote_command)
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def resolve_openbao_init_local_file() -> Path:
    group_vars = LOCAL_REPO_ROOT / "inventory" / "group_vars" / "all.yml"
    payload = yaml.safe_load(group_vars.read_text(encoding="utf-8")) or {}
    init_path = str(payload.get("openbao_init_local_file") or "").strip()
    if not init_path:
        raise ValueError("openbao_init_local_file is not declared in inventory/group_vars/all.yml")
    return Path(init_path)


def run_local_converge_restic(env: str) -> None:
    init_path = resolve_openbao_init_local_file()
    if not init_path.is_file():
        raise ValueError(f"OpenBao init payload is missing locally: {init_path}")

    command = ["make", "converge-restic-config-backup", f"env={env}"]
    completed = subprocess.run(
        command,
        cwd=str(LOCAL_REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "local restic converge failed"
        raise RuntimeError(detail)


def ensure_remote_runtime_credentials(
    context: dict,
    *,
    env: str,
    credential_file: str,
    target: str = "docker-runtime-lv3",
) -> None:
    if remote_file_exists(context, target=target, path=credential_file):
        return

    run_local_converge_restic(env)

    if not remote_file_exists(context, target=target, path=credential_file):
        raise RuntimeError(
            f"restic runtime credentials are still missing on {target} after converge: {credential_file}"
        )


def normalize_repo_relative_path(path: str) -> PurePosixPath:
    candidate = PurePosixPath(str(path).strip())
    if candidate.is_absolute():
        raise ValueError(f"expected a repo-relative path, got absolute path: {path}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError(f"receipt sync path must stay within the repo root: {path}")
    if not candidate.parts or candidate.parts[0] != "receipts":
        raise ValueError(f"receipt sync path must stay under receipts/: {path}")
    return candidate


def fetch_remote_repo_file(
    context: dict,
    *,
    target: str,
    repo_root: str,
    relative_path: str,
) -> str:
    relative = normalize_repo_relative_path(relative_path)
    remote_path = str(PurePosixPath(repo_root) / relative)
    remote_command = f"sudo cat {shlex.quote(remote_path)}"
    command = build_guest_ssh_command(context, target, remote_command)
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "remote download failed"
        raise RuntimeError(f"{remote_path}: {detail}")
    return completed.stdout


def sync_reported_receipt_artifacts(
    context: dict,
    *,
    target: str,
    repo_root: str,
    report: dict | None,
) -> list[str]:
    if not isinstance(report, dict):
        return []

    synced: list[str] = []
    for key in SYNCABLE_REPORT_KEYS:
        relative_path = report.get(key)
        if not isinstance(relative_path, str) or not relative_path.strip():
            continue
        relative = normalize_repo_relative_path(relative_path)
        local_path = LOCAL_REPO_ROOT / Path(*relative.parts)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(
            fetch_remote_repo_file(
                context,
                target=target,
                repo_root=repo_root,
                relative_path=relative_path,
            ),
            encoding="utf-8",
        )
        synced.append(relative_path)
    return synced


def ensure_remote_runtime_support_files(context: dict, *, repo_root: str, target: str = "docker-runtime-lv3") -> None:
    repo_root_path = PurePosixPath(repo_root)
    for relative_path, mode in REMOTE_RUNTIME_SUPPORT_FILES:
        local_path = LOCAL_REPO_ROOT / relative_path
        if not local_path.is_file():
            raise ValueError(f"required runtime support file is missing locally: {local_path}")
        remote_path = str(repo_root_path / relative_path)
        sync_remote_runtime_file(
            context,
            target=target,
            local_path=local_path,
            remote_path=remote_path,
            mode=mode,
        )


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
        ensure_remote_runtime_support_files(context, repo_root=args.repo_root)
        ensure_remote_runtime_credentials(
            context,
            env=args.env,
            credential_file=args.credential_file,
        )
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
        if outcome.returncode == 0:
            synced_paths = sync_reported_receipt_artifacts(
                context,
                target="docker-runtime-lv3",
                repo_root=args.repo_root,
                report=report,
            )
            if synced_paths:
                payload["synced_local_paths"] = synced_paths
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
