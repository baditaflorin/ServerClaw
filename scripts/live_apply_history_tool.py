#!/usr/bin/env python3
"""live_apply_history_tool.py — Query and analyse live-apply receipts.

Data source: receipts/live-applies/

Commands
--------
  list   [--adr ADR] [--since DATE] [--limit N]   List live-apply receipts
  show   <receipt-id-or-file>                      Show full receipt content
  search <query>                                   Full-text search across receipts
  summary                                          Statistics overview
  failed                                          Show receipts with any failed verifications

Examples
--------
  python scripts/live_apply_history_tool.py list
  python scripts/live_apply_history_tool.py list --adr 0011
  python scripts/live_apply_history_tool.py list --since 2026-03-01
  python scripts/live_apply_history_tool.py show 2026-03-22-adr-0011-monitoring-live-apply
  python scripts/live_apply_history_tool.py search "gitea"
  python scripts/live_apply_history_tool.py summary
  python scripts/live_apply_history_tool.py failed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPLY_DIR = REPO_ROOT / "receipts" / "live-applies"


def _all_receipts() -> list[tuple[Path, dict]]:
    if not APPLY_DIR.exists():
        return []
    results: list[tuple[Path, dict]] = []
    for path in sorted(APPLY_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
            results.append((path, data))
        except (json.JSONDecodeError, OSError):
            results.append((path, {"_error": "parse error", "_file": path.name}))
    return results


def _verification_passed(receipt: dict) -> bool:
    for check in receipt.get("verification", []):
        if check.get("result", "pass") not in ("pass", "ok", "success"):
            return False
    return True


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> int:
    receipts = _all_receipts()
    adr_filter = args.adr
    since = args.since
    limit = args.limit

    results = []
    for path, data in receipts:
        if "_error" in data:
            continue
        if adr_filter and data.get("adr", "") != adr_filter.lstrip("0"):
            # Also try zero-padded match
            if data.get("adr", "") != adr_filter:
                continue
        applied = data.get("applied_on", data.get("recorded_on", ""))
        if since and applied < since:
            continue
        results.append((path, data))

    results = results[:limit]
    print(f"{'RECEIPT_ID':<60}  {'ADR':<6}  {'APPLIED':<12}  {'BY':<15}  WORKFLOW")
    print("-" * 120)
    for path, data in results:
        rid = data.get("receipt_id", path.stem)
        adr = data.get("adr", "?")
        applied = data.get("applied_on", data.get("recorded_on", "?"))
        by = data.get("recorded_by", "?")
        wf = data.get("workflow_id", "?")
        ok = "OK" if _verification_passed(data) else "FAIL"
        print(f"{rid:<60}  {adr:<6}  {applied:<12}  {by:<15}  {wf}  [{ok}]")
    print(f"\n{len(results)} receipt(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    receipts = _all_receipts()
    query = args.receipt_id.lower()
    match_data = None
    for path, data in receipts:
        if path.stem.lower() == query or query in path.stem.lower():
            match_data = data
            break
    if match_data is None:
        print(f"ERROR: no receipt matching '{args.receipt_id}'")
        return 1
    print(json.dumps(match_data, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = args.query.lower()
    receipts = _all_receipts()
    hits: list[tuple[Path, str]] = []
    for path, data in receipts:
        text = json.dumps(data).lower()
        if query in text:
            rid = data.get("receipt_id", path.stem)
            adr = data.get("adr", "?")
            wf = data.get("workflow_id", "?")
            hits.append((path, f"ADR={adr} workflow={wf}"))
    if not hits:
        print(f"No receipts matching '{args.query}'")
        return 0
    print(f"Receipts matching '{args.query}':\n")
    for path, info in hits:
        print(f"  {path.stem}  ({info})")
    print(f"\n{len(hits)} match(es)")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    receipts = _all_receipts()
    total = len(receipts)
    parse_errors = sum(1 for _, d in receipts if "_error" in d)
    valid = [(p, d) for p, d in receipts if "_error" not in d]
    passed = sum(1 for _, d in valid if _verification_passed(d))
    failed = len(valid) - passed

    adrs: set[str] = set()
    workflows: dict[str, int] = {}
    by_month: dict[str, int] = {}
    for _, d in valid:
        if d.get("adr"):
            adrs.add(d["adr"])
        wf = d.get("workflow_id", "unknown")
        workflows[wf] = workflows.get(wf, 0) + 1
        month = (d.get("applied_on") or d.get("recorded_on") or "?")[:7]
        by_month[month] = by_month.get(month, 0) + 1

    print(f"Live Apply History Summary\n")
    print(f"  Total receipts      : {total}")
    print(f"  Parse errors        : {parse_errors}")
    print(f"  Verification passed : {passed}")
    print(f"  Verification failed : {failed}")
    print(f"  Unique ADRs covered : {len(adrs)}")
    print(f"\n  Top 10 workflows:")
    for wf, cnt in sorted(workflows.items(), key=lambda x: -x[1])[:10]:
        print(f"    {wf:<50}  {cnt}")
    print(f"\n  By month:")
    for month, cnt in sorted(by_month.items(), reverse=True)[:12]:
        print(f"    {month}  {cnt}")
    return 0


def cmd_failed(args: argparse.Namespace) -> int:
    receipts = _all_receipts()
    failures = [
        (p, d) for p, d in receipts
        if "_error" not in d and not _verification_passed(d)
    ]
    if not failures:
        print("No receipts with failed verifications")
        return 0
    print(f"Receipts with failed verifications ({len(failures)}):\n")
    for path, data in failures:
        print(f"  {data.get('receipt_id', path.stem)}")
        for check in data.get("verification", []):
            result = check.get("result", "?")
            if result not in ("pass", "ok", "success"):
                print(f"    FAIL: {check.get('check','?')} — {check.get('observed','')[:80]}")
        print()
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="live_apply_history_tool.py",
        description="Query and analyse live-apply receipts.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    lp = sub.add_parser("list", help="List receipts with optional filters")
    lp.add_argument("--adr", metavar="ADR", help="Filter by ADR number (e.g. 0011)")
    lp.add_argument("--since", metavar="DATE", help="Only show receipts on or after DATE (YYYY-MM-DD)")
    lp.add_argument("--limit", type=int, default=50, metavar="N")

    shp = sub.add_parser("show", help="Show one receipt")
    shp.add_argument("receipt_id", metavar="RECEIPT_ID", help="Receipt file stem (partial match ok)")

    srp = sub.add_parser("search", help="Full-text search across receipts")
    srp.add_argument("query", help="Search term")

    sub.add_parser("summary", help="Statistics overview")
    sub.add_parser("failed", help="Show receipts with failed verifications")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "search": cmd_search,
        "summary": cmd_summary,
        "failed": cmd_failed,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
