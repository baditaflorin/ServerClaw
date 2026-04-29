#!/usr/bin/env python3
"""Auto-promote eligible advisory gates to required — ADR 0465 phase 9.2.

Phase 8's `promotion_tracker.py` is read-only — it identifies gates
that have stayed clean for ≥ MIN_CLEAN_RUNS consecutive sessions but
leaves the actual promotion to a human (or another LLM round-trip).

This script closes the loop:

  1. Runs `promotion_tracker.py --json` to enumerate eligible gates.
  2. Builds a structured plan: which `validate_repo.sh` line to flip,
     what gate-runs ledger entry to seed with `mode: required`.
  3. `--apply` writes the plan to disk; default mode prints it.

The plan is conservative on every axis:

  - Only gates explicitly tagged `(ADR NNNN — advisory)` in
    `validate_repo.sh` are eligible for the rewrite. The tagger looks
    for the literal string and refuses to act on anything else.
  - The rewrite is exact-string substitution
    (`(ADR NNNN — advisory)` → `(ADR NNNN — required)`); no regex
    surgery on the surrounding shell logic.
  - A new gate-runs ledger entry tagged `mode: required` is appended
    so the tracker reclassifies the gate as `promoted` on next run.
  - `--apply` refuses to run on a dirty `validate_repo.sh` working
    tree — preventing race with concurrent edits.

Exit:
  0  plan emitted (dry-run) or applied successfully
  1  --apply refused (dirty tree, missing tagger string, etc.)
  2  invocation error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_REPO_SH = REPO_ROOT / "scripts" / "validate_repo.sh"
LEDGER_DIR = REPO_ROOT / "receipts" / "gate-runs"
TRACKER_SCRIPT = REPO_ROOT / "scripts" / "promotion_tracker.py"

# Gates that this auto-promoter is allowed to flip. The tracker may
# surface eligibility for many gates; only the ones the platform has
# decided are safe-to-promote-via-script live here. Adding a new gate
# requires a code change AND an explicit "yes, this is safe to flip
# without operator review" decision.
ALLOWED_GATES: frozenset[str] = frozenset(
    {
        "validate_no_hardcoded_topology",
        "validate_catalogue_freshness",
        "validate_traceability",
        "validate_receipt_freshness",
    }
)


@dataclass(frozen=True)
class PromotionStep:
    """One eligible gate's proposed promotion."""

    gate: str
    rule: str | None
    line_number: int
    line_before: str
    line_after: str
    seeded_ledger_entry: str  # repo-relative path that will be created

    def to_dict(self) -> dict:
        out = asdict(self)
        out["key"] = f"{self.gate}/{self.rule}" if self.rule else self.gate
        return out


# ---------------------------------------------------------------------------
# Tracker integration
# ---------------------------------------------------------------------------


