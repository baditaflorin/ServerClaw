"""CI lint: every step in bootstrap_steps.yml must have ≥1 post-condition — ADR 0484 §5.

Reads config/bootstrap_steps.yml and config/post_conditions.yml and verifies
that for every step's make_target, there is at least one entry in
post_conditions.yml with a matching `after_step` value.

Steps whose post-conditions are declared inline (preconditions/postconditions
as type=schema or type=file checks) are intentionally excluded from this
requirement — those contracts live in bootstrap_steps.yml itself. Only steps
with an external `make_target` need a runtime check in post_conditions.yml.

Exit codes:
  0   all steps have ≥1 post-condition or are exempt
  1   one or more steps have no post-condition coverage
  2   could not load one of the config files

Usage:

    uv run --with pyyaml python scripts/lint_bootstrap_coverage.py
    uv run --with pyyaml python scripts/lint_bootstrap_coverage.py --strict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
STEPS_PATH = REPO_ROOT / "config" / "bootstrap_steps.yml"
CONDITIONS_PATH = REPO_ROOT / "config" / "post_conditions.yml"

# Steps whose post-conditions are structural (schema/file checks embedded in
# bootstrap_steps.yml) rather than runtime checks in post_conditions.yml.
# These are exempt from the lint.
_STRUCTURAL_STEPS = {
    "0-derive",  # file/schema checks only
    "12-final-smoke",  # meta-step that runs all final-smoke checks
    "13-write-receipt",  # file check only
}


def _load(path: Path) -> dict:
    if not path.is_file():
        sys.exit(f"file not found: {path}")
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def load_step_targets(steps_path: Path = STEPS_PATH) -> list[dict]:
    """Return list of dicts with id, make_target for each non-exempt step.

    Pure function — no side effects. Tested directly.
    """
    data = _load(steps_path)
    steps = data.get("steps") or []
    return [
        {"id": s["id"], "make_target": s.get("make_target", s["id"])}
        for s in steps
        if s.get("id") not in _STRUCTURAL_STEPS
    ]


def load_covered_steps(conditions_path: Path = CONDITIONS_PATH) -> set[str]:
    """Return the set of make_target values covered by ≥1 post-condition.

    Pure function — no side effects. Tested directly.
    """
    data = _load(conditions_path)
    conditions = data.get("post_conditions") or []
    return {c["after_step"] for c in conditions if c.get("after_step")}


def lint_coverage(
    steps_path: Path = STEPS_PATH,
    conditions_path: Path = CONDITIONS_PATH,
    *,
    strict: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (missing, present) step id lists.

    Pure: takes paths but only reads; all logic is separable. Tested directly.
    """
    steps = load_step_targets(steps_path)
    covered = load_covered_steps(conditions_path)

    missing: list[str] = []
    present: list[str] = []
    for s in steps:
        if s["make_target"] not in covered:
            missing.append(s["id"])
        else:
            present.append(s["id"])
    return missing, present


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--steps", default=str(STEPS_PATH), help="Path to bootstrap_steps.yml")
    p.add_argument("--conditions", default=str(CONDITIONS_PATH), help="Path to post_conditions.yml")
    p.add_argument("--strict", action="store_true", help="Exit 1 even for non-critical gaps")
    args = p.parse_args(argv)

    missing, present = lint_coverage(Path(args.steps), Path(args.conditions), strict=args.strict)

    sys.stderr.write(f"lint-bootstrap-coverage: {len(present)} covered, {len(missing)} uncovered\n")
    for step_id in present:
        sys.stderr.write(f"  [OK ] {step_id}\n")
    for step_id in missing:
        sys.stderr.write(f"  [GAP] {step_id}  ← no entry in post_conditions.yml\n")

    if missing:
        sys.stderr.write(
            f"\n  {len(missing)} step(s) lack post-condition coverage.\n"
            f"  Add entries to config/post_conditions.yml with:\n"
            f"    after_step: <make_target>\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
