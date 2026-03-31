#!/usr/bin/env python3
"""Windmill wrapper for the repo-managed Atlas drift check."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def set_default_env(env: dict[str, str], name: str, value: str) -> None:
    if not env.get(name, "").strip():
        env[name] = value


def set_default_env_from_text_file(env: dict[str, str], name: str, path: Path) -> None:
    if env.get(name, "").strip():
        return
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if value:
        env[name] = value


def set_default_env_from_json_file(env: dict[str, str], name: str, path: Path) -> None:
    if env.get(name, "").strip():
        return
    try:
        raw_value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if not raw_value:
        return
    try:
        env[name] = json.dumps(json.loads(raw_value))
    except json.JSONDecodeError:
        env[name] = raw_value


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    publish_nats: bool = True,
    publish_ntfy: bool = True,
    write_receipts: bool = True,
) -> dict[str, object]:
    repo_root = Path(repo_path)
    atlas_script = repo_root / "scripts" / "atlas_schema.py"
    package_runner = repo_root / "scripts" / "run_python_with_packages.sh"
    if not atlas_script.exists() or not package_runner.exists():
        return {
            "status": "blocked",
            "reason": "Atlas drift surfaces are missing from the worker checkout",
            "expected_repo_path": str(repo_root),
        }

    command = [
        str(package_runner),
        "docker",
        "nats-py",
        "pyyaml",
        "--",
        "scripts/atlas_schema.py",
        "drift",
        "--repo-root",
        str(repo_root),
        "--format",
        "json",
    ]
    if write_receipts:
        command.append("--write-receipts")
    if publish_nats:
        command.append("--publish-nats")
    if publish_ntfy:
        command.append("--publish-ntfy")

    command_env = os.environ.copy()
    # Windmill workers run on the private runtime guest and can talk to Atlas dependencies directly.
    set_default_env(command_env, "LV3_ATLAS_FORCE_DIRECT_ENDPOINTS", "1")
    set_default_env(command_env, "LV3_NATS_URL", "nats://127.0.0.1:4222")
    set_default_env_from_json_file(
        command_env,
        "LV3_ATLAS_OPENBAO_APPROLE_JSON",
        repo_root / ".local" / "openbao" / "atlas-approle.json",
    )
    set_default_env_from_json_file(
        command_env,
        "LV3_ATLAS_OPENBAO_INIT_JSON",
        repo_root / ".local" / "openbao" / "init.json",
    )
    set_default_env_from_text_file(
        command_env,
        "LV3_NTFY_ALERTMANAGER_PASSWORD",
        repo_root / ".local" / "ntfy" / "alertmanager-password.txt",
    )
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=command_env,
    )
    payload: dict[str, object] = {
        "status": "ok" if completed.returncode == 0 else "error",
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    if completed.stdout.strip():
        try:
            payload["report"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload["status"] = "error"
            payload["reason"] = "Atlas drift command did not return valid JSON"
    report = payload.get("report")
    if completed.returncode == 2 and isinstance(report, dict):
        report_status = str(report.get("status") or "").strip().lower()
        if report_status == "drift_detected":
            payload["status"] = "drift"
        elif report_status == "clean":
            payload["status"] = "ok"
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the repo-managed Atlas drift check from Windmill.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--no-publish-nats", action="store_true")
    parser.add_argument("--no-publish-ntfy", action="store_true")
    parser.add_argument("--no-write-receipts", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            main(
                repo_path=args.repo_path,
                publish_nats=not args.no_publish_nats,
                publish_ntfy=not args.no_publish_ntfy,
                write_receipts=not args.no_write_receipts,
            ),
            indent=2,
            sort_keys=True,
        )
    )
