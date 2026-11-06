"""Tests for the hostconf alerts (config/prometheus/rules/fleet-hostconf.yml) and their links to the tool that writes the metrics
(scripts/hostconf.py) and to the job that ships them (scripts/hostconf-scheduled.sh).

The promtool unit tests (tests/promtool/fleet_hostconf_rules_test.yml) run when promtool is installed (it is on the monitoring VM, not in the CI
image); the rest runs anywhere with only the standard library and PyYAML. What these tests are for: an alert that names a metric or a label the tool
no longer writes is silent forever (the 2026-10 rename of `host` to `machine` would have done exactly that), and a job that ships to another path than
the alert text names leaves nobody looking.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMTOOL_DIR = REPO_ROOT / "tests" / "promtool"
RULES = REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-hostconf.yml"
TOOL = REPO_ROOT / "scripts" / "hostconf.py"
JOB = REPO_ROOT / "scripts" / "hostconf-scheduled.sh"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "host-local-config.md"

requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _rules() -> list[dict]:
    return [r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"]]


def _tool():
    spec = importlib.util.spec_from_file_location("hostconf", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@requires_promtool
def test_rules_pass_promtool_check_and_unit_tests() -> None:
    for args in (("check", "rules", str(RULES)), ("test", "rules", str(PROMTOOL_DIR / "fleet_hostconf_rules_test.yml"))):
        result = subprocess.run(["promtool", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr


def test_every_alert_has_a_promtool_case_and_the_test_points_at_the_rule_file() -> None:
    tests = yaml.safe_load((PROMTOOL_DIR / "fleet_hostconf_rules_test.yml").read_text(encoding="utf-8"))
    assert [(PROMTOOL_DIR / item).resolve() for item in tests["rule_files"]] == [RULES]
    covered = {check["alertname"] for case in tests["tests"] for check in case["alert_rule_test"]}
    declared = {rule["alert"] for rule in _rules()}
    assert covered == declared, f"alerts without a promtool case: {sorted(declared - covered)}"


def test_every_alert_is_a_warning_of_the_hostconf_service_with_a_runbook_that_names_it() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for rule in _rules():
        assert rule["labels"] == {"severity": "warning", "service": "hostconf"}, rule["alert"]
        assert rule["annotations"]["runbook_url"] == "docs/runbooks/host-local-config.md", rule["alert"]
        assert rule["alert"] in runbook, f"{rule['alert']} is not described in the runbook"
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], rule["alert"]


def test_the_for_durations_count_daily_runs() -> None:
    """The textfile keeps its last values between daily runs: 2h = still there at the next look, 26h = there on two runs in a row."""
    by_name = {r["alert"]: r for r in _rules()}
    for name in ("HostconfBelowBaseline", "HostconfDrift", "HostconfInventoryFinding", "HostconfCheckMissing"):
        assert by_name[name]["for"] == "2h", name
    for name in ("HostconfMachineUnreachable", "HostconfInventoryUnreachable"):
        assert by_name[name]["for"] == "26h", name
    assert "> 129600" in by_name["HostconfCheckStale"]["expr"]   # 36 hours: one missed day is a laptop that slept, two is a job that died


def test_the_rules_use_only_metrics_and_labels_the_tool_writes() -> None:
    tool = _tool()
    manifest = {"hosts": {"a": {"files": []}, "b": {"files": []}}}
    results = [{"host": "a", "files": [], "expects": [{"file": "<baseline>", "ok": False}]}, {"host": "b", "unreachable": "x", "files": [], "expects": []}]
    inventory = {"hv1": {"unreachable": False, "findings": ["x"]}, "hv2": {"unreachable": True, "findings": []}}
    text = tool.metrics_text(manifest, results, now=1, inventory=inventory)
    written = {line.split("{")[0].split(" ")[0] for line in text.splitlines() if line and not line.startswith("#")}
    labels_written = set(re.findall(r'(\w+)="', text))
    used_metrics: set[str] = set()
    used_labels: set[str] = set()
    for rule in _rules():
        used_metrics |= set(re.findall(r"fleet_hostconf_[a-z_]+", rule["expr"]))
        used_labels |= set(re.findall(r"on \((\w+)\)", rule["expr"]))
        used_labels |= set(re.findall(r"\$labels\.(\w+)", rule["annotations"]["summary"] + rule["annotations"]["description"]))
    assert used_metrics <= written, f"metrics the rules use but the tool does not write: {sorted(used_metrics - written)}"
    assert used_labels <= labels_written, f"labels the rules use but the tool does not write: {sorted(used_labels - labels_written)}"
    assert "host" not in labels_written  # Prometheus renames a scraped `host` to `exported_host`: the machine label is `machine`


def test_the_job_ships_to_the_path_and_the_log_the_alert_texts_name() -> None:
    job = JOB.read_text(encoding="utf-8")
    descriptions = " ".join(r["annotations"]["description"] for r in _rules())
    assert "/var/lib/prometheus/node-exporter/fleet_hostconf.prom" in job
    assert "fleet_hostconf.prom" in descriptions and "/var/lib/prometheus/node-exporter/" in descriptions
    assert "Library/Logs/hostconf-drift.log" in job and "Library/Logs/hostconf-drift.log" in descriptions
    assert "hostconf-scheduled.sh" in descriptions and "status" in descriptions
