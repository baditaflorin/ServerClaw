#!/usr/bin/env python3
"""Record explicit validation gate bypasses."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

from scripts import gate_bypass_waivers


DEFAULT_RECEIPT_DIR = Path("receipts/gate-bypasses")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a validation gate bypass receipt.")
    parser.add_argument("--bypass", required=True, help="Bypass identifier, for example skip_remote_gate.")
    parser.add_argument("--source", default="manual", help="Source surface that triggered the receipt.")
    parser.add_argument("--reason-code", required=True, help="Controlled waiver reason code from the catalog.")
    parser.add_argument("--detail", required=True, help="Human-readable explanation for the bypass.")
    parser.add_argument(
        "--impacted-lane",
        action="append",
        default=[],
        help="Impacted validation lane identifier or a comma-separated list of identifiers.",
    )
    parser.add_argument(
        "--substitute-evidence",
        action="append",
        default=[],
        help="Passed substitute validation command, receipt, or note. Accepts repeated flags or comma-separated values.",
    )
    parser.add_argument("--owner", help="Waiver owner. Defaults to the current git user or shell user.")
    parser.add_argument("--expires-on", help="Waiver expiry date in YYYY-MM-DD. Defaults to the catalog policy window.")
    parser.add_argument("--remediation-ref", required=True, help="Linked remediation workstream or issue reference.")
    parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    return parser.parse_args()


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def resolve_owner() -> str:
    for args in (
        ("config", "user.email"),
        ("config", "user.name"),
    ):
        value = git_output(*args)
        if value:
            return value
    result = subprocess.run(["id", "-un"], text=True, capture_output=True, check=False)
    return result.stdout.strip() or Path.home().name or "unknown"


def main() -> int:
    args = parse_args()
    created_at = datetime.now(UTC)
    created_at_slug = created_at.strftime("%Y%m%dT%H%M%SZ")
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    commit = git_output("rev-parse", "HEAD") or "unknown"
    catalog = gate_bypass_waivers.load_catalog()
    gate_bypass_waivers.validate_catalog(catalog)
    impacted_lanes = gate_bypass_waivers.split_list_values(args.impacted_lane)
    if not impacted_lanes:
        raise SystemExit("At least one --impacted-lane value is required for a governed gate bypass waiver.")
    substitute_evidence = gate_bypass_waivers.split_list_values(args.substitute_evidence)
    if not substitute_evidence:
        raise SystemExit("At least one --substitute-evidence value is required for a governed gate bypass waiver.")
    expires_on = (
        gate_bypass_waivers.parse_date(args.expires_on, "--expires-on")
        if args.expires_on
        else gate_bypass_waivers.default_expiry_date(
            created_at=created_at,
            catalog=catalog,
            reason_code=args.reason_code,
        )
    )
    payload = gate_bypass_waivers.build_receipt_payload(
        created_at=created_at,
        bypass=args.bypass,
        source=args.source,
        branch=branch,
        commit=commit,
        reason_code=args.reason_code,
        detail=args.detail,
        impacted_lanes=impacted_lanes,
        substitute_evidence=substitute_evidence,
        owner=args.owner or resolve_owner(),
        expires_on=expires_on,
        remediation_ref=args.remediation_ref,
        catalog=catalog,
    )
    gate_bypass_waivers.validate_receipt(payload, path="<generated>", catalog=catalog)

    args.receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.receipt_dir / (f"{created_at_slug}-{slugify(branch)}-{commit[:7]}-{slugify(args.bypass)}.json")
    receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(receipt_path)
    _publish_to_outline(receipt_path)
    return 0


def _publish_to_outline(receipt_path: Path) -> None:
    """Best-effort: publish the receipt to the Outline wiki if OUTLINE_API_TOKEN is set."""
    import os

    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token:
        token_file = REPO_ROOT / ".local" / "outline" / "api-token.txt"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return
    outline_tool = SCRIPT_DIR / "outline_tool.py"
    if not outline_tool.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(outline_tool), "bypass.publish", "--file", str(receipt_path)],
            capture_output=True,
            check=False,
            env={**__import__("os").environ, "OUTLINE_API_TOKEN": token},
        )
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
