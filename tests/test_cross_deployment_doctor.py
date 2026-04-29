"""Unit tests for scripts/cross_deployment_doctor.py — ADR 0460 phase 8.2.

Synthetic deployment trees under tmp_path exercise the loader, drift
classifier, and CLI. The live `.local/deployments/` tree is not
exercised — it's gitignored and varies per operator.
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
SCRIPT_PATH = REPO_ROOT / "scripts" / "cross_deployment_doctor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("cross_deployment_doctor", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["cross_deployment_doctor"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cdd():
    return _load_module()


def _write_state(
    deployments_dir: Path,
    slug: str,
    receipts: dict[str, str],
    *,
    layout: str = "state",
) -> Path:
    """Materialise a deployment under <deployments_dir>/<slug>/.

    `layout` selects which schema variant to write — `state` writes
    `state/live_apply_evidence.yaml` (matching ADR 0440); `flat`
    writes `receipts/latest_receipts.yaml` (older fallback shape).
    """
    deployment_root = deployments_dir / slug
    if layout == "state":
        path = deployment_root / "state" / "live_apply_evidence.yaml"
        payload = {"live_apply_evidence": {"latest_receipts": receipts}}
    elif layout == "flat":
        path = deployment_root / "receipts" / "latest_receipts.yaml"
        payload = {"latest_receipts": receipts}
    else:
        raise ValueError(f"unknown layout {layout!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload))
    return path


# ---------------------------------------------------------------------------
# parse_receipt_date
# ---------------------------------------------------------------------------


def test_parse_receipt_date_real(cdd):
    assert cdd.parse_receipt_date("2026-04-21-x") == dt.date(2026, 4, 21)


def test_parse_receipt_date_invalid(cdd):
    assert cdd.parse_receipt_date("not-dated") is None
    assert cdd.parse_receipt_date("2026-02-30-bogus") is None
    assert cdd.parse_receipt_date(None) is None


# ---------------------------------------------------------------------------
# list_deployments
# ---------------------------------------------------------------------------


def test_list_deployments_returns_directory_names(cdd, tmp_path):
    (tmp_path / "lv3").mkdir()
    (tmp_path / "0fork").mkdir()
    (tmp_path / ".active-deployment").write_text("lv3")  # dotfile, ignored
    (tmp_path / "stray.yaml").write_text("")  # not a directory, ignored
    out = cdd.list_deployments(tmp_path)
    assert out == ["0fork", "lv3"]


def test_list_deployments_handles_missing_dir(cdd, tmp_path):
    assert cdd.list_deployments(tmp_path / "no-such-dir") == []


# ---------------------------------------------------------------------------
# load_deployment_receipts — both layouts
# ---------------------------------------------------------------------------


def test_load_deployment_receipts_state_layout(cdd, tmp_path):
    deps = tmp_path / "deployments"
    _write_state(deps, "lv3", {"alpha": "2026-04-01-x"}, layout="state")
    out = cdd.load_deployment_receipts(deps / "lv3", "lv3")
    assert out.slug == "lv3"
    assert out.receipts == {"alpha": "2026-04-01-x"}
    assert out.receipt_dates["alpha"] == dt.date(2026, 4, 1)


def test_load_deployment_receipts_flat_layout(cdd, tmp_path):
    deps = tmp_path / "deployments"
    _write_state(deps, "lv3", {"alpha": "2026-04-01-x"}, layout="flat")
    out = cdd.load_deployment_receipts(deps / "lv3", "lv3")
    assert out.receipts == {"alpha": "2026-04-01-x"}


def test_load_deployment_receipts_missing_returns_empty(cdd, tmp_path):
    out = cdd.load_deployment_receipts(tmp_path / "ghost", "ghost")
    assert out.receipts == {}
    assert out.receipt_dates == {}


def test_load_deployment_receipts_malformed_yaml(cdd, tmp_path):
    """Malformed YAML must be skipped without crashing."""
    path = tmp_path / "lv3" / "state" / "live_apply_evidence.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("[: not valid yaml")
    out = cdd.load_deployment_receipts(tmp_path / "lv3", "lv3")
    assert out.receipts == {}


def test_load_deployment_receipts_state_takes_precedence_over_flat(cdd, tmp_path):
    """When both files exist, state/live_apply_evidence.yaml wins."""
    deps = tmp_path / "deployments"
    _write_state(deps, "lv3", {"alpha": "2026-04-01-state"}, layout="state")
    _write_state(deps, "lv3", {"alpha": "2026-04-01-flat"}, layout="flat")
    out = cdd.load_deployment_receipts(deps / "lv3", "lv3")
    assert out.receipts["alpha"] == "2026-04-01-state"


# ---------------------------------------------------------------------------
# compute_drift
# ---------------------------------------------------------------------------


def _dr(cdd, slug: str, receipts: dict[str, str]) -> "object":
    dates = {svc: cdd.parse_receipt_date(slug_) for svc, slug_ in receipts.items()}
    return cdd.DeploymentReceipts(slug=slug, receipts=receipts, receipt_dates=dates)


def test_compute_drift_in_sync_when_close(cdd):
    """Two deployments, identical receipts → in_sync."""
    today = dt.date(2026, 4, 28)
    deployments = [
        _dr(cdd, "lv3", {"alpha": "2026-04-20-x"}),
        _dr(cdd, "0fork", {"alpha": "2026-04-20-x"}),
    ]
    report = cdd.compute_drift(deployments, today=today)
    assert report.summary()["in_sync"] == 1
    assert report.summary()["presence_drift"] == 0
    assert report.summary()["skew_drift"] == 0


def test_compute_drift_presence_drift(cdd):
    """Service in lv3 but not 0fork → presence drift."""
    today = dt.date(2026, 4, 28)
    deployments = [
        _dr(cdd, "lv3", {"alpha": "2026-04-20-x"}),
        _dr(cdd, "0fork", {}),
    ]
    report = cdd.compute_drift(deployments, today=today)
    assert report.summary()["presence_drift"] == 1
    entry = report.drift_entries[0]
    assert entry.drift_kind == "presence"
    assert "0fork" in entry.detail


def test_compute_drift_skew_drift(cdd):
    """Both deployments have receipt; one is much older → skew drift."""
    today = dt.date(2026, 4, 28)
    deployments = [
        _dr(cdd, "lv3", {"alpha": "2026-04-20-x"}),  # 8 days old
        _dr(cdd, "0fork", {"alpha": "2026-01-01-x"}),  # 117 days old
    ]
    report = cdd.compute_drift(deployments, today=today, skew_threshold_days=14)
    assert report.summary()["skew_drift"] == 1
    entry = report.drift_entries[0]
    assert entry.drift_kind == "skew"
    assert entry.skew_days is not None and entry.skew_days > 14


def test_compute_drift_skew_below_threshold_is_in_sync(cdd):
    """Differences within the threshold count as in_sync — no false
    alarms when one deployment got an update an hour later than the
    other."""
    today = dt.date(2026, 4, 28)
    deployments = [
        _dr(cdd, "lv3", {"alpha": "2026-04-20-x"}),  # 8d old
        _dr(cdd, "0fork", {"alpha": "2026-04-15-x"}),  # 13d old → 5d skew
    ]
    report = cdd.compute_drift(deployments, today=today, skew_threshold_days=14)
    assert report.summary()["in_sync"] == 1


def test_compute_drift_handles_no_deployments(cdd):
    today = dt.date(2026, 4, 28)
    report = cdd.compute_drift([], today=today)
    assert report.deployments == []
    assert report.drift_entries == []


def test_compute_drift_three_deployments_all_diverge(cdd):
    """A presence drift can involve more than two deployments —
    presence list reports every missing slug."""
    today = dt.date(2026, 4, 28)
    deployments = [
        _dr(cdd, "lv3", {"alpha": "2026-04-20-x"}),
        _dr(cdd, "0fork", {}),
        _dr(cdd, "synthetic", {}),
    ]
    report = cdd.compute_drift(deployments, today=today)
    entry = report.drift_entries[0]
    assert entry.drift_kind == "presence"
    assert "0fork" in entry.detail and "synthetic" in entry.detail


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_no_deployments_emits_clean_message(cdd, tmp_path, capsys):
    rc = cdd.main(["--deployments-dir", str(tmp_path / "missing")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no deployments configured" in out


def test_cli_filters_to_specific_slug(cdd, tmp_path, capsys):
    deps = tmp_path / "deployments"
    _write_state(deps, "lv3", {"alpha": "2026-04-20-x"})
    _write_state(deps, "0fork", {"alpha": "2026-04-20-x"})
    rc = cdd.main(
        [
            "--deployments-dir",
            str(deps),
            "--deployment",
            "lv3",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # Only one deployment listed (no 0fork in the comparison set).
    assert "1 deployments" in out


def test_cli_unknown_deployment_returns_two(cdd, tmp_path, capsys):
    deps = tmp_path / "deployments"
    _write_state(deps, "lv3", {"alpha": "2026-04-20-x"})
    rc = cdd.main(["--deployments-dir", str(deps), "--deployment", "ghost"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ghost" in err


def test_cli_negative_threshold_returns_two(cdd, tmp_path):
    rc = cdd.main(
        [
            "--deployments-dir",
            str(tmp_path),
            "--skew-threshold-days",
            "-1",
        ]
    )
    assert rc == 2


def test_cli_json_output_round_trips(cdd, tmp_path, capsys):
    deps = tmp_path / "deployments"
    _write_state(deps, "lv3", {"alpha": "2026-04-20-x"})
    _write_state(deps, "0fork", {})  # alpha missing on 0fork
    rc = cdd.main(
        ["--deployments-dir", str(deps), "--json"],
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["presence_drift"] == 1
    # Both deployments listed.
    assert sorted(payload["deployments"]) == ["0fork", "lv3"]
