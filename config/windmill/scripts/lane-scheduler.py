#!/usr/bin/env python3
"""Run one VM-scoped execution-lane dispatch pass."""

from __future__ import annotations

import argparse
import json
import os
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


def main(repo_path: str = "/srv/proxmox_florin_server", *, max_dispatches: int = 10) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from platform.scheduler import build_scheduler

    base_url = _resolve_windmill_url(repo_root)
    token = _resolve_windmill_token(repo_root)
    if not base_url or not token:
        return {
            "status": "blocked",
            "reason": "Windmill API base URL or token is unavailable",
            "base_url_present": bool(base_url),
            "token_present": bool(token),
        }

    scheduler = build_scheduler(
        base_url=base_url,
        token=token,
        workspace="lv3",
        repo_root=repo_root,
    )
    summary = scheduler.dispatch_queued(max_dispatches=max_dispatches)
    summary["status"] = "ok"
    summary["repo_path"] = str(repo_root)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one ADR 0154 lane dispatch pass.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--max-dispatches", type=int, default=10)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    print(json.dumps(main(repo_path=args.repo_path, max_dispatches=args.max_dispatches), indent=2, sort_keys=True))
