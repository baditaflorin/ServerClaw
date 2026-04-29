"""Tests for `scripts/reserve_adr.py --release` — ADR 0472 phase 10.3.

The release flag is the cleanup half of the reservation flow: once an
ADR file lands on main, the reservation entry has served its purpose
and should be removed so the ledger doesn't accumulate stale records.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "reserve_adr.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reserve_adr_release", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["reserve_adr_release"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ra():
    return _load_module()


def _ledger(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"schema_version": 1, "reservations": entries}))
    return p


def test_release_removes_matching_entry(ra, tmp_path, capsys):
    ledger = _ledger(
        tmp_path,
        [{"id": "res-0467", "start": 467, "end": 467, "status": "active"}],
    )
    rc = ra._release(467, reservations_path=ledger)
    assert rc == 0
    out = capsys.readouterr().out
    assert "released 1" in out
    data = yaml.safe_load(ledger.read_text())
    assert data["reservations"] == []


def test_release_idempotent_when_no_match(ra, tmp_path, capsys):
    """Releasing a number that isn't reserved is a no-op (exit 0,
    `released 0`). The caller doesn't need to track which numbers
    are still in flight."""
    ledger = _ledger(
        tmp_path,
        [{"id": "res-0500", "start": 500, "end": 500, "status": "active"}],
    )
    rc = ra._release(467, reservations_path=ledger)
    assert rc == 0
    out = capsys.readouterr().out
    assert "released 0" in out
    # Existing entry untouched.
    data = yaml.safe_load(ledger.read_text())
    assert len(data["reservations"]) == 1


def test_release_handles_range_reservation(ra, tmp_path):
    """A reservation covering 460-465 should be removed when
    releasing any number in that range."""
    ledger = _ledger(
        tmp_path,
        [{"id": "res-range", "start": 460, "end": 465, "status": "active"}],
    )
    rc = ra._release(463, reservations_path=ledger)
    assert rc == 0
    data = yaml.safe_load(ledger.read_text())
    assert data["reservations"] == []


def test_release_skips_malformed_entries(ra, tmp_path, capsys):
    """Reservations with non-integer start/end are kept untouched —
    we only act on entries we can parse."""
    ledger = _ledger(
        tmp_path,
        [
            {"id": "ok", "start": 467, "end": 467, "status": "active"},
            {"id": "bad", "start": "oops", "end": 200, "status": "active"},
            "not-a-mapping",
        ],
    )
    rc = ra._release(467, reservations_path=ledger)
    assert rc == 0
    data = yaml.safe_load(ledger.read_text())
    # Only the parseable ok entry was matched + removed; bad + non-mapping
    # remain.
    ids = [(e.get("id") if isinstance(e, dict) else e) for e in data["reservations"]]
    assert "ok" not in ids
    assert "bad" in ids
    assert "not-a-mapping" in ids


def test_release_negative_number_returns_two(ra, tmp_path, capsys):
    ledger = _ledger(tmp_path, [])
    rc = ra._release(-1, reservations_path=ledger)
    assert rc == 2
    err = capsys.readouterr().err
    assert ">= 1" in err


def test_release_missing_ledger_returns_two(ra, tmp_path, capsys):
    rc = ra._release(467, reservations_path=tmp_path / "no-such.yaml")
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing" in err.lower()


def test_release_non_list_top_level_returns_two(ra, tmp_path, capsys):
    p = tmp_path / "reservations.yaml"
    p.write_text(yaml.safe_dump({"reservations": "not-a-list"}))
    rc = ra._release(467, reservations_path=p)
    assert rc == 2


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_release_works_end_to_end(ra, tmp_path, capsys):
    ledger = _ledger(
        tmp_path,
        [{"id": "res-0467", "start": 467, "end": 467, "status": "active"}],
    )
    rc = ra.main(
        [
            "--release",
            "467",
            "--reservations-path",
            str(ledger),
        ]
    )
    assert rc == 0
    data = yaml.safe_load(ledger.read_text())
    assert data["reservations"] == []
