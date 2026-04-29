#!/usr/bin/env python3
"""Advisory-to-required promotion eligibility tracker — ADR 0460 phase 8.1.

Reads `receipts/gate-runs/<gate>/*.yaml` per-gate ledger entries and
classifies each gate as one of:

  eligible    last MIN_CLEAN_RUNS entries (default 3) are all `result:
              clean` — gate is ready for promotion from advisory to
              required.
  streaking   1 or 2 clean entries in a row but fewer than the
              threshold — needs more sessions of clean evidence.
  unstable    any non-clean entry in the most recent window — wait
              for a clean streak to resume.
  promoted    gate is already running in `mode: required` per its
              latest entry — nothing to do.
  unknown     no ledger entries yet.

Output is human-readable by default; `--json` for ops_portal /
`make doctor` consumers; `--list` for a terse one-line-per-gate view.

The tracker does NOT mutate `validate_repo.sh` or any gate wiring —
that's a deliberate `--apply` flow deferred to phase 9. This script
ships the eligibility surface only.

Exit:
  0   normal run
  2   invocation error or ledger missing
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_DIR = REPO_ROOT / "receipts" / "gate-runs"
DEFAULT_MIN_CLEAN_RUNS = 3
DEFAULT_WINDOW = 5


@dataclass(frozen=True)
class GateRunEntry:
    """One ledger record. `rule` is optional — None for gates without
    a rule axis."""

    gate: str
    rule: str | None
    ran_on: str  # ISO timestamp string; we don't parse it for ordering
    result: str  # clean | findings | errored | skipped
    finding_count: int
    mode: str  # advisory | required
    session_id: str | None
    source_path: str  # repo-relative

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.gate, self.rule)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateClassification:
    """One row in the tracker's output."""

    gate: str
    rule: str | None
    status: str  # eligible | streaking | unstable | promoted | unknown
    detail: str
    last_clean_count: int
    window_size: int
    current_mode: str | None  # mode of the most recent entry, or None
    last_run_at: str | None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["key"] = f"{self.gate}/{self.rule}" if self.rule else self.gate
        return out


# ---------------------------------------------------------------------------
# Ledger loading
# ---------------------------------------------------------------------------


def load_ledger(directory: Path) -> list[GateRunEntry]:
    """Walk every `<gate>/*.yaml` under `directory` and return a flat
    list of GateRunEntry. Tolerates missing directory, malformed
    files, and missing fields — surfaces issues as skip rather than
    crash so the tracker degrades gracefully on a brand-new repo."""
    if not directory.is_dir():
        return []
    entries: list[GateRunEntry] = []
    for gate_dir in sorted(directory.iterdir()):
        if not gate_dir.is_dir():
            continue  # README.md, stray files
        for path in sorted(gate_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text()) or {}
            except (yaml.YAMLError, OSError):
                continue
            if not isinstance(data, dict):
                continue
            gate = data.get("gate")
            if not isinstance(gate, str) or not gate:
                continue
            rule = data.get("rule")
            if rule is not None and not isinstance(rule, str):
                rule = None
            result = str(data.get("result", "")).strip()
            if result not in {"clean", "findings", "errored", "skipped"}:
                continue
            finding_count_raw = data.get("finding_count", 0)
            try:
                finding_count = int(finding_count_raw)
            except (TypeError, ValueError):
                finding_count = 0
            mode = str(data.get("mode", "advisory")).strip() or "advisory"
            ran_on = str(data.get("ran_on", "")).strip()
            session_id = data.get("session_id")
            if session_id is not None:
                session_id = str(session_id)
            try:
                rel = str(path.relative_to(REPO_ROOT))
            except ValueError:
                rel = str(path)
            entries.append(
                GateRunEntry(
                    gate=gate,
                    rule=rule,
                    ran_on=ran_on,
                    result=result,
                    finding_count=finding_count,
                    mode=mode,
                    session_id=session_id,
                    source_path=rel,
                )
            )
    return entries


