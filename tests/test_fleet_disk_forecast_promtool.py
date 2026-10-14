"""FleetRootFilesystemFillsWithin14Days: promtool unit tests (skipped when promtool is not installed) and structure checks.

pg-primary (a Postgres primary) was found with about a week of disk left only by accident on 2026-10-13: the existing
24 hour rule leaves a day to react, too little to order storage or prune a database.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES = REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-disk.yml"
PROMTOOL_DIR = REPO_ROOT / "tests" / "promtool"
ALERT = "FleetRootFilesystemFillsWithin14Days"

requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _rule() -> dict:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return next(rule for group in data["groups"] for rule in group["rules"] if rule.get("alert") == ALERT)


@requires_promtool
def test_forecast_rule_passes_promtool_check_and_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_DIR / "fleet_disk_forecast_test.yml")]):
        result = subprocess.run(["promtool", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr


def test_forecast_rule_looks_far_enough_ahead_without_paging() -> None:
    rule = _rule()
    expr = " ".join(rule["expr"].split())
    assert re.search(r"predict_linear\(node_filesystem_avail_bytes\{[^}]*\}\[3d\], 14 \* 86400\) < 0", expr)
    assert re.search(r"predict_linear\(node_filesystem_avail_bytes\{[^}]*\}\[1d\], 14 \* 86400\) < 0", expr)  # a step older than a day stays quiet
    assert "< 0.4" in expr  # large, mostly empty disks stay quiet
    assert 'mountpoint="/"' in expr and "tmpfs" in expr  # virtual filesystems must not warn
    assert rule["labels"]["severity"] == "warning"  # a week or two of warning must not page at night
    assert rule["for"] in {"6h", "12h"}
    assert rule["annotations"]["summary"] and "14 days" in rule["annotations"]["summary"]
    assert (REPO_ROOT / rule["annotations"]["runbook_url"]).is_file()


def test_forecast_unit_tests_cover_the_alert_and_point_at_the_rule_file() -> None:
    tests = yaml.safe_load((PROMTOOL_DIR / "fleet_disk_forecast_test.yml").read_text(encoding="utf-8"))
    assert [(PROMTOOL_DIR / item).resolve() for item in tests["rule_files"]] == [RULES]
    assert {check["alertname"] for case in tests["tests"] for check in case["alert_rule_test"]} == {ALERT}
    names = " ".join(case["name"] for case in tests["tests"])
    for phrase in ("fills within 14 days", "too slowly", "40% free", "one-off step", "older than a day"):
        assert phrase in names, phrase
