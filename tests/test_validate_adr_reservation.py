"""Unit tests for scripts/validate_adr_reservation.py — ADR 0472 phase 10.2.

The git-integration paths (`origin/main` lookup, diff scanning) are
mocked via monkeypatching `_git`; the pure logic (filename parse,
reservation set, find_unreserved_adrs) is exercised against
synthetic fixtures.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_adr_reservation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_adr_reservation", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["validate_adr_reservation"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def var():
    return _load_module()


# ---------------------------------------------------------------------------
# _extract_adr_numbers
# ---------------------------------------------------------------------------


def test_extract_adr_numbers_picks_up_full_and_bare_paths(var):
    out = var._extract_adr_numbers(
        [
            "docs/adr/0467-phase10-reservation.md",
            "0468-other.md",
            "docs/adr/.index.yaml",  # not an ADR file
            "scripts/foo.py",  # not in adr dir
            "",
        ]
    )
    assert out == {467, 468}


def test_extract_adr_numbers_skips_non_4digit_prefixes(var):
    out = var._extract_adr_numbers(["docs/adr/123-three-digits.md", "docs/adr/0467-ok.md"])
    assert out == {467}


# ---------------------------------------------------------------------------
# reservation_numbers
# ---------------------------------------------------------------------------


def test_reservation_numbers_picks_up_range_entries(var, tmp_path):
    p = tmp_path / "reservations.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "reservations": [
                    {"id": "single", "start": 467, "end": 467, "status": "active"},
                    {"id": "range", "start": 470, "end": 472, "status": "active"},
                    {"id": "released", "start": 500, "end": 500, "status": "released"},
                ]
            }
        )
    )
    out = var.reservation_numbers(p)
    # Released reservations still count — the gate cares whether the
    # number was ever reserved, not whether the reservation is current.
    assert out == {467, 470, 471, 472, 500}


def test_reservation_numbers_handles_missing_file(var, tmp_path):
    assert var.reservation_numbers(tmp_path / "nope.yaml") == set()


def test_reservation_numbers_handles_malformed_yaml(var, tmp_path):
    p = tmp_path / "reservations.yaml"
    p.write_text("[: not yaml")
    assert var.reservation_numbers(p) == set()


def test_reservation_numbers_handles_non_list_reservations(var, tmp_path):
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": "not-a-list"}))
    assert var.reservation_numbers(p) == set()


def test_reservation_numbers_skips_malformed_entries(var, tmp_path):
    p = tmp_path / "reservations.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "reservations": [
                    {"id": "ok", "start": 467, "end": 467, "status": "active"},
                    {"id": "bad", "start": "oops", "end": 200, "status": "active"},
                    "not-a-mapping",
                ]
            }
        )
    )
    assert var.reservation_numbers(p) == {467}


# ---------------------------------------------------------------------------
# find_unreserved_adrs
# ---------------------------------------------------------------------------


def _patched(monkeypatch, *, added: set[int], on_origin_reservations: set[int]):
    """Mock the git-integration helpers so tests don't shell out."""

    def fake_added(base_ref, head_ref):
        return added

    def fake_origin_reservations(*args, **kwargs):
        return on_origin_reservations

    return fake_added, fake_origin_reservations


def test_find_unreserved_passes_when_added_match_origin_reservation(var, tmp_path, monkeypatch):
    """Common case: agent reserved 0467 via the early-merge flow.
    By the time the ADR PR opens, the reservation is already on
    origin. The gate passes."""
    fake_added, fake_origin = _patched(monkeypatch, added={467}, on_origin_reservations={467})
    monkeypatch.setattr(var, "added_adrs_in_diff", fake_added)
    monkeypatch.setattr(var, "origin_reservation_numbers", fake_origin)
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": []}))
    out = var.find_unreserved_adrs(reservations_path=p)
    assert out == []


