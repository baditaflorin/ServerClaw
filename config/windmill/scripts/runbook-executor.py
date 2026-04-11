#!/usr/bin/env python3
"""Windmill wrapper for the ADR 0129 runbook automation executor."""

from __future__ import annotations

import os

import argparse
import importlib.util
import json
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
    runbook_id: str | None = None,
    params: dict[str, Any] | None = None,
    run_id: str | None = None,
    action: str = "execute",
    actor_id: str = "automation:windmill-runbook-executor",
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
) -> dict[str, Any]:
    repo_root = Path(repo_path)
    workflow = repo_root / "scripts" / "runbook_executor.py"
    if not workflow.exists():
        return {
            "status": "blocked",
            "reason": "repo checkout not mounted on the worker",
            "expected_repo_path": str(repo_root),
        }

    module = load_module("runbook_executor_worker", workflow)
    runner = module.default_runner(repo_root)
    executor = module.RunbookExecutor(repo_root=repo_root, workflow_runner=runner)

    if action == "execute":
        if not runbook_id:
            return {"status": "blocked", "reason": "runbook_id is required"}
        record = executor.execute(runbook_id, params or {}, actor_id=actor_id)
    elif action == "approve":
        if not run_id:
            return {"status": "blocked", "reason": "run_id is required"}
        record = executor.resume(run_id, actor_id=actor_id)
    elif action == "status":
        if not run_id:
            return {"status": "blocked", "reason": "run_id is required"}
        record = executor.status(run_id)
    else:
        return {"status": "blocked", "reason": f"unsupported action: {action}"}

    return {"status": "ok", "record": record}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ADR 0129 runbook executor Windmill wrapper.")
    parser.add_argument("--repo-path", default=os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"))
    parser.add_argument("--action", choices=["execute", "approve", "status"], default="execute")
    parser.add_argument("--runbook-id")
    parser.add_argument("--run-id")
    parser.add_argument("--params-file", type=Path, help="Optional JSON params file.")
    parser.add_argument("--actor-id", default="automation:windmill-runbook-executor")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    params = json.loads(args.params_file.read_text(encoding="utf-8")) if args.params_file else None
    print(
        json.dumps(
            main(
                runbook_id=args.runbook_id,
                params=params,
                run_id=args.run_id,
                action=args.action,
                actor_id=args.actor_id,
                repo_path=args.repo_path,
            ),
            indent=2,
            sort_keys=True,
        )
    )