def group_by_gate(entries: list[GateRunEntry]) -> dict[tuple[str, str | None], list[GateRunEntry]]:
    """Return `{(gate, rule): [entries sorted by ran_on ascending]}`.

    Sorts by `ran_on` lexicographically — the schema mandates ISO
    timestamps so string-sort matches chronological order. Entries
    with malformed/missing `ran_on` sort to the start (we treat them
    as oldest, so they fall out of the recency window first).
    """
    out: dict[tuple[str, str | None], list[GateRunEntry]] = {}
    for entry in entries:
        out.setdefault(entry.key, []).append(entry)
    for entries_for_key in out.values():
        entries_for_key.sort(key=lambda e: e.ran_on)
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_gate(
    entries: list[GateRunEntry],
    *,
    min_clean_runs: int = DEFAULT_MIN_CLEAN_RUNS,
    window: int = DEFAULT_WINDOW,
) -> GateClassification:
    """Classify a single gate from its chronologically-sorted entries.

    Rules (in order):

      1. No entries → unknown.
      2. Most recent entry has `mode: required` → promoted.
      3. Last `min_clean_runs` entries all clean → eligible.
      4. Any entry in the recent window has result != clean → unstable.
      5. Otherwise → streaking (insufficient clean evidence yet).
    """
    if not entries:
        return GateClassification(
            gate="(none)",
            rule=None,
            status="unknown",
            detail="no ledger entries yet",
            last_clean_count=0,
            window_size=0,
            current_mode=None,
            last_run_at=None,
        )
    last = entries[-1]
    recent = entries[-window:]
    clean_streak = 0
    for entry in reversed(recent):
        if entry.result == "clean":
            clean_streak += 1
        else:
            break
    if last.mode == "required":
        status = "promoted"
        detail = f"already running in required mode (last run {last.ran_on or 'unknown'})"
    elif clean_streak >= min_clean_runs:
        status = "eligible"
        detail = f"last {clean_streak} run(s) clean (threshold {min_clean_runs}); current mode={last.mode}"
    elif any(e.result != "clean" for e in recent):
        status = "unstable"
        non_clean = [e for e in recent if e.result != "clean"]
        last_bad = non_clean[-1]
        detail = (
            f"last non-clean run was {last_bad.ran_on or 'unknown'} "
            f"({last_bad.result}, {last_bad.finding_count} finding(s))"
        )
    else:
        status = "streaking"
        detail = (
            f"{clean_streak}/{min_clean_runs} clean run(s) in a row; "
            f"need {min_clean_runs - clean_streak} more before eligible"
        )
    return GateClassification(
        gate=last.gate,
        rule=last.rule,
        status=status,
        detail=detail,
        last_clean_count=clean_streak,
        window_size=len(recent),
        current_mode=last.mode,
        last_run_at=last.ran_on or None,
    )


def classify_all(
    entries: list[GateRunEntry],
    *,
    min_clean_runs: int = DEFAULT_MIN_CLEAN_RUNS,
    window: int = DEFAULT_WINDOW,
) -> list[GateClassification]:
    grouped = group_by_gate(entries)
    out: list[GateClassification] = []
    for key, gate_entries in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        out.append(classify_gate(gate_entries, min_clean_runs=min_clean_runs, window=window))
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _format_human(classifications: list[GateClassification]) -> str:
    if not classifications:
        return "promotion_tracker: no ledger entries — receipts/gate-runs/ is empty."
    by_status: dict[str, list[GateClassification]] = {}
    for c in classifications:
        by_status.setdefault(c.status, []).append(c)
    lines = []
    eligible = by_status.get("eligible", [])
    if eligible:
        lines.append(f"[eligible for promotion] {len(eligible)}")
        for c in eligible:
            key = f"{c.gate}/{c.rule}" if c.rule else c.gate
            lines.append(f"  {key}: {c.detail}")
    streaking = by_status.get("streaking", [])
    if streaking:
        lines.append(f"\n[streaking] {len(streaking)}")
        for c in streaking:
            key = f"{c.gate}/{c.rule}" if c.rule else c.gate
            lines.append(f"  {key}: {c.detail}")
    unstable = by_status.get("unstable", [])
    if unstable:
        lines.append(f"\n[unstable] {len(unstable)}")
        for c in unstable:
            key = f"{c.gate}/{c.rule}" if c.rule else c.gate
            lines.append(f"  {key}: {c.detail}")
    promoted = by_status.get("promoted", [])
    if promoted:
        lines.append(f"\n[promoted] {len(promoted)} (already required)")
    summary = (
        f"\nsummary: {len(eligible)} eligible / {len(streaking)} streaking / "
        f"{len(unstable)} unstable / {len(promoted)} promoted"
    )
    lines.append(summary)
    return "\n".join(lines)


def _format_list(classifications: list[GateClassification]) -> str:
    if not classifications:
        return "(no gates classified)"
    lines = []
    for c in classifications:
        key = f"{c.gate}/{c.rule}" if c.rule else c.gate
        lines.append(f"{c.status:<10}  {key}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--ledger",
        default=str(LEDGER_DIR),
        help="Path to receipts/gate-runs/ directory.",
    )
    parser.add_argument(
        "--min-clean-runs",
        type=int,
        default=DEFAULT_MIN_CLEAN_RUNS,
        help=f"Consecutive clean runs required for eligible (default {DEFAULT_MIN_CLEAN_RUNS}).",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=DEFAULT_WINDOW,
        help=f"Recency window over which to assess instability (default {DEFAULT_WINDOW}).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--list",
        dest="terse",
        action="store_true",
        help="Terse one-line-per-gate output.",
    )
    args = parser.parse_args(argv)

    if args.min_clean_runs < 1 or args.window < 1:
        print(
            "promotion_tracker: --min-clean-runs and --window must be >= 1",
            file=sys.stderr,
        )
        return 2

    entries = load_ledger(Path(args.ledger))
    classifications = classify_all(
        entries,
        min_clean_runs=args.min_clean_runs,
        window=args.window,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "summary": {
                        "total": len(classifications),
                        "by_status": {
                            status: sum(1 for c in classifications if c.status == status)
                            for status in (
                                "eligible",
                                "streaking",
                                "unstable",
                                "promoted",
                                "unknown",
                            )
                        },
                    },
                    "gates": [c.to_dict() for c in classifications],
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif args.terse:
        print(_format_list(classifications))
    else:
        print(_format_human(classifications))
    return 0


if __name__ == "__main__":
    sys.exit(main())