def test_find_unreserved_passes_when_atomic_pr_includes_reservation(var, tmp_path, monkeypatch):
    """Operator skipped the early-merge step but added BOTH the ADR
    AND the reservation entry in one PR. Gate accepts because the
    local reservations file (visible to the gate) backs the new
    ADR."""
    fake_added, fake_origin = _patched(monkeypatch, added={467}, on_origin_reservations=set())
    monkeypatch.setattr(var, "added_adrs_in_diff", fake_added)
    monkeypatch.setattr(var, "origin_reservation_numbers", fake_origin)
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": [{"id": "res-0467", "start": 467, "end": 467, "status": "active"}]}))
    out = var.find_unreserved_adrs(reservations_path=p)
    assert out == []


def test_find_unreserved_fails_when_no_reservation_anywhere(var, tmp_path, monkeypatch):
    """The collision case: ADR 0467 added by this PR with no
    reservation either on origin or in this PR's local file."""
    fake_added, fake_origin = _patched(monkeypatch, added={467}, on_origin_reservations=set())
    monkeypatch.setattr(var, "added_adrs_in_diff", fake_added)
    monkeypatch.setattr(var, "origin_reservation_numbers", fake_origin)
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": []}))
    out = var.find_unreserved_adrs(reservations_path=p)
    assert out == [467]


def test_find_unreserved_returns_multiple(var, tmp_path, monkeypatch):
    fake_added, fake_origin = _patched(monkeypatch, added={467, 468, 470}, on_origin_reservations={468})
    monkeypatch.setattr(var, "added_adrs_in_diff", fake_added)
    monkeypatch.setattr(var, "origin_reservation_numbers", fake_origin)
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": []}))
    out = var.find_unreserved_adrs(reservations_path=p)
    # 467 + 470 unreserved; 468 is on origin → passes.
    assert out == [467, 470]


def test_find_unreserved_no_added_adrs_returns_empty(var, tmp_path, monkeypatch):
    fake_added, fake_origin = _patched(monkeypatch, added=set(), on_origin_reservations=set())
    monkeypatch.setattr(var, "added_adrs_in_diff", fake_added)
    monkeypatch.setattr(var, "origin_reservation_numbers", fake_origin)
    out = var.find_unreserved_adrs(reservations_path=tmp_path / "no.yaml")
    assert out == []


def test_find_unreserved_all_files_mode(var, tmp_path, monkeypatch):
    """`--all-files` walks disk + compares against origin disk +
    reservations. Useful for the `all` lane in validate_repo.sh."""
    adr = tmp_path / "adr"
    adr.mkdir()
    (adr / "0467-phase10.md").write_text("x")
    (adr / "0468-other.md").write_text("x")
    monkeypatch.setattr(var, "adrs_on_origin", lambda origin_ref="origin/main": {467})
    monkeypatch.setattr(var, "origin_reservation_numbers", lambda: set())
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": []}))
    out = var.find_unreserved_adrs(
        adr_dir=adr,
        reservations_path=p,
        all_files=True,
    )
    # 467 already on origin → no longer "new"; 468 added on disk + no
    # reservation → flagged.
    assert out == [468]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_clean_passes_with_zero(var, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(var, "added_adrs_in_diff", lambda **kw: set())
    monkeypatch.setattr(var, "origin_reservation_numbers", lambda *a, **k: set())
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": []}))
    rc = var.main(["--reservations-path", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "every added ADR is backed" in out


def test_cli_unreserved_returns_one(var, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(var, "added_adrs_in_diff", lambda **kw: {467})
    monkeypatch.setattr(var, "origin_reservation_numbers", lambda *a, **k: set())
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": []}))
    rc = var.main(["--reservations-path", str(p)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ADR 0467" in err


def test_cli_advisory_swallows_findings(var, tmp_path, capsys, monkeypatch):
    """During the rollout window, --advisory keeps the gate from
    blocking pushes while still surfacing the warning. Mirror of the
    pattern used by Phase 1's late-bound-default rule."""
    monkeypatch.setattr(var, "added_adrs_in_diff", lambda **kw: {467})
    monkeypatch.setattr(var, "origin_reservation_numbers", lambda *a, **k: set())
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": []}))
    rc = var.main(["--reservations-path", str(p), "--advisory"])
    assert rc == 0  # advisory mode swallows the finding
    err = capsys.readouterr().err
    assert "ADR 0467" in err  # but still surfaced
