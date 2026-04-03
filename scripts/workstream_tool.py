#!/usr/bin/env python3
"""Workstream query tool for the proxmox_florin_server repo.

LLM guidance — use this tool when you need to:
  - Understand what work is currently in flight, blocked, or complete
  - Find which workstreams touch a given file or branch (conflict analysis)
  - Identify the next workstream ready to start (dependencies met, not in_progress)
  - Get blockers: workstreams that are stuck and why
  - Get a summary count of workstream states

Do NOT read workstreams.yaml manually when these commands cover your need.

Commands:
  list            List all workstreams (optional --status filter)
  show <id|adr>   Full detail on one workstream, including doc content
  blockers        Workstreams that are blocked or have unmet dependencies
  conflicts <arg> Workstreams sharing files with a given file path or branch
  next            Suggest the next workstream to pick up
  summary         Aggregate stats

Output: JSON to stdout.  Errors to stderr.  Exit 0=ok, 1=error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error
from platform.workstream_registry import load_workstreams

REPO_ROOT = Path(__file__).resolve().parents[1]

# Statuses considered "terminal" — dependencies on these are satisfied
SATISFIED_STATUSES = {"merged", "live_applied"}
IN_PROGRESS_STATUS = "in_progress"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_workstreams() -> list[dict[str, Any]]:
    return load_workstreams(repo_root=REPO_ROOT, include_archive=True)


def _ws_key(ws: dict[str, Any]) -> str:
    return str(ws.get("id", ""))


def _ws_adr(ws: dict[str, Any]) -> str:
    return str(ws.get("adr", ""))


def _ws_status(ws: dict[str, Any]) -> str:
    return str(ws.get("status", ""))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    workstreams = _load_workstreams()
    status_filter = getattr(args, "status", None)
    results = []
    for ws in workstreams:
        if status_filter and _ws_status(ws) != status_filter:
            continue
        results.append({
            "id": _ws_key(ws),
            "adr": _ws_adr(ws),
            "title": ws.get("title", ""),
            "status": _ws_status(ws),
            "ready_to_merge": ws.get("ready_to_merge", False),
            "live_applied": ws.get("live_applied", False),
            "owner": ws.get("owner", ""),
            "branch": ws.get("branch", ""),
        })
    print(json.dumps(results, indent=2))


def cmd_show(args: argparse.Namespace) -> None:
    workstreams = _load_workstreams()
    query = args.id_or_adr.strip()

    match = None
    for ws in workstreams:
        if _ws_key(ws) == query or _ws_adr(ws) == query:
            match = ws
            break

    if match is None:
        print(f"No workstream found for id/adr: {query!r}", file=sys.stderr)
        sys.exit(1)

    result: dict[str, Any] = dict(match)

    doc_path_raw = match.get("doc")
    if doc_path_raw:
        doc_path = Path(doc_path_raw)
        if doc_path.exists():
            result["doc_content"] = doc_path.read_text()
        else:
            result["doc_content"] = None
            result["doc_missing"] = True

    print(json.dumps(result, indent=2, default=str))


def cmd_blockers(args: argparse.Namespace) -> None:
    workstreams = _load_workstreams()

    # Build a lookup: id -> status, adr -> status (for dependency resolution)
    id_status: dict[str, str] = {}
    adr_status: dict[str, str] = {}
    for ws in workstreams:
        id_status[_ws_key(ws)] = _ws_status(ws)
        adr = _ws_adr(ws)
        if adr:
            # Store most-advanced status per ADR (live_applied > merged > …)
            priority = {"live_applied": 3, "merged": 2, "in_progress": 1, "planned": 0, "blocked": -1}
            existing = adr_status.get(adr)
            if existing is None or priority.get(_ws_status(ws), -1) > priority.get(existing, -1):
                adr_status[adr] = _ws_status(ws)

    def _dep_satisfied(dep: str) -> bool:
        # dep may look like "adr-0107-platform-extension-model" or "ws-0282-live-apply"
        # Try exact id match first
        if dep in id_status:
            return id_status[dep] in SATISFIED_STATUSES
        # Try extracting ADR number from dep string like "adr-0107-..."
        parts = dep.split("-")
        if parts and parts[0] == "adr" and len(parts) > 1:
            adr_num = parts[1]
            if adr_num in adr_status:
                return adr_status[adr_num] in SATISFIED_STATUSES
        return True  # Unknown dep — assume satisfied rather than crying wolf

    results = []
    for ws in workstreams:
        status = _ws_status(ws)
        ws_id = _ws_key(ws)
        blocked_by: list[str] = []

        # Explicitly blocked workstreams
        if status == "blocked":
            blocked_by.append("status=blocked")

        # Unsatisfied dependencies
        for dep in ws.get("depends_on") or []:
            if not _dep_satisfied(dep):
                blocked_by.append(dep)

        if blocked_by:
            suggestion = (
                "Resolve explicit block before proceeding."
                if "status=blocked" in blocked_by
                else f"Complete or verify these dependencies first: {', '.join(b for b in blocked_by if b != 'status=blocked')}"
            )
            results.append({
                "ws_id": ws_id,
                "title": ws.get("title", ""),
                "status": status,
                "blocked_by": blocked_by,
                "suggestion": suggestion,
            })

    print(json.dumps(results, indent=2))


def cmd_conflicts(args: argparse.Namespace) -> None:
    workstreams = _load_workstreams()
    query = args.branch_or_file.strip()

    # Determine if the query is a branch name or a file path
    # Branch: look for workstreams whose shared_surfaces overlap with the branch's own shared_surfaces
    # File: look for workstreams that list the file in shared_surfaces

    # First check if it matches a branch
    matching_ws = None
    for ws in workstreams:
        if ws.get("branch") == query or _ws_key(ws) == query:
            matching_ws = ws
            break

    results = []
    if matching_ws is not None:
        target_surfaces = set(matching_ws.get("shared_surfaces") or [])
        target_id = _ws_key(matching_ws)
        for ws in workstreams:
            if _ws_key(ws) == target_id:
                continue
            other_surfaces = set(ws.get("shared_surfaces") or [])
            shared = sorted(target_surfaces & other_surfaces)
            # Also check explicit conflicts_with
            explicit_conflict = (
                target_id in (ws.get("conflicts_with") or [])
                or _ws_key(ws) in (matching_ws.get("conflicts_with") or [])
            )
            if shared or explicit_conflict:
                results.append({
                    "ws_id": _ws_key(ws),
                    "title": ws.get("title", ""),
                    "status": _ws_status(ws),
                    "shared_files": shared,
                    "explicit_conflict": explicit_conflict,
                })
    else:
        # Treat query as a file path fragment
        for ws in workstreams:
            matched_surfaces = [
                s for s in (ws.get("shared_surfaces") or [])
                if query in s or s in query
            ]
            if matched_surfaces:
                results.append({
                    "ws_id": _ws_key(ws),
                    "title": ws.get("title", ""),
                    "status": _ws_status(ws),
                    "shared_files": matched_surfaces,
                    "explicit_conflict": False,
                })

    print(json.dumps(results, indent=2))


def cmd_next(args: argparse.Namespace) -> None:
    workstreams = _load_workstreams()

    id_status: dict[str, str] = {}
    adr_status: dict[str, str] = {}
    for ws in workstreams:
        id_status[_ws_key(ws)] = _ws_status(ws)
        adr = _ws_adr(ws)
        if adr:
            priority = {"live_applied": 3, "merged": 2, "in_progress": 1, "planned": 0, "blocked": -1}
            existing = adr_status.get(adr)
            if existing is None or priority.get(_ws_status(ws), -1) > priority.get(existing, -1):
                adr_status[adr] = _ws_status(ws)

    def _dep_satisfied(dep: str) -> bool:
        if dep in id_status:
            return id_status[dep] in {"merged", "live_applied"}
        parts = dep.split("-")
        if parts and parts[0] == "adr" and len(parts) > 1:
            adr_num = parts[1]
            if adr_num in adr_status:
                return adr_status[adr_num] in {"merged", "live_applied"}
        return True

    candidates = []
    for ws in workstreams:
        status = _ws_status(ws)
        if status in {"merged", "live_applied", "in_progress", "blocked"}:
            continue
        deps = ws.get("depends_on") or []
        unmet = [d for d in deps if not _dep_satisfied(d)]
        if not unmet:
            candidates.append({
                "ws_id": _ws_key(ws),
                "title": ws.get("title", ""),
                "adr": _ws_adr(ws),
                "status": status,
                "reason": "All dependencies satisfied; not yet started.",
            })

    print(json.dumps(candidates, indent=2))


def cmd_summary(args: argparse.Namespace) -> None:
    workstreams = _load_workstreams()
    by_status: dict[str, int] = {}
    ready_to_merge_count = 0
    live_applied_count = 0
    in_progress_count = 0

    for ws in workstreams:
        status = _ws_status(ws)
        by_status[status] = by_status.get(status, 0) + 1
        if ws.get("ready_to_merge"):
            ready_to_merge_count += 1
        if ws.get("live_applied"):
            live_applied_count += 1
        if status == IN_PROGRESS_STATUS:
            in_progress_count += 1

    result = {
        "total": len(workstreams),
        "by_status": by_status,
        "ready_to_merge_count": ready_to_merge_count,
        "live_applied_count": live_applied_count,
        "in_progress_count": in_progress_count,
    }
    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Query the shard-backed workstream registry before manual YAML reads.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List all workstreams")
    p_list.add_argument(
        "--status",
        choices=["in_progress", "merged", "live_applied", "blocked", "planned"],
        help="Filter by status",
    )

    # show
    p_show = sub.add_parser("show", help="Full detail on one workstream")
    p_show.add_argument("id_or_adr", help="Workstream id (ws-XXXX-*) or ADR number (e.g. 0286)")

    # blockers
    sub.add_parser("blockers", help="Show blocked workstreams and unmet dependencies")

    # conflicts
    p_conflicts = sub.add_parser("conflicts", help="Find workstreams sharing files with a branch or file")
    p_conflicts.add_argument("branch_or_file", help="Branch name (codex/ws-*) or file path fragment")

    # next
    sub.add_parser("next", help="Suggest next workstream to start (deps met, not in_progress)")

    # summary
    sub.add_parser("summary", help="Aggregate stats across all workstreams")

    args = parser.parse_args(argv)
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "blockers": cmd_blockers,
        "conflicts": cmd_conflicts,
        "next": cmd_next,
        "summary": cmd_summary,
    }
    try:
        dispatch[args.command](args)
        return 0
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        return emit_cli_error("workstream tool", exc)


if __name__ == "__main__":
    raise SystemExit(main())
