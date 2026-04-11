#!/usr/bin/env python3
"""api_gateway_tool.py — Browse the platform API gateway catalog.

Data source: config/api-gateway-catalog.json

Commands
--------
  list   [--auth AUTH]          List all gateway service entries
  show   --id ID                Show full entry for one service
  auth-required                 List services grouped by auth mechanism
  upstream --service ID         Show the upstream URL and healthcheck path
  summary                       Overview of gateway coverage

Examples
--------
  python scripts/api_gateway_tool.py list
  python scripts/api_gateway_tool.py list --auth keycloak_jwt
  python scripts/api_gateway_tool.py show --id gitea
  python scripts/api_gateway_tool.py auth-required
  python scripts/api_gateway_tool.py upstream --service grafana
  python scripts/api_gateway_tool.py summary
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GW_CATALOG = REPO_ROOT / "config" / "api-gateway-catalog.json"


def _load() -> list[dict]:
    if not GW_CATALOG.exists():
        print(f"ERROR: {GW_CATALOG} not found", file=sys.stderr)
        sys.exit(1)
    data = json.loads(GW_CATALOG.read_text())
    return data.get("services", [])


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    services = _load()
    auth_filter = (args.auth or "").lower()
    results = [s for s in services if not auth_filter or auth_filter in s.get("auth", "").lower()]
    print(f"{'ID':<20}  {'GATEWAY_PREFIX':<25}  {'AUTH':<20}  {'ROLE':<25}  {'TIMEOUT_S':>9}")
    print("-" * 105)
    for s in sorted(results, key=lambda x: x["id"]):
        print(
            f"{s['id']:<20}  {s.get('gateway_prefix', ''):<25}  "
            f"{s.get('auth', ''):<20}  {s.get('required_role', ''):<25}  "
            f"{s.get('timeout_seconds', '?'):>9}"
        )
    print(f"\n{len(results)} service(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    services = _load()
    match = next((s for s in services if s["id"] == args.id), None)
    if match is None:
        id_lower = args.id.lower()
        match = next((s for s in services if id_lower in s["id"].lower()), None)
    if match is None:
        print(f"ERROR: service '{args.id}' not found in API gateway catalog")
        return 1
    print(json.dumps(match, indent=2))
    return 0


def cmd_auth_required(args: argparse.Namespace) -> int:
    services = _load()
    groups: dict[str, list[str]] = defaultdict(list)
    for s in services:
        groups[s.get("auth", "none")].append(s["id"])
    for auth, ids in sorted(groups.items()):
        print(f"\n[{auth}]")
        for sid in sorted(ids):
            print(f"  {sid}")
    return 0


def cmd_upstream(args: argparse.Namespace) -> int:
    services = _load()
    svc = args.service.lower()
    match = next((s for s in services if s["id"].lower() == svc), None)
    if match is None:
        match = next((s for s in services if svc in s["id"].lower()), None)
    if match is None:
        print(f"ERROR: service '{args.service}' not found")
        return 1
    print(f"Service        : {match['id']}")
    print(f"Upstream       : {match.get('upstream', 'N/A')}")
    print(f"Gateway prefix : {match.get('gateway_prefix', 'N/A')}")
    print(f"Healthcheck    : {match.get('upstream', '')}{match.get('healthcheck_path', '')}")
    print(f"Auth           : {match.get('auth', 'N/A')}")
    print(f"Required role  : {match.get('required_role', 'N/A')}")
    print(f"Timeout (s)    : {match.get('timeout_seconds', 'N/A')}")
    strip = match.get("strip_prefix", False)
    print(f"Strip prefix   : {strip}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    services = _load()
    auth_counts: dict[str, int] = defaultdict(int)
    for s in services:
        auth_counts[s.get("auth", "none")] += 1
    print("API Gateway Catalog Summary\n")
    print(f"  Total services : {len(services)}")
    print("\n  Auth mechanisms:")
    for auth, cnt in sorted(auth_counts.items(), key=lambda x: -x[1]):
        print(f"    {auth:<30}  {cnt}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="api_gateway_tool.py",
        description="Browse the platform API gateway catalog.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    lp = sub.add_parser("list", help="List gateway service entries")
    lp.add_argument("--auth", metavar="AUTH", help="Filter by auth mechanism")

    shp = sub.add_parser("show", help="Show one service entry")
    shp.add_argument("--id", required=True, metavar="ID")

    sub.add_parser("auth-required", help="Group services by auth mechanism")

    up = sub.add_parser("upstream", help="Show upstream URL for a service")
    up.add_argument("--service", required=True, metavar="ID")

    sub.add_parser("summary", help="Overview of gateway coverage")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "auth-required": cmd_auth_required,
        "upstream": cmd_upstream,
        "summary": cmd_summary,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
