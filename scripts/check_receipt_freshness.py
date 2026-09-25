#!/usr/bin/env python3
"""Receipt freshness checker — ADR 0446 item 14.

Reads `versions/stack.yaml::live_apply_evidence.latest_receipts`, parses
the date prefix of each receipt slug (format `YYYY-MM-DD-<slug>`), and
reports the age of every receipt against a freshness window.

The signal: a stale receipt means a service's code has likely changed
since the last live-apply, but nobody has re-converged it. That is the
canonical "drift on disk that nobody noticed" failure mode the 20-change
review flagged. ADR 0443 catches runtime drift; this script catches
receipt drift.

Default window: 30 days. Override via `--max-age-days N` or env
`RECEIPT_MAX_AGE_DAYS`. Default mode is **advisory** — exit 0 even when
stale. Pass `--strict` to exit 1 on any stale receipt; ADR 0446 phase 5
promotes the gate wiring to strict.

Output:

  - default                       human-readable per-receipt list
  - `--json`                      `{stale: [...], fresh: [...], summary: {...}}`
  - `--quiet`                     emit only summary line

Exit:

  0  no stale receipts (or stale present but advisory mode)
  1  stale receipts present and `--strict` set
  2  invocation error (missing stack.yaml, malformed entries)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
STACK_YAML = REPO_ROOT / "versions" / "stack.yaml"
RECEIPT_DIR = REPO_ROOT / "receipts" / "live-applies"


# ---------------------------------------------------------------------------
# ADR 0461 — receipt-file-existence check
# ---------------------------------------------------------------------------


def find_dangling_receipts(receipts: dict[str, str], receipt_dir: Path = RECEIPT_DIR) -> list[tuple[str, str]]:
    """Return [(service, slug), ...] for receipt slugs that have no JSON file.

    PR #71 (2026-04-28) added a `latest_receipts.coolify_runtime` slug
    to versions/stack.yaml without committing the corresponding
    receipts/live-applies/<slug>.json file. The schema-validation gate
    failed for every subsequent push to main until ws-0448 reconstructed
    the missing file. This function gives the gate a programmatic way
    to refuse the same class of commit.
    """
    dangling: list[tuple[str, str]] = []
    for service, slug in sorted(receipts.items()):
        if not slug:
            continue
        path = receipt_dir / f"{slug}.json"
        if not path.is_file():
            dangling.append((str(service), str(slug)))
    return dangling


def write_receipt_atomic(path: Path, payload: dict, *, indent: int = 2) -> None:
    """Atomic JSON-receipt write (ADR 0461).

    Writes to <path>.tmp, fsync, rename. Never leaves a half-written file
    in place: a crash between fsync and rename leaves the original
    receipt (or no receipt) intact, never a truncated one.
    """
    import os as _os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_str)
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=indent, sort_keys=True)
            fh.write("\n")
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise

# A receipt slug starts `YYYY-MM-DD-<rest>`. Examples from the live file:
#   2026-04-27-ws-0372-0fork-services-all-7-deployed
#   2026-03-28-adr-0250-log-queryability-canary-live-apply
_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")


@dataclass(frozen=True)
class ReceiptStatus:
    service: str
    slug: str
    receipt_date: str | None  # ISO YYYY-MM-DD or None on parse failure
    age_days: int | None  # None on parse failure
    is_stale: bool
    parse_error: str | None  # human-readable detail on failure

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_receipt_date(slug: str) -> tuple[dt.date | None, str | None]:
    """Extract a `dt.date` from a receipt slug.

    Returns `(date, None)` on success or `(None, error_message)` on
    failure. Failure modes are surfaced (not swallowed) so the caller
    can decide whether malformed entries should be a hard error or a
    soft warning.
    """
    if not isinstance(slug, str) or not slug.strip():
        return None, "empty or non-string slug"
    m = _DATE_PREFIX_RE.match(slug.strip())
    if not m:
        return None, "slug does not start with YYYY-MM-DD-"
    year, month, day, _ = m.groups()
    try:
        return dt.date(int(year), int(month), int(day)), None
    except ValueError as exc:
        return None, f"invalid date: {exc}"


def evaluate_receipts(
    receipts: dict[str, str],
    max_age_days: int,
    today: dt.date,
) -> list[ReceiptStatus]:
    """Compute a ReceiptStatus per (service, slug) pair.

    Receipts whose slug fails date parsing are returned with
    `receipt_date=None` and `is_stale=True` (they cannot be confirmed
    fresh). The caller can choose to surface those as hard errors via
    `--json`.
    """
    results: list[ReceiptStatus] = []
    for service, slug in sorted(receipts.items()):
        date, err = parse_receipt_date(slug)
        if date is None:
            results.append(
                ReceiptStatus(
                    service=service,
                    slug=str(slug) if slug is not None else "",
                    receipt_date=None,
                    age_days=None,
                    is_stale=True,  # unknown age treated as stale
                    parse_error=err,
                )
            )
            continue
        age = (today - date).days
        results.append(
            ReceiptStatus(
                service=service,
                slug=slug,
                receipt_date=date.isoformat(),
                age_days=age,
                is_stale=age > max_age_days,
                parse_error=None,
            )
        )
    return results


def load_receipts(stack_yaml_path: Path) -> dict[str, str]:
    """Load `live_apply_evidence.latest_receipts` from stack.yaml.

    Returns the receipt mapping (possibly empty). Raises FileNotFoundError
    or ValueError on schema violations so the CLI can return exit code 2.
    """
    if not stack_yaml_path.is_file():
        raise FileNotFoundError(f"missing {stack_yaml_path}")
    data = yaml.safe_load(stack_yaml_path.read_text()) or {}
    evidence = data.get("live_apply_evidence")
    if evidence is None:
        return {}
    if not isinstance(evidence, dict):
        raise ValueError("live_apply_evidence must be a mapping")
    receipts = evidence.get("latest_receipts") or {}
    if not isinstance(receipts, dict):
        raise ValueError("live_apply_evidence.latest_receipts must be a mapping")
    return {str(k): str(v) for k, v in receipts.items()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_human(results: list[ReceiptStatus], max_age_days: int) -> str:
    lines = []
    stale = [r for r in results if r.is_stale]
    fresh = [r for r in results if not r.is_stale]
    for r in sorted(results, key=lambda r: -1 if r.age_days is None else r.age_days, reverse=True):
        if r.parse_error:
            lines.append(f"  [???] {r.service:<30} {r.slug:<70}  parse error: {r.parse_error}")
        elif r.is_stale:
            lines.append(f"  [STALE] {r.service:<28} {r.receipt_date}  ({r.age_days}d old, window={max_age_days}d)")
        else:
            lines.append(f"  [ok]    {r.service:<28} {r.receipt_date}  ({r.age_days}d old)")
    lines.append(
        f"\nsummary: {len(stale)} stale / {len(fresh)} fresh / {len(results)} total (window={max_age_days} days)"
    )
    return "\n".join(lines)


def _format_json(results: list[ReceiptStatus], max_age_days: int) -> str:
    stale = [r.to_dict() for r in results if r.is_stale]
    fresh = [r.to_dict() for r in results if not r.is_stale]
    payload = {
        "stale": stale,
        "fresh": fresh,
        "summary": {
            "stale": len(stale),
            "fresh": len(fresh),
            "total": len(results),
            "max_age_days": max_age_days,
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True)


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
    parser.add_argument("--quiet", action="store_true", help="Print only the summary line")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when stale receipts present (default: advisory, exit 0)",
    )
    parser.add_argument(
        "--check-files",
        action="store_true",
        help=(
            "ADR 0461 — also verify each latest_receipts slug has a "
            "matching receipts/live-applies/<slug>.json file. Always "
            "exits non-zero on dangling references regardless of --strict."
        ),
    )
    args = parser.parse_args(argv)

    if args.max_age_days < 0:
        print(
            f"check_receipt_freshness: --max-age-days must be >= 0, got {args.max_age_days}",
            file=sys.stderr,
        )
        return 2

    try:
        receipts = load_receipts(Path(args.stack_yaml))
    except FileNotFoundError as exc:
        print(f"check_receipt_freshness: {exc}", file=sys.stderr)
        return 2
    except (ValueError, yaml.YAMLError) as exc:
        print(f"check_receipt_freshness: {args.stack_yaml}: {exc}", file=sys.stderr)
        return 2

    if not receipts:
        print("check_receipt_freshness: no receipts in live_apply_evidence.latest_receipts.")
        return 0

    if args.check_files:
        # Read RECEIPT_DIR from the module so tests can monkeypatch it.
        import sys as _sys

        _mod = _sys.modules[__name__]
        dangling = find_dangling_receipts(receipts, receipt_dir=getattr(_mod, "RECEIPT_DIR"))
        if dangling:
            for service, slug in dangling:
                print(
                    f"check_receipt_freshness: DANGLING receipt — service={service} slug={slug} "
                    f"has no matching receipts/live-applies/{slug}.json (ADR 0461). "
                    f"Either commit the receipt JSON or revert the latest_receipts entry.",
                    file=sys.stderr,
                )
            return 1

    today = today or dt.date.today()
    results = evaluate_receipts(receipts, args.max_age_days, today)

    if args.json:
        print(_format_json(results, args.max_age_days))
    elif args.quiet:
        stale = sum(1 for r in results if r.is_stale)
        print(f"check_receipt_freshness: {stale}/{len(results)} stale (window={args.max_age_days} days)")
    else:
        print(_format_human(results, args.max_age_days))

    has_stale = any(r.is_stale for r in results)
    return 1 if has_stale and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
