"""Disk health alerts (config/prometheus/rules/fleet-disk-health.yml), added 2026-10-29 with the 0pipe build server.

The collector (fleet-state scripts/proxmox-storage-metrics.py) exported SMART facts for weeks without a single alert on them; on the day these
rules were written one 0docker mirror half had failed SMART at 110 % wear and 0pipe's only SSD was at 80 %. The thresholds are calibrated on the live series.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-disk-health.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_disk_health_rules_test.yml"
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
        "FleetDiskSmartFailed": ("critical", "10m"),
        "FleetDiskWearHigh": ("warning", "1h"),
        "FleetDiskWearCritical": ("critical", "1h"),
        "FleetDiskWearForecast": ("warning", "6h"),
        "FleetDiskBadSectors": ("warning", "30m"),
        "FleetDiskHot": ("warning", "30m"),
        "FleetDiskHealthMissing": ("warning", "30m"),
    }
    assert set(alerts) == set(expected)
    for name, (severity, delay) in expected.items():
        assert alerts[name]["for"] == delay, name
        assert alerts[name]["labels"] == {"severity": severity, "service": "fleet_disk_health"}, name
        assert alerts[name]["annotations"]["runbook_url"].endswith("#disk-health-alerts"), name
    assert "## Disk health alerts" in RUNBOOK.read_text(encoding="utf-8")


def test_every_alert_reads_a_metric_the_collector_exports_and_merges_duplicate_series() -> None:
    exported = {
        "fleet_disk_smart_passed", "fleet_disk_wear_percent", "fleet_disk_reallocated_sectors", "fleet_disk_pending_sectors",
        "fleet_disk_offline_uncorrectable", "fleet_disk_media_errors", "fleet_disk_temperature_celsius",
    }
    for name, rule in _alerts().items():
        expr = " ".join(rule["expr"].split())
        assert any(metric in expr for metric in exported), f"{name} reads no fleet_disk_* metric"
        assert "max by" in expr or "min by" in expr, f"{name} must merge the duplicate series an exporter restart leaves"


def test_the_missing_alert_counts_hosts_so_a_verifier_that_reads_nothing_cannot_stay_green() -> None:
    expr = " ".join(_alerts()["FleetDiskHealthMissing"]["expr"].split())
    assert expr == "count(max by (pve_host) (fleet_disk_smart_passed)) < 5"
