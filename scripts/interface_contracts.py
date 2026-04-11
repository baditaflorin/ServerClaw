#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from controller_automation_toolkit import emit_cli_error
from platform.interface_contracts import check_live_apply_target, validate_contracts


def list_contracts() -> int:
    print("Interface contracts:")
    for contract in validate_contracts():
        print(
            f"  - {contract['contract_id']} "
            f"[{contract['version']}, {contract['compatibility']}] "
            f"owner={contract['owner']}"
        )
    return 0


def show_contract(contract_id: str) -> int:
    for contract in validate_contracts():
        if contract["contract_id"] != contract_id:
            continue
        payload = dict(contract)
        payload["path"] = str(Path(payload.pop("__path__")))
        print(json.dumps(payload, indent=2))
        return 0
    raise ValueError(f"unknown contract_id '{contract_id}'")


def validate_all() -> int:
    contracts = validate_contracts()
    print(f"Interface contracts OK: {len(contracts)} contract(s)")
    return 0


def check_live_apply(target: str) -> int:
    result = check_live_apply_target(target)
    print(f"Live apply contract OK: {result['target']} -> {Path(result['playbook']).relative_to(Path.cwd())}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and validate cross-workstream interface contracts.")
    parser.add_argument("--list", action="store_true", help="List all validated contracts.")
    parser.add_argument("--contract", help="Show one validated contract as JSON.")
    parser.add_argument("--validate", action="store_true", help="Validate all contract files.")
    parser.add_argument(
        "--check-live-apply",
        help="Validate contracts and verify one live-apply target, for example service:n8n or group:automation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.list:
            return list_contracts()
        if args.contract:
            return show_contract(args.contract)
        if args.validate:
            return validate_all()
        if args.check_live_apply:
            return check_live_apply(args.check_live_apply)
        parser.print_help()
        return 0
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        return emit_cli_error("interface contracts", exc)


if __name__ == "__main__":
    raise SystemExit(main())
