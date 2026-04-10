#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.ansible.execution_scopes import (
    AnsibleExecutionScopeError,
    CATALOG_PATH,
    INVENTORY_PATH,
    plan_playbook_execution,
    run_planned_playbook,
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

    parallel_parser = subparsers.add_parser(
        "parallel-run",
        help="Run multiple playbooks in parallel, grouped by target lane (ADR 0392 Phase 2.2).",
    )
    parallel_parser.add_argument("--playbooks", required=True, nargs="+", type=Path)
    parallel_parser.add_argument("--env", default="production")
    parallel_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parallel_parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)
    parallel_parser.add_argument("--max-parallel", type=int, default=4, help="Max concurrent lanes.")
    parallel_parser.add_argument("ansible_args", nargs=argparse.REMAINDER)
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
    print(f"Planning scoped playbook: {args.playbook} (env={args.env})", flush=True)
    plan = plan_playbook_execution(
        args.playbook,
        env=args.env,
        run_id=args.run_id,
        shard_root=args.shard_root,
        catalog_path=args.catalog,
        inventory_path=args.inventory,
    )
    print(
        f"Running scoped playbook: {plan.playbook_path} limit={plan.limit_expression} shard={plan.inventory_shard_path}",
        flush=True,
    )
    result = run_planned_playbook(
        plan,
        passthrough_args=passthrough_args,
        inventory_path=args.inventory,
    )
    return result.returncode


def _run_single_plan(plan, passthrough_args, inventory_path):
    """Execute a single planned playbook and return (playbook_path, returncode)."""
    print(
        f"[lane={plan.target_lane or 'default'}] Running: {plan.playbook_path} "
        f"limit={plan.limit_expression}",
        flush=True,
    )
    result = run_planned_playbook(
        plan,
        passthrough_args=passthrough_args,
        inventory_path=inventory_path,
    )
    return plan.playbook_path, result.returncode


def handle_parallel_run(args: argparse.Namespace) -> int:
    """Group playbooks by target lane and run independent lanes in parallel (ADR 0392)."""
    passthrough_args = list(args.ansible_args)
    if passthrough_args and passthrough_args[0] == "--":
        passthrough_args = passthrough_args[1:]

    # Plan all playbooks and group by target lane
    plans = []
    for playbook in args.playbooks:
        plan = plan_playbook_execution(
            playbook,
            env=args.env,
            catalog_path=args.catalog,
            inventory_path=args.inventory,
        )
        plans.append(plan)

    lane_groups: dict[str, list] = defaultdict(list)
    for plan in plans:
        lane_key = plan.target_lane or f"_host:{','.join(plan.target_hosts)}"
        lane_groups[lane_key].append(plan)

    print(
        f"Parallel dispatch: {len(plans)} playbooks across {len(lane_groups)} lane(s) "
        f"(max_parallel={args.max_parallel})",
        flush=True,
    )
    for lane_key, group in lane_groups.items():
        print(f"  Lane {lane_key}: {[p.playbook_path for p in group]}", flush=True)

    # Within each lane, playbooks run sequentially; across lanes, they run in parallel
    worst_rc = 0
    failed_playbooks: list[str] = []

    def run_lane(lane_key: str, lane_plans: list) -> list[tuple[str, int]]:
        results = []
        for plan in lane_plans:
            playbook_path, rc = _run_single_plan(plan, passthrough_args, args.inventory)
            results.append((playbook_path, rc))
            if rc != 0:
                print(f"[lane={lane_key}] FAILED: {playbook_path} (rc={rc})", flush=True)
                break  # Stop this lane on first failure
        return results

    with ThreadPoolExecutor(max_workers=min(len(lane_groups), args.max_parallel)) as pool:
        futures = {
            pool.submit(run_lane, lane_key, lane_plans): lane_key
            for lane_key, lane_plans in lane_groups.items()
        }
        for future in as_completed(futures):
            lane_key = futures[future]
            for playbook_path, rc in future.result():
                if rc != 0:
                    worst_rc = max(worst_rc, rc)
                    failed_playbooks.append(playbook_path)

    if failed_playbooks:
        print(f"\nParallel run completed with failures: {failed_playbooks}", flush=True)
    else:
        print(f"\nParallel run completed successfully ({len(plans)} playbooks).", flush=True)
    return worst_rc


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
        if args.command == "parallel-run":
            return handle_parallel_run(args)
        parser.error(f"unsupported command '{args.command}'")
    except AnsibleExecutionScopeError as exc:
        print(f"ansible-scope-runner error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
