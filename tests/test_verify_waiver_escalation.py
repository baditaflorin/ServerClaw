"""Full branch coverage for scripts/verify_waiver_escalation.py.

Coverage targets:
  _python_repeat_count  — all loop/condition branches
  _python_status        — all three return branches
  _validate_model       — pass path, count mismatch, status mismatch, both
  _run_proofs           — z3 not installed, all proofs pass, P1-P6 individual
                          failures (ControlledSolver), P4b unexpected-unsat
  main                  — model failures → 1, proof failures → 1, all pass → 0
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_waiver_escalation.py"


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------


def _load_module():
    """Return a freshly executed instance of verify_waiver_escalation."""
    spec = importlib.util.spec_from_file_location("verify_waiver_escalation", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_waiver_escalation"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# ControlledSolver factory
#
# Replaces z3.Solver so that the solver instantiated at `fail_at_index`
# returns `fail_result` from check() instead of the real SMT result.
# All other solvers delegate to the real z3.Solver.  model() returns a
# printable sentinel string for the forced-failure solver so that f-string
# interpolation in _run_proofs does not crash.
# ---------------------------------------------------------------------------


def _make_controlled_solver(fail_at_index: int, fail_result):
    import z3

    real_Solver = z3.Solver
    call_count = [0]

    class ControlledSolver:
        def __init__(self):
            self._idx = call_count[0]
            call_count[0] += 1
            self._inner = real_Solver()

        def add(self, *args):
            self._inner.add(*args)

        def check(self):
            if self._idx == fail_at_index:
                return fail_result
            return self._inner.check()

        def model(self):
            # P4b success path calls model.eval(); return the inner model for
            # any solver we did not force (fall-through to else branch).
            if self._idx == fail_at_index:
                return "<forced-counterexample>"
            return self._inner.model()

    return ControlledSolver


# ---------------------------------------------------------------------------
# _python_repeat_count
# ---------------------------------------------------------------------------


class TestPythonRepeatCount:
    def setup_method(self):
        self.fn = _load_module()._python_repeat_count

    def test_empty_list(self):
        assert self.fn([]) == 0

    def test_single_receipt_no_expiry(self):
        # index=0 → no predecessor slice → inner any() vacuously False
        assert self.fn([(0, None)]) == 0

    def test_single_receipt_with_expiry(self):
        # index=0 still has no predecessors
        assert self.fn([(0, 5)]) == 0

    def test_prev_expires_is_none_branch(self):
        # prev_expires is None → `prev_expires is not None` is False → short-circuit
        assert self.fn([(0, None), (10, None)]) == 0

    def test_prev_expires_strictly_before_created_at(self):
        # 5 < 10 → True → IS a repeat
        assert self.fn([(0, 5), (10, None)]) == 1

    def test_prev_expires_equals_created_at_not_repeat(self):
        # strict <: 10 < 10 is False → NOT a repeat
        assert self.fn([(0, 10), (10, None)]) == 0

    def test_prev_expires_after_created_at(self):
        # 15 < 10 is False → NOT a repeat
        assert self.fn([(0, 15), (10, None)]) == 0

    def test_both_later_receipts_are_repeats(self):
        assert self.fn([(0, 5), (10, 15), (20, None)]) == 2

    def test_multiple_expired_predecessors_increment_once(self):
        # Both (0,5) and (3,7) expire before created_at=10 → any() fires once → count=1
        assert self.fn([(0, 5), (3, 7), (10, None)]) == 1


# ---------------------------------------------------------------------------
# _python_status
# ---------------------------------------------------------------------------


class TestPythonStatus:
    def setup_method(self):
        self.fn = _load_module()._python_status

    def test_none_below_warning(self):
        assert self.fn(0, 2, 3) == "none"

    def test_warning_at_threshold(self):
        assert self.fn(2, 2, 3) == "warning"

    def test_warning_above_warning_below_blocker(self):
        assert self.fn(2, 1, 3) == "warning"

    def test_release_blocker_at_threshold(self):
        assert self.fn(3, 2, 3) == "release_blocker"

    def test_release_blocker_above_threshold(self):
        assert self.fn(10, 2, 3) == "release_blocker"

    def test_coincident_thresholds_blocker_wins(self):
        # blocker_after == warning_after == 1; blocker branch is checked first
        assert self.fn(1, 1, 1) == "release_blocker"


# ---------------------------------------------------------------------------
# _validate_model
# ---------------------------------------------------------------------------


class TestValidateModel:
    def setup_method(self):
        self.m = _load_module()

    def test_all_vectors_pass(self):
        assert self.m._validate_model() == []

    def test_count_mismatch_reported(self):
        # Vector whose expected_count is wrong (actual=1, expected=99)
        bad = [([(0, 5), (10, None)], 2, 3, 99, "none")]
        original, self.m._VECTORS = self.m._VECTORS, bad
        try:
            failures = self.m._validate_model()
        finally:
            self.m._VECTORS = original
        assert any("count mismatch" in f for f in failures)

    def test_status_mismatch_reported(self):
        # count=1, thresholds 2/3 → actual status "none"; expected wrong
        bad = [([(0, 5), (10, None)], 2, 3, 1, "release_blocker")]
        original, self.m._VECTORS = self.m._VECTORS, bad
        try:
            failures = self.m._validate_model()
        finally:
            self.m._VECTORS = original
        assert any("status mismatch" in f for f in failures)

    def test_both_mismatches_reported(self):
        # Both count and status are wrong → two failure messages for one vector
        bad = [([(0, 5), (10, None)], 2, 3, 99, "release_blocker")]
        original, self.m._VECTORS = self.m._VECTORS, bad
        try:
            failures = self.m._validate_model()
        finally:
            self.m._VECTORS = original
        assert any("count mismatch" in f for f in failures)
        assert any("status mismatch" in f for f in failures)


# ---------------------------------------------------------------------------
# _run_proofs
# ---------------------------------------------------------------------------


class TestRunProofs:
    def setup_method(self):
        self.m = _load_module()

    def test_z3_not_installed(self):
        """ModuleNotFoundError branch: returns a single install-hint message."""
        z3_backup = sys.modules.get("z3")
        sys.modules["z3"] = None  # type: ignore[assignment]  # sentinel: absent module
        try:
            failures = self.m._run_proofs()
        finally:
            if z3_backup is not None:
                sys.modules["z3"] = z3_backup
            else:
                sys.modules.pop("z3", None)
        assert len(failures) == 1
        assert "z3-solver is not installed" in failures[0]

    def test_all_proofs_pass(self):
        pytest.importorskip("z3")
        failures = self.m._run_proofs()
        assert failures == []

    # Solver call order inside _run_proofs:
    #   0 → P1   1 → P2   2 → P3   3 → P4   4 → P5   5 → P6   6 → P4b
    @pytest.mark.parametrize(
        "solver_index,fragment",
        [
            (0, "P1 FAILED"),
            (1, "P2 FAILED"),
            (2, "P3 FAILED"),
            (3, "P4 FAILED"),
            (4, "P5 FAILED"),
            (5, "P6 FAILED"),
        ],
    )
    def test_proof_pN_failure(self, solver_index: int, fragment: str):
        """Forcing sat at each solver index triggers the corresponding failure message."""
        import z3

        pytest.importorskip("z3")
        real_Solver = z3.Solver
        z3.Solver = _make_controlled_solver(solver_index, z3.sat)
        try:
            failures = self.m._run_proofs()
        finally:
            z3.Solver = real_Solver
        assert any(fragment in f for f in failures), f"Expected '{fragment}' in failures, got: {failures}"

    def test_p4b_unexpected_unsat_triggers_failure(self):
        """Forcing unsat at P4b solver (index 6) triggers the 'constraint redundant' failure."""
        import z3

        pytest.importorskip("z3")
        real_Solver = z3.Solver
        z3.Solver = _make_controlled_solver(6, z3.unsat)
        try:
            failures = self.m._run_proofs()
        finally:
            z3.Solver = real_Solver
        assert any("P4b UNEXPECTED" in f for f in failures), f"Expected 'P4b UNEXPECTED' in failures, got: {failures}"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def setup_method(self):
        self.m = _load_module()

    def test_model_failures_returns_1(self, capsys):
        self.m._validate_model = lambda: ["  count mismatch receipts=... expected 99, got 1"]
        result = self.m.main()
        assert result == 1
        out = capsys.readouterr().out
        assert "FAILED" in out

    def test_proof_failures_returns_1(self, capsys):
        self.m._validate_model = lambda: []
        self.m._run_proofs = lambda: ["P1 FAILED — counterexample: <model>"]
        result = self.m.main()
        assert result == 1
        out = capsys.readouterr().out
        assert "PROOF FAILURE" in out

    def test_all_pass_returns_0(self, capsys):
        self.m._validate_model = lambda: []
        self.m._run_proofs = lambda: []
        result = self.m.main()
        assert result == 0
        out = capsys.readouterr().out
        assert "formally verified" in out
