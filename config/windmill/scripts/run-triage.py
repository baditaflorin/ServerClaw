#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0114 incident triage engine."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(
    alert_payload: dict[str, Any] | None = None,
    repo_path: str = "/srv/proxmox_florin_server",
    emit: bool = True,
    mattermost_webhook_url: str | None = None,
    loki_query_url: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "incident_triage.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    payload = alert_payload or {}
    if not isinstance(payload, dict):
        return {
            "status": "blocked",
            "reason": "alert_payload must be an object",
        }
    if not payload:
        return {
            "status": "blocked",
            "reason": "alert_payload is required",
        }

    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    incident_triage = load_module("incident_triage_worker", workflow)

    report = incident_triage.build_report(payload, loki_query_url=loki_query_url)
    if emit:
        report["emission"] = incident_triage.emit_triage_report(
            report,
            emit_audit=True,
            mattermost_webhook_url=mattermost_webhook_url,
        )
    report["status"] = "ok"
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0114 triage Windmill wrapper.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--payload-file", type=Path, help="Optional JSON alert payload file.")
    parser.add_argument("--no-emit", action="store_true", help="Do not emit the report after building it.")
    parser.add_argument("--mattermost-webhook-url", help="Optional Mattermost webhook override.")
    parser.add_argument("--loki-query-url", help="Optional Loki query_range URL override.")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    payload = json.loads(args.payload_file.read_text(encoding="utf-8")) if args.payload_file else None
    print(
        json.dumps(
            main(
                alert_payload=payload,
                repo_path=args.repo_path,
                emit=not args.no_emit,
                mattermost_webhook_url=args.mattermost_webhook_url,
                loki_query_url=args.loki_query_url,
            ),
            indent=2,
            sort_keys=True,
        )
    )
