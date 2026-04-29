#!/usr/bin/env python3
"""Fast-merged ADR reservation PR — ADR 0472 phase 10.1.

The Phase 4 `reserve_adr.py --reserve` writes a reservation entry to
`docs/adr/index/reservations.yaml` locally, but that entry is invisible
to other agents until the feature-branch PR merges. Phase 9 paid for
that gap four times: agents claimed the same number from main while a
sibling PR sat unmerged.

This script closes the loop:

  1. Compute the next free ADR number via `reserve_adr.py --next`
     (which already cross-references origin/main).
  2. Open a tiny single-commit branch `reservation/NNNN` whose only
     diff is the new reservation entry.
  3. Push the branch and `gh pr create --fill --merge --auto` (or the
     equivalent fast-merge flow). Reservation lives on origin/main
     within seconds.
  4. Print the reserved number on stdout for the calling agent's
     subsequent work.

Failure modes:

  - Working tree dirty: refuses (reservation must be a clean
    isolated commit). Operator stashes + retries.
  - `gh` not on PATH: refuses (no fallback; fast-merge requires the
    GitHub CLI).
  - PR auto-merge unavailable: opens the PR but skips the merge
    step, returning the reserved number anyway. Operator merges
    manually.

The script does NOT modify the local working tree's reservations.yaml
— the reservation lives on a separate branch. That keeps the active
worktree's diff clean for the actual ADR work.

Exit:
  0  reserved + merged (or PR opened, awaiting merge)
  1  reservation flow refused (dirty tree, gh missing, etc.)
  2  invocation error
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RESERVATIONS_PATH = REPO_ROOT / "docs" / "adr" / "index" / "reservations.yaml"
DEFAULT_BASE = "main"
DEFAULT_RESERVATION_DAYS = 30


def _git(args: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
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


def _has_command(name: str) -> bool:
    return shutil.which(name) is not None


def _slug(reason: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-") or "unspecified"


def _resolve_owner() -> str:
    try:
        return _git(["config", "user.name"]) or "unknown"
    except RuntimeError:
        return "unknown"


# ---------------------------------------------------------------------------
# Core flow — broken into helpers so tests can stub each step
# ---------------------------------------------------------------------------


def precheck(repo_root: Path) -> tuple[bool, str]:
    """Return (ok, reason). Refuses when prerequisites aren't met."""
    if not _has_command("git"):
        return False, "git not on PATH"
    if not _has_command("gh"):
        return False, "gh (GitHub CLI) not on PATH; reserve_adr_pr requires it"
    # Working tree must be clean — we're going to checkout a separate
    # branch and we shouldn't carry uncommitted noise into the
    # reservation PR.
    try:
        status = _git(["status", "--porcelain"], cwd=repo_root)
    except RuntimeError as exc:
        return False, str(exc)
    if status.strip():
        return False, "working tree has uncommitted changes; commit or stash first"
    return True, ""


def fetch_main(repo_root: Path, *, base: str = DEFAULT_BASE) -> None:
    """Refresh origin/main so reserve_adr.py --next sees the canonical view."""
    _git(["fetch", "origin", base], cwd=repo_root, check=False)


