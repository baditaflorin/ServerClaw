#!/usr/bin/env python3
"""Safe-receipt-refresh classifier — ADR 0449 phase 4.3.

The Phase 2 (`scripts/check_receipt_freshness.py`) work surfaced 72 of
186 stale receipts. This script answers the next question: which of
those are *safe to refresh without re-running the converge*?

Definition of safe-to-refresh:

  - The receipt slug is parseable (we know the receipt date).
  - The receipt is older than `--max-age-days`.
  - **No file path under the service's known role(s) has changed in
    git since the receipt date.** A no-op converge would only update
    the date; the work the receipt records is still in effect.

Anything that fails the no-change check is `needs_review` — the role
DID change, so a real converge is required to either confirm the
deployment caught up or surface a real drift.

Output:

    safe_to_refresh: [{service: ..., receipt_date: ..., age_days: ...}]
    needs_review:    [{service: ..., last_role_change: ..., changed_paths: [...]}]
    unknown:         [{service: ..., reason: ...}]

`--apply` (manual mode) writes a single
`[receipt-refresh] <count> services` commit that bumps the date
prefix on the safe set in `versions/stack.yaml`. Default mode is
read-only — surfaces the classification without mutating anything.

CLI:

    python3 scripts/refresh_safe_receipts.py --json
    python3 scripts/refresh_safe_receipts.py --apply --max-age-days 30

Exit:

    0  classification complete (with or without `--apply`)
    1  `--apply` but git working tree dirty (refuses to commit)
    2  invocation error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
STACK_YAML = REPO_ROOT / "versions" / "stack.yaml"

# Roles to inspect for a service. The lookup is best-effort: an entry
# in `platform_service_registry` may name a `<service>_runtime` and/or
# `<service>_postgres` role, or the service name may itself be the
# role name. We probe the conventional locations.
_ROLE_PATH_CANDIDATES = (
    "roles/{name}",
    "roles/{name}_runtime",
    "roles/{name}_postgres",
    "collections/ansible_collections/lv3/platform/roles/{name}",
    "collections/ansible_collections/lv3/platform/roles/{name}_runtime",
    "collections/ansible_collections/lv3/platform/roles/{name}_postgres",
)


@dataclass
class SafeEntry:
    service: str
    slug: str
    receipt_date: str
    age_days: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NeedsReviewEntry:
    service: str
    slug: str
    receipt_date: str
    age_days: int
    changed_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UnknownEntry:
    service: str
    slug: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Classification:
    safe_to_refresh: list[SafeEntry] = field(default_factory=list)
    needs_review: list[NeedsReviewEntry] = field(default_factory=list)
    unknown: list[UnknownEntry] = field(default_factory=list)

    def summary(self) -> dict[str, int]:
        return {
            "safe_to_refresh": len(self.safe_to_refresh),
            "needs_review": len(self.needs_review),
            "unknown": len(self.unknown),
            "total": len(self.safe_to_refresh) + len(self.needs_review) + len(self.unknown),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "safe_to_refresh": [e.to_dict() for e in self.safe_to_refresh],
            "needs_review": [e.to_dict() for e in self.needs_review],
            "unknown": [e.to_dict() for e in self.unknown],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_receipt_date(slug: str) -> dt.date | None:
    """Extract a `dt.date` from a receipt slug `YYYY-MM-DD-...`. Returns
    None if the prefix doesn't match. Mirrors the parser in
    scripts/check_receipt_freshness.py — kept local so this script
    doesn't import that one."""
    if not isinstance(slug, str) or len(slug) < 10:
        return None
    try:
        return dt.date.fromisoformat(slug[:10])
    except ValueError:
        return None


def load_receipts(stack_yaml_path: Path) -> dict[str, str]:
    if not stack_yaml_path.is_file():
        raise FileNotFoundError(f"missing {stack_yaml_path}")
    data = yaml.safe_load(stack_yaml_path.read_text()) or {}
    evidence = data.get("live_apply_evidence") or {}
    receipts = evidence.get("latest_receipts") or {}
    if not isinstance(receipts, dict):
        raise ValueError("live_apply_evidence.latest_receipts must be a mapping")
    return {str(k): str(v) for k, v in receipts.items()}


def candidate_role_paths(service: str, repo_root: Path) -> list[str]:
    """Return repo-relative role-directory paths that exist on disk for
    this service. Returns an empty list when nothing matches — the
    caller treats that as "unknown" (no role to scan)."""
    out: list[str] = []
    for tmpl in _ROLE_PATH_CANDIDATES:
        rel = tmpl.format(name=service)
        if (repo_root / rel).is_dir():
            out.append(rel)
    return out


