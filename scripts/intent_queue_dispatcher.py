#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _resolve_windmill_url(repo_root: Path) -> str | None:
    for env_name in ("LV3_WINDMILL_BASE_URL", "BASE_URL"):
        override = os.environ.get(env_name, "").strip()
        if override:
            return override.rstrip("/")
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
    path = Path(secret_path).expanduser()
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def main(
    *,
    repo_root: str = "/srv/proxmox_florin_server",
    resource_hints: list[str] | None = None,
    workflow_hints: list[str] | None = None,
    max_items: int = 5,
) -> dict[str, Any]:
    base = Path(repo_root)
    if not base.exists():
        return {"status": "blocked", "reason": "repo checkout missing", "repo_root": str(base)}
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))

    from platform.scheduler import build_scheduler

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
    parser.add_argument("--repo-root", default="/srv/proxmox_florin_server")
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
