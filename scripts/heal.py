#!/usr/bin/env python3
"""`make heal` — execute every doctor heal_command — ADR 0451 phase 6.2.

Phase 5's `scripts/doctor.py` aggregates drift signals and points each
non-zero signal at a `heal_command`. The pointers are advisory; this
script is the orchestrator that actually runs them.

Default mode is **dry-run** — every heal command is printed with a
"would run:" prefix but never executed. Heal commands can mutate disk
state (refresh_safe_receipts rewrites versions/stack.yaml,
heal_workstream_renames rewrites workstream YAMLs), so `--apply` is a
deliberate gesture.

Output (default):

    heal: dry-run; 4 signal(s) have heal commands.
      stale_receipts:        would run: python3 scripts/refresh_safe_receipts.py --apply
      dangling_surfaces:     would run: bash .githooks/post-merge
      validator_gaps:        (no heal command)
      blocked_substrate:     (no heal command — manual cleanup required)

`--apply` runs each heal command sequentially, captures stdout/stderr,
and emits a per-signal pass/fail summary. The orchestrator never
short-circuits — one failing heal does not stop the others.

Exit codes:

    0  dry-run completed successfully
    0  --apply completed; all heals returned 0
    1  --apply completed; at least one heal returned non-zero
    2  invocation error (doctor unavailable, JSON parse failure)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR_SCRIPT = REPO_ROOT / "scripts" / "doctor.py"


@dataclass
class HealOutcome:
    signal_name: str
    heal_command: str | None
    ran: bool
    exit_code: int | None
    stderr_summary: str | None


def load_doctor_signals(repo_root: Path) -> list[dict]:
    """Run `doctor.py --json` and return the parsed signals list.

    Raises RuntimeError on any failure — the caller turns that into a
    CLI exit code 2.
    """
    if not DOCTOR_SCRIPT.is_file():
        raise RuntimeError(f"doctor.py not found at {DOCTOR_SCRIPT}")
    runner = ["uv", "run", "--with", "pyyaml", "python"] if shutil.which("uv") else ["python3"]
    proc = subprocess.run(
        [*runner, str(DOCTOR_SCRIPT), "--json", "--root", str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"doctor returned exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"doctor JSON output unparseable: {exc}")
    signals = payload.get("signals")
    if not isinstance(signals, list):
        raise RuntimeError("doctor JSON missing 'signals' list")
    return signals


def actionable_signals(signals: list[dict]) -> list[dict]:
    """Filter the doctor signal list down to ones with count > 0 AND a
    heal_command. The orchestrator skips zero-count signals (nothing
    to heal) and signals without a heal_command (manual action only).
    """
    return [s for s in signals if s.get("count", 0) > 0 and (s.get("heal_command") or "").strip()]


def run_heal(signal: dict, *, cwd: Path) -> HealOutcome:
    """Execute one heal command. Captures output; returns a HealOutcome.

    Heal commands are executed via `bash -c` so shell features (pipes,
    redirects, comments) work. The doctor signal's heal_command is the
    exact string passed to bash.
    """
    name = signal.get("name", "(unknown)")
    cmd = signal.get("heal_command") or ""
    if not cmd.strip():
        return HealOutcome(
            signal_name=name,
            heal_command=None,
            ran=False,
            exit_code=None,
            stderr_summary=None,
        )
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return HealOutcome(
            signal_name=name,
            heal_command=cmd,
            ran=True,
            exit_code=124,
            stderr_summary="timed out after 300s",
        )
    except OSError as exc:
        return HealOutcome(
            signal_name=name,
            heal_command=cmd,
            ran=True,
            exit_code=127,
            stderr_summary=f"exec failed: {exc}",
        )
    stderr = (proc.stderr or "").strip()
    return HealOutcome(
        signal_name=name,
        heal_command=cmd,
        ran=True,
        exit_code=proc.returncode,
        stderr_summary=stderr.splitlines()[-1][:200] if stderr else None,
    )


def format_dry_run(signals: list[dict]) -> str:
    actionable = actionable_signals(signals)
    if not actionable:
        return "heal: no actionable signals — every drift signal is either clean or has no heal command."
    lines = [f"heal: dry-run; {len(actionable)} signal(s) have heal commands."]
    for s in actionable:
        lines.append(f"  {s['name']}: would run: {s['heal_command']}")
    lines.append("")
    lines.append("Pass --apply to execute these heal commands.")
    return "\n".join(lines)


def format_apply_summary(outcomes: list[HealOutcome]) -> str:
    if not outcomes:
        return "heal: no heal commands to run."
    lines = [f"heal: ran {len(outcomes)} heal command(s)."]
    passed = sum(1 for o in outcomes if o.exit_code == 0)
    for o in outcomes:
        marker = "ok " if o.exit_code == 0 else "fail"
        lines.append(f"  [{marker}] {o.signal_name}: exit {o.exit_code}")
        if o.stderr_summary:
            lines.append(f"        {o.stderr_summary}")
    lines.append(f"\nsummary: {passed}/{len(outcomes)} heal command(s) returned 0")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root override (for tests).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute each heal command (default: dry-run).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    repo_root = Path(args.root)
    try:
        signals = load_doctor_signals(repo_root)
    except RuntimeError as exc:
        print(f"heal: {exc}", file=sys.stderr)
        return 2

    if not args.apply:
        if args.json:
            print(json.dumps({"mode": "dry_run", "signals": actionable_signals(signals)}, indent=2))
        else:
            print(format_dry_run(signals))
        return 0

    outcomes: list[HealOutcome] = []
    for signal in actionable_signals(signals):
        outcomes.append(run_heal(signal, cwd=repo_root))

    if args.json:
        print(
            json.dumps(
                {
                    "mode": "apply",
                    "outcomes": [
                        {
                            "signal_name": o.signal_name,
                            "heal_command": o.heal_command,
                            "ran": o.ran,
                            "exit_code": o.exit_code,
                            "stderr_summary": o.stderr_summary,
                        }
                        for o in outcomes
                    ],
                },
                indent=2,
            )
        )
    else:
        print(format_apply_summary(outcomes))

    failed = sum(1 for o in outcomes if o.exit_code not in (0, None))
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
