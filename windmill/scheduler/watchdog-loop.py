#!/usr/bin/env python3
"""Run one scheduler watchdog pass against active Windmill jobs."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _resolve_windmill_url(repo_root: Path) -> str | None:
    override = os.environ.get("LV3_WINDMILL_BASE_URL", "").strip()
    if override:
        return override.rstrip("/")
    catalog_path = repo_root / "config" / "service-capability-catalog.json"
    if not catalog_path.exists():
        return None
    payload = _load_json(catalog_path)
    for service in payload.get("services", []):
        if not isinstance(service, dict) or service.get("id") != "windmill":
            continue
        for key in ("internal_url", "public_url"):
            value = service.get(key)
            if isinstance(value, str) and value.strip():
                return value.rstrip("/")
        environments = service.get("environments")
        if isinstance(environments, dict):
            binding = environments.get("production")
            if isinstance(binding, dict):
                value = binding.get("url")
                if isinstance(value, str) and value.strip():
                    return value.rstrip("/")
    return None


def _resolve_windmill_token(repo_root: Path) -> str | None:
    override = os.environ.get("LV3_WINDMILL_TOKEN", "").strip()
    if override:
        return override
    manifest_path = repo_root / "config" / "controller-local-secrets.json"
    if not manifest_path.exists():
        return None
    payload = _load_json(manifest_path)
    entry = payload.get("secrets", {}).get("windmill_superadmin_secret")
    if not isinstance(entry, dict):
        return None
    secret_path = entry.get("path")
    if not isinstance(secret_path, str):
        return None
    path = Path(secret_path).expanduser()
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def main(repo_path: str = "/srv/proxmox_florin_server") -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from platform.ledger import LedgerWriter
        from platform.scheduler import HttpWindmillClient, SchedulerStateStore, Watchdog
    except ModuleNotFoundError as exc:
        if exc.name != "yaml":
            raise
        command = [
            "uv",
            "run",
            "--with",
            "pyyaml",
            "python",
            str(repo_root / "windmill" / "scheduler" / "watchdog-loop.py"),
            "--repo-path",
            str(repo_root),
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{repo_root}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(repo_root)
        result = subprocess.run(command, cwd=repo_root, env=env, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            return {
                "status": "error",
                "command": " ".join(shlex.quote(part) for part in command),
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        return json.loads(result.stdout) if result.stdout.strip() else {"status": "ok"}

    base_url = _resolve_windmill_url(repo_root)
    token = _resolve_windmill_token(repo_root)
    if not base_url or not token:
        return {
            "status": "blocked",
            "reason": "Windmill API base URL or token is unavailable",
            "base_url_present": bool(base_url),
            "token_present": bool(token),
        }

    dsn = os.environ.get("LV3_LEDGER_DSN", "").strip()
    ledger_writer = LedgerWriter(dsn=dsn) if dsn else None
    client = HttpWindmillClient(base_url=base_url, token=token, workspace="lv3")
    state_store = SchedulerStateStore(repo_root / ".local" / "scheduler" / "active-jobs.json")
    watchdog = Watchdog(
        windmill_client=client,
        state_store=state_store,
        ledger_writer=ledger_writer,
    )
    summary = watchdog.monitor_once()
    summary["status"] = "ok"
    summary["repo_path"] = str(repo_root)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one ADR 0119 watchdog scan.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(json.dumps(main(repo_path=args.repo_path), indent=2, sort_keys=True))
