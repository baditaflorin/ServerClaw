"""Unit tests for scripts/heal.py — ADR 0451 phase 6.2.

The orchestrator's logic is small (filter signals, run commands,
format output). Tests focus on:

  - actionable_signals filter (count + heal_command predicates)
  - format_dry_run / format_apply_summary shape
  - CLI dry-run vs --apply branching
  - graceful degradation when doctor.py is missing or returns junk
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "heal.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("heal", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["heal"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def h():
    return _load_module()


# ---------------------------------------------------------------------------
# actionable_signals
# ---------------------------------------------------------------------------


def test_actionable_signals_requires_count_and_heal_command(h):
    signals = [
        {"name": "a", "count": 0, "heal_command": "x"},  # zero count → skip
        {"name": "b", "count": 5, "heal_command": ""},  # empty heal → skip
        {"name": "c", "count": 5, "heal_command": None},  # null heal → skip
        {"name": "d", "count": 3, "heal_command": "make heal-d"},  # ✓
    ]
    out = h.actionable_signals(signals)
    assert [s["name"] for s in out] == ["d"]


def test_actionable_signals_handles_missing_keys(h):
    """Defensive: if doctor's JSON shape changes, we should not crash —
    just filter out the malformed entries."""
    signals = [{}, {"name": "a"}, {"name": "b", "count": 1}]
    out = h.actionable_signals(signals)
    assert out == []


# ---------------------------------------------------------------------------
# format_dry_run
# ---------------------------------------------------------------------------


def test_format_dry_run_with_actionable(h):
    out = h.format_dry_run(
        [
            {"name": "alpha", "count": 1, "heal_command": "make heal-alpha"},
            {"name": "skip_me", "count": 0, "heal_command": "ignored"},
        ]
    )
    assert "1 signal(s) have heal commands" in out
    assert "alpha" in out
    assert "make heal-alpha" in out
    assert "Pass --apply" in out


def test_format_dry_run_with_no_actionable(h):
    out = h.format_dry_run([{"name": "x", "count": 0, "heal_command": "y"}])
    assert "no actionable signals" in out


# ---------------------------------------------------------------------------
# format_apply_summary
# ---------------------------------------------------------------------------


def test_format_apply_summary_shows_pass_fail(h):
    outcomes = [
        h.HealOutcome("alpha", "make heal-alpha", True, 0, None),
        h.HealOutcome("beta", "make heal-beta", True, 1, "boom"),
    ]
    out = h.format_apply_summary(outcomes)
    assert "[ok ]" in out
    assert "[fail]" in out
    assert "boom" in out
    assert "1/2" in out


def test_format_apply_summary_handles_empty(h):
    assert "no heal commands" in h.format_apply_summary([])


# ---------------------------------------------------------------------------
# load_doctor_signals — error paths
# ---------------------------------------------------------------------------


def test_load_doctor_signals_handles_missing_doctor(h, tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DOCTOR_SCRIPT", tmp_path / "no-such-doctor.py")
    with pytest.raises(RuntimeError, match="not found"):
        h.load_doctor_signals(tmp_path)


# ---------------------------------------------------------------------------
# run_heal
# ---------------------------------------------------------------------------


def test_run_heal_runs_real_bash_command(h, tmp_path):
    """A trivial `true` command exits 0; we use it to confirm the
    bash-c invocation path works without mocking subprocess."""
    outcome = h.run_heal(
        {"name": "alpha", "heal_command": "true"},
        cwd=tmp_path,
    )
    assert outcome.ran is True
    assert outcome.exit_code == 0
    assert outcome.stderr_summary is None


def test_run_heal_captures_failure_exit_code(h, tmp_path):
    outcome = h.run_heal(
        {"name": "beta", "heal_command": "false"},
        cwd=tmp_path,
    )
    assert outcome.ran is True
    assert outcome.exit_code == 1


def test_run_heal_skips_signals_without_heal_command(h, tmp_path):
    outcome = h.run_heal({"name": "x", "heal_command": ""}, cwd=tmp_path)
    assert outcome.ran is False
    assert outcome.exit_code is None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_does_not_execute(h, tmp_path, monkeypatch, capsys):
    """In dry-run mode the orchestrator must not touch run_heal at all."""
    monkeypatch.setattr(
        h,
        "load_doctor_signals",
        lambda root: [{"name": "alpha", "count": 1, "heal_command": "echo would not run"}],
    )

    def boom(*a, **kw):
        raise AssertionError("dry-run must not call run_heal")

    monkeypatch.setattr(h, "run_heal", boom)
    rc = h.main(["--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "would run" in out


def test_cli_apply_runs_each_heal(h, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        h,
        "load_doctor_signals",
        lambda root: [
            {"name": "alpha", "count": 1, "heal_command": "true"},
            {"name": "beta", "count": 2, "heal_command": "false"},
        ],
    )
    rc = h.main(["--root", str(tmp_path), "--apply"])
    # One heal failed → exit 1.
    assert rc == 1
    out = capsys.readouterr().out
    assert "alpha" in out and "beta" in out


def test_cli_apply_returns_zero_when_all_heals_pass(h, tmp_path, monkeypatch):
    monkeypatch.setattr(
        h,
        "load_doctor_signals",
        lambda root: [{"name": "alpha", "count": 1, "heal_command": "true"}],
    )
    rc = h.main(["--root", str(tmp_path), "--apply"])
    assert rc == 0


def test_cli_doctor_missing_returns_two(h, tmp_path, monkeypatch, capsys):
    def raise_runtime(root):
        raise RuntimeError("doctor.py not found")

    monkeypatch.setattr(h, "load_doctor_signals", raise_runtime)
    rc = h.main(["--root", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "doctor" in err.lower()


def test_cli_json_dry_run_emits_payload(h, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        h,
        "load_doctor_signals",
        lambda root: [{"name": "x", "count": 1, "heal_command": "y"}],
    )
    rc = h.main(["--root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry_run"
    assert payload["signals"][0]["name"] == "x"
