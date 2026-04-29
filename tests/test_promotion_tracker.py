"""Unit tests for scripts/promotion_tracker.py — ADR 0460 phase 8.1.

Synthetic ledger trees under tmp_path exercise the full classification
matrix. The live receipts/gate-runs/ tree is not exercised — it
changes over time and would couple test outcomes to operator history.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "promotion_tracker.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("promotion_tracker", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["promotion_tracker"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pt():
    return _load_module()


def _write_entry(
    ledger_dir: Path,
    *,
    gate: str,
    timestamp: str,
    result: str = "clean",
    rule: str | None = None,
    finding_count: int = 0,
    mode: str = "advisory",
    session_id: str | None = "test-session",
) -> Path:
    """Drop a synthetic ledger entry under <ledger>/<gate>/<timestamp>.yaml.

    Timestamps are pure strings — the schema mandates ISO format and we
    sort lexically. Tests pass timestamps in the order they want
    chronological resolution.
    """
    gate_dir = ledger_dir / gate
    gate_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "gate": gate,
        "ran_on": timestamp,
        "result": result,
        "finding_count": finding_count,
        "mode": mode,
        "session_id": session_id,
    }
    if rule is not None:
        payload["rule"] = rule
    path = gate_dir / f"{timestamp.replace(':', '').replace('-', '')}.yaml"
    path.write_text(yaml.safe_dump(payload))
    return path


# ---------------------------------------------------------------------------
# load_ledger
# ---------------------------------------------------------------------------


def test_load_ledger_skips_missing_directory(pt, tmp_path):
    assert pt.load_ledger(tmp_path / "no-such-dir") == []


def test_load_ledger_picks_up_real_entries(pt, tmp_path):
    ledger = tmp_path / "gate-runs"
    _write_entry(ledger, gate="alpha", timestamp="2026-04-01T08:00:00Z")
    _write_entry(ledger, gate="beta", timestamp="2026-04-02T08:00:00Z", rule="r1")
    out = pt.load_ledger(ledger)
    assert len(out) == 2
    by_gate = {(e.gate, e.rule) for e in out}
    assert by_gate == {("alpha", None), ("beta", "r1")}


def test_load_ledger_skips_malformed_entries(pt, tmp_path):
    """A YAML file with the wrong shape (missing gate, broken result,
    not a mapping) must be skipped, not crash the run."""
    ledger = tmp_path / "gate-runs"
    gate_dir = ledger / "messy"
    gate_dir.mkdir(parents=True)
    (gate_dir / "no-gate.yaml").write_text(yaml.safe_dump({"ran_on": "x"}))
    (gate_dir / "bad-result.yaml").write_text(yaml.safe_dump({"gate": "messy", "result": "wat", "ran_on": "x"}))
    (gate_dir / "not-mapping.yaml").write_text(yaml.safe_dump(["a", "b"]))
    (gate_dir / "broken.yaml").write_text("this is :: not yaml ::")
    # Plus a valid entry so we know the loop continues.
    _write_entry(ledger, gate="messy", timestamp="2026-04-01T08:00:00Z")
    out = pt.load_ledger(ledger)
    assert len(out) == 1
    assert out[0].result == "clean"


def test_load_ledger_skips_non_directory_siblings(pt, tmp_path):
    """README.md and other top-level files under receipts/gate-runs/
    must be ignored — load_ledger only walks gate subdirectories."""
    ledger = tmp_path / "gate-runs"
    ledger.mkdir()
    (ledger / "README.md").write_text("docs")
    (ledger / "scratch.yaml").write_text("ignore")
    _write_entry(ledger, gate="alpha", timestamp="2026-04-01T08:00:00Z")
    out = pt.load_ledger(ledger)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# group_by_gate
# ---------------------------------------------------------------------------


def test_group_by_gate_sorts_chronologically(pt, tmp_path):
    ledger = tmp_path / "gate-runs"
    _write_entry(ledger, gate="alpha", timestamp="2026-04-03T08:00:00Z", finding_count=3, result="findings")
    _write_entry(ledger, gate="alpha", timestamp="2026-04-01T08:00:00Z")
    _write_entry(ledger, gate="alpha", timestamp="2026-04-02T08:00:00Z")
    entries = pt.load_ledger(ledger)
    grouped = pt.group_by_gate(entries)
    series = grouped[("alpha", None)]
    assert [e.ran_on for e in series] == [
        "2026-04-01T08:00:00Z",
        "2026-04-02T08:00:00Z",
        "2026-04-03T08:00:00Z",
    ]


# ---------------------------------------------------------------------------
# classify_gate
# ---------------------------------------------------------------------------


def _entry(pt, *, ran_on: str, result: str = "clean", mode: str = "advisory") -> "object":
    return pt.GateRunEntry(
        gate="g",
        rule=None,
        ran_on=ran_on,
        result=result,
        finding_count=0 if result == "clean" else 1,
        mode=mode,
        session_id="test",
        source_path="test.yaml",
    )


def test_classify_unknown_when_no_entries(pt):
    c = pt.classify_gate([])
    assert c.status == "unknown"


def test_classify_promoted_when_last_required(pt):
    """Most recent entry has mode=required → already promoted."""
    entries = [
        _entry(pt, ran_on="2026-04-01T00:00:00Z", result="clean"),
        _entry(pt, ran_on="2026-04-02T00:00:00Z", result="clean", mode="required"),
    ]
    c = pt.classify_gate(entries)
    assert c.status == "promoted"
    assert c.current_mode == "required"


def test_classify_eligible_after_three_clean(pt):
    entries = [
        _entry(pt, ran_on="2026-04-01T00:00:00Z", result="clean"),
        _entry(pt, ran_on="2026-04-02T00:00:00Z", result="clean"),
        _entry(pt, ran_on="2026-04-03T00:00:00Z", result="clean"),
    ]
    c = pt.classify_gate(entries)
    assert c.status == "eligible"
    assert c.last_clean_count == 3


def test_classify_streaking_when_under_threshold(pt):
    """One clean run, no prior entries → streaking, not eligible."""
    entries = [_entry(pt, ran_on="2026-04-01T00:00:00Z", result="clean")]
    c = pt.classify_gate(entries, min_clean_runs=3)
    assert c.status == "streaking"
    assert c.last_clean_count == 1


def test_classify_unstable_when_recent_findings(pt):
    """Latest is clean, but a prior entry in the window had findings →
    unstable until 3 clean in a row resume."""
    entries = [
        _entry(pt, ran_on="2026-04-01T00:00:00Z", result="findings"),
        _entry(pt, ran_on="2026-04-02T00:00:00Z", result="clean"),
        _entry(pt, ran_on="2026-04-03T00:00:00Z", result="clean"),
    ]
    c = pt.classify_gate(entries, min_clean_runs=3, window=5)
    # 2 clean in a row, but window contains a findings entry → unstable.
    assert c.status == "unstable"


def test_classify_eligible_when_unstable_aged_out_of_window(pt):
    """A findings entry older than the window is not unstable evidence
    anymore — the gate has recovered with enough clean runs."""
    entries = [
        _entry(pt, ran_on="2026-03-01T00:00:00Z", result="findings"),
        _entry(pt, ran_on="2026-04-01T00:00:00Z", result="clean"),
        _entry(pt, ran_on="2026-04-02T00:00:00Z", result="clean"),
        _entry(pt, ran_on="2026-04-03T00:00:00Z", result="clean"),
    ]
    c = pt.classify_gate(entries, min_clean_runs=3, window=3)
    # window=3 → only the 3 clean entries count → eligible.
    assert c.status == "eligible"


def test_classify_uses_run_streak_from_tail(pt):
    """Streak is counted from the most recent entry backwards. A clean
    run at the start does NOT count toward the trailing streak."""
    entries = [
        _entry(pt, ran_on="2026-04-01T00:00:00Z", result="clean"),
        _entry(pt, ran_on="2026-04-02T00:00:00Z", result="findings"),
        _entry(pt, ran_on="2026-04-03T00:00:00Z", result="clean"),
    ]
    c = pt.classify_gate(entries, min_clean_runs=3, window=5)
    # Trailing streak is 1 (just 2026-04-03); window has findings → unstable.
    assert c.status == "unstable"
    assert c.last_clean_count == 1


# ---------------------------------------------------------------------------
# classify_all + CLI
# ---------------------------------------------------------------------------


def test_classify_all_returns_one_per_gate(pt, tmp_path):
    ledger = tmp_path / "gate-runs"
    for ts in ("2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z", "2026-04-03T00:00:00Z"):
        _write_entry(ledger, gate="alpha", timestamp=ts, result="clean")
    _write_entry(ledger, gate="beta", timestamp="2026-04-01T00:00:00Z", result="findings")
    out = pt.classify_all(pt.load_ledger(ledger))
    by_gate = {c.gate: c for c in out}
    assert by_gate["alpha"].status == "eligible"
    assert by_gate["beta"].status == "unstable"


def test_cli_negative_args_return_two(pt):
    rc = pt.main(["--min-clean-runs", "0"])
    assert rc == 2


def test_cli_human_output_on_empty_ledger(pt, tmp_path, capsys):
    rc = pt.main(["--ledger", str(tmp_path / "missing")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no ledger entries" in out


def test_cli_human_output_with_eligible_gate(pt, tmp_path, capsys):
    ledger = tmp_path / "gate-runs"
    for ts in ("2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z", "2026-04-03T00:00:00Z"):
        _write_entry(ledger, gate="alpha", timestamp=ts, result="clean")
    rc = pt.main(["--ledger", str(ledger)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "eligible for promotion" in out
    assert "alpha" in out


def test_cli_json_output_summary_counts(pt, tmp_path, capsys):
    ledger = tmp_path / "gate-runs"
    for ts in ("2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z", "2026-04-03T00:00:00Z"):
        _write_entry(ledger, gate="alpha", timestamp=ts, result="clean")
    _write_entry(ledger, gate="beta", timestamp="2026-04-01T00:00:00Z", result="findings")
    rc = pt.main(["--ledger", str(ledger), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["by_status"]["eligible"] == 1
    assert payload["summary"]["by_status"]["unstable"] == 1


def test_cli_list_terse_format(pt, tmp_path, capsys):
    ledger = tmp_path / "gate-runs"
    for ts in ("2026-04-01T00:00:00Z", "2026-04-02T00:00:00Z", "2026-04-03T00:00:00Z"):
        _write_entry(ledger, gate="alpha", timestamp=ts, result="clean")
    rc = pt.main(["--ledger", str(ledger), "--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "eligible" in out
    assert "alpha" in out
