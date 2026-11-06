"""Woodpecker agent record alerts (config/prometheus/rules/fleet-woodpecker-agent-records.yml), added 2026-10-29.

On 2026-10-28 eight agent records lost their name and the load controller managed none of those slots for about a day without any alert.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-woodpecker-agent-records.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_woodpecker_agent_records_rules_test.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "fleet-observability.md"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_alerts_exist_with_the_severity_delay_and_runbook_the_unit_tests_assume() -> None:
    alerts = _alerts()
    expected = {
        "WoodpeckerAgentRecordUnnamed": ("warning", "10m"),
        "WoodpeckerControllerNodeMissingAgents": ("warning", "10m"),
        "WoodpeckerAgentRecordCheckBlind": ("warning", "15m"),
        "WoodpeckerAgentNamesBeingWiped": ("warning", "0m"),
    }
    assert set(alerts) == set(expected)
    for name, (severity, delay) in expected.items():
        assert alerts[name]["for"] == delay, name
        assert alerts[name]["labels"] == {"severity": severity, "service": "fleet_woodpecker_agent_records"}, name
        assert alerts[name]["annotations"]["runbook_url"].endswith("#woodpecker-agent-record-alerts"), name
    assert "## Woodpecker agent record alerts" in RUNBOOK.read_text(encoding="utf-8")
