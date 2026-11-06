"""Docker address-pool alerts (config/prometheus/rules/fleet-docker-networks.yml), added 2026-10-29 after leaked Woodpecker networks filled
the 31 built-in pools of infer-builder-ci and every workflow on agent 110 failed at once. The metrics come from fleet-state
scripts/docker-network-gc.py.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-docker-networks.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_docker_networks_rules_test.yml"
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
        "DockerNetworkPoolNearlyFull": ("5m", "warning"),
        "DockerNetworkPoolExhausted": ("1m", "critical"),
        "DockerNetworkGcStale": ("10m", "warning"),
        "DockerNetworkGcHostsMissing": ("30m", "warning"),
        "DockerNetworkGcHostsMissingNone": ("30m", "warning"),
    }
    assert set(alerts) == set(expected)
    for name, (delay, severity) in expected.items():
        assert alerts[name]["for"] == delay and alerts[name]["labels"] == {"severity": severity, "service": "fleet_docker_networks"}, name
        assert alerts[name]["annotations"]["runbook_url"].endswith("#docker-network-pool-alerts"), name
    assert "## Docker network pool alerts" in RUNBOOK.read_text(encoding="utf-8")


def test_the_pool_alert_fires_within_5_subnets_per_host_and_merges_duplicate_series() -> None:
    expr = " ".join(_alerts()["DockerNetworkPoolNearlyFull"]["expr"].split())
    assert expr == "max by (host) (docker_network_pool_capacity_subnets - docker_network_pool_used_subnets) < 5"


def test_a_check_that_reads_nothing_cannot_stay_green() -> None:
    alerts = _alerts()
    assert " ".join(alerts["DockerNetworkGcHostsMissing"]["expr"].split()) == "count(max by (host) (docker_network_gc_last_success_timestamp_seconds)) < 21"
    assert alerts["DockerNetworkGcHostsMissingNone"]["expr"].strip() == "absent(docker_network_gc_last_success_timestamp_seconds)"
