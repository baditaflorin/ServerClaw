#!/usr/bin/env python3
"""slo_catalog_tool.py — Query SLO objectives and identify at-risk services.

Data source: config/slo-catalog.json

Commands
--------
  list                        List all SLOs with objective and window
  show  --id ID               Show full detail for one SLO
  at-risk [--threshold PCT]   SLOs with objective below threshold (default 99.5)
  by-service --service ID     SLOs for a specific service_id

Examples
--------
  python scripts/slo_catalog_tool.py list
  python scripts/slo_catalog_tool.py show --id gitea-availability
  python scripts/slo_catalog_tool.py at-risk
  python scripts/slo_catalog_tool.py at-risk --threshold 99.9
  python scripts/slo_catalog_tool.py by-service --service gitea
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SLO_CATALOG = REPO_ROOT / "config" / "slo-catalog.json"


def _load() -> list[dict]:
    if not SLO_CATALOG.exists():
        print(f"ERROR: {SLO_CATALOG} not found", file=sys.stderr)
        sys.exit(1)
    data = json.loads(SLO_CATALOG.read_text())
    return data.get("slos", [])


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    slos = _load()
    print(f"{'ID':<45}  {'SERVICE':<30}  {'OBJ%':>6}  {'WINDOW_DAYS':>11}  INDICATOR")
    print("-" * 110)
    for s in sorted(slos, key=lambda x: x["id"]):
        print(
            f"{s['id']:<45}  {s.get('service_id', ''):<30}  "
            f"{s.get('objective_percent', 0):>6.2f}  "
            f"{s.get('window_days', 30):>11}  {s.get('indicator', '')}"
        )
    print(f"\n{len(slos)} SLO(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    slos = _load()
    match = next((s for s in slos if s["id"] == args.id), None)
    if match is None:
        print(f"ERROR: SLO '{args.id}' not found")
        return 1
    print(json.dumps(match, indent=2))
    return 0


def cmd_at_risk(args: argparse.Namespace) -> int:
    slos = _load()
    threshold = args.threshold
    at_risk = [s for s in slos if s.get("objective_percent", 100) < threshold]
    if not at_risk:
        print(f"No SLOs below {threshold}% objective threshold")
        return 0
    print(f"SLOs below {threshold}% objective:\n")
    print(f"{'ID':<45}  {'SERVICE':<30}  {'OBJ%':>6}  DESCRIPTION")
    print("-" * 120)
    for s in sorted(at_risk, key=lambda x: x.get("objective_percent", 100)):
        desc = s.get("description", "")[:55]
        print(f"{s['id']:<45}  {s.get('service_id', ''):<30}  {s.get('objective_percent', 0):>6.2f}  {desc}")
    print(f"\n{len(at_risk)} SLO(s) at risk")
    return 0


def cmd_by_service(args: argparse.Namespace) -> int:
    slos = _load()
    service = args.service.lower()
    matches = [s for s in slos if service in s.get("service_id", "").lower()]
    if not matches:
        print(f"No SLOs found for service matching '{args.service}'")
        return 0
    for s in matches:
        print(json.dumps(s, indent=2))
        print()
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="slo_catalog_tool.py",
        description="Query SLO objectives from config/slo-catalog.json.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("list", help="List all SLOs")

    shp = sub.add_parser("show", help="Show one SLO by ID")
    shp.add_argument("--id", required=True, metavar="ID")

    arp = sub.add_parser("at-risk", help="Show SLOs below an objective threshold")
    arp.add_argument(
        "--threshold",
        type=float,
        default=99.5,
        metavar="PCT",
        help="Flag SLOs below this objective percentage (default 99.5)",
    )

    bsp = sub.add_parser("by-service", help="List SLOs for a service_id")
    bsp.add_argument("--service", required=True, metavar="ID")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "at-risk": cmd_at_risk,
        "by-service": cmd_by_service,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
