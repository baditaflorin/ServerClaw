#!/usr/bin/env python3
"""Atomic ADR-number reservation CLI — ADR 0449 phase 4.1.

Eliminates the ADR-number-collision class documented in postmortem
2026-04-28 (the very class that made this workstream re-number itself
from 0448 → 0449 mid-session).

The substrate is ADR 0325 — `docs/adr/index/reservations.yaml` — which
has been around for months but lacks an ergonomic CLI. Authors who
forget to write a reservation race other agents.

Two modes:

  --next                    Print the next free ADR number to stdout.
  --reserve --reason "..."  Atomically reserve the next number under the
                            current branch + workstream (resolves owner
                            from `git config user.name`).

The atomic flow:

    1. Refuse to run if local has uncommitted changes touching
       `docs/adr/`.
    2. `git fetch origin main` (mandatory; respects --offline for tests).
    3. Build the universe of taken numbers from BOTH:
         - origin/main `docs/adr/04*.md` (committed ADRs)
         - `docs/adr/index/reservations.yaml` active reservations
    4. Pick the lowest free number ≥ floor.
    5. (--reserve only) Append a reservation entry to
       `docs/adr/index/reservations.yaml` and re-validate via the
       existing `scripts/adr_discovery.py::load_reservations`.

Exit codes:
    0  success
    1  conflict / refuses to run (uncommitted changes, divergent local)
    2  invocation error
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "adr"
RESERVATIONS_PATH = ADR_DIR / "index" / "reservations.yaml"
DEFAULT_FLOOR = 1
DEFAULT_RESERVATION_DAYS = 30

_ADR_FILENAME_RE = re.compile(r"^(\d{4})-")


def _git(args: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
    """Run a git command and return stdout (rstripped)."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.rstrip("\n")


def parse_adr_filename(name: str) -> int | None:
    """Return the ADR number from a filename, or None if it doesn't match."""
    m = _ADR_FILENAME_RE.match(name)
    return int(m.group(1)) if m else None


def numbers_taken_on_origin(origin_ref: str = "origin/main") -> set[int]:
    """Return the set of ADR numbers already committed to origin_ref.

    Uses `git ls-tree` so it works without a local checkout of the
    target ref. Falls back to scanning the working tree if the ref is
    unreachable (offline mode, fresh clone).
    """
    try:
        output = _git(["ls-tree", "--name-only", origin_ref, "docs/adr/"])
    except RuntimeError:
        # Offline / no remote — fall back to local working tree.
        return numbers_taken_on_disk()
    taken: set[int] = set()
    for line in output.splitlines():
        # ls-tree emits paths like `docs/adr/0445-phase1-...`.
        name = line.rsplit("/", 1)[-1]
        n = parse_adr_filename(name)
        if n is not None:
            taken.add(n)
    return taken


def numbers_taken_on_disk(adr_dir: Path | None = None) -> set[int]:
    d = adr_dir or ADR_DIR
    taken: set[int] = set()
    if not d.is_dir():
        return taken
    for path in d.iterdir():
        if path.is_file() and path.suffix == ".md":
            n = parse_adr_filename(path.name)
            if n is not None:
                taken.add(n)
    return taken


def numbers_taken_in_reservations(path: Path | None = None) -> set[int]:
    """Return numbers covered by ACTIVE reservations.

    Inactive (released/expired/realised) reservations are ignored — the
    number is back in the pool.
    """
    p = path or RESERVATIONS_PATH
    if not p.is_file():
        return set()
    data = yaml.safe_load(p.read_text()) or {}
    raw = data.get("reservations") or []
    if not isinstance(raw, list):
        return set()
    out: set[int] = set()
    active = {"active", "reserved"}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "active")).lower()
        if status not in active:
            continue
        try:
            start = int(entry.get("start"))
            end = int(entry.get("end", entry.get("start")))
        except (TypeError, ValueError):
            continue
        for n in range(start, end + 1):
            out.add(n)
    return out


