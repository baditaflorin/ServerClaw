"""Unit tests for scripts/doctor_regression_watch.py — ADR 0465 phase 9.3.

Synthetic baseline + current JSONs under tmp_path exercise the full
diff matrix. The Windmill schedule template is shipped alongside but
isn't unit-tested — its activation belongs to operators with API
access.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "doctor_regression_watch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("doctor_regression_watch", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["doctor_regression_watch"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drw():
    return _load_module()


def _doctor_payload(signals: dict[str, int]) -> dict:
    """Synthesise a doctor --json-shaped payload."""
    return {
        "summary": {"total": len(signals), "nonzero": sum(1 for v in signals.values() if v > 0)},
        "signals": [{"name": name, "headline": f"{name} headline", "count": count} for name, count in signals.items()],
    }


def _write_payload(path: Path, signals: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_doctor_payload(signals)))


# ---------------------------------------------------------------------------
# load_doctor_json
# ---------------------------------------------------------------------------


def test_load_doctor_json_picks_up_signals(drw, tmp_path):
    p = tmp_path / "doctor.json"
    _write_payload(p, {"alpha": 0, "beta": 3})
    out = drw.load_doctor_json(p)
    assert out == {"alpha": 0, "beta": 3}


def test_load_doctor_json_tolerates_snapshot_envelope(drw, tmp_path):
    """The snapshot mode wraps the doctor payload in a freshness
    envelope (head_sha + generated_at). The loader handles both."""
    p = tmp_path / "snapshot.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "head_sha": "deadbeef",
                "generated_at": "2026-04-29T08:00:00Z",
                **_doctor_payload({"alpha": 1}),
            }
        )
    )
    out = drw.load_doctor_json(p)
    assert out == {"alpha": 1}


def test_load_doctor_json_rejects_missing_signals(drw, tmp_path):
    p = tmp_path / "broken.json"
    p.write_text(json.dumps({"summary": {}}))
    with pytest.raises(ValueError, match="missing 'signals'"):
        drw.load_doctor_json(p)


def test_load_doctor_json_skips_bad_count_values(drw, tmp_path):
    """Defensive: a signal with non-integer count gets coerced to 0
    rather than crashing."""
    p = tmp_path / "weird.json"
    p.write_text(
        json.dumps(
            {
                "summary": {},
                "signals": [
                    {"name": "alpha", "count": "not-a-number"},
                    {"name": "beta", "count": 5},
                ],
            }
        )
    )
    out = drw.load_doctor_json(p)
    assert out == {"alpha": 0, "beta": 5}


# ---------------------------------------------------------------------------
# latest_baseline
# ---------------------------------------------------------------------------


def test_latest_baseline_picks_lexically_greatest(drw, tmp_path):
    (tmp_path / "2026-01-01.json").write_text("{}")
    (tmp_path / "2026-04-29.json").write_text("{}")
    (tmp_path / "2026-02-15.json").write_text("{}")
    out = drw.latest_baseline(tmp_path)
    assert out is not None
    assert out.name == "2026-04-29.json"


def test_latest_baseline_handles_missing_dir(drw, tmp_path):
    assert drw.latest_baseline(tmp_path / "no-such-dir") is None


def test_latest_baseline_handles_empty_dir(drw, tmp_path):
    assert drw.latest_baseline(tmp_path) is None


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


def test_compute_diff_classifies_regression(drw):
    deltas = drw.compute_diff({"alpha": 0}, {"alpha": 5})
    assert len(deltas) == 1
    assert deltas[0].kind == "regression"
    assert deltas[0].baseline_count == 0
    assert deltas[0].current_count == 5


def test_compute_diff_classifies_improvement(drw):
    deltas = drw.compute_diff({"alpha": 5}, {"alpha": 0})
    assert deltas[0].kind == "improvement"


def test_compute_diff_classifies_persistent(drw):
    deltas = drw.compute_diff({"alpha": 3}, {"alpha": 7})
    assert deltas[0].kind == "persistent"


def test_compute_diff_classifies_new_signal(drw):
    deltas = drw.compute_diff({}, {"alpha": 0})
    assert deltas[0].kind == "new"
    assert deltas[0].baseline_count is None


def test_compute_diff_classifies_removed_signal(drw):
    deltas = drw.compute_diff({"alpha": 5}, {})
    assert deltas[0].kind == "removed"
    assert deltas[0].current_count is None


def test_compute_diff_classifies_stable(drw):
    """Both 0 in baseline and current → stable. The full classification
    is reported in --json; human output skips it."""
    deltas = drw.compute_diff({"alpha": 0}, {"alpha": 0})
    assert deltas[0].kind == "stable"


def test_compute_diff_full_matrix(drw):
    """End-to-end: a realistic mix surfaces every category."""
    baseline = {"alpha": 0, "beta": 3, "gamma": 0, "delta": 5}
    current = {"alpha": 2, "beta": 0, "gamma": 0, "epsilon": 1}
    deltas = drw.compute_diff(baseline, current)
    by_kind = {d.name: d.kind for d in deltas}
    assert by_kind["alpha"] == "regression"
    assert by_kind["beta"] == "improvement"
    assert by_kind["gamma"] == "stable"
    assert by_kind["delta"] == "removed"  # was in baseline, gone now
    assert by_kind["epsilon"] == "new"


# ---------------------------------------------------------------------------
# RegressionReport
# ---------------------------------------------------------------------------


def test_regression_report_summary(drw):
    deltas = drw.compute_diff({"a": 0, "b": 0, "c": 5}, {"a": 1, "b": 0, "c": 0})
    report = drw.RegressionReport(
        baseline_path="b.json",
        current_path="c.json",
        deltas=deltas,
    )
    summary = report.summary()
    assert summary["regressions"] == 1  # a flipped 0 → 1
    assert summary["improvements"] == 1  # c flipped 5 → 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_no_baseline_returns_two(drw, tmp_path, capsys):
    rc = drw.main(["--baseline-dir", str(tmp_path / "missing")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no baseline" in err.lower()


def test_cli_no_current_returns_two(drw, tmp_path, capsys):
    baseline_dir = tmp_path / "baselines"
    _write_payload(baseline_dir / "b.json", {"alpha": 0})
    rc = drw.main(
        [
            "--baseline-dir",
            str(baseline_dir),
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "current snapshot" in err.lower()


def test_cli_no_regressions_returns_zero(drw, tmp_path, capsys):
    """Identical baseline + current → no regressions → exit 0."""
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _write_payload(baseline, {"alpha": 0, "beta": 0})
    _write_payload(current, {"alpha": 0, "beta": 0})
    rc = drw.main(
        ["--baseline", str(baseline), "--current", str(current)],
    )
    assert rc == 0


def test_cli_regression_returns_one(drw, tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _write_payload(baseline, {"alpha": 0})
    _write_payload(current, {"alpha": 3})
    rc = drw.main(
        ["--baseline", str(baseline), "--current", str(current)],
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "regression" in out.lower()


def test_cli_json_output(drw, tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    _write_payload(baseline, {"alpha": 0, "beta": 3})
    _write_payload(current, {"alpha": 2, "beta": 0})
    rc = drw.main(
        ["--baseline", str(baseline), "--current", str(current), "--json"],
    )
    assert rc == 1  # alpha regressed
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["regressions"] == 1
    assert payload["summary"]["improvements"] == 1


def test_cli_uses_latest_baseline_when_omitted(drw, tmp_path, capsys):
    """When --baseline is omitted, the script uses latest_baseline()
    against the baseline-dir."""
    baseline_dir = tmp_path / "baselines"
    _write_payload(baseline_dir / "2026-04-01.json", {"alpha": 0})
    _write_payload(baseline_dir / "2026-04-29.json", {"alpha": 0})
    current = tmp_path / "current.json"
    _write_payload(current, {"alpha": 5})
    rc = drw.main(
        [
            "--baseline-dir",
            str(baseline_dir),
            "--current",
            str(current),
        ]
    )
    assert rc == 1  # regression detected against latest baseline
