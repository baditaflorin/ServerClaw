"""config/prometheus/rules/fleet-apikey-wave.yml: alerts for apikey-wave, the unattended tool that moves pool replicas to their local keystore node.

The tool lives in baditaflorin/fleet-state (scripts/ct108/apikey-wave.py) and writes its metrics to the builder's node exporter textfile; the metric names
below are pinned in its own tests too. Here: every alert is complete and points at a real runbook, the rules read exactly those names, every wait
outlasts the nightly builder stop, the alerts only concern work that remains, and (where promtool is installed) the unit tests pass.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "config" / "prometheus" / "rules" / "fleet-apikey-wave.yml"
PROMTOOL_TEST = ROOT / "tests" / "promtool" / "fleet_apikey_wave_rules_test.yml"
WRITTEN = {"fleet_apikey_wave_pools", "fleet_apikey_wave_halted", "fleet_apikey_wave_last_run_timestamp_seconds"}
NIGHTLY_STOP_MINUTES = 60  # the builder's vzdump stop took 59 minutes on 2026-10-19


def alerts() -> dict[str, dict]:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in data["groups"] for r in g["rules"]}


def minutes(duration: str) -> float:
    m = re.fullmatch(r"(\d+)([smhd])", duration)
    assert m, duration
    return int(m.group(1)) * {"s": 1 / 60, "m": 1, "h": 60, "d": 1440}[m.group(2)]


def test_every_alert_is_complete_and_points_at_a_real_runbook():
    a = alerts()
    assert set(a) == {"ApikeyWaveHalted", "ApikeyWaveSilent", "ApikeyWaveStalled"}
    for name, rule in a.items():
        assert rule["labels"]["severity"] in {"warning", "critical"} and rule["labels"]["service"] == "apikey-wave", name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name
        assert (ROOT / rule["annotations"]["runbook_url"]).is_file(), name


def test_the_rules_read_only_metric_names_the_tool_writes():
    used = set()
    for rule in alerts().values():
        used |= set(re.findall(r"fleet_apikey_wave_\w+", rule["expr"]))
    assert used and used <= WRITTEN, sorted(used - WRITTEN)
    assert used == WRITTEN, "an alert for every metric the tool writes"


def test_the_runbook_names_the_commands_and_files_the_alerts_send_people_to():
    book = (ROOT / "docs" / "runbooks" / "apikey-wave.md").read_text(encoding="utf-8")
    for needle in ("apikey-wave.py --status", "--resume", "events.jsonl", "PAUSE", "plan.json", "apikey-wave.timer", "fleet_apikey_wave_halted"):
        assert needle in book, needle
    for rule in alerts().values():
        for cmd in re.findall(r"`([^`]*apikey-wave[^`]*)`", rule["annotations"]["description"]):
            assert cmd.split()[0] in {"python3", "systemctl", "journalctl"} or cmd.startswith("tail"), cmd


def test_every_alert_only_concerns_work_that_remains_and_every_wait_outlasts_the_nightly_stop():
    a = alerts()
    for name in ("ApikeyWaveSilent", "ApikeyWaveStalled"):
        assert 'state="total"' in a[name]["expr"] and 'state="done"' in a[name]["expr"] and "> 0" in a[name]["expr"], name
    assert "offset 24h" in a["ApikeyWaveStalled"]["expr"], "a series younger than the window must not count as flat"
    # the count is merged over the target labels first (identity verified/stale flips when the builder is stopped by its nightly backup, one sample under the other label
    # made `delta(done[24h]) == 0` true on 2026-10-22 although 82 pools were done): a subquery over `max by (instance, host)`, never `delta(...[24h])` on the raw series
    stalled = " ".join(a["ApikeyWaveStalled"]["expr"].split())
    assert 'delta(max by (instance, host) (fleet_apikey_wave_pools{state="done"})[24h:5m]) == 0' in stalled
    assert 'delta(fleet_apikey_wave_pools' not in stalled
    stale = re.search(r">\s*(\d+)\s*\*\s*3600\b", a["ApikeyWaveSilent"]["expr"])
    assert stale and int(stale.group(1)) * 60 > NIGHTLY_STOP_MINUTES, "the staleness threshold must exceed the nightly builder stop"
    assert minutes(a["ApikeyWaveHalted"]["for"]) >= 10 and minutes(a["ApikeyWaveStalled"]["for"]) >= 60


def test_the_rule_file_is_shipped_by_the_monitoring_role_and_run_by_ci():
    defaults = yaml.safe_load((ROOT / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/defaults/main.yml").read_text(encoding="utf-8"))
    assert "fleet-apikey-wave.yml" in defaults["monitoring_prometheus_adopted_rule_files"]
    ci = (ROOT / ".woodpecker.yml").read_text(encoding="utf-8")
    assert "tests/test_apikey_wave_rules.py" in ci


@pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed here (it runs on the monitoring VM)")
def test_promtool_accepts_the_rules_and_its_own_unit_tests_pass():
    check = subprocess.run(["promtool", "check", "rules", str(RULES)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    run = subprocess.run(["promtool", "test", "rules", str(PROMTOOL_TEST)], capture_output=True, text=True, cwd=PROMTOOL_TEST.parent)
    assert run.returncode == 0, run.stdout + run.stderr
