"""Run the promtool unit tests for config/prometheus/rules/fleet-loops.yml (skipped when promtool is not installed).

The tests in tests/promtool/fleet_loops_rules_test.yml feed the rules the heartbeat series of the pool guardian and
horizon loops: on-time reports (nothing fires), the nightly ten-minute stop of the builder (nothing fires), an exporter
that keeps serving an old timestamp (Silent fires), a series that vanished (NotReporting fires), and findings that must
persist before they page.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMTOOL_DIR = REPO_ROOT / "tests" / "promtool"
RULES = REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-loops.yml"

requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _run_promtool(*args: str) -> None:
    result = subprocess.run(["promtool", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


@requires_promtool
def test_fleet_loops_rules_pass_promtool_check_and_unit_tests() -> None:
    _run_promtool("check", "rules", str(RULES))
    _run_promtool("test", "rules", str(PROMTOOL_DIR / "fleet_loops_rules_test.yml"))


def test_the_unit_tests_cover_every_alert_and_point_at_the_rule_file() -> None:
    tests = yaml.safe_load((PROMTOOL_DIR / "fleet_loops_rules_test.yml").read_text(encoding="utf-8"))
    assert [(PROMTOOL_DIR / item).resolve() for item in tests["rule_files"]] == [RULES]
    covered = {check["alertname"] for case in tests["tests"] for check in case["alert_rule_test"]}
    declared = {rule["alert"] for group in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for rule in group["rules"]}
    assert covered == declared, f"alerts without a promtool case: {sorted(declared - covered)}"
    # The case that protects the nightly stop of the builder must stay.
    assert any("nightly" in case["name"] for case in tests["tests"])
