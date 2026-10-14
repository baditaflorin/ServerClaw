"""Run the promtool unit tests for the hypervisor memory and Alertmanager self-monitoring rules (skipped without promtool)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMTOOL_DIR = REPO_ROOT / "tests" / "promtool"
RULES = [
    REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-hypervisor-memory.yml",
    REPO_ROOT / "config" / "prometheus" / "rules" / "alertmanager-self.yml",
]
TEST_FILE = PROMTOOL_DIR / "fleet_hypervisor_memory_rules_test.yml"

requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


@requires_promtool
def test_rules_pass_promtool_check_and_unit_tests() -> None:
    for command in (["check", "rules", *map(str, RULES)], ["test", "rules", str(TEST_FILE)]):
        result = subprocess.run(["promtool", *command], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr


def test_the_unit_tests_cover_every_alert() -> None:
    tests = yaml.safe_load(TEST_FILE.read_text(encoding="utf-8"))
    assert [(PROMTOOL_DIR / item).resolve() for item in tests["rule_files"]] == RULES
    covered = {check["alertname"] for case in tests["tests"] for check in case["alert_rule_test"]}
    declared = {rule["alert"] for path in RULES for group in yaml.safe_load(path.read_text(encoding="utf-8"))["groups"] for rule in group["rules"]}
    assert covered == declared, f"alerts without a promtool case: {sorted(declared - covered)}"
