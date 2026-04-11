#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from controller_automation_toolkit import resolve_repo_local_path


def _read_proc_env_var(*names: str, proc_environ_path: str = "/proc/1/environ") -> str:
    proc_environ = Path(proc_environ_path)
    if not proc_environ.exists():
        return ""
    try:
        entries = proc_environ.read_bytes().split(b"\0")
    except OSError:
        return ""
    for name in names:
        prefix = f"{name}=".encode()
        for entry in entries:
            if entry.startswith(prefix):
                return entry.split(b"=", 1)[1].decode("utf-8", errors="ignore").strip()
    return ""


def _resolve_windmill_url(repo_root: Path) -> str | None:
    for env_name in ("LV3_WINDMILL_BASE_URL", "BASE_URL"):
        override = os.environ.get(env_name, "").strip()
        if override:
            return override.rstrip("/")
    proc_override = _read_proc_env_var("LV3_WINDMILL_BASE_URL", "BASE_URL")
    if proc_override:
        return proc_override.rstrip("/")
    catalog_path = repo_root / "config" / "service-capability-catalog.json"
    if not catalog_path.exists():
        return None
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    for service in payload.get("services", []):
        if not isinstance(service, dict) or service.get("id") != "windmill":
            continue
        for key in ("internal_url", "public_url"):
            value = service.get(key)
            if isinstance(value, str) and value.strip():
                return value.rstrip("/")
    return None


def _resolve_windmill_token(repo_root: Path) -> str | None:
    for env_name in ("LV3_WINDMILL_TOKEN", "SUPERADMIN_SECRET"):
        override = os.environ.get(env_name, "").strip()
        if override:
            return override
    proc_override = _read_proc_env_var("LV3_WINDMILL_TOKEN", "SUPERADMIN_SECRET")
    if proc_override:
        return proc_override
    worker_secret = repo_root / ".local" / "windmill" / "superadmin-secret.txt"
    if worker_secret.exists():
        return worker_secret.read_text(encoding="utf-8").strip()
    manifest_path = repo_root / "config" / "controller-local-secrets.json"
    if not manifest_path.exists():
        return None
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = payload.get("secrets", {}).get("windmill_superadmin_secret")
    if not isinstance(entry, dict):
        return None
    secret_path = entry.get("path")
    if not isinstance(secret_path, str):
        return None
    path = resolve_repo_local_path(secret_path, repo_root=repo_root)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def main(
    *,
    repo_root: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    resource_hints: list[str] | None = None,
    workflow_hints: list[str] | None = None,
    max_items: int = 5,
) -> dict[str, Any]:
    base = Path(repo_root)
    if not base.exists():
        return {"status": "blocked", "reason": "repo checkout missing", "repo_root": str(base)}
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))

    if importlib.util.find_spec("yaml") is None:
        command = [
            "uv",
            "run",
            "--no-project",
            "--with",
            "pyyaml",
            "python",
            str(base / "scripts" / "intent_queue_dispatcher.py"),
            "--repo-root",
            str(base),
            "--max-items",
            str(max_items),
        ]
        for resource_hint in resource_hints or []:
            command.extend(["--resource-hint", resource_hint])
        for workflow_hint in workflow_hints or []:
            command.extend(["--workflow-hint", workflow_hint])
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{base}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(base)
        result = subprocess.run(command, cwd=base, env=env, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            return {
                "status": "error",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        return json.loads(result.stdout) if result.stdout.strip() else {"status": "ok"}

    try:
        from platform.scheduler import build_scheduler
    except ModuleNotFoundError as exc:
        if exc.name != "yaml":
            raise
        command = [
            "uv",
            "run",
            "--no-project",
            "--with",
            "pyyaml",
            "python",
            str(base / "scripts" / "intent_queue_dispatcher.py"),
            "--repo-root",
            str(base),
            "--max-items",
            str(max_items),
        ]
        for resource_hint in resource_hints or []:
            command.extend(["--resource-hint", resource_hint])
        for workflow_hint in workflow_hints or []:
            command.extend(["--workflow-hint", workflow_hint])
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{base}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(base)
        result = subprocess.run(command, cwd=base, env=env, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            return {
                "status": "error",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        return json.loads(result.stdout) if result.stdout.strip() else {"status": "ok"}

    base_url = _resolve_windmill_url(base)
    token = _resolve_windmill_token(base)
    if not base_url or not token:
        return {
            "status": "blocked",
            "reason": "windmill credentials unavailable",
            "base_url_present": bool(base_url),
            "token_present": bool(token),
        }
    scheduler = build_scheduler(base_url=base_url, token=token, workspace="lv3", repo_root=base)
    return scheduler.drain_queued_intents(
        resource_hints=resource_hints or [],
        workflow_hints=workflow_hints or [],
        max_items=max_items,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch queued ADR 0155 intents.")
    parser.add_argument("--repo-root", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--resource-hint", action="append", default=[])
    parser.add_argument("--workflow-hint", action="append", default=[])
    parser.add_argument("--max-items", type=int, default=5)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(
        json.dumps(
            main(
                repo_root=args.repo_root,
                resource_hints=args.resource_hint,
                workflow_hints=args.workflow_hint,
                max_items=args.max_items,
            ),
            indent=2,
            sort_keys=True,
        )
    )
