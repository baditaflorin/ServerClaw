"""Unit tests for scripts/mass_refresh_receipts.py — ADR 0474 phase 12.1.

The classifier subprocess is mocked via monkeypatch on
`run_classifier`; the orchestrator's pure logic (summary parsing,
receipt write) is exercised against synthetic fixtures.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "mass_refresh_receipts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("mass_refresh_receipts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["mass_refresh_receipts"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mrr():
    return _load_module()


# ---------------------------------------------------------------------------
# parse_classifier_output / summary_from
# ---------------------------------------------------------------------------


def test_parse_classifier_output_handles_empty(mrr):
    assert mrr.parse_classifier_output("") == {}


def test_parse_classifier_output_handles_garbage(mrr):
    assert mrr.parse_classifier_output("not-json") == {}


def test_parse_classifier_output_passes_through_json(mrr):
    assert mrr.parse_classifier_output('{"summary": {"safe_to_refresh": 1}}') == {"summary": {"safe_to_refresh": 1}}


def test_summary_from_extracts_summary_envelope(mrr):
    payload = {"summary": {"safe_to_refresh": 12, "needs_review": 4, "unknown": 1, "total": 17}}
    assert mrr.summary_from(payload) == {
        "safe_to_refresh": 12,
        "needs_review": 4,
        "unknown": 1,
        "total": 17,
    }


def test_summary_from_falls_back_to_list_lengths(mrr):
    payload = {
        "safe_to_refresh": [{"service": "a"}, {"service": "b"}],
        "needs_review": [{"service": "c"}],
        "unknown": [],
    }
    assert mrr.summary_from(payload) == {
        "safe_to_refresh": 2,
        "needs_review": 1,
        "unknown": 0,
        "total": 3,
    }


def test_summary_from_handles_empty_payload(mrr):
    assert mrr.summary_from({}) == {
        "safe_to_refresh": 0,
        "needs_review": 0,
        "unknown": 0,
        "total": 0,
    }


# ---------------------------------------------------------------------------
# write_receipt
# ---------------------------------------------------------------------------


def test_write_receipt_creates_file_with_summary(mrr, tmp_path):
    ts = dt.datetime(2026, 4, 29, 12, 0, 0)
    out = mrr.write_receipt(
        receipts_dir=tmp_path,
        summary={"safe_to_refresh": 5, "needs_review": 2, "unknown": 0, "total": 7},
        applied=True,
        timestamp=ts,
    )
    assert out.is_file()
    parsed = yaml.safe_load(out.read_text())
    assert parsed["applied"] is True
    assert parsed["summary"]["safe_to_refresh"] == 5
    assert parsed["ran_at"].startswith("2026-04-29T12:00:00")


def test_write_receipt_creates_dir(mrr, tmp_path):
    ts = dt.datetime(2026, 4, 29, 0, 0, 0)
    target = tmp_path / "nested" / "heal-receipts"
    out = mrr.write_receipt(receipts_dir=target, summary={}, applied=False, timestamp=ts)
    assert out.parent.is_dir()


# ---------------------------------------------------------------------------
# render_summary_line
# ---------------------------------------------------------------------------


def test_render_summary_line(mrr):
    line = mrr.render_summary_line({"safe_to_refresh": 12, "needs_review": 4, "unknown": 1, "total": 17})
    assert "safe=12" in line
    assert "needs_review=4" in line
    assert "unknown=1" in line
    assert "total=17" in line


def test_render_summary_line_handles_missing_keys(mrr):
    line = mrr.render_summary_line({})
    assert "safe=0" in line and "total=0" in line


# ---------------------------------------------------------------------------
# main — classifier mocked
# ---------------------------------------------------------------------------


def _patch_classifier(monkeypatch, mrr, *, rc: int, stdout: str, stderr: str = ""):
    def fake_run(*, apply=False, max_age_days=None, extra_args=None):
        return rc, stdout, stderr

    monkeypatch.setattr(mrr, "run_classifier", fake_run)


def test_main_classify_only_returns_0(mrr, tmp_path, capsys, monkeypatch):
    _patch_classifier(
        monkeypatch,
        mrr,
        rc=0,
        stdout=json.dumps({"summary": {"safe_to_refresh": 3, "needs_review": 1, "unknown": 0, "total": 4}}),
    )
    rc = mrr.main(["--receipts-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "safe=3" in out
    receipts = list(tmp_path.glob("*.yaml"))
    assert len(receipts) == 1


def test_main_apply_returns_0(mrr, tmp_path, monkeypatch):
    _patch_classifier(
        monkeypatch,
        mrr,
        rc=0,
        stdout=json.dumps({"summary": {"safe_to_refresh": 2, "needs_review": 0, "unknown": 0, "total": 2}}),
    )
    rc = mrr.main(["--apply", "--receipts-dir", str(tmp_path)])
    assert rc == 0
    receipts = list(tmp_path.glob("*.yaml"))
    parsed = yaml.safe_load(receipts[0].read_text())
    assert parsed["applied"] is True


def test_main_apply_dirty_tree_returns_1(mrr, tmp_path, capsys, monkeypatch):
    _patch_classifier(
        monkeypatch,
        mrr,
        rc=1,
        stdout="",
        stderr="working tree dirty",
    )
    rc = mrr.main(["--apply", "--receipts-dir", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "dirty" in err


def test_main_unknown_classifier_failure_returns_nonzero(mrr, tmp_path, capsys, monkeypatch):
    _patch_classifier(monkeypatch, mrr, rc=2, stdout="", stderr="boom")
    rc = mrr.main(["--receipts-dir", str(tmp_path)])
    assert rc == 2


def test_main_json_emits_envelope(mrr, tmp_path, capsys, monkeypatch):
    _patch_classifier(
        monkeypatch,
        mrr,
        rc=0,
        stdout=json.dumps({"summary": {"safe_to_refresh": 1, "needs_review": 0, "unknown": 0, "total": 1}}),
    )
    rc = mrr.main(["--json", "--receipts-dir", str(tmp_path)])
    assert rc == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["summary"]["safe_to_refresh"] == 1
    assert envelope["applied"] is False


def test_main_no_receipt_skips_write(mrr, tmp_path, monkeypatch):
    _patch_classifier(
        monkeypatch,
        mrr,
        rc=0,
        stdout=json.dumps({"summary": {"safe_to_refresh": 0}}),
    )
    rc = mrr.main(["--no-receipt", "--receipts-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("*.yaml")) == []
