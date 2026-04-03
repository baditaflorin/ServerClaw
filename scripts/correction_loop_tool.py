#!/usr/bin/env python3
"""correction_loop_tool.py — Query self-healing correction loops from config/correction-loops.json.

Commands
--------
  list                        List all correction loops
  show  <id>                  Show full loop definition
  applicable --workflow ID    Find loops that apply to a workflow ID
  repair-actions <id>         List repair actions for a loop, annotated with risk level

Examples
--------
  python scripts/correction_loop_tool.py list
  python scripts/correction_loop_tool.py show ansible_reconcile
  python scripts/correction_loop_tool.py applicable --workflow converge-gitea
  python scripts/correction_loop_tool.py repair-actions ansible_reconcile
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOPS_FILE = REPO_ROOT / "config" / "correction-loops.json"


def _load() -> dict:
    if not LOOPS_FILE.exists():
        print(f"ERROR: {LOOPS_FILE} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(LOOPS_FILE.read_text())


def _loop_applies(loop: dict, workflow_id: str) -> bool:
    at = loop.get("applies_to", {})
    # Check explicit workflow IDs
    if workflow_id in at.get("workflow_ids", []):
        return True
    # Check prefix matches
    for prefix in at.get("workflow_id_prefixes", []):
        if workflow_id.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    data = _load()
    loops = data.get("loops", [])
    required = data.get("required_workflow_ids", [])
    print(f"Required workflow IDs: {', '.join(required)}\n")
    print(f"{'ID':<30}  {'INVARIANT (truncated)':60}")
    print("-" * 100)
    for loop in loops:
        inv = loop.get("invariant", "")[:60]
        print(f"{loop['id']:<30}  {inv}")
    print(f"\n{len(loops)} loop(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    data = _load()
    loops = data.get("loops", [])
    match = next((l for l in loops if l["id"] == args.id), None)
    if match is None:
        id_lower = args.id.lower()
        match = next((l for l in loops if id_lower in l["id"].lower()), None)
    if match is None:
        print(f"ERROR: loop '{args.id}' not found")
        return 1
    print(json.dumps(match, indent=2))
    return 0


def cmd_applicable(args: argparse.Namespace) -> int:
    data = _load()
    loops = data.get("loops", [])
    wf = args.workflow
    matches = [l for l in loops if _loop_applies(l, wf)]
    if not matches:
        print(f"No correction loops apply to workflow '{wf}'")
        return 0
    print(f"Correction loops applicable to '{wf}':\n")
    for loop in matches:
        print(f"  [{loop['id']}]")
        print(f"  Invariant: {loop.get('invariant','')}")
        actions = loop.get("repair_actions", [])
        print(f"  Repair actions ({len(actions)}): " +
              ", ".join(a["kind"] for a in actions))
        print()
    return 0


def cmd_repair_actions(args: argparse.Namespace) -> int:
    data = _load()
    loops = data.get("loops", [])
    match = next((l for l in loops if l["id"] == args.id), None)
    if match is None:
        id_lower = args.id.lower()
        match = next((l for l in loops if id_lower in l["id"].lower()), None)
    if match is None:
        print(f"ERROR: loop '{args.id}' not found")
        return 1
    actions = match.get("repair_actions", [])
    print(f"Repair actions for loop '{match['id']}':\n")
    print(f"{'KIND':<20}  {'APPROVAL?':<10}  {'DESTRUCTIVE?':<13}  SUMMARY")
    print("-" * 100)
    for a in actions:
        approval = "yes" if a.get("requires_approval") else "no"
        destructive = "yes" if a.get("destructive") else "no"
        summary = a.get("summary", "")[:65]
        print(f"{a['kind']:<20}  {approval:<10}  {destructive:<13}  {summary}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="correction_loop_tool.py",
        description="Query self-healing correction loops.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("list", help="List all correction loops")

    shp = sub.add_parser("show", help="Show full loop definition")
    shp.add_argument("id", help="Loop ID (partial match ok)")

    app = sub.add_parser("applicable", help="Find loops applicable to a workflow")
    app.add_argument("--workflow", required=True, metavar="ID", help="Workflow ID")

    rap = sub.add_parser("repair-actions", help="List repair actions for a loop")
    rap.add_argument("id", help="Loop ID (partial match ok)")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "applicable": cmd_applicable,
        "repair-actions": cmd_repair_actions,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