def load_eligible_gates(repo_root: Path) -> list[dict]:
    """Run `promotion_tracker.py --json` and return only `eligible`
    classifications. Returns an empty list on tracker errors so the
    caller surfaces "no plan" rather than crashing."""
    if not TRACKER_SCRIPT.is_file():
        return []
    runner = ["uv", "run", "--with", "pyyaml", "python"] if _has_uv() else ["python3"]
    proc = subprocess.run(
        [*runner, str(TRACKER_SCRIPT), "--json", "--ledger", str(repo_root / "receipts" / "gate-runs")],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    gates = payload.get("gates") or []
    return [g for g in gates if g.get("status") == "eligible"]


def _has_uv() -> bool:
    import shutil

    return shutil.which("uv") is not None


# ---------------------------------------------------------------------------
# validate_repo.sh inspection
# ---------------------------------------------------------------------------


_ADVISORY_LINE_RE = re.compile(
    r"\(ADR\s+\d+\s*[—-]\s*advisory\)",
    re.IGNORECASE,
)


def find_advisory_line(
    sh_text: str,
    gate: str,
) -> tuple[int, str] | None:
    """Locate the first `(ADR NNNN — advisory)` annotation that lives
    inside the bash function for `gate`. Returns (line_number, line)
    or None.

    The function block is identified by the `<gate>() {` opener and
    closed by the matching `}` at the same indent level (treated as
    "first standalone `}` after the opener" — bash style is consistent
    enough across the file).
    """
    lines = sh_text.splitlines()
    # Match `<gate>() {` with optional spaces.
    opener = re.compile(rf"^\s*{re.escape(gate)}\s*\(\s*\)\s*\{{\s*$")
    in_block = False
    for idx, line in enumerate(lines):
        if not in_block:
            if opener.match(line):
                in_block = True
            continue
        # Once inside, look for the advisory annotation.
        if _ADVISORY_LINE_RE.search(line):
            return (idx + 1, line)  # 1-indexed line number
        # Block closes at a lone `}` at column 0.
        stripped = line.rstrip()
        if stripped == "}":
            in_block = False
    return None


def synthesise_plan(
    eligible_gates: list[dict],
    sh_text: str,
    *,
    repo_root: Path,
) -> tuple[list[PromotionStep], list[str]]:
    """Map eligible-gate classifications onto concrete edits.

    Returns (plan, skipped) — `skipped` is a list of human-readable
    reasons for gates the script cannot act on (not in ALLOWED_GATES,
    no advisory annotation found, etc.).
    """
    plan: list[PromotionStep] = []
    skipped: list[str] = []
    today = dt.date.today().isoformat()
    for gate_cls in eligible_gates:
        gate = gate_cls.get("gate")
        rule = gate_cls.get("rule")
        if not isinstance(gate, str) or not gate:
            skipped.append(f"(unnamed gate): missing 'gate' field")
            continue
        if gate not in ALLOWED_GATES:
            skipped.append(f"{gate}: not in ALLOWED_GATES (auto-promotion not enabled for this gate)")
            continue
        match = find_advisory_line(sh_text, gate)
        if match is None:
            skipped.append(f"{gate}: no `(ADR NNNN — advisory)` annotation found in validate_repo.sh")
            continue
        line_number, line = match
        new_line = _ADVISORY_LINE_RE.sub(
            lambda m: m.group(0).rsplit("advisory", 1)[0] + "required" + m.group(0).rsplit("advisory", 1)[1],
            line,
        )
        # Compose the ledger seed path.
        seed_path = repo_root / "receipts" / "gate-runs" / gate / f"{today.replace('-', '')}T000000Z-promoted.yaml"
        try:
            seed_rel = str(seed_path.relative_to(repo_root))
        except ValueError:
            seed_rel = str(seed_path)
        plan.append(
            PromotionStep(
                gate=gate,
                rule=rule,
                line_number=line_number,
                line_before=line,
                line_after=new_line,
                seeded_ledger_entry=seed_rel,
            )
        )
    return plan, skipped


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def working_tree_clean(path: Path, *, repo_root: Path) -> bool:
    """Return True iff `path` has no uncommitted changes. Used to
    refuse `--apply` against a dirty validate_repo.sh — protects
    against racing with concurrent edits."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--", str(path.relative_to(repo_root))],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return False
    return proc.returncode == 0 and not proc.stdout.strip()


def apply_plan(
    plan: list[PromotionStep],
    *,
    sh_path: Path,
    repo_root: Path,
    today: dt.date | None = None,
) -> int:
    """Rewrite the targeted lines + seed ledger entries.

    Returns the number of steps applied. Raises FileNotFoundError if
    the script file is missing — the caller should pre-check.
    """
    if not plan:
        return 0
    if today is None:
        today = dt.date.today()
    text = sh_path.read_text()
    lines = text.splitlines(keepends=True)
    changed = 0
    for step in plan:
        idx = step.line_number - 1
        if idx >= len(lines):
            continue
        # Defensive: only rewrite if the line still matches what the
        # plan recorded. Concurrent edits can void the plan.
        current_stripped = lines[idx].rstrip("\r\n")
        if current_stripped != step.line_before.rstrip("\r\n"):
            continue
        line_ending = "\n"
        if lines[idx].endswith("\r\n"):
            line_ending = "\r\n"
        lines[idx] = step.line_after.rstrip("\r\n") + line_ending
        changed += 1
    if changed == 0:
        return 0
    sh_path.write_text("".join(lines))
    # Seed the ledger entries for each successfully-applied step.
    for step in plan[:changed]:
        seed_path = repo_root / step.seeded_ledger_entry
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        seed_payload = {
            "gate": step.gate,
            "ran_on": today.isoformat() + "T00:00:00Z",
            "result": "clean",
            "finding_count": 0,
            "mode": "required",
            "session_id": "ws-0465-phase9-auto-promote",
            "notes": (
                "Seeded by scripts/apply_promotion.py to record the "
                "advisory→required promotion. Tracker reclassifies the "
                "gate as `promoted` on next run."
            ),
        }
        if step.rule:
            seed_payload["rule"] = step.rule
        seed_path.write_text(yaml.safe_dump(seed_payload))
    return changed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_human(plan: list[PromotionStep], skipped: list[str]) -> str:
    lines = []
    if not plan and not skipped:
        return "apply_promotion: no eligible gates."
    if plan:
        lines.append(f"apply_promotion: {len(plan)} gate(s) ready to promote.")
        for step in plan:
            key = f"{step.gate}/{step.rule}" if step.rule else step.gate
            lines.append(f"  {key}:")
            lines.append(f"    line {step.line_number}:")
            lines.append(f"      - {step.line_before.strip()}")
            lines.append(f"      + {step.line_after.strip()}")
            lines.append(f"    will seed: {step.seeded_ledger_entry}")
    if skipped:
        lines.append(f"\nskipped {len(skipped)} gate(s):")
        for reason in skipped:
            lines.append(f"  {reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, today: dt.date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root override (for tests).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate validate_repo.sh + seed ledger (default: dry-run).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--gates",
        default="",
        help="Synthetic-test override: comma-separated eligible gate names "
        "to act on instead of running the tracker. The default empty value "
        "consults promotion_tracker.py.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root)
    sh_path = repo_root / "scripts" / "validate_repo.sh"
    if not sh_path.is_file():
        print(f"apply_promotion: validate_repo.sh not found at {sh_path}", file=sys.stderr)
        return 2

    if args.gates:
        eligible = [{"gate": g.strip(), "rule": None, "status": "eligible"} for g in args.gates.split(",") if g.strip()]
    else:
        eligible = load_eligible_gates(repo_root)

    sh_text = sh_path.read_text()
    plan, skipped = synthesise_plan(eligible, sh_text, repo_root=repo_root)

    if args.json:
        print(
            json.dumps(
                {
                    "plan": [s.to_dict() for s in plan],
                    "skipped": skipped,
                    "would_apply_count": len(plan),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(_format_human(plan, skipped))

    if not args.apply:
        if plan and not args.json:
            print("\nPass --apply to write these changes.")
        return 0

    if not working_tree_clean(sh_path, repo_root=repo_root):
        print(
            "apply_promotion: refused — scripts/validate_repo.sh has uncommitted changes.",
            file=sys.stderr,
        )
        return 1

    applied = apply_plan(plan, sh_path=sh_path, repo_root=repo_root, today=today)
    print(f"\napply_promotion: applied {applied}/{len(plan)} promotion(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
