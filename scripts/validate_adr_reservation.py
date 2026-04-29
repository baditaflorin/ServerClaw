#!/usr/bin/env python3
"""ADR-reservation gate — ADR 0472 phase 10.2.

Rejects PRs that add a `docs/adr/NNNN-*.md` file whose number is not
present in `reservations.yaml` on `origin/main`. This closes the
collision class that hit Phase 9 four times in one session: once an
agent reserves a number locally, the CI gate prevents another agent
from accidentally claiming the same number from main.

The gate is conservative — it only fails on positive evidence of a
collision. Cases that pass:

  - ADR is present in `reservations.yaml` on origin/main.
  - ADR is being added by the same PR that adds the matching
    reservation entry (the early-merge flow may not always be
    available; the gate gracefully accepts atomic single-PR
    additions).
  - ADR file already existed on origin/main (untouched by this PR).

Cases that fail:

  - ADR added by this PR; not in reservations.yaml on origin/main;
    not added in this PR's reservation entries.

Run modes:

  - default: scan committed-not-yet-pushed changes (HEAD..origin/main)
  - `--all-files`: scan every ADR on disk against current
    reservations.yaml — used by `validate_repo.sh` `all` lane.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "adr"
RESERVATIONS_PATH = ADR_DIR / "index" / "reservations.yaml"
_ADR_FILENAME_RE = re.compile(r"^docs/adr/(\d{4})-")


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    """Run a git command. Returns stdout (or empty string on failure)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd or REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def reservation_numbers(reservations_path: Path) -> set[int]:
    """Return the integer ADR numbers covered by reservations in the
    given file. Active and inactive both counted — the gate only
    cares whether the number was ever reserved."""
    if not reservations_path.is_file():
        return set()
    try:
        data = yaml.safe_load(reservations_path.read_text()) or {}
    except yaml.YAMLError:
        return set()
    raw = data.get("reservations") or []
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            start = int(entry.get("start"))
            end = int(entry.get("end", entry.get("start")))
        except (TypeError, ValueError):
            continue
        for n in range(start, end + 1):
            out.add(n)
    return out


def origin_reservation_numbers(
    reservations_relpath: str = "docs/adr/index/reservations.yaml",
    *,
    origin_ref: str = "origin/main",
) -> set[int]:
    """Read reservations.yaml from origin/main directly via git
    show. Lets the gate compare against the canonical ledger even
    when local has uncommitted reservation changes."""
    text = _git(["show", f"{origin_ref}:{reservations_relpath}"])
    if not text:
        return set()
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return set()
    raw = data.get("reservations") or []
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            start = int(entry.get("start"))
            end = int(entry.get("end", entry.get("start")))
        except (TypeError, ValueError):
            continue
        for n in range(start, end + 1):
            out.add(n)
    return out


def added_adrs_in_diff(
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
) -> set[int]:
    """Return ADR numbers added by `<base>...<head>` (i.e. files that
    didn't exist on base but do on head)."""
    output = _git(
        [
            "diff",
            "--name-only",
            "--diff-filter=A",
            f"{base_ref}...{head_ref}",
            "--",
            "docs/adr/",
        ]
    )
    return _extract_adr_numbers(output.splitlines())


def adrs_on_disk(adr_dir: Path | None = None) -> set[int]:
    """Return every ADR number on disk (used by --all-files mode)."""
    d = adr_dir or ADR_DIR
    if not d.is_dir():
        return set()
    out: set[int] = set()
    for path in d.iterdir():
        if path.is_file() and path.suffix == ".md":
            m = re.match(r"^(\d{4})-", path.name)
            if m:
                out.add(int(m.group(1)))
    return out


def adrs_on_origin(origin_ref: str = "origin/main") -> set[int]:
    """Return ADR numbers committed to origin_ref."""
    output = _git(["ls-tree", "--name-only", origin_ref, "docs/adr/"])
    return _extract_adr_numbers(output.splitlines())


def _extract_adr_numbers(paths: list[str]) -> set[int]:
    out: set[int] = set()
    for path in paths:
        path = path.strip()
        if not path:
            continue
        # Normalise: ls-tree gives bare names, diff gives full paths.
        for prefix in ("docs/adr/", ""):
            if not prefix or path.startswith(prefix):
                name = path.removeprefix("docs/adr/")
                m = re.match(r"^(\d{4})-", name)
                if m:
                    out.add(int(m.group(1)))
                break
    return out


def find_unreserved_adrs(
    *,
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    adr_dir: Path | None = None,
    reservations_path: Path | None = None,
    all_files: bool = False,
) -> list[int]:
    """Return the sorted list of ADR numbers added by this PR but not
    backed by any reservation.

    `all_files` mode walks the full disk; useful for the validate_repo.sh
    `all` lane.
    """
    if all_files:
        # Compare disk ADRs vs disk reservations vs origin (so we don't
        # complain about ADRs already on origin).
        on_disk = adrs_on_disk(adr_dir)
        on_origin = adrs_on_origin()
        added = on_disk - on_origin
    else:
        added = added_adrs_in_diff(base_ref=base_ref, head_ref=head_ref)
    if not added:
        return []
    # The reservation must be visible on origin/main OR added in the
    # same diff (so a single atomic PR works).
    on_origin_reservations = origin_reservation_numbers()
    local_reservations = reservation_numbers(reservations_path or RESERVATIONS_PATH)
    reserved = on_origin_reservations | local_reservations
    return sorted(added - reserved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("RESERVE_ADR_BASE", "origin/main"),
        help="Base git ref for the diff (default: origin/main).",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Head git ref (default: HEAD).",
    )
    parser.add_argument(
        "--adr-dir",
        type=Path,
        default=ADR_DIR,
        help="Override the ADR directory (for tests).",
    )
    parser.add_argument(
        "--reservations-path",
        type=Path,
        default=RESERVATIONS_PATH,
        help="Override the reservations ledger path (for tests).",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Scan every ADR on disk; default is HEAD..base diff only.",
    )
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="Exit 0 even on findings (used during gate-rollout window).",
    )
    args = parser.parse_args(argv)

    findings = find_unreserved_adrs(
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        adr_dir=args.adr_dir,
        reservations_path=args.reservations_path,
        all_files=args.all_files,
    )

    if not findings:
        print("validate_adr_reservation: every added ADR is backed by a reservation.")
        return 0

    print(
        f"validate_adr_reservation: {len(findings)} ADR(s) added without a reservation:",
        file=sys.stderr,
    )
    for n in findings:
        print(f"  ADR {n:04d}", file=sys.stderr)
    print(
        '\nReserve via: make reserve-adr-pr reason="<short reason>" '
        '(or scripts/reserve_adr.py --reserve --reason "<X>").',
        file=sys.stderr,
    )

    return 0 if args.advisory else 1


if __name__ == "__main__":
    sys.exit(main())
