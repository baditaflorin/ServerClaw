"""Pressure alerts for the CI hosts (config/prometheus/rules/fleet-ci-host-pressure.yml), added 2026-10-26 with the graded Woodpecker admission.

The thresholds come from a 7 day back-test of the real series (CPU waiting over 0.4 for 30 minutes: 2 episodes; IO stalled over 0.5 for 30 minutes: 4 episodes, all on the 0own HDD guest).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-ci-host-pressure.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_ci_host_pressure_rules_test.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "fleet-observability.md"
HOSTS = 'host=~"0docker-builder|docker-build-lv3|0own-build-worker|infer-builder-ci|0pipe-build"'
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
    assert set(alerts) == {"FleetCiHostCpuPressureHigh", "FleetCiHostIoPressureHigh", "FleetCiHostPressureMissing"}
    for name, delay in (("FleetCiHostCpuPressureHigh", "30m"), ("FleetCiHostIoPressureHigh", "30m"), ("FleetCiHostPressureMissing", "15m")):
        assert alerts[name]["for"] == delay and alerts[name]["labels"] == {"severity": "warning", "service": "fleet_ci_host_pressure"}, name
        assert alerts[name]["annotations"]["runbook_url"].endswith("#ci-host-pressure-alerts"), name
    assert "## CI host pressure alerts" in RUNBOOK.read_text(encoding="utf-8")


def test_the_pressure_alerts_merge_duplicate_series_per_host_and_read_the_pressure_counters() -> None:
    alerts = _alerts()
    cpu = " ".join(alerts["FleetCiHostCpuPressureHigh"]["expr"].split())
    io = " ".join(alerts["FleetCiHostIoPressureHigh"]["expr"].split())
    assert cpu == f"max by (host) (rate(node_pressure_cpu_waiting_seconds_total{{{HOSTS}}}[5m])) > 0.4"
    assert io == f"max by (host) (rate(node_pressure_io_stalled_seconds_total{{{HOSTS}}}[5m])) > 0.5"


def test_the_missing_alert_counts_hosts_so_a_verifier_that_reads_nothing_cannot_stay_green() -> None:
    expr = " ".join(_alerts()["FleetCiHostPressureMissing"]["expr"].split())
    assert expr == f"count(max by (host) (node_pressure_cpu_waiting_seconds_total{{{HOSTS}}})) < 5"
