#!/usr/bin/env python3
"""Receipt mass-refresh orchestrator — ADR 0474 phase 12.1.

Thin wrapper around `scripts/refresh_safe_receipts.py`. Closes the
loop end-to-end so an operator (or a scheduled cron, or
`make heal --apply`) can run a single command:

  - Classify stale receipts via the underlying tool's `--json` output.
  - Print a one-line summary.
  - If `--apply` and `safe_to_refresh > 0`, invoke the tool's
    `--apply` mode to land the bump commit.
  - Write a YAML receipt under `receipts/heal-receipts/<ISO>.yaml`
    so the next operator can see when the last sweep ran.

CLI:

    python3 scripts/mass_refresh_receipts.py
    python3 scripts/mass_refresh_receipts.py --apply --max-age-days 30
    python3 scripts/mass_refresh_receipts.py --json

Exit:

    0  classification (and optional apply) succeeded
    1  underlying classifier failed, or --apply but tree dirty
    2  invocation error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIPTS_DIR = REPO_ROOT / "receipts" / "heal-receipts"
CLASSIFIER = REPO_ROOT / "scripts" / "refresh_safe_receipts.py"


def _runner_prefix() -> list[str]:
    """Mirror `validate_repo.sh`'s lookup: prefer uv, fall back to python3."""
    if shutil.which("uv"):
        return ["uv", "run", "--with", "pyyaml", "python"]
    return ["python3"]


def run_classifier(
    *,
    apply: bool = False,
    max_age_days: int | None = None,
    extra_args: list[str] | None = None,
) -> tuple[int, str, str]:
    """Invoke refresh_safe_receipts.py. Returns (rc, stdout, stderr)."""
    cmd = [*_runner_prefix(), str(CLASSIFIER), "--json"]
    if apply:
        cmd.append("--apply")
    if max_age_days is not None:
        cmd.extend(["--max-age-days", str(max_age_days)])
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(REPO_ROOT))
    return proc.returncode, proc.stdout, proc.stderr


def parse_classifier_output(stdout: str) -> dict[str, Any]:
    """Best-effort parse of the classifier's --json envelope.

    The classifier's exact envelope is `{summary, safe_to_refresh,
    needs_review, unknown}`. We treat unknown shapes leniently so
    older versions of the script still surface useful counts.
    """
    if not stdout.strip():
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {}


def summary_from(payload: dict[str, Any]) -> dict[str, int]:
    summary = payload.get("summary") if isinstance(payload, dict) else None
    if isinstance(summary, dict):
        return {
            "safe_to_refresh": int(summary.get("safe_to_refresh", 0)),
            "needs_review": int(summary.get("needs_review", 0)),
            "unknown": int(summary.get("unknown", 0)),
            "total": int(summary.get("total", 0)),
        }
    # Fall back: count list lengths if the tool returns them directly.
    counts: dict[str, int] = {}
    for key in ("safe_to_refresh", "needs_review", "unknown"):
        value = payload.get(key) if isinstance(payload, dict) else None
        counts[key] = len(value) if isinstance(value, list) else 0
    counts["total"] = sum(counts.values())
    return counts


def write_receipt(
    *,
    receipts_dir: Path,
    summary: dict[str, int],
    applied: bool,
    timestamp: dt.datetime,
) -> Path:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    fname = timestamp.strftime("%Y-%m-%dT%H-%M-%SZ") + ".yaml"
    out = receipts_dir / fname
    body = {
        "schema_version": 1,
        "ran_at": timestamp.isoformat() + "Z",
        "applied": bool(applied),
        "summary": summary,
    }
    out.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return out


def render_summary_line(summary: dict[str, int]) -> str:
    return (
        f"mass_refresh_receipts: safe={summary.get('safe_to_refresh', 0)} "
        f"needs_review={summary.get('needs_review', 0)} "
        f"unknown={summary.get('unknown', 0)} "
        f"total={summary.get('total', 0)}"
    )


def main(argv: list[str] | None = None, *, now: dt.datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Land the bump commit when safe_to_refresh > 0.",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Forward to refresh_safe_receipts.py.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the structured summary to stdout (always written to receipt).",
    )
    parser.add_argument(
        "--no-receipt",
        action="store_true",
        help="Skip writing the receipts/heal-receipts/<ISO>.yaml file.",
    )
    parser.add_argument(
        "--receipts-dir",
        default=str(RECEIPTS_DIR),
        help="Override receipts/heal-receipts location (used by tests).",
    )
    args = parser.parse_args(argv)

    rc, stdout, stderr = run_classifier(apply=args.apply, max_age_days=args.max_age_days)
    if rc not in (0, 1):
        print(stderr.rstrip(), file=sys.stderr)
        return rc or 1
    if rc == 1 and args.apply:
        # Underlying classifier returns 1 when --apply but tree is dirty.
        print(stderr.rstrip() or "mass_refresh_receipts: classifier refused (working tree dirty)", file=sys.stderr)
        return 1

    payload = parse_classifier_output(stdout)
    summary = summary_from(payload)
    line = render_summary_line(summary)

    if args.json:
        envelope = {"summary": summary, "applied": args.apply}
        print(json.dumps(envelope))
    else:
        print(line)

    if not args.no_receipt:
        timestamp = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        path = write_receipt(
            receipts_dir=Path(args.receipts_dir),
            summary=summary,
            applied=args.apply,
            timestamp=timestamp,
        )
        print(f"mass_refresh_receipts: wrote receipt {path.as_posix()}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
