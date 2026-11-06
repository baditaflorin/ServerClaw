"""The alerts that watch vzdump-guard (config/prometheus/rules/pve-host-incident.yml).

2026-10-19: the guard (fleet-state hypervisor-0docker/libexec/vzdump-guard.py, timer every minute) stops a snapshot backup of VM 100 when that guest's own load or I/O wait collapses; it writes the
textfile vzdump-guard.prom. Three alerts watch it: it stopped a backup (VzdumpGuardTripped), it stopped running (VzdumpGuardSilent, a dead-man switch that must also fire when the metric vanishes) and
its kill switch was left on (VzdumpGuardDisabled). Pinned here: the alerts exist with the severities and delays the unit tests assume, they select the same scrape job as the rest of the file (a typo in a
job label never fires and nothing notices), the dead-man switch has its absent() branch, and (when promtool is installed) the rules pass `promtool check` and tests/promtool/vzdump_guard_rules_test.yml.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "pve-host-incident.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "vzdump_guard_rules_test.yml"
JOB = "pve_0docker_host_node_exporter_via_tailscale"
GUARD_ALERTS = ("VzdumpGuardTripped", "VzdumpGuardSilent", "VzdumpGuardDisabled")
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_three_alerts_exist_with_the_severities_and_delays_the_unit_tests_assume() -> None:
    a = _alerts()
    want = {"VzdumpGuardTripped": ("warning", "1m"), "VzdumpGuardSilent": ("warning", "5m"), "VzdumpGuardDisabled": ("warning", "1h")}
    for name, (severity, delay) in want.items():
        rule = a[name]
        assert rule["labels"]["severity"] == severity and rule["labels"]["service"] == "pve_backup" and rule["for"] == delay, name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name


def test_every_guard_alert_selects_the_same_scrape_job_as_the_host_health_alerts() -> None:
    a = _alerts()
    assert f'job="{JOB}"' in a["PveHostHealthMetricsStale"]["expr"], "the reference alert moved to another job: update JOB here and in the promtool test"
    for name in GUARD_ALERTS:
        expr = a[name]["expr"]
        assert f'job="{JOB}"' in expr, name
        assert expr.count("vzdump_guard_") == expr.count(f'{{job="{JOB}"}}'), (name, "every guard metric must carry the job selector")


def test_the_dead_man_switch_fires_when_the_metric_is_stale_and_when_it_is_gone() -> None:
    expr = _alerts()["VzdumpGuardSilent"]["expr"]
    assert "time() - vzdump_guard_last_run_timestamp_seconds" in expr and "> 300" in expr
    assert "absent(vzdump_guard_last_run_timestamp_seconds" in expr, "a guard whose textfile vanished must also alert"


def test_the_tripped_alert_ignores_never_and_old_trips() -> None:
    expr = _alerts()["VzdumpGuardTripped"]["expr"]
    assert "vzdump_guard_last_trip_timestamp_seconds{" in expr and "> 0" in expr, "0 means never tripped"
    assert "< 86400" in expr, "a trip is news for 24 hours"


def test_the_disabled_alert_reads_the_enabled_gauge_the_guard_writes() -> None:
    assert _alerts()["VzdumpGuardDisabled"]["expr"].strip().endswith("== 0")
    assert "vzdump_guard_enabled{" in _alerts()["VzdumpGuardDisabled"]["expr"]


def test_the_promtool_test_file_covers_each_alert_firing_and_not_firing() -> None:
    doc = yaml.safe_load(PROMTOOL_TEST.read_text(encoding="utf-8"))
    seen: dict[str, set[bool]] = {name: set() for name in GUARD_ALERTS}
    for case in doc["tests"]:
        for check in case["alert_rule_test"]:
            if check["alertname"] in seen:
                seen[check["alertname"]].add(bool(check["exp_alerts"]))
    assert seen == {name: {True, False} for name in GUARD_ALERTS}, seen
