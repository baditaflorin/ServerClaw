"""config/prometheus/rules/netpolicy.yml: alerts for the network policy drift check.

The rules must use the metric names the tool really writes, every alert must be complete and point at a real runbook, the waits must
outlast the nightly builder stop, and (where promtool is installed) its own unit tests must pass.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import netpolicy as np  # noqa: E402

RULES = ROOT / "config" / "prometheus" / "rules" / "netpolicy.yml"
PROMTOOL_TEST = ROOT / "tests" / "promtool" / "netpolicy_rules_test.yml"
NIGHTLY_STOP_MINUTES = 10
TIMER_MINUTES = 30


def alerts() -> dict[str, dict]:
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in data["groups"] for r in g["rules"]}


def minutes(duration: str) -> float:
    m = re.fullmatch(r"(\d+)([smhd])", duration)
    assert m, duration
    return int(m.group(1)) * {"s": 1 / 60, "m": 1, "h": 60, "d": 1440}[m.group(2)]


def test_every_alert_is_complete_and_points_at_a_real_runbook():
    a = alerts()
    assert set(a) == {"NetpolicyDrift", "NetpolicySilent", "NetpolicyNotReporting", "NetpolicyCannotLook", "NetpolicyUnmodelledRules"}
    for name, rule in a.items():
        assert rule["labels"]["severity"] in {"warning", "critical"} and rule["labels"]["service"] == "netpolicy", name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name
        assert (ROOT / rule["annotations"]["runbook_url"]).is_file(), name


def test_the_rules_use_exactly_metric_names_the_tool_writes():
    snap = {"host": "t", "cluster_fw": "", "vms": {"1": {"name": "x", "status": "running", "fw": "[OPTIONS]\nenable: 1\n", "ip": "10.0.0.1", "guest": {"ok": False}}}}
    policy = {"version": 1, "host": "t", "ipsets": {}, "vms": {"1": {"name": "x", "groups": [], "pve": {}, "guest": {}}}}
    res = np.drift(policy, snap)
    res["vms"]["1"]["name"] = "x"
    emitted = set(re.findall(r"^(netpolicy_\w+)", np.metrics_text(res, "t", False) + np.metrics_text(None, "t", True), re.M))
    used = set()
    for rule in alerts().values():
        used |= set(re.findall(r"netpolicy_\w+", rule["expr"]))
    assert used and used <= emitted, f"alerts read metrics the tool does not write: {sorted(used - emitted)}"
    for rule in alerts().values():
        for label in re.findall(r"\$labels\.(\w+)", rule["annotations"]["summary"] + rule["annotations"]["description"]):
            assert label in {"hypervisor", "vm"}, f"{label} is not a label the tool writes"


def test_staleness_is_paired_with_absent_and_every_wait_outlasts_the_builder_stop():
    a = alerts()
    assert "time() - netpolicy_last_run_timestamp_seconds" in a["NetpolicySilent"]["expr"]
    assert a["NetpolicyNotReporting"]["expr"] == "absent(netpolicy_last_run_timestamp_seconds)"
    # alerts whose condition a short outage of the builder can trip must wait longer than that outage
    for name in ("NetpolicyNotReporting", "NetpolicyCannotLook", "NetpolicyDrift", "NetpolicyUnmodelledRules"):
        assert minutes(a[name]["for"]) > NIGHTLY_STOP_MINUTES, name
    # the staleness alert is protected by its threshold instead: it takes 3 hours of silence before its `for:` even starts
    stale = re.search(r">\s*(\d+)\s*\*\s*3600\b", a["NetpolicySilent"]["expr"])
    assert stale and int(stale.group(1)) * 60 >= 6 * TIMER_MINUTES, "the staleness threshold exceeds several runs of the timer"
    assert int(stale.group(1)) * 60 > NIGHTLY_STOP_MINUTES


def test_the_timer_matches_the_cadence_the_alerts_assume():
    timer = (ROOT / "config" / "systemd" / "netpolicy-drift.timer").read_text()
    assert f"OnUnitInactiveSec={TIMER_MINUTES}min" in timer
    service = (ROOT / "config" / "systemd" / "netpolicy-drift.service").read_text()
    assert "SuccessExitStatus=2" in service and "flock -n" in service and "/usr/local/bin/netpolicy-run" in service


@pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")
def test_promtool_accepts_the_rules_and_its_unit_tests_pass():
    check = subprocess.run(["promtool", "check", "rules", str(RULES)], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
    test = subprocess.run(["promtool", "test", "rules", str(PROMTOOL_TEST)], cwd=ROOT, capture_output=True, text=True)
    assert test.returncode == 0, test.stdout + test.stderr


def test_the_textfile_directory_is_the_one_the_builders_node_exporter_reads():
    """Written to any other directory, the metrics never reach Prometheus and only the dead-man alert would notice, 3 hours later.
    The tailnet reconciler on the same builder uses the same directory; the wrapper must agree with the tool."""
    expected_dir = "/var/lib/prometheus-node-exporter/textfile"
    assert np.DEFAULT_TEXTFILE_DIR == expected_dir
    import tailscale_policy_reconcile as ts  # noqa: PLC0415
    assert str(ts.DEFAULT_TEXTFILE_DIR) == np.DEFAULT_TEXTFILE_DIR
    wrapper = (ROOT / "scripts" / "netpolicy-run").read_text()
    assert f"NETPOLICY_TEXTFILE_DIR:-{expected_dir}" in wrapper
    assert expected_dir in (ROOT / "docs" / "runbooks" / "network-policy.md").read_text()
    assert expected_dir in (ROOT / "scripts" / "netpolicy-install.sh").read_text() and "/var/lib/prometheus/node-exporter" not in (ROOT / "scripts" / "netpolicy-install.sh").read_text()
