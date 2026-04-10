"""CLI entry point for the platform reconciliation library.

Usage::

    python -m scripts.reconciliation.cli reconcile-all
    python -m scripts.reconciliation.cli check-drift
    python -m scripts.reconciliation.cli check-drift --portal ops
    python -m scripts.reconciliation.cli regenerate --portal homepage
    python -m scripts.reconciliation.cli validate

All commands emit machine-readable JSON to stdout and a human-readable
summary to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _emit(result: dict[str, Any]) -> None:
    """Write JSON to stdout and a human summary to stderr."""
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def _summary(msg: str) -> None:
    """Write a human-readable summary line to stderr."""
    sys.stderr.write(msg + "\n")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_check_drift(args: argparse.Namespace) -> int:
    from scripts.reconciliation.core import (
        KNOWN_PORTALS,
        detect_portal_drift,
    )

    portals = [args.portal] if args.portal else KNOWN_PORTALS
    results = []
    any_drifted = False

    for portal in portals:
        report = detect_portal_drift(portal)
        results.append(report)
        _summary(report["summary"])
        if report["drifted"]:
            any_drifted = True

    _emit({"portals_checked": len(results), "any_drifted": any_drifted, "results": results})
    return 1 if any_drifted else 0


def _cmd_regenerate(args: argparse.Namespace) -> int:
    from scripts.reconciliation.core import regenerate_portal

    result = regenerate_portal(args.portal)
    if result["success"]:
        _summary(f"Regenerated portal '{args.portal}' successfully")
    else:
        _summary(f"Failed to regenerate portal '{args.portal}': {result['error']}")

    _emit(result)
    return 0 if result["success"] else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    from scripts.reconciliation.core import validate_all_artifacts

    result = validate_all_artifacts()
    for r in result["results"]:
        status = "OK" if r["valid"] else "STALE"
        _summary(f"  [{status}] {r['portal']}: {r['detail']}")

    if result["all_valid"]:
        _summary("All portal artifacts are valid.")
    else:
        _summary("Some portal artifacts are stale — run 'make reconcile-portals' to fix.")

    _emit(result)
    return 0 if result["all_valid"] else 1


def _cmd_reconcile_all(args: argparse.Namespace) -> int:
    from scripts.reconciliation.core import reconcile_all_portals

    result = reconcile_all_portals()
    for r in result["results"]:
        status = "OK" if r["success"] else "FAIL"
        detail = r.get("error") or "success"
        _summary(f"  [{status}] {r['portal']}: {detail}")

    _summary(
        f"Reconciliation complete: {result['portals_regenerated']} succeeded, "
        f"{result['portals_failed']} failed."
    )

    _emit(result)
    return 0 if result["portals_failed"] == 0 else 1


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.reconciliation.cli",
        description="Platform portal reconciliation — detect drift, regenerate, and validate artifacts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # check-drift
    p_drift = sub.add_parser(
        "check-drift",
        help="Check if any portal artifacts are stale.",
    )
    p_drift.add_argument(
        "--portal",
        choices=["homepage", "ops", "docs", "changelog"],
        help="Check a single portal instead of all.",
    )
    p_drift.set_defaults(func=_cmd_check_drift)

    # regenerate
    p_regen = sub.add_parser(
        "regenerate",
        help="Regenerate artifacts for a single portal.",
    )
    p_regen.add_argument(
        "--portal",
        required=True,
        choices=["homepage", "ops", "docs", "changelog"],
        help="Which portal to regenerate.",
    )
    p_regen.set_defaults(func=_cmd_regenerate)

    # validate
    p_val = sub.add_parser(
        "validate",
        help="Validate all portal artifacts (runs --check where supported).",
    )
    p_val.set_defaults(func=_cmd_validate)

    # reconcile-all
    p_all = sub.add_parser(
        "reconcile-all",
        help="Regenerate all portal artifacts from canonical catalogs.",
    )
    p_all.set_defaults(func=_cmd_reconcile_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
