#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from controller_automation_toolkit import emit_cli_error
from platform.live_apply import (
    create_rollback_bundle,
    enqueue_workstreams,
    execute_merge_train,
    execute_rollback_bundle,
    load_merge_train_state,
    plan_merge_train,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage ADR 0182 live-apply merge trains and rollback bundles.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    subparsers = parser.add_subparsers(dest="command", required=True)

    queue = subparsers.add_parser("queue", help="Queue one or more workstreams for the next merge train.")
    queue.add_argument("--workstream", action="append", required=True)
    queue.add_argument("--requested-by", default="operator:merge-train")
    queue.add_argument("--reason")

    plan = subparsers.add_parser("plan", help="Build the current merge-train execution plan.")
    plan.add_argument("--workstream", action="append")
    plan.add_argument("--skip-checks", action="store_true")

    bundle = subparsers.add_parser("bundle", help="Create a rollback bundle for the current merge-train plan.")
    bundle.add_argument("--workstream", action="append")
    bundle.add_argument("--skip-checks", action="store_true")

    run = subparsers.add_parser("run", help="Merge queued workstreams and execute their live-apply plans.")
    run.add_argument("--workstream", action="append")
    run.add_argument("--requested-by", default="operator:merge-train")
    run.add_argument("--no-auto-rollback", action="store_true")

    rollback = subparsers.add_parser("rollback", help="Execute a previously created rollback bundle.")
    rollback.add_argument("--bundle", required=True, type=Path)

    subparsers.add_parser("status", help="Show the current merge-train queue state.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "queue":
            payload = enqueue_workstreams(
                args.workstream,
                requested_by=args.requested_by,
                reason=args.reason,
                repo_root=args.repo_root,
            )
        elif args.command == "plan":
            payload = plan_merge_train(
                repo_root=args.repo_root,
                workstream_ids=args.workstream,
                run_checks=not args.skip_checks,
            )
        elif args.command == "bundle":
            plan = plan_merge_train(
                repo_root=args.repo_root,
                workstream_ids=args.workstream,
                run_checks=not args.skip_checks,
            )
            bundle_path = create_rollback_bundle(repo_root=args.repo_root, plan=plan)
            payload = {"status": "created", "bundle_path": str(bundle_path), "plan": plan}
        elif args.command == "run":
            payload = execute_merge_train(
                repo_root=args.repo_root,
                workstream_ids=args.workstream,
                requested_by=args.requested_by,
                auto_rollback=not args.no_auto_rollback,
            )
        elif args.command == "rollback":
            payload = execute_rollback_bundle(args.bundle, repo_root=args.repo_root)
        else:
            payload = load_merge_train_state(args.repo_root)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("live apply merge train", exc)


if __name__ == "__main__":
    raise SystemExit(main())
