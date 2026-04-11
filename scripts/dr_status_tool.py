#!/usr/bin/env python3
"""dr_status_tool.py — Disaster-recovery status, RTO/RPO targets, and restore history.

Data sources:
  config/disaster-recovery-targets.json
  receipts/restore-verifications/

Commands
--------
  report                    Full DR status report (targets + restore history)
  scenarios                 List all DR scenarios with RTO/RPO
  show   --scenario ID      Show detail for one scenario
  restore-history           List all restore verification receipts
  rto-check                 Flag scenarios whose RTO exceeds the platform target

Examples
--------
  python scripts/dr_status_tool.py report
  python scripts/dr_status_tool.py scenarios
  python scripts/dr_status_tool.py show --scenario single_service_failure
  python scripts/dr_status_tool.py restore-history
  python scripts/dr_status_tool.py rto-check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DR_TARGETS = REPO_ROOT / "config" / "disaster-recovery-targets.json"
RESTORE_DIR = REPO_ROOT / "receipts" / "restore-verifications"


def _load_targets() -> dict:
    if not DR_TARGETS.exists():
        print(f"ERROR: {DR_TARGETS} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(DR_TARGETS.read_text())


def _restore_receipts() -> list[dict]:
    receipts: list[dict] = []
    if not RESTORE_DIR.exists():
        return receipts
    for path in sorted(RESTORE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            data["_file"] = path.name
            receipts.append(data)
        except (json.JSONDecodeError, OSError):
            receipts.append({"_file": path.name, "_error": "parse error"})
    return receipts


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> int:
    data = _load_targets()
    platform = data.get("platform_target", {})
    review = data.get("review_policy", {})
    scenarios = data.get("scenarios", [])
    offsite = data.get("offsite_backup", {})
    receipts = _restore_receipts()

    print("=" * 70)
    print("DISASTER RECOVERY STATUS REPORT")
    print("=" * 70)
    print(f"\nPlatform RTO: {platform.get('rto_minutes', '?')} minutes")
    print(f"Platform RPO: {platform.get('rpo_hours', '?')} hours")
    print(f"Table-top review interval: {review.get('table_top_interval_days', '?')} days")
    print(f"Live drill interval      : {review.get('live_drill_interval_days', '?')} days")
    print(f"\nOffsite backup strategy: {offsite.get('strategy', 'N/A')}")
    print(f"Offsite target VMIDs   : {offsite.get('target_vmids', [])}")
    print(f"Offsite schedule (UTC) : {offsite.get('schedule_utc', 'N/A')}")

    print(f"\nDR Scenarios ({len(scenarios)}):")
    print(f"  {'ID':<35}  {'RTO':>8}  {'RPO':>8}")
    print("  " + "-" * 60)
    for sc in scenarios:
        rto = f"{sc.get('rto_minutes', '?')}m"
        rpo_h = sc.get("rpo_hours")
        rpo_m = sc.get("rpo_minutes")
        rpo = f"{rpo_h}h" if rpo_h is not None else (f"{rpo_m}m" if rpo_m is not None else "?")
        print(f"  {sc['id']:<35}  {rto:>8}  {rpo:>8}")

    print(f"\nRestore Verification Receipts ({len(receipts)}):")
    if receipts:
        for r in receipts:
            if "_error" in r:
                print(f"  {r['_file']} [PARSE ERROR]")
            else:
                result = r.get("result", r.get("outcome", r.get("status", "?")))
                print(f"  {r['_file']:<55}  result={result}")
    else:
        print("  No restore verification receipts found")
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    data = _load_targets()
    scenarios = data.get("scenarios", [])
    print(f"{'ID':<40}  {'RTO':>8}  {'RPO':>8}  NOTES")
    print("-" * 100)
    for sc in scenarios:
        rto = f"{sc.get('rto_minutes', '?')}m"
        rpo_h = sc.get("rpo_hours")
        rpo_m = sc.get("rpo_minutes")
        rpo = f"{rpo_h}h" if rpo_h is not None else (f"{rpo_m}m" if rpo_m is not None else "?")
        notes = sc.get("notes", "")[:55]
        print(f"{sc['id']:<40}  {rto:>8}  {rpo:>8}  {notes}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    data = _load_targets()
    scenarios = data.get("scenarios", [])
    match = next((s for s in scenarios if s["id"] == args.scenario), None)
    if match is None:
        slug_lower = args.scenario.lower()
        match = next((s for s in scenarios if slug_lower in s["id"].lower()), None)
    if match is None:
        print(f"ERROR: scenario '{args.scenario}' not found")
        return 1
    print(json.dumps(match, indent=2))
    return 0


def cmd_restore_history(args: argparse.Namespace) -> int:
    receipts = _restore_receipts()
    if not receipts:
        print("No restore verification receipts found")
        return 0
    print(f"Restore verification receipts ({len(receipts)}):\n")
    for r in receipts:
        print(f"  File: {r['_file']}")
        if "_error" in r:
            print("    [parse error]")
        else:
            for key in ("result", "outcome", "status", "vmid", "target_vmid", "snapshot", "verified_at", "notes"):
                if key in r:
                    print(f"    {key}: {r[key]}")
        print()
    return 0


def cmd_rto_check(args: argparse.Namespace) -> int:
    data = _load_targets()
    platform = data.get("platform_target", {})
    platform_rto = platform.get("rto_minutes", 240)
    scenarios = data.get("scenarios", [])
    breaches = [s for s in scenarios if s.get("rto_minutes") is not None and s["rto_minutes"] > platform_rto]
    if not breaches:
        print(f"All scenarios within platform RTO of {platform_rto} minutes")
        return 0
    print(f"Scenarios breaching platform RTO ({platform_rto}m):\n")
    for s in breaches:
        print(f"  {s['id']} — RTO={s['rto_minutes']}m  (target: {platform_rto}m)")
        if s.get("notes"):
            print(f"    {s['notes']}")
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dr_status_tool.py",
        description="Disaster-recovery status, RTO/RPO targets, and restore history.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("report", help="Full DR status report")
    sub.add_parser("scenarios", help="List DR scenarios with RTO/RPO")

    shp = sub.add_parser("show", help="Show one scenario")
    shp.add_argument("--scenario", required=True, metavar="ID")

    sub.add_parser("restore-history", help="List restore verification receipts")
    sub.add_parser("rto-check", help="Flag scenarios exceeding platform RTO")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "report": cmd_report,
        "scenarios": cmd_scenarios,
        "show": cmd_show,
        "restore-history": cmd_restore_history,
        "rto-check": cmd_rto_check,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
