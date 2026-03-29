#!/usr/bin/env python3
"""Run approved governed commands inside transient systemd units."""

from __future__ import annotations

import argparse
import base64
import json
import os
import pwd
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from platform.datetime_compat import UTC, datetime

def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_int(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def decode_payload(payload_base64: str) -> dict[str, Any]:
    raw = base64.b64decode(payload_base64.encode("utf-8"))
    return require_mapping(json.loads(raw.decode("utf-8")), "payload")


def ensure_repo_compat_symlink(repo_root: Path, compat_repo_root: Path) -> None:
    compat_repo_root.parent.mkdir(parents=True, exist_ok=True)
    if compat_repo_root.exists() or compat_repo_root.is_symlink():
        if compat_repo_root.resolve() == repo_root.resolve():
            return
        raise RuntimeError(
            f"compatibility repo path exists but points elsewhere: {compat_repo_root}"
        )
    compat_repo_root.symlink_to(repo_root)


def resolve_account_ids(user: str) -> tuple[int, int]:
    account = pwd.getpwnam(user)
    return account.pw_uid, account.pw_gid


def chown_path(path: Path, uid: int, gid: int) -> None:
    os.chown(path, uid, gid)


def grant_runtime_secret_access(destination: Path, repo_root: Path, uid: int, gid: int) -> None:
    try:
        relative = destination.relative_to(repo_root)
    except ValueError:
        return
    if ".local" not in relative.parts:
        return
    marker_index = relative.parts.index(".local")
    if len(relative.parts) <= marker_index + 1:
        return
    current = repo_root / ".local"
    for part in relative.parts[marker_index + 1 : -1]:
        current = current / part
        if not current.exists():
            continue
        chown_path(current, uid, gid)
        current.chmod(current.stat().st_mode | 0o700)


def stage_files(
    staged_files: list[dict[str, Any]],
    *,
    runtime_user: str,
    repo_root: Path,
) -> list[str]:
    uid, gid = resolve_account_ids(runtime_user)
    written_paths: list[str] = []
    for index, item in enumerate(staged_files):
        item = require_mapping(item, f"payload.staged_files[{index}]")
        destination = Path(require_str(item.get("path"), f"payload.staged_files[{index}].path"))
        mode = int(str(item.get("mode", "0600")), 8)
        content_b64 = require_str(item.get("content_b64"), f"payload.staged_files[{index}].content_b64")
        destination.parent.mkdir(parents=True, exist_ok=True)
        grant_runtime_secret_access(destination, repo_root, uid, gid)
        destination.write_bytes(base64.b64decode(content_b64.encode("utf-8")))
        chown_path(destination, uid, gid)
        destination.chmod(mode)
        written_paths.append(str(destination))
    return written_paths


def write_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_systemd_run_command(payload: dict[str, Any], stdout_log: Path, stderr_log: Path) -> list[str]:
    env = require_mapping(payload.get("env", {}), "payload.env")
    command = [
        "systemd-run",
        "--quiet",
        "--wait",
        "--collect",
        "--service-type=exec",
        f"--unit={require_str(payload.get('unit_name'), 'payload.unit_name')}",
        f"--description=LV3 governed command {require_str(payload.get('command_id'), 'payload.command_id')}",
        f"--uid={require_str(payload.get('effective_user'), 'payload.effective_user')}",
        f"--property=WorkingDirectory={require_str(payload.get('working_directory'), 'payload.working_directory')}",
        f"--property=RuntimeMaxSec={require_int(payload.get('timeout_seconds'), 'payload.timeout_seconds', 1)}s",
        f"--property=KillMode={require_str(payload.get('kill_mode'), 'payload.kill_mode')}",
        f"--property=StandardOutput=append:{stdout_log}",
        f"--property=StandardError=append:{stderr_log}",
    ]
    runtime_user = require_str(payload.get("effective_user"), "payload.effective_user")
    merged_env = {
        "HOME": f"/home/{runtime_user}",
        "USER": runtime_user,
        "LOGNAME": runtime_user,
        **{name: str(value) for name, value in env.items()},
    }
    for name, value in sorted(merged_env.items()):
        command.append(f"--setenv={name}={value}")
    command.extend(str(part) for part in require_list(payload.get("command"), "payload.command"))
    return command


def submit(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    repo_root = Path(require_str(payload.get("runtime_repo_root"), "payload.runtime_repo_root"))
    compat_repo_root = Path(
        require_str(payload.get("runtime_compat_repo_root"), "payload.runtime_compat_repo_root")
    )
    log_directory = Path(require_str(payload.get("log_directory"), "payload.log_directory"))
    receipt_directory = Path(require_str(payload.get("receipt_directory"), "payload.receipt_directory"))
    log_directory.mkdir(parents=True, exist_ok=True)
    receipt_directory.mkdir(parents=True, exist_ok=True)
    ensure_repo_compat_symlink(repo_root, compat_repo_root)
    staged_paths = stage_files(
        [require_mapping(item, "payload.staged_files[]") for item in payload.get("staged_files", [])],
        runtime_user=require_str(payload.get("effective_user"), "payload.effective_user"),
        repo_root=repo_root,
    )
    stdout_log = log_directory / f"{payload['unit_name']}.stdout.log"
    stderr_log = log_directory / f"{payload['unit_name']}.stderr.log"
    started_at = utc_now_iso()
    systemd_command = build_systemd_run_command(payload, stdout_log, stderr_log)
    completed = subprocess.run(systemd_command, text=True, capture_output=True, check=False)
    finished_at = utc_now_iso()
    receipt_path = receipt_directory / f"{payload['unit_name']}.json"
    result = {
        "status": "ok" if completed.returncode == 0 else "error",
        "command_id": payload["command_id"],
        "unit_name": payload["unit_name"],
        "runtime_host": payload["runtime_host"],
        "effective_user": payload["effective_user"],
        "working_directory": payload["working_directory"],
        "returncode": completed.returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "receipt_path": str(receipt_path),
        "staged_paths": staged_paths,
        "env_names": sorted(require_mapping(payload.get("env", {}), "payload.env").keys()),
        "command": [str(part) for part in payload["command"]],
        "systemd_command": [
            part if not part.startswith("--setenv=") else part.split("=", 1)[0] + "=<redacted>"
            for part in systemd_command
        ],
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    write_receipt(receipt_path, result)
    return result, completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run approved governed commands via systemd-run.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("--payload-base64", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command != "submit":
            raise ValueError(f"unsupported command {args.command}")
        payload = decode_payload(args.payload_base64)
        result, exit_code = submit(payload)
    except Exception as exc:
        result = {
            "status": "error",
            "error": str(exc),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