def next_free(
    floor: int | None = None,
    *,
    origin_ref: str = "origin/main",
    offline: bool = False,
    reservations_path: Path | None = None,
    adr_dir: Path | None = None,
) -> int:
    """Compute the next unused ADR number.

    Default semantic: `max(taken) + 1`. This matches author intuition
    ("what's the next ADR I should write?") rather than "the lowest
    free hole" — backfilling holes would risk reusing numbers that
    earlier ADRs referenced before deletion.

    `floor` overrides the lower bound. Useful when you want a number
    in a specific range (e.g. floor=500 to start a new ADR series).
    `floor=1` is the strict lowest-free-hole semantic.
    """
    on_origin: set[int] = set() if offline else numbers_taken_on_origin(origin_ref)
    on_disk = numbers_taken_on_disk(adr_dir)
    reserved = numbers_taken_in_reservations(reservations_path)
    taken = on_origin | on_disk | reserved
    if floor is None:
        # Author intuition: pick the next number after the highest
        # currently-taken one. Holes from deleted ADRs stay vacant.
        floor = (max(taken) + 1) if taken else 1
    n = max(floor, 1)
    while n in taken:
        n += 1
    return n


def working_tree_clean_for_adr(repo_root: Path | None = None) -> tuple[bool, str]:
    """Return (clean, detail). Clean iff `docs/adr/` has no uncommitted
    changes. Refuses to reserve on a dirty tree because the existing
    diff might already be the ADR being reserved.
    """
    root = repo_root or REPO_ROOT
    try:
        output = _git(
            ["status", "--porcelain", "--", "docs/adr/"],
            cwd=root,
        )
    except RuntimeError as exc:
        return False, str(exc)
    if output.strip():
        return False, output.strip()
    return True, ""


def write_reservation(
    *,
    number: int,
    reason: str,
    workstream: str,
    branch: str,
    owner: str,
    today: dt.date,
    expires_days: int = DEFAULT_RESERVATION_DAYS,
    reservations_path: Path | None = None,
) -> dict:
    """Append a reservation to reservations.yaml, return the entry written.

    The schema mirrors `scripts/adr_discovery.py::AdrReservation` —
    `id`, not `reservation_id`. The validator there is the source of
    truth; mismatches are surfaced at index regen time.
    """
    p = reservations_path or RESERVATIONS_PATH
    if not p.is_file():
        raise RuntimeError(f"missing reservations ledger at {p}")
    data = yaml.safe_load(p.read_text()) or {}
    reservations = data.get("reservations") or []
    if not isinstance(reservations, list):
        raise RuntimeError("reservations.yaml: top-level reservations must be a list")
    entry = {
        "id": f"res-{number:04d}-{_slug(reason)[:40]}",
        "start": number,
        "end": number,
        "owner": owner,
        "branch": branch,
        "workstream": workstream,
        "reason": reason,
        "reserved_on": today.isoformat(),
        "expires_on": (today + dt.timedelta(days=expires_days)).isoformat(),
        "status": "active",
    }
    reservations.append(entry)
    data["reservations"] = reservations
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return entry


