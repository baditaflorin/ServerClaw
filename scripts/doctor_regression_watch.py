#!/usr/bin/env python3
"""Doctor regression watcher — ADR 0465 phase 9.3.

Inverts the "agent must look" pattern. Today an agent runs `make
doctor`, reads 9 probe outputs, decides what's new vs. baseline, and
acts. This script does the diff deterministically:

  1. Read the live doctor JSON (or generate one in-process).
  2. Read a baseline JSON from `receipts/doctor-baselines/<sha>.json`
     or whichever baseline was named.
  3. Compute the per-signal diff:
       - regressions = signals that flipped from count=0 → count>0
       - improvements = signals that flipped count>0 → count=0
       - persistent = signals still non-zero
       - new_signals = probes added since baseline
       - removed_signals = probes dropped since baseline

`--json` emits the full diff for downstream automation (e.g. a
Windmill schedule that posts to Plane on regression). Default human
output highlights regressions with `[!]` markers.

Exit:
  0  no regressions (improvements-only, or in-sync with baseline)
  1  at least one signal regressed (`count` went from 0 → > 0)
  2  invocation error (no baseline available, malformed input)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = REPO_ROOT / "receipts" / "doctor-baselines"


@dataclass
class SignalDelta:
    name: str
    baseline_count: int | None  # None when probe didn't exist in baseline
    current_count: int | None  # None when probe doesn't exist now
    kind: str  # regression | improvement | persistent | new | removed | stable

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegressionReport:
    baseline_path: str | None
    current_path: str | None
    deltas: list[SignalDelta] = field(default_factory=list)
    generated_at: str = ""

    def regressions(self) -> list[SignalDelta]:
        return [d for d in self.deltas if d.kind == "regression"]

    def improvements(self) -> list[SignalDelta]:
        return [d for d in self.deltas if d.kind == "improvement"]

    def persistent(self) -> list[SignalDelta]:
        return [d for d in self.deltas if d.kind == "persistent"]

    def new_signals(self) -> list[SignalDelta]:
        return [d for d in self.deltas if d.kind == "new"]

    def removed_signals(self) -> list[SignalDelta]:
        return [d for d in self.deltas if d.kind == "removed"]

    def summary(self) -> dict[str, int]:
        return {
            "regressions": len(self.regressions()),
            "improvements": len(self.improvements()),
            "persistent": len(self.persistent()),
            "new_signals": len(self.new_signals()),
            "removed_signals": len(self.removed_signals()),
            "total": len(self.deltas),
        }

    def to_dict(self) -> dict:
        return {
            "baseline_path": self.baseline_path,
            "current_path": self.current_path,
            "generated_at": self.generated_at,
            "summary": self.summary(),
            "deltas": [d.to_dict() for d in self.deltas],
        }


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_doctor_json(path: Path) -> dict[str, int]:
    """Return `{signal_name: count}` from a doctor JSON payload.

    Tolerates both the snapshot envelope (with `head_sha`/
    `generated_at` wrapper) and the bare doctor --json output.
    """
    data = json.loads(path.read_text())
    signals = data.get("signals")
    if not isinstance(signals, list):
        raise ValueError(f"{path}: missing 'signals' list")
    out: dict[str, int] = {}
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        name = sig.get("name")
        if not isinstance(name, str):
            continue
        try:
            count = int(sig.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        out[name] = count
    return out


def latest_baseline(directory: Path) -> Path | None:
    """Return the lexically-greatest `*.json` file under `directory`.

    Baselines are named with timestamps or git SHAs that sort
    chronologically; the latest is the most recent one. Returns None
    when no baselines exist.
    """
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob("*.json"))
    return candidates[-1] if candidates else None


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def compute_diff(
    baseline: dict[str, int],
    current: dict[str, int],
) -> list[SignalDelta]:
    """Classify every signal across baseline + current.

    Five categories, in priority order:
      - regression: was 0, now > 0
      - improvement: was > 0, now 0
      - persistent: > 0 in both (status quo non-zero)
      - new: probe didn't exist in baseline
      - removed: probe existed in baseline but not in current
      - stable: 0 in both (most signals; reported only in --json)
    """
    deltas: list[SignalDelta] = []
    all_names = sorted(set(baseline) | set(current))
    for name in all_names:
        b = baseline.get(name)
        c = current.get(name)
        if b is None and c is not None:
            kind = "new"
        elif b is not None and c is None:
            kind = "removed"
        elif b == 0 and (c or 0) > 0:
            kind = "regression"
        elif (b or 0) > 0 and c == 0:
            kind = "improvement"
        elif (b or 0) > 0 and (c or 0) > 0:
            kind = "persistent"
        else:
            kind = "stable"
        deltas.append(
            SignalDelta(
                name=name,
                baseline_count=b,
                current_count=c,
                kind=kind,
            )
        )
    return deltas


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _format_human(report: RegressionReport) -> str:
    lines = []
    if not report.deltas:
        return "doctor_regression_watch: no signals to compare."
    summary = report.summary()
    if summary["regressions"]:
        lines.append(f"[!] {summary['regressions']} regression(s) since baseline:")
        for d in report.regressions():
            lines.append(f"    {d.name}: {d.baseline_count} → {d.current_count}")
    if summary["improvements"]:
        lines.append(f"\n[ok] {summary['improvements']} improvement(s):")
        for d in report.improvements():
            lines.append(f"    {d.name}: {d.baseline_count} → {d.current_count}")
    if summary["persistent"]:
        lines.append(f"\n[same] {summary['persistent']} persistent non-zero:")
        for d in report.persistent():
            lines.append(f"    {d.name}: still {d.current_count}")
    if summary["new_signals"]:
        lines.append(f"\n[new] {summary['new_signals']} probe(s) added since baseline:")
        for d in report.new_signals():
            lines.append(f"    {d.name}: {d.current_count}")
    if summary["removed_signals"]:
        lines.append(f"\n[gone] {summary['removed_signals']} probe(s) dropped since baseline:")
        for d in report.removed_signals():
            lines.append(f"    {d.name}: was {d.baseline_count}")
    lines.append(
        f"\nsummary: {summary['regressions']} regressions / "
        f"{summary['improvements']} improvements / "
        f"{summary['persistent']} persistent"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--baseline",
        help="Path to baseline doctor JSON. Default: latest under receipts/doctor-baselines/.",
    )
    parser.add_argument(
        "--current",
        help="Path to current doctor JSON. Default: build/doctor-snapshot.json.",
    )
    parser.add_argument(
        "--baseline-dir",
        default=str(BASELINE_DIR),
        help="Directory holding baseline files (used when --baseline is omitted).",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root override (for tests).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)

    repo_root = Path(args.root)
    baseline_path: Path | None
    if args.baseline:
        baseline_path = Path(args.baseline)
    else:
        baseline_path = latest_baseline(Path(args.baseline_dir))
    if baseline_path is None or not baseline_path.is_file():
        print(
            f"doctor_regression_watch: no baseline available — pass --baseline or populate {args.baseline_dir}.",
            file=sys.stderr,
        )
        return 2
    current_path = Path(args.current) if args.current else repo_root / "build" / "doctor-snapshot.json"
    if not current_path.is_file():
        print(
            f"doctor_regression_watch: current snapshot {current_path} not found "
            "— run `python3 scripts/doctor.py --snapshot` first.",
            file=sys.stderr,
        )
        return 2

    try:
        baseline = load_doctor_json(baseline_path)
        current = load_doctor_json(current_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"doctor_regression_watch: {exc}", file=sys.stderr)
        return 2

    report = RegressionReport(
        baseline_path=str(baseline_path),
        current_path=str(current_path),
        deltas=compute_diff(baseline, current),
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(_format_human(report))

    return 1 if report.summary()["regressions"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
