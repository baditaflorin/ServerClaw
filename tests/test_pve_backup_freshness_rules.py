"""The backup-freshness alert for the 0docker hypervisor's guests (config/prometheus/rules/pve-host-incident.yml).

2026-10-29: PveBackupFreshnessLow held every guest to a fixed 30 hours, so CT 108 (the builder), whose vzdump job went from nightly to weekly on 2026-10-28
(`ct108-nightly`, "sun 03:30"), fired a critical alert from the day after each run until the next one (about 5.75 days of every 7) although nothing had failed. The host collector (fleet-state
hypervisor-0docker/libexec/pve-host-health-metrics.py) already publishes `proxmox_backup_max_age_seconds` per guest (36 hours, or 204 hours = 8.5 days when the guest's only
enabled job has a weekday schedule) and looks back 10 days for a weekly guest. The alert now uses that limit for a weekly guest and keeps 30 hours for every other guest
(the collector's 36 hours would loosen the daily guests, so it is not used for them). Pinned here: the alert's labels and delay, that every series it reads carries the same scrape job
(a guest id repeats across hypervisors), the two numbers the unit tests assume (30 hours for a daily guest, anything over 48 hours counts as weekly), that the limits the unit tests feed
in are the ones the collector publishes, that the unit-test file covers a weekly guest and a daily guest both quiet and firing, and (when promtool is installed) that the rules pass
`promtool check` and tests/promtool/pve_backup_freshness_rules_test.yml.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "pve-host-incident.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "pve_backup_freshness_rules_test.yml"
ALERT = "PveBackupFreshnessLow"
JOB = 'job="pve_0docker_host_node_exporter_via_tailscale"'
# What the collector publishes (hypervisor-0docker/libexec/pve-host-health-metrics.py: DAILY_MAX_AGE = 36 h, WEEKLY_MAX_AGE = 204 h).
COLLECTOR_DAILY_LIMIT = 36 * 3600
COLLECTOR_WEEKLY_LIMIT = 204 * 3600
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


def _expr() -> str:
    return _alerts()[ALERT]["expr"]


def _hours(pattern: str) -> int:
    """The hours in a `* N * 3600` or `> N * 3600` term of the expression (it must appear exactly once)."""
    found = re.findall(pattern, _expr())
    assert len(found) == 1, (pattern, found)
    return int(found[0])


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_alert_exists_with_the_severity_and_delay_the_unit_tests_assume() -> None:
    rule = _alerts()[ALERT]
    assert rule["labels"] == {"severity": "critical", "service": "pve_backup"}
    assert rule["for"] == "10m"
    assert "{{ $labels.guest_id }}" in rule["annotations"]["summary"]
    description = rule["annotations"]["description"]
    assert "30 hours" in description and "8.5 days" in description, (
        "the text must name both limits, a weekly guest is not judged at 30 hours"
    )


def test_every_series_it_reads_carries_the_same_scrape_job() -> None:
    # Guest ids repeat across hypervisors: a selector without the job would let another host's guest alert, or lend its limit to this host's guest.
    expr = _expr()
    uses = re.findall(r"proxmox_backup_[a-z_]+", expr)
    scoped = re.findall(r"proxmox_backup_[a-z_]+\{" + re.escape(JOB) + r"\}", expr)
    assert uses and len(uses) == len(scoped), (len(uses), len(scoped))
    assert {
        "proxmox_backup_expected_guest",
        "proxmox_backup_last_success_timestamp_seconds",
        "proxmox_backup_max_age_seconds",
    } <= {u.split("{")[0] for u in uses}


def test_a_daily_guest_keeps_the_old_30_hour_limit_and_a_weekly_guest_is_told_apart_by_the_collectors_limit() -> None:
    expr = _expr()
    assert "108000" not in expr, "the fixed 30 hour constant is replaced by a per-guest limit"
    daily = _hours(r"\*\s*(\d+)\s*\*\s*3600")
    weekly_marker = _hours(r">\s*(\d+)\s*\*\s*3600")
    assert daily * 3600 == 108000, "a daily guest must be exactly as strict as before the weekly job existed"
    assert daily * 3600 < COLLECTOR_DAILY_LIMIT, (
        "the collector's own daily limit is looser than the alert's: it must not be used for a daily guest"
    )
    assert COLLECTOR_DAILY_LIMIT < weekly_marker * 3600 < COLLECTOR_WEEKLY_LIMIT, (
        "only a limit above the daily one marks a weekly guest"
    )


def test_the_unit_tests_feed_in_the_limits_the_collector_publishes() -> None:
    doc = yaml.safe_load(PROMTOOL_TEST.read_text(encoding="utf-8"))
    limits = set()
    for case in doc["tests"]:
        for s in case["input_series"]:
            if s["series"].startswith("proxmox_backup_max_age_seconds{"):
                limits.update(int(float(v)) for v in re.findall(r"\d+", s["values"].split("x")[0]))
    assert limits == {COLLECTOR_DAILY_LIMIT, COLLECTOR_WEEKLY_LIMIT}, limits


def test_the_promtool_test_file_covers_a_weekly_and_a_daily_guest_quiet_and_firing() -> None:
    doc = yaml.safe_load(PROMTOOL_TEST.read_text(encoding="utf-8"))
    firing: set[str] = set()
    quiet_cases = 0
    for case in doc["tests"]:
        for check in case["alert_rule_test"]:
            if check["alertname"] != ALERT:
                continue
            if check["exp_alerts"]:
                firing.update(a["exp_labels"]["guest_id"] for a in check["exp_alerts"])
            else:
                quiet_cases += 1
    assert {"108", "107"} <= firing, ("a weekly guest (108) and a daily guest (107) must each be shown firing", firing)
    assert quiet_cases >= 5, (
        "the quiet side (a weekly guest within 8.5 days, a daily guest within 30 hours) must be covered too"
    )