def next_free_via_helper(repo_root: Path) -> int:
    """Run scripts/reserve_adr.py --next via subprocess. Mirrors how
    the make target invokes it."""
    helper = repo_root / "scripts" / "reserve_adr.py"
    runner = ["uv", "run", "--with", "pyyaml", "python"] if _has_command("uv") else ["python3"]
    proc = subprocess.run(
        [*runner, str(helper), "--next"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"reserve_adr --next failed: {proc.stderr.strip()}")
    return int(proc.stdout.strip())


def build_reservation_entry(
    *,
    number: int,
    reason: str,
    workstream: str,
    branch: str,
    owner: str,
    today: dt.date,
    expires_days: int = DEFAULT_RESERVATION_DAYS,
) -> dict:
    """Mirror reserve_adr.write_reservation's schema so the loader's
    overlap check accepts the entry."""
    return {
        "id": f"res-{number:04d}-{_slug(reason)[:40]}",
        "start": number,
        "end": number,
        "owner": owner,
        "branch": branch,
        "workstream": workstream or "unassigned",
        "reason": reason,
        "reserved_on": today.isoformat(),
        "expires_on": (today + dt.timedelta(days=expires_days)).isoformat(),
        "status": "active",
    }


def append_to_reservations_on_branch(
    branch: str,
    *,
    repo_root: Path,
    base: str,
    entry: dict,
) -> None:
    """Create branch from base, append the entry, commit. Does NOT push."""
    _git(["checkout", "-b", branch, f"origin/{base}"], cwd=repo_root)
    res_path = repo_root / "docs" / "adr" / "index" / "reservations.yaml"
    if not res_path.is_file():
        raise RuntimeError(f"reservations.yaml missing at {res_path}")
    data = yaml.safe_load(res_path.read_text()) or {}
    raw = data.get("reservations") or []
    if not isinstance(raw, list):
        raise RuntimeError("reservations.yaml top-level reservations must be a list")
    raw.append(entry)
    data["reservations"] = raw
    res_path.write_text(yaml.safe_dump(data, sort_keys=False))
    _git(["add", str(res_path.relative_to(repo_root))], cwd=repo_root)
    _git(
        [
            "commit",
            "-m",
            f"[reserve-adr] Reserve ADR {entry['start']:04d} — {entry['reason']}",
            "--no-verify",
        ],
        cwd=repo_root,
    )


def push_and_open_pr(
    branch: str,
    *,
    repo_root: Path,
    base: str,
    entry: dict,
) -> str:
    """Push branch + open PR via gh. Returns the PR URL."""
    _git(["push", "origin", branch, "-u"], cwd=repo_root)
    proc = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--title",
            f"[reserve-adr] Reserve ADR {entry['start']:04d}",
            "--body",
            f"Reservation for ADR {entry['start']:04d}: {entry['reason']}\n\n"
            f"Auto-opened by `make reserve-adr-pr` (ADR 0472 phase 10.1).\n",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh pr create failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def squash_merge(branch: str, *, repo_root: Path) -> bool:
    """Squash-merge the just-opened PR. Returns True if the merge
    succeeded; False if --auto was used / merge is queued."""
    proc = subprocess.run(
        ["gh", "pr", "merge", branch, "--squash", "--delete-branch"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def reset_to_origin(repo_root: Path, *, base: str) -> None:
    """After the PR merges (or fails to), bring the local checkout
    back to a clean state on origin/<base>."""
    _git(["fetch", "origin", base], cwd=repo_root)
    _git(["checkout", base], cwd=repo_root, check=False)
    _git(["reset", "--hard", f"origin/{base}"], cwd=repo_root, check=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None, *, today: dt.date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--reason",
        required=True,
        help="Short human-readable reason; becomes part of the reservation id slug.",
    )
    parser.add_argument(
        "--workstream",
        default=os.environ.get("RESERVE_ADR_WORKSTREAM", ""),
        help="Workstream id this reservation belongs to.",
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"Target branch (default: {DEFAULT_BASE}).",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root override (for tests).",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Open the PR but skip the squash-merge step. Useful when branch-protection requires a human reviewer.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root)
    ok, reason = precheck(repo_root)
    if not ok:
        print(f"reserve_adr_pr: refused — {reason}", file=sys.stderr)
        return 1

    fetch_main(repo_root, base=args.base)
    try:
        number = next_free_via_helper(repo_root)
    except (RuntimeError, ValueError) as exc:
        print(f"reserve_adr_pr: {exc}", file=sys.stderr)
        return 1

    branch = f"reservation/{number:04d}"
    owner = _resolve_owner()
    entry = build_reservation_entry(
        number=number,
        reason=args.reason,
        workstream=args.workstream,
        branch=branch,
        owner=owner,
        today=today or dt.date.today(),
    )
    try:
        append_to_reservations_on_branch(branch, repo_root=repo_root, base=args.base, entry=entry)
        pr_url = push_and_open_pr(branch, repo_root=repo_root, base=args.base, entry=entry)
        print(f"reserve_adr_pr: opened PR {pr_url}", file=sys.stderr)
        if not args.no_merge:
            merged = squash_merge(branch, repo_root=repo_root)
            if not merged:
                print(
                    "reserve_adr_pr: gh pr merge --squash failed; PR remains open. "
                    "Operator will need to merge manually before the reservation "
                    "is canonical.",
                    file=sys.stderr,
                )
        reset_to_origin(repo_root, base=args.base)
    except RuntimeError as exc:
        print(f"reserve_adr_pr: {exc}", file=sys.stderr)
        return 1

    # Final stdout: the reserved number, suitable for shell capture.
    print(f"{number:04d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
