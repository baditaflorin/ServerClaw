"""Unit tests for scripts/doctor.py — ADR 0450 phase 5.1.

The aggregator is mostly orchestration over already-tested sub-tools.
Tests focus on:

  - Signal dataclass shape (so JSON consumers don't drift)
  - format_human output structure (markers, heal/explain rows)
  - CLI flags (--json, --quiet, --strict, --probes filtering)
  - graceful degradation when sub-tools are missing or error
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "doctor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("doctor", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["doctor"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def d():
    return _load_module()


# ---------------------------------------------------------------------------
# Signal dataclass shape
# ---------------------------------------------------------------------------


def test_signal_to_dict_carries_expected_keys(d):
    sig = d.Signal(name="x", headline="ok", count=0)
    out = sig.to_dict()
    assert set(out) >= {
        "name",
        "headline",
        "count",
        "detail",
        "heal_command",
        "explain_command",
        "error",
    }


# ---------------------------------------------------------------------------
# format_human
# ---------------------------------------------------------------------------


def test_format_human_marks_clean_vs_nonzero(d):
    out = d.format_human(
        [
            d.Signal(name="alpha", headline="all good", count=0),
            d.Signal(
                name="beta",
                headline="3 things broken",
                count=3,
                heal_command="make heal-beta",
                explain_command="make explain-beta",
            ),
        ]
    )
    assert "[ok]" in out
    assert "[!]" in out
    assert "make heal-beta" in out
    assert "make explain-beta" in out


def test_format_human_marks_errors_separately(d):
    out = d.format_human(
        [
            d.Signal(
                name="boom",
                headline="sub-tool errored",
                count=0,
                error="exit 2: missing yaml",
                explain_command="bash check.sh",
            )
        ]
    )
    assert "[err]" in out
    # Errored signals still show explain command since the error matters
    assert "bash check.sh" in out


def test_format_human_emits_summary_line(d):
    out = d.format_human(
        [
            d.Signal(name="a", headline="x", count=0),
            d.Signal(name="b", headline="y", count=2),
            d.Signal(name="c", headline="z", count=0, error="boom"),
        ]
    )
    assert "summary:" in out
    assert "1/3 signal(s) non-zero" in out
    assert "1 errored" in out


# ---------------------------------------------------------------------------
# Probe degradation when sub-tools missing
# ---------------------------------------------------------------------------


def test_probe_stale_receipts_handles_missing_script(d, tmp_path):
    """Sub-tool absent → Signal with error, not crash."""
    sig = d.probe_stale_receipts(tmp_path)
    assert sig.error == "script missing"
    assert sig.count == 0


def test_probe_validator_gaps_handles_missing_catalogue(d, tmp_path):
    """validator-catalogue.yaml absent → headline points at heal command."""
    sig = d.probe_validator_gaps(tmp_path)
    assert "not generated" in sig.headline
    assert sig.heal_command and "generate_validator_catalogue.py" in sig.heal_command


def test_probe_blocked_substrate_handles_missing_collections(d, tmp_path):
    """Collections base absent → count 0, no error (it's a green field)."""
    sig = d.probe_blocked_substrate(tmp_path)
    assert sig.count == 0
    assert sig.error is None


def test_probe_blocked_substrate_finds_gitkeep(d, tmp_path):
    base = tmp_path / "collections" / "ansible_collections" / "lv3" / "platform"
    base.mkdir(parents=True)
    (base / "molecule").mkdir()
    (base / "molecule" / ".gitkeep").write_text("")
    sig = d.probe_blocked_substrate(tmp_path)
    assert sig.count == 1
    assert ".gitkeep" in sig.detail["paths"][0]


def test_probe_unreserved_adrs_handles_missing_dir(d, tmp_path):
    sig = d.probe_unreserved_adrs(tmp_path)
    assert sig.error == "directory missing"


def test_probe_unreserved_adrs_classifies_disk_vs_reservations(d, tmp_path):
    import yaml

    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0445-x.md").write_text("x")
    (adr / "0500-y.md").write_text("x")
    res_dir = adr / "index"
    res_dir.mkdir()
    res = res_dir / "reservations.yaml"
    res.write_text(yaml.safe_dump({"reservations": [{"id": "r", "start": 500, "end": 500, "status": "active"}]}))
    sig = d.probe_unreserved_adrs(tmp_path)
    # 0445 is on disk and not reserved → unreserved sample
    assert "0445" in sig.detail["sample"]
    # 0500 is reserved → not in sample
    assert "0500" not in sig.detail["sample"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_default_runs_against_tmp_repo(d, tmp_path, capsys):
    """`doctor.py --root <empty>` should run, print human-readable
    output, and exit 0 — every probe degrades gracefully on an empty
    tree."""
    rc = d.main(["--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "summary:" in out


def test_cli_json_emits_structured_payload(d, tmp_path, capsys):
    rc = d.main(["--root", str(tmp_path), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "summary" in payload
    assert "signals" in payload
    assert isinstance(payload["signals"], list)


def test_cli_quiet_emits_summary_only(d, tmp_path, capsys):
    rc = d.main(["--root", str(tmp_path), "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out
    # Quiet mode is ONE line.
    assert out.count("\n") == 1
    assert "non-zero" in out


def test_cli_probes_filter_runs_subset(d, tmp_path, capsys):
    """--probes blocked_substrate runs only that probe."""
    rc = d.main(["--root", str(tmp_path), "--probes", "blocked_substrate"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "blocked_substrate" in out
    assert "stale_receipts" not in out


def test_cli_unknown_probe_returns_two(d, tmp_path, capsys):
    rc = d.main(["--root", str(tmp_path), "--probes", "ghost_probe"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "no probes matched" in err


def test_cli_strict_returns_one_when_any_signal_nonzero(d, tmp_path):
    """Stage one .gitkeep so blocked_substrate count=1, then run --strict."""
    base = tmp_path / "collections" / "ansible_collections" / "lv3" / "platform"
    base.mkdir(parents=True)
    (base / ".gitkeep").write_text("")
    rc = d.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            "blocked_substrate",
            "--strict",
            "--quiet",
        ]
    )
    assert rc == 1


def test_cli_strict_returns_zero_when_clean(d, tmp_path):
    rc = d.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            "blocked_substrate",
            "--strict",
            "--quiet",
        ]
    )
    assert rc == 0


# ---------------------------------------------------------------------------
# run_all smoke
# ---------------------------------------------------------------------------


def test_run_all_returns_one_signal_per_probe(d, tmp_path):
    signals = d.run_all(tmp_path)
    assert len(signals) == len(d.PROBES)
    names = {s.name for s in signals}
    assert "stale_receipts" in names
    assert "blocked_substrate" in names
