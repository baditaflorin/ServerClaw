#!/usr/bin/env python3
"""runbook_tool.py — Search and render operational runbooks from docs/runbooks/.

Commands
--------
  list   [--topic TOPIC]                List all runbooks, optionally filtered by topic keyword
  search <query>                        Case-insensitive full-text search across runbook files
  show   <name>                         Print the full content of a runbook (name or partial match)
  topics                                List unique topic keywords inferred from runbook titles

Examples
--------
  python scripts/runbook_tool.py list
  python scripts/runbook_tool.py list --topic agent
  python scripts/runbook_tool.py search "break glass"
  python scripts/runbook_tool.py show break-glass
  python scripts/runbook_tool.py topics
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNBOOK_DIR = REPO_ROOT / "docs" / "runbooks"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _all_runbooks() -> list[Path]:
    if not RUNBOOK_DIR.exists():
        return []
    return sorted(RUNBOOK_DIR.glob("*.md"))


def _title_from_file(path: Path) -> str:
    """Return the first H1 heading or the stem as a fallback."""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return path.stem.replace("-", " ").title()


def _topic_words(stem: str) -> list[str]:
    """Split a filename stem into meaningful words, skipping short noise words."""
    stop = {"a", "and", "the", "of", "for", "in", "on", "to", "with", "via", "at"}
    return [w for w in re.split(r"[-_]", stem) if len(w) > 2 and w not in stop]


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    runbooks = _all_runbooks()
    topic = (args.topic or "").lower()
    results = []
    for rb in runbooks:
        if topic and topic not in rb.stem.lower():
            continue
        title = _title_from_file(rb)
        results.append((rb.stem, title))
    if not results:
        print("No runbooks found" + (f" matching topic '{args.topic}'" if topic else ""))
        return 0
    print(f"{'FILE':<55}  TITLE")
    print("-" * 90)
    for stem, title in results:
        print(f"{stem:<55}  {title}")
    print(f"\n{len(results)} runbook(s)")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = args.query.lower()
    runbooks = _all_runbooks()
    hits: list[tuple[Path, int, str]] = []  # path, line_no, line
    for rb in runbooks:
        try:
            lines = rb.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if query in line.lower():
                hits.append((rb, i, line.strip()))
    if not hits:
        print(f"No matches for '{args.query}'")
        return 0
    # Group by file
    current_file = None
    for path, lineno, line in hits:
        if path != current_file:
            print(f"\n=== {path.stem} ===")
            current_file = path
        print(f"  L{lineno:>4}: {line[:120]}")
    print(f"\n{len(hits)} match(es) across {len({h[0] for h in hits})} runbook(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    name = args.name.lower()
    runbooks = _all_runbooks()
    # Exact match first, then partial
    match: Path | None = None
    for rb in runbooks:
        if rb.stem.lower() == name:
            match = rb
            break
    if match is None:
        for rb in runbooks:
            if name in rb.stem.lower():
                match = rb
                break
    if match is None:
        print(f"No runbook matching '{args.name}'")
        print("Run 'python scripts/runbook_tool.py list' to see all available runbooks.")
        return 1
    print(f"# {match.stem}\n")
    print(match.read_text(encoding="utf-8", errors="replace"))
    return 0


def cmd_topics(args: argparse.Namespace) -> int:
    runbooks = _all_runbooks()
    freq: dict[str, int] = {}
    for rb in runbooks:
        for word in _topic_words(rb.stem):
            freq[word] = freq.get(word, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    print(f"{'TOPIC':<30}  COUNT")
    print("-" * 42)
    for word, count in ranked:
        print(f"{word:<30}  {count}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="runbook_tool.py",
        description="Search and render operational runbooks from docs/runbooks/.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    lp = sub.add_parser("list", help="List runbooks, optionally filtered by topic")
    lp.add_argument("--topic", metavar="TOPIC", help="Filter by keyword in filename")

    sp = sub.add_parser("search", help="Full-text search across all runbooks")
    sp.add_argument("query", help="Search query (case-insensitive)")

    shp = sub.add_parser("show", help="Print a runbook by name (partial match ok)")
    shp.add_argument("name", help="Runbook name or partial stem")

    sub.add_parser("topics", help="List topic keywords ranked by frequency")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "search": cmd_search,
        "show": cmd_show,
        "topics": cmd_topics,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
