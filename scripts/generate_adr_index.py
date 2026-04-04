#!/usr/bin/env python3
"""
generate_adr_index.py — ADR 0164 / ADR 0168 / ADR 0325
======================================================
Generate the compact ADR root manifest plus faceted ADR metadata shards.

Usage:
    python scripts/generate_adr_index.py              # preview root manifest
    python scripts/generate_adr_index.py --write      # write docs/adr/.index.yaml and shard files
    python scripts/generate_adr_index.py --check      # check generated files are current
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import subprocess
import sys

from adr_discovery import (
    ADR_DIR,
    INDEX_PATH,
    RESERVATIONS_PATH,
    build_generated_index_documents,
    check_generated_index_documents,
    ensure_reservations_file,
    load_adrs,
    load_reservation_ledger,
    validate_reservation_ledger,
    write_generated_index_documents,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def generated_date() -> dt.date:
    source_paths = [
        ADR_DIR,
        RESERVATIONS_PATH,
    ]
    relative_paths = [path.relative_to(REPO_ROOT).as_posix() for path in source_paths if path.exists()]
    if relative_paths:
        try:
            result = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%cs", "--", *relative_paths],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, OSError, subprocess.CalledProcessError):
            pass
        else:
            generated_on = result.stdout.strip()
            if generated_on:
                return dt.date.fromisoformat(generated_on)
    return dt.datetime.now(dt.timezone.utc).date()


def _load_inputs(today: dt.date) -> tuple[list, object, list[str]]:
    adrs = load_adrs(ADR_DIR)
    ledger = load_reservation_ledger(RESERVATIONS_PATH)
    issues = validate_reservation_ledger(ledger, adrs, today=today)
    return adrs, ledger, issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate shard-based ADR discovery metadata.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Write docs/adr/.index.yaml and ADR shard files.")
    mode.add_argument("--check", action="store_true", help="Fail when generated ADR discovery files are stale.")
    args = parser.parse_args(argv)

    created_reservations_file = False
    if args.write:
        created_reservations_file = ensure_reservations_file(RESERVATIONS_PATH)

    today = generated_date()
    adrs, ledger, issues = _load_inputs(today)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        return 1

    documents = build_generated_index_documents(
        adrs,
        ledger,
        adr_dir=ADR_DIR,
        generated_on=today,
    )

    if args.check:
        drift = check_generated_index_documents(documents, adr_dir=ADR_DIR)
        if drift:
            for issue in drift:
                print(f"ERROR: {issue}", file=sys.stderr)
            print(f"Run: python scripts/generate_adr_index.py --write", file=sys.stderr)
            return 1
        print(
            f"OK: {INDEX_PATH} and {len(documents) - 1} ADR shard files are current "
            f"({len(adrs)} ADRs indexed)"
        )
        return 0

    if args.write:
        write_generated_index_documents(documents, adr_dir=ADR_DIR)
        if created_reservations_file:
            print(f"Created {RESERVATIONS_PATH}")
        print(
            f"Written {INDEX_PATH} and {len(documents) - 1} ADR shard files "
            f"({len(adrs)} ADRs indexed)"
        )
        return 0

    print(documents[INDEX_PATH])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
