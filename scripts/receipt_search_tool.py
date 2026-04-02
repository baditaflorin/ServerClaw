#!/usr/bin/env python3
"""Receipt search and browse tool for the proxmox_florin_server repo.

USE THIS TOOL when you need to find, browse, or inspect operation receipts.
Do not manually walk the receipts/ directory — use this tool instead.

Receipts live under receipts/ across 15+ subdirectories:
  agent-coordination, dr-table-top-reviews, drift-reports, fixtures,
  gate-bypasses, image-scans, live-applies, preview-environments,
  promotions, restore-verifications, security-incidents, security-reports,
  security-scan, subdomain-exposure-audit, token-lifecycle,
  witness-replication

Files are .json or .md. JSON receipts typically carry fields like:
  adr, status, timestamp, applied_on, vmid, summary, receipt_id, etc.

COMMANDS
--------
list    List receipts, optionally filtered by type and/or date.
search  Full-text search across receipt filenames and content.
show    Display one receipt by exact path or partial stem match.
summary Aggregate stats (total, by_type, date_range).

EXAMPLES
--------
  python3 scripts/receipt_search_tool.py list
  python3 scripts/receipt_search_tool.py list --type live-applies --since 2026-03-01 --limit 20
  python3 scripts/receipt_search_tool.py search "postgres failover"
  python3 scripts/receipt_search_tool.py search "adr-0188" --type live-applies --limit 5
  python3 scripts/receipt_search_tool.py show 2026-03-27-adr-0188-postgres-rehearsal-evidence
  python3 scripts/receipt_search_tool.py show receipts/live-applies/2026-03-22-adr-0011-monitoring-live-apply.json
  python3 scripts/receipt_search_tool.py summary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIPTS_ROOT = REPO_ROOT / "receipts"

# Files or extensions to skip entirely
_SKIP_EXTENSIONS = {".html"}
_SKIP_NAMES = {".DS_Store"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iter_receipts(type_filter: str | None = None):
    """Yield (path, receipt_type) for every receipt file under RECEIPTS_ROOT."""
    if not RECEIPTS_ROOT.exists():
        return
    for child in sorted(RECEIPTS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        receipt_type = child.name
        if type_filter and receipt_type != type_filter:
            continue
        for fp in sorted(child.rglob("*")):
            if not fp.is_file():
                continue
            if fp.name in _SKIP_NAMES:
                continue
            if fp.suffix in _SKIP_EXTENSIONS:
                continue
            yield fp, receipt_type


def _file_meta(fp: Path, receipt_type: str) -> dict:
    stat = fp.stat()
    return {
        "path": str(fp.relative_to(REPO_ROOT)),
        "type": receipt_type,
        "name": fp.stem,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "size_bytes": stat.st_size,
    }


def _read_text(fp: Path) -> str:
    try:
        return fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse_date_from_name(stem: str) -> str | None:
    """Try to extract a YYYY-MM-DD date from the start of a filename stem."""
    if len(stem) >= 10 and stem[4] == "-" and stem[7] == "-":
        try:
            datetime.strptime(stem[:10], "%Y-%m-%d")
            return stem[:10]
        except ValueError:
            pass
    return None


def _snippet(text: str, query: str, max_len: int = 200) -> str:
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx == -1:
        return text[:max_len]
    start = max(0, idx - 60)
    end = min(len(text), idx + len(query) + 140)
    fragment = text[start:end]
    if start > 0:
        fragment = "..." + fragment
    if end < len(text):
        fragment = fragment + "..."
    return fragment


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def command_list(args) -> int:
    since: str | None = args.since
    limit: int | None = args.limit
    type_filter: str | None = args.type

    results = []
    for fp, receipt_type in _iter_receipts(type_filter):
        meta = _file_meta(fp, receipt_type)
        if since:
            date_str = _parse_date_from_name(fp.stem)
            mtime_date = meta["mtime"][:10]
            effective_date = date_str or mtime_date
            if effective_date < since:
                continue
        results.append(meta)

    results.sort(key=lambda m: m["mtime"], reverse=True)
    if limit:
        results = results[:limit]

    if not results:
        print(json.dumps([]))
        return 2

    print(json.dumps(results, indent=2))
    return 0


def command_search(args) -> int:
    query: str = args.query
    type_filter: str | None = args.type
    limit: int = args.limit
    query_lower = query.lower()

    scored = []
    for fp, receipt_type in _iter_receipts(type_filter):
        name_lower = fp.stem.lower()
        name_hits = name_lower.count(query_lower)

        content = _read_text(fp)
        content_hits = content.lower().count(query_lower)

        total_hits = name_hits * 3 + content_hits  # weight filename matches
        if total_hits == 0:
            continue

        snippet = _snippet(content, query) if content_hits else fp.stem
        scored.append({
            "path": str(fp.relative_to(REPO_ROOT)),
            "type": receipt_type,
            "snippet": snippet,
            "score": total_hits,
        })

    scored.sort(key=lambda r: r["score"], reverse=True)
    scored = scored[:limit]

    if not scored:
        print(json.dumps([]))
        return 2

    print(json.dumps(scored, indent=2))
    return 0


def command_show(args) -> int:
    target: str = args.path_or_name

    # 1. Try as an absolute or relative path first.
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / target
    if candidate.exists() and candidate.is_file():
        return _emit_receipt(candidate)

    # 2. Walk all receipts looking for a stem match.
    for fp, _receipt_type in _iter_receipts():
        if target in fp.stem or target == fp.name:
            return _emit_receipt(fp)

    print(
        json.dumps({"error": f"No receipt found matching: {target}", "type": "FileNotFoundError"}),
        file=sys.stderr,
    )
    return 1


def _emit_receipt(fp: Path) -> int:
    raw = _read_text(fp)
    if fp.suffix == ".json":
        try:
            parsed = json.loads(raw)
            print(json.dumps(parsed, indent=2))
            return 0
        except json.JSONDecodeError:
            pass
    # Markdown or malformed JSON — wrap in a text envelope
    print(json.dumps({"path": str(fp.relative_to(REPO_ROOT)), "content": raw}, indent=2))
    return 0


def command_summary(args) -> int:  # noqa: ARG001
    by_type: dict[str, int] = {}
    dates: list[str] = []

    for fp, receipt_type in _iter_receipts():
        by_type[receipt_type] = by_type.get(receipt_type, 0) + 1
        date_str = _parse_date_from_name(fp.stem)
        if date_str:
            dates.append(date_str)
        else:
            stat = fp.stat()
            mtime_date = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
            dates.append(mtime_date)

    total = sum(by_type.values())
    date_range = {}
    if dates:
        dates_sorted = sorted(dates)
        date_range = {"earliest": dates_sorted[0], "latest": dates_sorted[-1]}

    result = {
        "total": total,
        "by_type": dict(sorted(by_type.items())),
        "date_range": date_range,
    }
    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search and browse operation receipts in the proxmox_florin_server repo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List receipts with optional filters.")
    p_list.add_argument("--type", help="Receipt subdirectory type, e.g. live-applies, gate-bypasses.")
    p_list.add_argument("--since", help="Only include receipts on or after this date (YYYY-MM-DD).")
    p_list.add_argument("--limit", type=int, help="Maximum number of results to return.")
    p_list.set_defaults(func=command_list)

    # search
    p_search = subparsers.add_parser("search", help="Full-text search across receipt filenames and content.")
    p_search.add_argument("query", help="Search query string (case-insensitive substring match).")
    p_search.add_argument("--type", help="Restrict search to one receipt type subdirectory.")
    p_search.add_argument("--limit", type=int, default=10, help="Maximum number of results (default: 10).")
    p_search.set_defaults(func=command_search)

    # show
    p_show = subparsers.add_parser("show", help="Display one receipt by path or partial name match.")
    p_show.add_argument("path_or_name", help="Exact relative path, full filename, or partial stem to match.")
    p_show.set_defaults(func=command_show)

    # summary
    p_summary = subparsers.add_parser("summary", help="Aggregate stats across all receipts.")
    p_summary.set_defaults(func=command_summary)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
