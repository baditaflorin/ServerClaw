#!/usr/bin/env python3
"""secret_rotation_tool.py — Track secret rotation status from config/secret-catalog.json.

Commands
--------
  list                          List all secrets with rotation status
  show   --id ID                Show full detail for one secret
  overdue                       List secrets past their rotation deadline (today > last_rotated + period)
  due-soon [--days N]           List secrets due within N days (default 14)
  summary                       Show rotation health overview

Today's date is used as the reference for all calculations.

Examples
--------
  python scripts/secret_rotation_tool.py list
  python scripts/secret_rotation_tool.py overdue
  python scripts/secret_rotation_tool.py due-soon --days 30
  python scripts/secret_rotation_tool.py show --id gitea_admin_password
  python scripts/secret_rotation_tool.py summary
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRET_CATALOG = REPO_ROOT / "config" / "secret-catalog.json"


def _load() -> list[dict]:
    if not SECRET_CATALOG.exists():
        print(f"ERROR: {SECRET_CATALOG} not found", file=sys.stderr)
        sys.exit(1)
    data = json.loads(SECRET_CATALOG.read_text())
    return data.get("secrets", [])


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _days_until_due(secret: dict, today: date) -> int | None:
    """Days until rotation is due. Negative means overdue."""
    last = _parse_date(secret.get("last_rotated_at", ""))
    period = secret.get("rotation_period_days")
    if last is None or period is None:
        return None
    due = last + timedelta(days=period)
    return (due - today).days


def _status(days: int | None, warning_window: int) -> str:
    if days is None:
        return "UNKNOWN"
    if days < 0:
        return "OVERDUE"
    if days <= warning_window:
        return "DUE-SOON"
    return "OK"


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    secrets = _load()
    today = date.today()
    print(f"{'ID':<45}  {'SERVICE':<25}  {'STATUS':<10}  {'DAYS_LEFT':>9}  MODE")
    print("-" * 115)
    for s in sorted(secrets, key=lambda x: x["id"]):
        days = _days_until_due(s, today)
        warn = s.get("warning_window_days", 14)
        status = _status(days, warn)
        days_str = str(days) if days is not None else "?"
        print(
            f"{s['id']:<45}  {s.get('owner_service', ''):<25}  "
            f"{status:<10}  {days_str:>9}  {s.get('rotation_mode', '')}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    secrets = _load()
    today = date.today()
    match = next((s for s in secrets if s["id"] == args.id), None)
    if match is None:
        id_lower = args.id.lower()
        match = next((s for s in secrets if id_lower in s["id"].lower()), None)
    if match is None:
        print(f"ERROR: secret '{args.id}' not found")
        return 1
    days = _days_until_due(match, today)
    warn = match.get("warning_window_days", 14)
    status = _status(days, warn)
    print(json.dumps(match, indent=2))
    print(f"\nStatus today ({today}): {status}" + (f"  ({days} days remaining)" if days is not None else ""))
    return 0


def cmd_overdue(args: argparse.Namespace) -> int:
    secrets = _load()
    today = date.today()
    overdue = [s for s in secrets if (_days_until_due(s, today) or 0) < 0 and _days_until_due(s, today) is not None]
    if not overdue:
        print("No secrets are overdue")
        return 0
    print(f"OVERDUE secrets (reference date: {today}):\n")
    print(f"{'ID':<45}  {'SERVICE':<25}  {'DAYS_OVERDUE':>12}  {'LAST_ROTATED':<15}  MODE")
    print("-" * 115)
    for s in sorted(overdue, key=lambda x: _days_until_due(x, today) or 0):
        days = _days_until_due(s, today)
        print(
            f"{s['id']:<45}  {s.get('owner_service', ''):<25}  "
            f"{abs(days):>12}  {s.get('last_rotated_at', '?'):<15}  {s.get('rotation_mode', '')}"
        )
    print(f"\n{len(overdue)} overdue secret(s)")
    return 1 if overdue else 0


def cmd_due_soon(args: argparse.Namespace) -> int:
    secrets = _load()
    today = date.today()
    window = args.days
    due = [
        s
        for s in secrets
        if _days_until_due(s, today) is not None and 0 <= (_days_until_due(s, today) or 999) <= window
    ]
    if not due:
        print(f"No secrets due within {window} days")
        return 0
    print(f"Secrets due within {window} days (reference: {today}):\n")
    print(f"{'ID':<45}  {'SERVICE':<25}  {'DAYS_LEFT':>9}  {'LAST_ROTATED':<15}  MODE")
    print("-" * 115)
    for s in sorted(due, key=lambda x: _days_until_due(x, today) or 0):
        days = _days_until_due(s, today)
        print(
            f"{s['id']:<45}  {s.get('owner_service', ''):<25}  "
            f"{days:>9}  {s.get('last_rotated_at', '?'):<15}  {s.get('rotation_mode', '')}"
        )
    print(f"\n{len(due)} secret(s) due soon")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    secrets = _load()
    today = date.today()
    counts = {"OK": 0, "DUE-SOON": 0, "OVERDUE": 0, "UNKNOWN": 0}
    for s in secrets:
        days = _days_until_due(s, today)
        warn = s.get("warning_window_days", 14)
        status = _status(days, warn)
        counts[status] = counts.get(status, 0) + 1
    total = len(secrets)
    print(f"Secret rotation summary (reference date: {today})\n")
    print(f"  Total secrets   : {total}")
    print(f"  OK              : {counts['OK']}")
    print(f"  Due soon        : {counts['DUE-SOON']}")
    print(f"  Overdue         : {counts['OVERDUE']}")
    print(f"  Unknown         : {counts['UNKNOWN']}")
    health = (
        "HEALTHY"
        if counts["OVERDUE"] == 0 and counts["DUE-SOON"] == 0
        else ("DEGRADED" if counts["OVERDUE"] == 0 else "CRITICAL")
    )
    print(f"\n  Overall health  : {health}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="secret_rotation_tool.py",
        description="Track secret rotation status from config/secret-catalog.json.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("list", help="List all secrets with rotation status")

    shp = sub.add_parser("show", help="Show detail for one secret")
    shp.add_argument("--id", required=True, metavar="ID")

    sub.add_parser("overdue", help="List overdue secrets")

    dsp = sub.add_parser("due-soon", help="List secrets due within N days")
    dsp.add_argument("--days", type=int, default=14, metavar="N", help="Lookahead window in days (default 14)")

    sub.add_parser("summary", help="Rotation health overview")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "overdue": cmd_overdue,
        "due-soon": cmd_due_soon,
        "summary": cmd_summary,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