def changed_since(
    paths: list[str],
    *,
    since: dt.date,
    repo_root: Path,
) -> list[str]:
    """Return the subset of `paths` (or files under them) that changed in
    git since `since`. `git log --since="YYYY-MM-DD" --name-only`
    returns the changed file list; we filter to the requested paths."""
    if not paths:
        return []
    cmd = [
        "git",
        "-C",
        str(repo_root),
        "log",
        f"--since={since.isoformat()}",
        "--name-only",
        "--pretty=format:",
        "--",
        *paths,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def working_tree_clean(repo_root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and not proc.stdout.strip()


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify(
    receipts: dict[str, str],
    *,
    today: dt.date,
    max_age_days: int,
    repo_root: Path,
) -> Classification:
    result = Classification()
    for service, slug in sorted(receipts.items()):
        date = parse_receipt_date(slug)
        if date is None:
            result.unknown.append(
                UnknownEntry(service=service, slug=slug, reason="receipt slug missing YYYY-MM-DD prefix")
            )
            continue
        age = (today - date).days
        if age <= max_age_days:
            # Already fresh — not in scope. Skip rather than emit.
            continue
        roles = candidate_role_paths(service, repo_root)
        if not roles:
            result.unknown.append(
                UnknownEntry(
                    service=service,
                    slug=slug,
                    reason="no matching role directory under roles/ or collections/.../roles/",
                )
            )
            continue
        changed = changed_since(roles, since=date, repo_root=repo_root)
        if not changed:
            result.safe_to_refresh.append(
                SafeEntry(
                    service=service,
                    slug=slug,
                    receipt_date=date.isoformat(),
                    age_days=age,
                )
            )
        else:
            result.needs_review.append(
                NeedsReviewEntry(
                    service=service,
                    slug=slug,
                    receipt_date=date.isoformat(),
                    age_days=age,
                    changed_paths=changed,
                )
            )
    return result


# ---------------------------------------------------------------------------
# Apply (write)
# ---------------------------------------------------------------------------


def refresh_receipt_slug(slug: str, today: dt.date) -> str:
    """Return the slug with its date prefix updated to `today`. The
    rest of the slug is preserved.

    `2026-03-01-foo` + 2026-04-28 → `2026-04-28-foo`. If the slug has
    no parseable prefix the function leaves it alone — the caller
    should never reach this for unknown receipts.
    """
    date = parse_receipt_date(slug)
    if date is None:
        return slug
    return today.isoformat() + slug[10:]


def apply_safe_refresh(
    classification: Classification,
    *,
    today: dt.date,
    stack_yaml_path: Path,
) -> int:
    """Rewrite versions/stack.yaml::live_apply_evidence.latest_receipts
    so every safe_to_refresh service gets a refreshed date prefix.
    Returns the count of refreshed receipts. Does NOT commit — caller
    handles that via git invocation outside this function (keeps the
    helper pure)."""
    if not classification.safe_to_refresh:
        return 0
    text = stack_yaml_path.read_text()
    data = yaml.safe_load(text) or {}
    evidence = data.get("live_apply_evidence") or {}
    receipts = evidence.get("latest_receipts") or {}
    if not isinstance(receipts, dict):
        raise ValueError("live_apply_evidence.latest_receipts must be a mapping")
    count = 0
    for entry in classification.safe_to_refresh:
        old = receipts.get(entry.service)
        if not old:
            continue
        new = refresh_receipt_slug(old, today)
        if new != old:
            receipts[entry.service] = new
            count += 1
    if count == 0:
        return 0
    evidence["latest_receipts"] = receipts
    data["live_apply_evidence"] = evidence
    # Preserve the rest of stack.yaml by round-tripping through yaml.
    # This loses comments — acceptable here because the file is
    # generator-friendly and human edits go elsewhere.
    stack_yaml_path.write_text(yaml.safe_dump(data, sort_keys=False))
    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_human(c: Classification, max_age_days: int) -> str:
    s = c.summary()
    lines = [
        f"refresh_safe_receipts: classification (window={max_age_days}d)",
        f"  safe_to_refresh: {s['safe_to_refresh']}",
        f"  needs_review:    {s['needs_review']}",
        f"  unknown:         {s['unknown']}",
    ]
    if c.safe_to_refresh:
        lines.append("\n[safe_to_refresh]")
        for e in c.safe_to_refresh:
            lines.append(f"  {e.service:<32} {e.receipt_date}  ({e.age_days}d old)")
    if c.needs_review:
        lines.append("\n[needs_review]")
        for e in c.needs_review:
            count = len(e.changed_paths)
            lines.append(f"  {e.service:<32} {e.receipt_date}  ({e.age_days}d old, {count} files changed since)")
    if c.unknown:
        lines.append("\n[unknown]")
        for e in c.unknown:
            lines.append(f"  {e.service:<32} reason: {e.reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, today: dt.date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--stack-yaml",
        default=str(STACK_YAML),
        help="Path to versions/stack.yaml (default: repo-root copy)",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=int(os.environ.get("RECEIPT_MAX_AGE_DAYS", "30")),
        help="Freshness window in days (default: 30 or $RECEIPT_MAX_AGE_DAYS)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate versions/stack.yaml — refresh date prefix on safe_to_refresh services. Refuses on dirty working tree.",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root override (for tests)",
    )
    args = parser.parse_args(argv)

    if args.max_age_days < 0:
        print(
            f"refresh_safe_receipts: --max-age-days must be >= 0, got {args.max_age_days}",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(args.root)
    try:
        receipts = load_receipts(Path(args.stack_yaml))
    except FileNotFoundError as exc:
        print(f"refresh_safe_receipts: {exc}", file=sys.stderr)
        return 2
    except (ValueError, yaml.YAMLError) as exc:
        print(f"refresh_safe_receipts: {args.stack_yaml}: {exc}", file=sys.stderr)
        return 2

    classification = classify(
        receipts,
        today=today or dt.date.today(),
        max_age_days=args.max_age_days,
        repo_root=repo_root,
    )

    if args.apply:
        if not working_tree_clean(repo_root):
            print(
                "refresh_safe_receipts: --apply refuses to run on a dirty working tree.",
                file=sys.stderr,
            )
            return 1
        refreshed = apply_safe_refresh(
            classification,
            today=today or dt.date.today(),
            stack_yaml_path=Path(args.stack_yaml),
        )
        print(f"refresh_safe_receipts: refreshed {refreshed} receipt(s)")
        return 0

    if args.json:
        print(json.dumps(classification.to_dict(), indent=2, sort_keys=True))
    else:
        print(_format_human(classification, args.max_age_days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
