#!/usr/bin/env python3
"""validation_gate_tool.py — Inspect and dry-run the repository validation gate.

Data sources:
  config/validation-gate.json        (overall gate config)
  config/check-runner-manifest.json  (individual check definitions)
  receipts/gate-bypasses/            (bypass history)

Commands
--------
  list-checks                     List all checks from the check-runner manifest
  show   --check NAME             Show full definition of one check
  gate-config                     Show the overall validation gate configuration
  bypass-history [--limit N]      Show recent gate bypass receipts
  simulate [--skip-checks NAMES]  Simulate the gate with optional checks skipped

Examples
--------
  python scripts/validation_gate_tool.py list-checks
  python scripts/validation_gate_tool.py show --check ansible-lint
  python scripts/validation_gate_tool.py gate-config
  python scripts/validation_gate_tool.py bypass-history --limit 10
  python scripts/validation_gate_tool.py simulate
  python scripts/validation_gate_tool.py simulate --skip-checks ansible-lint,packer-validate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_CONFIG = REPO_ROOT / "config" / "validation-gate.json"
CHECK_MANIFEST = REPO_ROOT / "config" / "check-runner-manifest.json"
BYPASS_DIR = REPO_ROOT / "receipts" / "gate-bypasses"


def _load_gate() -> dict:
    if not GATE_CONFIG.exists():
        return {}
    return json.loads(GATE_CONFIG.read_text())


def _load_checks() -> dict:
    if not CHECK_MANIFEST.exists():
        return {}
    return json.loads(CHECK_MANIFEST.read_text())


def _bypass_files() -> list[Path]:
    if not BYPASS_DIR.exists():
        return []
    files: list[Path] = []
    for item in BYPASS_DIR.iterdir():
        if item.is_file() and item.suffix == ".json":
            files.append(item)
        elif item.is_dir():
            files.extend(item.glob("*.json"))
    return sorted(files, reverse=True)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_list_checks(args: argparse.Namespace) -> int:
    checks = _load_checks()
    if not checks:
        print("No checks found in check-runner manifest")
        return 0
    print(f"{'CHECK NAME':<35}  {'SEVERITY':<10}  {'TIMEOUT_S':>9}  DESCRIPTION")
    print("-" * 110)
    for name, cfg in sorted(checks.items()):
        desc = cfg.get("description", "")[:55]
        sev = cfg.get("severity", "")
        timeout = cfg.get("timeout_seconds", "?")
        print(f"{name:<35}  {sev:<10}  {timeout!s:>9}  {desc}")
    print(f"\n{len(checks)} check(s)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    checks = _load_checks()
    name = args.check
    check = checks.get(name)
    if check is None:
        name_lower = name.lower()
        for k, v in checks.items():
            if name_lower in k.lower():
                check = v
                name = k
                break
    if check is None:
        print(f"ERROR: check '{args.check}' not found")
        return 1
    print(f"Check: {name}")
    print(json.dumps(check, indent=2))
    return 0


def cmd_gate_config(args: argparse.Namespace) -> int:
    gate = _load_gate()
    if not gate:
        print("No validation-gate.json found or it is empty")
        return 0
    print(json.dumps(gate, indent=2))
    return 0


def cmd_bypass_history(args: argparse.Namespace) -> int:
    files = _bypass_files()
    limit = args.limit
    files = files[:limit]
    if not files:
        print("No gate bypass receipts found")
        return 0
    print(f"Recent gate bypass receipts ({len(files)} shown):\n")
    print(f"{'FILE':<65}  {'BYPASS':<25}  {'SOURCE':<20}  REASON_CODE")
    print("-" * 130)
    for f in files:
        try:
            data = json.loads(f.read_text())
            bypass = data.get("bypass", data.get("bypass_type", "?"))
            source = data.get("source", "?")
            reason = data.get("reason_code", data.get("reason", "?"))
            print(f"{f.name:<65}  {bypass:<25}  {source:<20}  {reason}")
        except (json.JSONDecodeError, OSError):
            print(f"{f.name:<65}  [parse error]")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    checks = _load_checks()
    skip = set()
    if args.skip_checks:
        skip = {s.strip() for s in args.skip_checks.split(",")}

    print("Validation Gate Simulation\n")
    print(f"Checks in manifest : {len(checks)}")
    print(f"Skipped checks     : {skip or '(none)'}")
    print()

    results = []
    for name, cfg in sorted(checks.items()):
        if name in skip:
            status = "SKIPPED"
        else:
            status = "WOULD_RUN"
        sev = cfg.get("severity", "")
        results.append((name, status, sev))

    print(f"{'CHECK':<35}  {'STATUS':<12}  SEVERITY")
    print("-" * 65)
    for name, status, sev in results:
        print(f"{name:<35}  {status:<12}  {sev}")

    would_run = sum(1 for _, s, _ in results if s == "WOULD_RUN")
    skipped = sum(1 for _, s, _ in results if s == "SKIPPED")
    errors = sum(1 for _, s, sev in results if s == "WOULD_RUN" and sev == "error")
    print(f"\nSummary: {would_run} would run, {skipped} skipped, {errors} are error-severity")
    if skipped:
        print("WARNING: Skipping checks bypasses the gate — ensure a bypass receipt is written.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="validation_gate_tool.py",
        description="Inspect and simulate the repository validation gate.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    sub.add_parser("list-checks", help="List all check-runner checks")

    shp = sub.add_parser("show", help="Show one check definition")
    shp.add_argument("--check", required=True, metavar="NAME")

    sub.add_parser("gate-config", help="Show validation gate configuration")

    bhp = sub.add_parser("bypass-history", help="Show recent bypass receipts")
    bhp.add_argument("--limit", type=int, default=20, metavar="N")

    simp = sub.add_parser("simulate", help="Simulate gate execution")
    simp.add_argument(
        "--skip-checks",
        metavar="NAMES",
        help="Comma-separated list of check names to skip in simulation",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "list-checks": cmd_list_checks,
        "show": cmd_show,
        "gate-config": cmd_gate_config,
        "bypass-history": cmd_bypass_history,
        "simulate": cmd_simulate,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
