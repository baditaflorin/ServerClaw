"""Tests for config/prometheus/rules/fleet-loops.yml: dead-man and finding alerts for the pool guardian and horizon loops.

Nothing here contacts a host or needs promtool. It pins the properties that make the alerts trustworthy: a staleness
alert is paired with an absent() alert (a dead target yields no series, so staleness alone resolves itself), every
`for:` outlasts the nightly 10-minute stop of the builder, thresholds are several multiples of the timer cadence, and
the file is actually shipped by the monitoring_vm role and documented.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES = REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-loops.yml"
ROLE = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "monitoring_vm"

NIGHTLY_STOP_MINUTES = 10  # ct108-nightly stops the builder CT for about this long
GUARDIAN_CADENCE_MINUTES = 10  # fleet-pool-guardian.timer OnUnitInactiveSec
HORIZON_CADENCE_HOURS = 6  # fleet-horizon.timer OnUnitInactiveSec


def _alerts() -> dict[str, dict]:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {rule["alert"]: rule for group in data["groups"] for rule in group["rules"]}


def _minutes(duration: str) -> float:
    match = re.fullmatch(r"(\d+)([smhd])", duration)
    assert match, duration
    return int(match.group(1)) * {"s": 1 / 60, "m": 1, "h": 60, "d": 1440}[match.group(2)]


def test_every_alert_is_complete_and_points_at_a_real_runbook() -> None:
    alerts = _alerts()
    assert set(alerts) == {
        "FleetPoolGuardianSilent",
        "FleetPoolGuardianNotReporting",
        "FleetPoolGuardianCriticalFinding",
        "FleetPoolGuardianCircuitOpen",
        "FleetPoolGuardianPaused",
        "FleetHorizonSilent",
        "FleetHorizonNotReporting",
        "FleetHorizonCriticalFinding",
    }
    for name, rule in alerts.items():
        assert rule["labels"]["severity"] in {"warning", "critical"}, name
        assert rule["labels"]["service"] == "fleet_loops", name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name
        assert (REPO_ROOT / rule["annotations"]["runbook_url"]).is_file(), name


def test_staleness_alerts_are_paired_with_absent_alerts() -> None:
    alerts = _alerts()
    for loop, metric in (
        ("FleetPoolGuardian", "fleet_pool_guardian_last_run_timestamp_seconds"),
        ("FleetHorizon", "fleet_horizon_last_run_timestamp_seconds"),
    ):
        assert f"time() - {metric}" in alerts[f"{loop}Silent"]["expr"]
        # No series (target down, file unreadable) makes the staleness expression return nothing and resolve:
        assert alerts[f"{loop}NotReporting"]["expr"] == f"absent({metric})"


def test_every_wait_outlasts_the_nightly_builder_stop_and_thresholds_exceed_the_cadence() -> None:
    alerts = _alerts()
    for name in ("FleetPoolGuardianNotReporting", "FleetHorizonNotReporting"):
        assert _minutes(alerts[name]["for"]) > NIGHTLY_STOP_MINUTES, name
    guardian = re.search(r">\s*(\d+)\s*\*\s*60\b", alerts["FleetPoolGuardianSilent"]["expr"])
    assert guardian and int(guardian.group(1)) >= 3 * GUARDIAN_CADENCE_MINUTES
    assert int(guardian.group(1)) > NIGHTLY_STOP_MINUTES
    horizon = re.search(r">\s*(\d+)\s*\*\s*3600\b", alerts["FleetHorizonSilent"]["expr"])
    assert horizon and int(horizon.group(1)) >= 2 * HORIZON_CADENCE_HOURS


def test_the_dead_man_of_the_repair_loop_pages() -> None:
    alerts = _alerts()
    assert alerts["FleetPoolGuardianSilent"]["labels"]["severity"] == "critical"
    assert alerts["FleetPoolGuardianNotReporting"]["labels"]["severity"] == "critical"
    assert alerts["FleetHorizonCriticalFinding"]["labels"]["severity"] == "critical"
    assert 'severity="critical"' in alerts["FleetHorizonCriticalFinding"]["expr"]
    assert 'severity="critical"' in alerts["FleetPoolGuardianCriticalFinding"]["expr"]


def test_the_monitoring_role_ships_the_rule_file() -> None:
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["monitoring_prometheus_fleet_loops_rules_source_file"].endswith("/config/prometheus/rules/fleet-loops.yml")
    assert defaults["monitoring_prometheus_fleet_loops_rules_file"].endswith("/fleet-loops.yml")
    tasks = yaml.safe_load((ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    copies = [t for t in tasks if "fleet_loops_rules_source_file" in str(t.get("ansible.builtin.copy", ""))]
    assert len(copies) == 1
    assert "fleet_loops_rules_file" in copies[0]["ansible.builtin.copy"]["dest"]
    assert copies[0]["notify"] == "Reload Prometheus configuration"
    assert copies[0]["ansible.builtin.copy"]["mode"] == "0640"


def test_the_runbook_documents_the_rules_and_their_rollback() -> None:
    text = (REPO_ROOT / "docs" / "runbooks" / "fleet-observability.md").read_text(encoding="utf-8")
    assert "config/prometheus/rules/fleet-loops.yml" in text
    assert "/etc/prometheus/rules/fleet-loops.yml" in text
    for name in _alerts():
        assert name in text, name
