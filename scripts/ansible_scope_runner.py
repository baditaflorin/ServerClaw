#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.ansible.execution_scopes import (
    AnsibleExecutionScopeError,
    CATALOG_PATH,
    INVENTORY_PATH,
    plan_playbook_execution,
    run_scoped_playbook,
    validate_scope_catalog,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve Ansible execution scope metadata, render an inventory shard, and optionally run the playbook."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate the execution-scope catalog and Makefile coverage.")
    validate_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    validate_parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)

    plan_parser = subparsers.add_parser("plan", help="Print the resolved scope and shard plan for a playbook.")
    plan_parser.add_argument("--playbook", required=True, type=Path)
    plan_parser.add_argument("--env", default="production")
    plan_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    plan_parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)
    plan_parser.add_argument("--run-id")
    plan_parser.add_argument("--shard-root", type=Path)

    run_parser = subparsers.add_parser("run", help="Run ansible-playbook through a scoped shard inventory.")
    run_parser.add_argument("--playbook", required=True, type=Path)
    run_parser.add_argument("--env", default="production")
    run_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    run_parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)
    run_parser.add_argument("--run-id")
    run_parser.add_argument("--shard-root", type=Path)
    run_parser.add_argument("ansible_args", nargs=argparse.REMAINDER)
    return parser


def handle_validate(args: argparse.Namespace) -> int:
    validate_scope_catalog(catalog_path=args.catalog, inventory_path=args.inventory)
    return 0


def handle_plan(args: argparse.Namespace) -> int:
    plan = plan_playbook_execution(
        args.playbook,
        env=args.env,
        run_id=args.run_id,
        shard_root=args.shard_root,
        catalog_path=args.catalog,
        inventory_path=args.inventory,
    )
    print(
        json.dumps(
            {
                "playbook_path": plan.playbook_path,
                "env": plan.env,
                "run_id": plan.run_id,
                "mutation_scope": plan.mutation_scope,
                "execution_class": plan.execution_class,
                "target_lane": plan.target_lane,
                "target_hosts": list(plan.target_hosts),
                "limit_expression": plan.limit_expression,
                "inventory_shard_path": plan.inventory_shard_path,
                "shared_surfaces": list(plan.shared_surfaces),
                "source_leaf_playbooks": list(plan.source_leaf_playbooks),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def handle_run(args: argparse.Namespace) -> int:
    passthrough_args = list(args.ansible_args)
    if passthrough_args and passthrough_args[0] == "--":
        passthrough_args = passthrough_args[1:]
    result = run_scoped_playbook(
        args.playbook,
        env=args.env,
        passthrough_args=passthrough_args,
        run_id=args.run_id,
        shard_root=args.shard_root,
        catalog_path=args.catalog,
        inventory_path=args.inventory,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return handle_validate(args)
        if args.command == "plan":
            return handle_plan(args)
        if args.command == "run":
            return handle_run(args)
        parser.error(f"unsupported command '{args.command}'")
    except AnsibleExecutionScopeError as exc:
        print(f"ansible-scope-runner error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
