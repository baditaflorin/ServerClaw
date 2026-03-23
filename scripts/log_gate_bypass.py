#!/usr/bin/env python3
"""Record explicit validation gate bypasses."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RECEIPT_DIR = Path("receipts/gate-bypasses")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a validation gate bypass receipt.")
    parser.add_argument("--bypass", required=True, help="Bypass identifier, for example skip_remote_gate.")
    parser.add_argument("--reason", default="unspecified", help="Why the bypass was needed.")
    parser.add_argument("--source", default="manual", help="Source surface that triggered the receipt.")
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


def main() -> int:
    args = parse_args()
    created_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    branch = git_output("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    commit = git_output("rev-parse", "HEAD") or "unknown"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "bypass": args.bypass,
        "reason": args.reason,
        "source": args.source,
        "branch": branch,
        "commit": commit,
    }

    args.receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.receipt_dir / (
        f"{created_at}-{slugify(branch)}-{commit[:7]}-{slugify(args.bypass)}.json"
    )
    receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(receipt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
