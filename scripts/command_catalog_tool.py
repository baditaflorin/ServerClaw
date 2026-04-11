#!/usr/bin/env python3
"""command_catalog_tool.py — Browse governed commands and verify approval policies.

Data source: config/command-catalog.json

Commands
--------
  list   [--policy POLICY] [--scope SCOPE]   List all governed commands
  show   <name>                               Show full command definition
  policy <name>                               Show the approval policy for a command
  check  --command CMD --requester-class CLS  Check if a requester class can submit CMD
  policies                                    List all approval policy names and descriptions

Examples
--------
  python scripts/command_catalog_tool.py list
  python scripts/command_catalog_tool.py list --policy sensitive_live_change
  python scripts/command_catalog_tool.py show converge-gitea
  python scripts/command_catalog_tool.py policy converge-gitea
  python scripts/command_catalog_tool.py check --command converge-gitea --requester-class agent
  python scripts/command_catalog_tool.py policies
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMD_CATALOG = REPO_ROOT / "config" / "command-catalog.json"


def _load() -> dict:
    if not CMD_CATALOG.exists():
        print(f"ERROR: {CMD_CATALOG} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(CMD_CATALOG.read_text())


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    data = _load()
    commands = data.get("commands", {})
    policies = data.get("approval_policies", {})

    policy_filter = args.policy.lower() if args.policy else None
    scope_filter = args.scope.lower() if args.scope else None

    results = []
    for name, cmd in sorted(commands.items()):
        pol = cmd.get("approval_policy", "")
        scope = cmd.get("scope", "")
        if policy_filter and policy_filter not in pol.lower():
            continue
        if scope_filter and scope_filter not in scope.lower():
            continue
        results.append((name, pol, scope, cmd.get("description", "")))

    print(f"{'COMMAND':<45}  {'POLICY':<30}  {'SCOPE':<20}  DESCRIPTION")
    print("-" * 140)
    for name, pol, scope, desc in results:
        print(f"{name:<45}  {pol:<30}  {scope:<20}  {desc[:50]}")
    print(f"\n{len(results)} command(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    data = _load()
    commands = data.get("commands", {})
    # exact then partial
    name = args.name
    cmd = commands.get(name)
    if cmd is None:
        name_lower = name.lower()
        for k, v in commands.items():
            if name_lower in k.lower():
                cmd = v
                name = k
                break
    if cmd is None:
        print(f"ERROR: command '{args.name}' not found")
        return 1
    print(f"Command: {name}")
    print(json.dumps(cmd, indent=2))
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    data = _load()
    commands = data.get("commands", {})
    policies = data.get("approval_policies", {})
    cmd = commands.get(args.name)
    if cmd is None:
        name_lower = args.name.lower()
        for k, v in commands.items():
            if name_lower in k.lower():
                cmd = v
                break
    if cmd is None:
        print(f"ERROR: command '{args.name}' not found")
        return 1
    pol_name = cmd.get("approval_policy", "")
    pol = policies.get(pol_name)
    if pol is None:
        print(f"Policy '{pol_name}' not found in catalog")
        return 1
    print(f"Policy: {pol_name}")
    print(json.dumps(pol, indent=2))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    data = _load()
    commands = data.get("commands", {})
    policies = data.get("approval_policies", {})

    cmd = commands.get(args.command)
    if cmd is None:
        print(f"ERROR: command '{args.command}' not found")
        return 1

    pol_name = cmd.get("approval_policy", "")
    pol = policies.get(pol_name, {})
    requester_classes = pol.get("allowed_requester_classes", [])
    requester = args.requester_class

    can_submit = requester in requester_classes
    self_approve = pol.get("allow_self_approval", False)
    approver_classes = pol.get("allowed_approver_classes", [])
    can_self_approve = self_approve and requester in approver_classes

    print(f"Command          : {args.command}")
    print(f"Policy           : {pol_name}")
    print(f"Requester class  : {requester}")
    print(f"Allowed requesters: {', '.join(requester_classes)}")
    print()
    if can_submit:
        print("RESULT: ALLOWED — requester class can submit this command")
    else:
        print("RESULT: DENIED  — requester class is NOT in allowed_requester_classes")
    print(f"Self-approval    : {'yes' if can_self_approve else 'no'}")
    print(f"Require preflight: {pol.get('require_preflight', False)}")
    print(f"Require receipt  : {pol.get('require_receipt_plan', False)}")
    print(f"Break-glass ok   : {pol.get('allow_break_glass', False)}")
    return 0 if can_submit else 2


def cmd_policies(args: argparse.Namespace) -> int:
    data = _load()
    policies = data.get("approval_policies", {})
    print(f"{'POLICY NAME':<35}  DESCRIPTION")
    print("-" * 100)
    for name, pol in sorted(policies.items()):
        print(f"{name:<35}  {pol.get('description', '')[:65]}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="command_catalog_tool.py",
        description="Browse governed commands and verify approval policies.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    lp = sub.add_parser("list", help="List governed commands")
    lp.add_argument("--policy", metavar="POLICY", help="Filter by approval policy name")
    lp.add_argument("--scope", metavar="SCOPE", help="Filter by scope")

    shp = sub.add_parser("show", help="Show full command definition")
    shp.add_argument("name", help="Command name (partial match ok)")

    pp = sub.add_parser("policy", help="Show the approval policy for a command")
    pp.add_argument("name", help="Command name (partial match ok)")

    cp = sub.add_parser("check", help="Check if a requester class can submit a command")
    cp.add_argument("--command", required=True, metavar="CMD")
    cp.add_argument("--requester-class", required=True, metavar="CLS")

    sub.add_parser("policies", help="List all approval policy names")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "policy": cmd_policy,
        "check": cmd_check,
        "policies": cmd_policies,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
