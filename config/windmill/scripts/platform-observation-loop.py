#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0126 observation-to-action closure loop."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any


def main(
    findings: list[dict[str, Any]] | None = None,
    source: str = "controller-observation-loop",
    repo_path: str = "/srv/proxmox_florin_server",
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    closure_loop = importlib.import_module("platform.closure_loop")
    loop = closure_loop.ClosureLoop(repo_root)
    processed: list[dict[str, Any]] = []
    finding_list = findings or []
    for index, finding in enumerate(finding_list, start=1):
        payload = closure_loop.observation_finding_to_alert_payload(
            finding,
            fallback_ref=f"{source}:{index}",
        )
        if payload is None:
            continue
        run = loop.start(
            trigger_type="observation_finding",
            trigger_ref=str(payload.get("incident_id") or f"{source}:{index}"),
            service_id=str(payload["service_id"]),
            trigger_payload=payload,
        )
        processed.append(
            {
                "run_id": run["run_id"],
                "service_id": run["service_id"],
                "state": run["current_state"],
            }
        )

    return {
        "status": "ok",
        "source": source,
        "workspace": __import__("os").environ.get("WM_WORKSPACE"),
        "job_id_present": bool(__import__("os").environ.get("WM_JOB_ID")),
        "finding_count": len(finding_list),
        "processed_count": len(processed),
        "processed_runs": processed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0126 observation-loop wrapper.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--findings-file", type=Path, help="Optional JSON file containing the finding list.")
    parser.add_argument("--source", default="controller-observation-loop")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    payload = json.loads(args.findings_file.read_text(encoding="utf-8")) if args.findings_file else None
    print(
        json.dumps(
            main(findings=payload, source=args.source, repo_path=args.repo_path),
            indent=2,
            sort_keys=True,
        )
    )
