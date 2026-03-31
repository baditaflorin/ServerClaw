#!/usr/bin/env python3
"""Run the ADR 0302 restic workflow on docker-runtime-lv3 through the managed SSH path."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path, PurePosixPath

from controller_automation_toolkit import emit_cli_error
from drift_lib import build_guest_ssh_command, load_controller_context, run_command


LOCAL_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REMOTE_REPO_ROOT = "/srv/proxmox_florin_server"
DEFAULT_RUNTIME_CREDENTIAL_FILE = "/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json"
FALLBACK_REMOTE_REPO_ROOT = "/opt/api-gateway/service"
REMOTE_RUNTIME_SUPPORT_FILES = (
    ("scripts/restic_config_backup.py", 0o755),
    ("scripts/script_bootstrap.py", 0o644),
    ("scripts/controller_automation_toolkit.py", 0o644),
    ("config/restic-file-backup-catalog.json", 0o644),
)


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
) -> str:
    script_path = f"{repo_root}/scripts/restic_config_backup.py"
    fallback_script_path = f"{FALLBACK_REMOTE_REPO_ROOT}/scripts/restic_config_backup.py"
    command = [
        "sudo",
        "python3",
        '"$script_path"',
        "--repo-root",
        repo_root,
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
    rendered_command = " ".join(command)
    shell_lines = [
        f'primary_script={shlex.quote(script_path)}',
        f'fallback_script={shlex.quote(fallback_script_path)}',
        'script_path="$primary_script"',
        'if [ ! -f "$script_path" ] && [ -f "$fallback_script" ]; then script_path="$fallback_script"; fi',
        'if [ ! -f "$script_path" ]; then',
        '  echo "restic_config_backup.py is missing from both $primary_script and $fallback_script" >&2',
        "  exit 2",
        "fi",
        rendered_command,
    ]
    return "sh -lc " + shlex.quote("\n".join(shell_lines))


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