def _slug(reason: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-") or "unspecified"


def _resolve_owner() -> str:
    try:
        return _git(["config", "user.name"]) or "unknown"
    except RuntimeError:
        return "unknown"


def _resolve_branch() -> str:
    try:
        return _git(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    except RuntimeError:
        return "unknown"


def _release(number: int, *, reservations_path: Path) -> int:
    """Remove the reservation entry covering `number`. Idempotent —
    returning 0 even when no entry exists. ADR 0470 phase 10.3.

    Multiple reservations covering the same number (rare but legal —
    the loader's first-wins rule applies) are all removed in one
    pass; the caller is alerted via the printed `removed N` count.
    """
    if number < 1:
        print(f"reserve_adr --release: number must be >= 1, got {number}", file=sys.stderr)
        return 2
    if not reservations_path.is_file():
        print(f"reserve_adr --release: ledger missing at {reservations_path}", file=sys.stderr)
        return 2
    data = yaml.safe_load(reservations_path.read_text()) or {}
    raw = data.get("reservations") or []
    if not isinstance(raw, list):
        print(
            "reserve_adr --release: reservations.yaml top-level must be a list",
            file=sys.stderr,
        )
        return 2
    kept: list = []
    removed = 0
    for entry in raw:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        try:
            start = int(entry.get("start"))
            end = int(entry.get("end", entry.get("start")))
        except (TypeError, ValueError):
            kept.append(entry)
            continue
        if start <= number <= end:
            removed += 1
            continue
        kept.append(entry)
    if removed > 0:
        data["reservations"] = kept
        reservations_path.write_text(yaml.safe_dump(data, sort_keys=False))
    print(f"reserve_adr: released {removed} reservation(s) covering {number:04d}")
    return 0


def main(argv: list[str] | None = None, *, today: dt.date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--next",
        action="store_true",
        help="Print the next free ADR number and exit.",
    )
    parser.add_argument(
        "--reserve",
        action="store_true",
        help="Reserve the next free number atomically (writes to reservations.yaml).",
    )
    parser.add_argument(
        "--release",
        type=int,
        metavar="N",
        help="Release a previously-reserved ADR number (idempotent; ADR 0470 phase 10.3). "
        "Removes any matching entry from reservations.yaml. Run from the release "
        "commit that lands the ADR file, after the entry has served its purpose.",
    )
    parser.add_argument(
        "--reason",
        help="Required with --reserve. Short human-readable reason; becomes part of the reservation id slug.",
    )
    parser.add_argument(
        "--workstream",
        default=os.environ.get("RESERVE_ADR_WORKSTREAM", ""),
        help="Workstream id this reservation belongs to (default: $RESERVE_ADR_WORKSTREAM).",
    )
    parser.add_argument(
        "--floor",
        type=int,
        default=None,
        help="Lowest number to consider. Default: max(taken)+1, i.e. one higher "
        "than the highest currently-taken number. Pass --floor=1 for "
        "strict lowest-free-hole semantics.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip the origin/main scan (for tests / fresh clones).",
    )
    parser.add_argument(
        "--origin-ref",
        default="origin/main",
        help="Git ref to scan for committed ADRs (default: origin/main).",
    )
    parser.add_argument(
        "--reservations-path",
        type=Path,
        default=RESERVATIONS_PATH,
        help="Override the reservations ledger path (for tests).",
    )
    parser.add_argument(
        "--adr-dir",
        type=Path,
        default=ADR_DIR,
        help="Override the ADR directory (for tests).",
    )
    args = parser.parse_args(argv)

    # --release is independent of --next/--reserve. Handle it first.
    if args.release is not None:
        return _release(
            args.release,
            reservations_path=args.reservations_path,
        )

    if not args.next and not args.reserve:
        parser.print_help(sys.stderr)
        return 2

    # `--next` is read-only; safe to run on dirty trees.
    if args.next and not args.reserve:
        n = next_free(
            args.floor,
            origin_ref=args.origin_ref,
            offline=args.offline,
            reservations_path=args.reservations_path,
            adr_dir=args.adr_dir,
        )
        print(f"{n:04d}")
        return 0

    # --reserve enforces --reason and a clean working tree.
    if not args.reason:
        print("reserve_adr: --reserve requires --reason", file=sys.stderr)
        return 2
    clean, detail = working_tree_clean_for_adr(REPO_ROOT)
    if not clean:
        print(
            "reserve_adr: working tree has uncommitted changes under docs/adr/:",
            file=sys.stderr,
        )
        print(detail, file=sys.stderr)
        print(
            "Commit or stash the existing changes before reserving a number.",
            file=sys.stderr,
        )
        return 1

    n = next_free(
        args.floor,
        origin_ref=args.origin_ref,
        offline=args.offline,
        reservations_path=args.reservations_path,
        adr_dir=args.adr_dir,
    )
    entry = write_reservation(
        number=n,
        reason=args.reason,
        workstream=args.workstream or "unassigned",
        branch=_resolve_branch(),
        owner=_resolve_owner(),
        today=today or dt.date.today(),
        reservations_path=args.reservations_path,
    )
    print(f"reserved {n:04d} as {entry['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
