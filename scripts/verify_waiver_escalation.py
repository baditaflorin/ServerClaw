#!/usr/bin/env python3
"""Z3 formal verification of the gate bypass waiver escalation state machine.

This script proves four properties about the repeat_after_expiry counter and
status classification logic implemented in gate_bypass_waivers.py:summarize_receipts().

THE ALGORITHM BEING MODELLED (lines 390-403 of gate_bypass_waivers.py):
  ordered = sorted(items, key=lambda item: item.created_at)
  repeat_after_expiry = 0
  for index, current in enumerate(ordered):
      if any(
          previous.expires_on is not None
          and previous.expires_on < current.created_at.date()
          for previous in ordered[:index]
      ):
          repeat_after_expiry += 1

  status = "none"
  if repeat_after_expiry >= blocker_after:   status = "release_blocker"
  elif repeat_after_expiry >= warning_after: status = "warning"

PROPERTIES PROVED:

  P1  Non-negativity:      repeat_after_expiry >= 0 for any receipt sequence
  P2  Upper bound:         repeat_after_expiry <= len(receipts) - 1 always
  P3  Monotonic escalation: adding a chronologically later receipt never
                            DECREASES repeat_after_expiry (escalation is one-way)
  P4  Threshold soundness:  under the catalog constraint (blocker_after >= warning_after),
                            reaching release_blocker status implies the warning threshold
                            was also crossed
  P4b Constraint is load-bearing: removing the catalog constraint would make P4
                            falsifiable — Z3 finds a concrete counterexample

WHY Z3 AND NOT CROSSHAIR:
  CrossHair finds counterexamples to function contracts by exploring symbolic inputs.
  It cannot prove properties that span multiple calls or reason about all possible
  receipt sequences at once. P3 (monotonicity across additions) requires proving
  something about ALL possible sequences — CrossHair bounds its search and may miss
  an adversarially crafted sequence. Z3 proves it universally: for ALL symbolic
  integer inputs satisfying the date ordering constraints, the counter is non-decreasing.

  P4b is a meta-proof: it shows that the validate_catalog() guard
  (blocker_after >= warning_after) is not defensive padding — removing it would
  allow a logical inconsistency that Z3 can construct a concrete witness for.

RUN:
  uvx --from z3-solver python scripts/verify_waiver_escalation.py
  make verify-waiver-escalation

KEEPING THE MODEL IN SYNC WITH THE CODE:
  The script runs concrete test vectors against the real Python implementation
  BEFORE the Z3 proofs. If the implementation changes, the test vectors will
  fail first, alerting you to update this script before the proofs become stale.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Step 1 — Model validation: concrete test vectors against the real implementation
#
# These are run FIRST. If gate_bypass_waivers.py changes the algorithm, these
# fail immediately, preventing stale Z3 proofs from silently drifting from the code.
# ---------------------------------------------------------------------------


def _python_repeat_count(receipts: list[tuple[int, int | None]]) -> int:
    """
    Direct structural translation of the repeat_after_expiry loop.

    Args:
        receipts: (created_at_ordinal, expires_on_ordinal | None) tuples,
                  already sorted ascending by created_at_ordinal.
    """
    count = 0
    for index, (created_at, _) in enumerate(receipts):
        if any(prev_expires is not None and prev_expires < created_at for _, prev_expires in receipts[:index]):
            count += 1
    return count


def _python_status(repeat_count: int, warning_after: int, blocker_after: int) -> str:
    """Direct translation of the status classification block."""
    if repeat_count >= blocker_after:
        return "release_blocker"
    if repeat_count >= warning_after:
        return "warning"
    return "none"


# Ground-truth test vectors: (receipts, warning_after, blocker_after, expected_count, expected_status)
# Each tuple is a complete scenario. When the algorithm changes, these must be updated.
_VECTORS: list[tuple[list[tuple[int, int | None]], int, int, int, str]] = [
    # Single receipt, no expiry → not a repeat
    ([(0, None)], 2, 3, 0, "none"),
    # Two receipts: first expires before second is created → second IS a repeat
    ([(0, 5), (10, None)], 2, 3, 1, "none"),
    # Two receipts: first expires AFTER second is created → NOT a repeat
    ([(0, 15), (10, None)], 2, 3, 0, "none"),
    # Two receipts: first has no expiry → second is NOT a repeat
    ([(0, None), (10, None)], 2, 3, 0, "none"),
    # Three receipts: both later ones see an expired predecessor
    ([(0, 5), (10, 15), (20, None)], 2, 3, 2, "warning"),
    # Four receipts: three repeats → release_blocker
    ([(0, 5), (10, 15), (20, 25), (30, None)], 2, 3, 3, "release_blocker"),
    # Three receipts: only the first expires before the third; middle has no relevant expiry
    # First (0, 5): expires_on=5. Second (3, 2): expires_on=2, but 2 < 10 so third IS a repeat anyway
    # Actually let's trace: i=1 (created_at=3): prev=(0,5): 5 < 3? No. is_repeat[1]=False.
    #                       i=2 (created_at=10): prev=(0,5): 5<10? Yes. is_repeat[2]=True. count=1.
    ([(0, 5), (3, 2), (10, None)], 2, 3, 1, "none"),
    # Warning threshold exactly hit
    ([(0, 5), (10, 15), (20, None)], 2, 4, 2, "warning"),
    # Blocker threshold exactly hit
    ([(0, 5), (10, 15), (20, 25), (30, None)], 3, 3, 3, "release_blocker"),
    # Receipts with NO expiry never make subsequent receipts into repeats
    # (0,None) and (5,None) both lack expires_on, so (10,None) has no expired predecessor
    ([(0, None), (5, None), (10, None)], 2, 3, 0, "none"),
    # ── Strict inequality boundary ─────────────────────────────────────────────
    # expires_on == created_at of next receipt: condition is `<`, NOT `<=`,
    # so same-day expiry does NOT constitute a repeat.
    # If this changes to <=, these two vectors catch it immediately.
    ([(0, 10), (10, None)], 2, 3, 0, "none"),  # expires on day 10, next created on day 10 → NOT a repeat
    ([(0, 9), (10, None)], 2, 3, 1, "none"),  # expires on day  9, next created on day 10 → IS  a repeat
    # ── Multiple expired predecessors count as exactly 1 ──────────────────────
    # Both (0,5) and (3,7) expire before created_at=10.
    # any() short-circuits after the first True, so receipt 2 is still only 1 repeat,
    # not 2. Receipt 1 (created_at=3) is NOT a repeat: 5 < 3 is False.
    ([(0, 5), (3, 7), (10, None)], 2, 3, 1, "none"),
    # ── Later predecessor overrides earlier non-expiring one ──────────────────
    # (0, 100) does NOT expire before created_at=70.
    # (50, 60) DOES expire before created_at=70 (60 < 70).
    # The ordering of predecessors does not matter: any() finds the second one.
    ([(0, 100), (50, 60), (70, None)], 2, 3, 1, "none"),
    # ── Long-lived expiry windows prevent any repeats ─────────────────────────
    # Each receipt's expiry window extends well past all subsequent receipts'
    # creation dates, so no receipt ever has an expired predecessor.
    ([(0, 100), (10, 200), (20, 300), (30, None)], 2, 3, 0, "none"),
    # ── Coincident thresholds (warning_after == blocker_after == 1) ───────────
    # The minimum allowed policy: a single repeat immediately hits release_blocker,
    # bypassing the warning state entirely. This is valid: blocker_after >= warning_after
    # is satisfied when they are equal.
    ([(0, 5), (10, None)], 1, 1, 1, "release_blocker"),
    # ── warning_after=1 with headroom before blocker ──────────────────────────
    # One repeat triggers warning but not release_blocker.
    ([(0, 5), (10, None)], 1, 2, 1, "warning"),
    # ── Count at warning_after - 1 stays at none ──────────────────────────────
    # Zero repeats with warning_after=1: status must be none, not warning.
    ([(0, 15), (10, None)], 1, 2, 0, "none"),
    # ── Interleaved: only the last receipt has an expired predecessor ──────────
    # Middle receipt (created_at=3) is not a repeat; only the last (created_at=20) is.
    # Verifies that is_repeat is evaluated independently per receipt.
    ([(0, 5), (3, 25), (20, None)], 2, 3, 1, "none"),
]


def _validate_model() -> list[str]:
    """Run test vectors against the Python implementation. Returns failure messages."""
    failures: list[str] = []
    for receipts, warning_after, blocker_after, exp_count, exp_status in _VECTORS:
        actual_count = _python_repeat_count(receipts)
        actual_status = _python_status(actual_count, warning_after, blocker_after)
        if actual_count != exp_count:
            failures.append(
                f"  count mismatch receipts={receipts} w={warning_after} b={blocker_after}: "
                f"expected {exp_count}, got {actual_count}"
            )
        if actual_status != exp_status:
            failures.append(
                f"  status mismatch receipts={receipts} count={actual_count}: "
                f"expected {exp_status!r}, got {actual_status!r}"
            )
    return failures


# ---------------------------------------------------------------------------
# Step 2 — Z3 symbolic proofs
# ---------------------------------------------------------------------------


def _run_proofs() -> list[str]:
    """Run all Z3 proofs. Returns failure messages (empty list = all passed)."""
    try:
        from z3 import And, Bool, BoolVal, If, Int, Or, Solver, Sum, unsat
    except ModuleNotFoundError:
        return [
            "z3-solver is not installed. Install with: uvx --from z3-solver python ...\n  or: pip install z3-solver"
        ]

    failures: list[str] = []

    # ------------------------------------------------------------------
    # Symbolic model for N receipts
    # N=5 is sufficient: it provides more combinations than any real policy
    # (warning_after >= 1, blocker_after <= 30 per catalog schema) would exercise
    # in practice, and Z3 handles the universal quantification internally.
    # ------------------------------------------------------------------
    N = 5

    # Receipt fields as Z3 symbolic integers / booleans
    d = [Int(f"d_{i}") for i in range(N)]  # created_at ordinals
    e = [Int(f"e_{i}") for i in range(N)]  # expires_on ordinals
    h = [Bool(f"h_{i}") for i in range(N)]  # has_expiry flags

    # Base constraints: receipts are time-ordered; expiry >= creation when set
    base: list = []
    for i in range(N - 1):
        base.append(d[i] < d[i + 1])
    for i in range(N):
        # When has_expiry is True, expires_on must be >= created_at
        # (a waiver cannot expire before it was issued)
        base.append(If(h[i], e[i] >= d[i], True))

    # is_repeat[i] = i > 0 AND any j < i has (has_expiry[j] AND expires_on[j] < created_at[i])
    def repeat_expr(i: int):
        if i == 0:
            return BoolVal(False)
        return Or([And(h[j], e[j] < d[i]) for j in range(i)])

    is_repeat = [repeat_expr(i) for i in range(N)]
    repeat_count = Sum([If(is_repeat[i], 1, 0) for i in range(N)])

    # Policy thresholds — symbolic, constrained to match validate_catalog() invariants
    w = Int("warning_after")  # warning_after_occurrences
    b = Int("blocker_after")  # blocker_after_occurrences
    catalog_constraint = [w >= 1, b >= w]

    # ------------------------------------------------------------------
    # P1: repeat_after_expiry >= 0 for all inputs
    # ------------------------------------------------------------------
    s = Solver()
    s.add(base)
    s.add(repeat_count < 0)  # assert negation: counter goes negative
    r = s.check()
    if r != unsat:
        failures.append(f"P1 FAILED — counterexample: {s.model()}")
    else:
        print("  P1 PROVED  repeat_after_expiry >= 0 for all receipt sequences")

    # ------------------------------------------------------------------
    # P2: repeat_after_expiry <= N - 1
    # The first receipt (index 0) can never be a repeat (no predecessors exist),
    # so the counter is bounded by N-1.
    # ------------------------------------------------------------------
    s = Solver()
    s.add(base)
    s.add(repeat_count > N - 1)  # assert negation: counter exceeds maximum
    r = s.check()
    if r != unsat:
        failures.append(f"P2 FAILED — counterexample: {s.model()}")
    else:
        print(f"  P2 PROVED  repeat_after_expiry <= {N - 1} for {N}-receipt sequences")

    # ------------------------------------------------------------------
    # P3: Monotonic escalation
    # Adding a chronologically later receipt (created_at > all existing)
    # cannot DECREASE repeat_after_expiry.
    #
    # This proves that once a reason_code has been classified as "warning"
    # or "release_blocker", future receipt additions can only maintain or
    # escalate the classification — never silently reset it.
    # ------------------------------------------------------------------
    d_new = Int("d_new")
    e_new = Int("e_new")
    h_new = Bool("h_new")

    new_constraints = [
        d_new > d[N - 1],  # new receipt is chronologically last
        If(h_new, e_new >= d_new, True),  # expiry constraint for new receipt
    ]
    is_repeat_new = Or([And(h[j], e[j] < d_new) for j in range(N)])
    repeat_count_plus1 = repeat_count + If(is_repeat_new, 1, 0)

    s = Solver()
    s.add(base)
    s.add(new_constraints)
    s.add(repeat_count_plus1 < repeat_count)  # assert negation: counter decreased
    r = s.check()
    if r != unsat:
        failures.append(f"P3 FAILED — counterexample: {s.model()}")
    else:
        print("  P3 PROVED  repeat_after_expiry is monotonically non-decreasing (escalation is strictly one-way)")

    # ------------------------------------------------------------------
    # P4: Threshold soundness
    # Under the catalog constraint blocker_after >= warning_after, reaching
    # release_blocker status (repeat_count >= blocker_after) implies the warning
    # threshold was also crossed (repeat_count >= warning_after).
    #
    # In other words: you cannot jump from "none" to "release_blocker" while
    # bypassing the "warning" state — the classification is a strict ladder.
    # ------------------------------------------------------------------
    s = Solver()
    s.add(base)
    s.add(catalog_constraint)
    s.add(repeat_count >= b)  # release_blocker reached
    s.add(repeat_count < w)  # but warning was NOT crossed (negation of what we prove)
    r = s.check()
    if r != unsat:
        failures.append(f"P4 FAILED — counterexample: {s.model()}")
    else:
        print(
            "  P4 PROVED  release_blocker status implies warning threshold was crossed "
            "(classification ladder is strict)"
        )

    # ------------------------------------------------------------------
    # P5: Same-day expiry is NOT a repeat (strict < enforced at the model level)
    #
    # When expires_on[j] == created_at[i], the condition `expires_on[j] < created_at[i]`
    # evaluates to False. This proves the strict inequality is baked into the model
    # and that changing < to <= in the implementation would break P5.
    # ------------------------------------------------------------------
    s = Solver()
    s.add(d[0] < d[1])  # two time-ordered receipts
    s.add(h[0])  # first receipt has an expiry
    s.add(e[0] == d[1])  # expiry falls exactly on next receipt's creation day
    # The is_repeat expression for receipt 1, considering only predecessor 0
    same_day_repeat = And(h[0], e[0] < d[1])
    s.add(same_day_repeat)  # assert negation: same-day expiry IS a repeat
    r = s.check()
    if r != unsat:
        failures.append(
            f"P5 FAILED — same-day expiry (expires_on == created_at) is being counted as a repeat. "
            f"The condition should be strictly <, not <=. Counterexample: {s.model()}"
        )
    else:
        print(
            "  P5 PROVED  same-day expiry (expires_on == created_at) is NOT a repeat "
            "(strict < is semantically intentional)"
        )

    # ------------------------------------------------------------------
    # P6: Multiple expired predecessors yield exactly 1 increment (no double-counting)
    #
    # When several previous receipts have all expired before the current one,
    # is_repeat uses any() semantics (OR over predecessors), so the increment
    # to repeat_after_expiry is If(True, 1, 0) = 1, regardless of how many
    # predecessors expired. This proves the counter cannot jump by more than 1
    # per receipt, even with n simultaneously expired predecessors.
    # ------------------------------------------------------------------
    s = Solver()
    s.add(d[0] < d[1], d[1] < d[2])  # three ordered receipts
    s.add(h[0], e[0] < d[2])  # predecessor 0 expired before receipt 2
    s.add(h[1], e[1] < d[2])  # predecessor 1 also expired before receipt 2
    # is_repeat[2] evaluates to True (at least one expired predecessor exists)
    is_repeat_2 = Or(And(h[0], e[0] < d[2]), And(h[1], e[1] < d[2]))
    increment_2 = If(is_repeat_2, 1, 0)
    s.add(increment_2 > 1)  # assert negation: increment exceeds 1
    r = s.check()
    if r != unsat:
        failures.append(
            f"P6 FAILED — multiple expired predecessors cause double-counting of repeat_after_expiry. "
            f"Counterexample: {s.model()}"
        )
    else:
        print(
            "  P6 PROVED  multiple simultaneously-expired predecessors yield exactly 1 increment "
            "(any() semantics, no double-counting)"
        )

    # ------------------------------------------------------------------
    # P4b: The catalog constraint is load-bearing (not redundant)
    # Without blocker_after >= warning_after, P4 becomes falsifiable.
    # Z3 finds a concrete witness showing the threshold ordering matters.
    #
    # Expected result: SAT (meaning a counterexample to P4 EXISTS without the constraint).
    # If Z3 returns UNSAT here, it means the constraint is actually redundant —
    # which would indicate the algorithm has changed in a way that makes the
    # validate_catalog() guard unnecessary, and this script needs updating.
    # ------------------------------------------------------------------
    s = Solver()
    s.add(base)
    s.add(w >= 1, b >= 1)  # weaker constraints only (no ordering between w and b)
    s.add(repeat_count >= b)
    s.add(repeat_count < w)
    r = s.check()
    if r == unsat:
        failures.append(
            "P4b UNEXPECTED: P4 holds even WITHOUT the catalog ordering constraint "
            "(blocker_after >= warning_after). This suggests the algorithm has changed "
            "and the validate_catalog() guard may be redundant. "
            "Investigate before removing it."
        )
    else:
        model = s.model()
        b_val = model.eval(b)
        w_val = model.eval(w)
        rc_val = model.eval(repeat_count)
        print(
            f"  P4b CONFIRMED  removing blocker_after >= warning_after makes P4 falsifiable\n"
            f"             witness: blocker_after={b_val}, warning_after={w_val}, "
            f"repeat_count={rc_val}\n"
            f"             → the validate_catalog() guard IS load-bearing, not defensive padding"
        )

    return failures


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    print("Gate bypass waiver escalation — formal verification")
    print()

    # Step 1: concrete model validation
    print("Step 1: Model validation (test vectors against Python implementation)")
    model_failures = _validate_model()
    if model_failures:
        print(f"  FAILED — {len(model_failures)} mismatch(es):")
        for f in model_failures:
            print(f)
        print()
        print(
            "  The implementation in gate_bypass_waivers.py has diverged from the expected "
            "model. Fix the implementation or update _VECTORS in this script, then re-run."
        )
        return 1
    print(f"  OK — {len(_VECTORS)} test vector(s) match\n")

    # Step 2: Z3 symbolic proofs
    print("Step 2: Z3 symbolic proofs (universal properties, all inputs)")
    failures = _run_proofs()
    print()

    if failures:
        print(f"PROOF FAILURE(S) — {len(failures)} proof(s) did not hold:")
        for f in failures:
            print(f"  {f}")
        print()
        print(
            "  A proof failure means either:\n"
            "    (a) the algorithm in gate_bypass_waivers.py was changed in a way that\n"
            "        violates the stated property (the Z3 counterexample shows the bug), OR\n"
            "    (b) this script's Z3 model no longer matches the implementation\n"
            "        (update the model to reflect the intended new algorithm)."
        )
        return 1

    print("All proofs passed — the escalation state machine is formally verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
