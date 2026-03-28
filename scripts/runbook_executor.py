#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from controller_automation_toolkit import emit_cli_error
from platform.use_cases.runbooks import (
    REPO_ROOT,
    RunbookExecutor,
    RunbookRegistry,
    RunbookRunStore,
    RunbookSurfaceError,
    RunbookUseCaseService,
    WindmillWorkflowRunner,
    WorkflowRunner,
    render_status,
)

__all__ = [
    "REPO_ROOT",
    "RunbookExecutor",
    "RunbookRegistry",
    "RunbookRunStore",
    "RunbookSurfaceError",
    "RunbookUseCaseService",
    "WindmillWorkflowRunner",
    "WorkflowRunner",
    "build_parser",
    "default_runner",
    "main",
    "parse_params",
    "render_status",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute structured automation-compatible runbooks.")
    parser.add_argument("--repo-path", default=str(REPO_ROOT))
    parser.add_argument("--actor-id", default="operator:runbook-cli")
    subparsers = parser.add_subparsers(dest="action", required=True)

    execute = subparsers.add_parser("execute", help="Execute one runbook.")
    execute.add_argument("runbook")
    execute.add_argument("--param", action="append", default=[], help="Runbook parameter in key=value format.")
    execute.add_argument("--dry-run", action="store_true")

    status = subparsers.add_parser("status", help="Show one persisted run.")
    status.add_argument("run_id")

    approve = subparsers.add_parser("approve", help="Resume one escalated run.")
    approve.add_argument("run_id")
    return parser


def parse_params(items: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"expected key=value, got {item!r}")
        key, value = item.split("=", 1)
        params[key] = value
    return params


def default_runner(repo_root: Path) -> WindmillWorkflowRunner:
    from lv3_cli import load_secret_file, load_service_map, windmill_url

    service_map = load_service_map()
    return WindmillWorkflowRunner(
        base_url=windmill_url(service_map),
        token=load_secret_file("windmill_superadmin_secret"),
        repo_root=repo_root,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_path)
    try:
        service = RunbookUseCaseService(repo_root=repo_root, workflow_runner=default_runner(repo_root))
        if args.action == "execute":
            params = parse_params(args.param)
            if args.dry_run:
                print(json.dumps(service.preview(args.runbook, params, surface="cli"), indent=2, sort_keys=True))
                return 0
            print(
                json.dumps(
                    service.execute(args.runbook, params, actor_id=args.actor_id, surface="cli"),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.action == "status":
            print(render_status(service.status(args.run_id)))
            return 0
        if args.action == "approve":
            print(json.dumps(service.resume(args.run_id, actor_id=args.actor_id), indent=2, sort_keys=True))
            return 0
        parser.print_help()
        return 1
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("runbook executor", exc)


if __name__ == "__main__":
    raise SystemExit(main())
