"""Unit tests for scripts/check_receipt_freshness.py — ADR 0446 item 14.

Covers the date-parsing helper, the evaluation logic against a synthetic
date, and the CLI advisory/strict modes. The live versions/stack.yaml is
not exercised — that is integration territory and would couple this test
suite to the receipts the platform happens to carry today.
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
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_receipt_freshness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_receipt_freshness", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["check_receipt_freshness"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def crf():
    return _load_module()


# ---------------------------------------------------------------------------
# parse_receipt_date
# ---------------------------------------------------------------------------


def test_parse_receipt_date_real_slug(crf):
    date, err = crf.parse_receipt_date("2026-04-27-ws-0372-0fork-services-all-7-deployed")
    assert err is None
    assert date == dt.date(2026, 4, 27)


def test_parse_receipt_date_handles_long_slugs(crf):
    """The real receipts have many dashes after the date; the parser
    must not stop at the first dash."""
    date, err = crf.parse_receipt_date("2026-03-28-adr-0250-log-queryability-canary-live-apply")
    assert err is None
    assert date == dt.date(2026, 3, 28)


def test_parse_receipt_date_rejects_missing_prefix(crf):
    date, err = crf.parse_receipt_date("ws-0372-no-date")
    assert date is None
    assert err == "slug does not start with YYYY-MM-DD-"


def test_parse_receipt_date_rejects_empty(crf):
    date, err = crf.parse_receipt_date("")
    assert date is None
    assert "empty" in err


def test_parse_receipt_date_rejects_non_string(crf):
    date, err = crf.parse_receipt_date(None)  # type: ignore[arg-type]
    assert date is None


def test_parse_receipt_date_rejects_invalid_calendar_date(crf):
    """`2026-02-30` is well-formed but not a real date. The parser must
    surface that as an explicit error rather than silently swallowing."""
    date, err = crf.parse_receipt_date("2026-02-30-bogus")
    assert date is None
    assert "invalid date" in err


# ---------------------------------------------------------------------------
# evaluate_receipts
# ---------------------------------------------------------------------------


def test_evaluate_receipts_marks_old_as_stale(crf):
    today = dt.date(2026, 4, 28)
    receipts = {
        "fresh_service": "2026-04-15-recent",  # 13 days
        "old_service": "2026-03-01-stale",  # 58 days
    }
    results = crf.evaluate_receipts(receipts, max_age_days=30, today=today)
    by_service = {r.service: r for r in results}
    assert by_service["fresh_service"].is_stale is False
    assert by_service["fresh_service"].age_days == 13
    assert by_service["old_service"].is_stale is True
    assert by_service["old_service"].age_days == 58


def test_evaluate_receipts_boundary_is_inclusive_lower(crf):
    """Exactly `max_age_days` is fresh; one day older is stale.
    Pinning this so a future refactor doesn't silently flip the
    inequality."""
    today = dt.date(2026, 4, 28)
    receipts = {
        "exactly_30d": "2026-03-29-ok",  # 30 days
        "31d_old": "2026-03-28-old",  # 31 days
    }
    results = crf.evaluate_receipts(receipts, max_age_days=30, today=today)
    by_service = {r.service: r for r in results}
    assert by_service["exactly_30d"].is_stale is False
    assert by_service["31d_old"].is_stale is True


def test_evaluate_receipts_unparseable_treated_as_stale(crf):
    """A slug whose date cannot be parsed has unknown age and must be
    flagged stale by default — the safe choice is to surface, not
    swallow."""
    today = dt.date(2026, 4, 28)
    receipts = {"weird": "no-date-here"}
    results = crf.evaluate_receipts(receipts, max_age_days=30, today=today)
    assert len(results) == 1
    r = results[0]
    assert r.receipt_date is None
    assert r.age_days is None
    assert r.is_stale is True
    assert r.parse_error == "slug does not start with YYYY-MM-DD-"


def test_evaluate_receipts_empty_input(crf):
    today = dt.date(2026, 4, 28)
    assert crf.evaluate_receipts({}, max_age_days=30, today=today) == []


# ---------------------------------------------------------------------------
# load_receipts
# ---------------------------------------------------------------------------


def test_load_receipts_reads_real_shape(crf, tmp_path):
    stack = tmp_path / "stack.yaml"
    stack.write_text(
        yaml.safe_dump(
            {
                "live_apply_evidence": {
                    "receipt_dir": "receipts/live-applies",
                    "latest_receipts": {
                        "platform": "2026-04-21-some-receipt",
                        "monitoring": "2026-03-28-other-receipt",
                    },
                }
            }
        )
    )
    receipts = crf.load_receipts(stack)
    assert receipts == {
        "platform": "2026-04-21-some-receipt",
        "monitoring": "2026-03-28-other-receipt",
    }


def test_load_receipts_missing_evidence_returns_empty(crf, tmp_path):
    stack = tmp_path / "stack.yaml"
    stack.write_text("# no live_apply_evidence here\n")
    assert crf.load_receipts(stack) == {}


def test_load_receipts_rejects_malformed_evidence(crf, tmp_path):
    stack = tmp_path / "stack.yaml"
    stack.write_text(yaml.safe_dump({"live_apply_evidence": "not-a-map"}))
    with pytest.raises(ValueError, match="must be a mapping"):
        crf.load_receipts(stack)


def test_load_receipts_rejects_malformed_receipts_subkey(crf, tmp_path):
    stack = tmp_path / "stack.yaml"
    stack.write_text(yaml.safe_dump({"live_apply_evidence": {"latest_receipts": ["a", "b"]}}))
    with pytest.raises(ValueError, match="latest_receipts"):
        crf.load_receipts(stack)


def test_load_receipts_missing_file_raises(crf, tmp_path):
    with pytest.raises(FileNotFoundError):
        crf.load_receipts(tmp_path / "does-not-exist.yaml")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def stack_with_receipts(tmp_path):
    """Create a stack.yaml fixture and return its path."""

    def _mk(receipts: dict[str, str]) -> Path:
        path = tmp_path / "stack.yaml"
        path.write_text(yaml.safe_dump({"live_apply_evidence": {"latest_receipts": receipts}}))
        return path

    return _mk


def test_cli_advisory_default_returns_zero_even_when_stale(crf, stack_with_receipts, capsys):
    stack = stack_with_receipts({"old": "2026-01-01-ancient"})
    rc = crf.main(
        ["--stack-yaml", str(stack), "--max-age-days", "30"],
        today=dt.date(2026, 4, 28),
    )
    assert rc == 0  # advisory by default
    out = capsys.readouterr().out
    assert "STALE" in out
    assert "1 stale" in out


def test_cli_strict_returns_one_when_stale(crf, stack_with_receipts):
    stack = stack_with_receipts({"old": "2026-01-01-ancient"})
    rc = crf.main(
        ["--stack-yaml", str(stack), "--max-age-days", "30", "--strict"],
        today=dt.date(2026, 4, 28),
    )
    assert rc == 1


def test_cli_strict_returns_zero_when_all_fresh(crf, stack_with_receipts):
    stack = stack_with_receipts({"recent": "2026-04-20-recent"})
    rc = crf.main(
        ["--stack-yaml", str(stack), "--max-age-days", "30", "--strict"],
        today=dt.date(2026, 4, 28),
    )
    assert rc == 0


def test_cli_json_output_is_well_formed(crf, stack_with_receipts, capsys):
    stack = stack_with_receipts(
        {
            "old": "2026-01-01-ancient",
            "recent": "2026-04-20-fresh",
        }
    )
    rc = crf.main(
        ["--stack-yaml", str(stack), "--max-age-days", "30", "--json"],
        today=dt.date(2026, 4, 28),
    )
    assert rc == 0  # advisory by default
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["summary"]["stale"] == 1
    assert payload["summary"]["fresh"] == 1
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["max_age_days"] == 30
    stale_services = {r["service"] for r in payload["stale"]}
    assert stale_services == {"old"}


def test_cli_missing_stack_yaml_returns_two(crf, tmp_path, capsys):
    rc = crf.main(["--stack-yaml", str(tmp_path / "missing.yaml")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing" in err.lower()


def test_cli_negative_max_age_days_returns_two(crf, stack_with_receipts):
    stack = stack_with_receipts({"any": "2026-04-20-x"})
    rc = crf.main(["--stack-yaml", str(stack), "--max-age-days", "-1"])
    assert rc == 2
