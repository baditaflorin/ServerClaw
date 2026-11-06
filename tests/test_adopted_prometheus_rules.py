"""Rule files that ran on the monitoring VM with no copy in git (found 2026-10-14) and are now shipped by the monitoring_vm role.

A rebuilt monitoring VM would have lost every one of them: node placement and contention alerts, the PVE host incident, recovery and
storage alerts, thermal alerts, Prometheus capacity and the edge probe rules. The tests pin that each file exists, parses, is shipped
by the role, and that nothing in config/prometheus/rules/ is left without a way onto the VM.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES = REPO_ROOT / "config" / "prometheus" / "rules"
ROLE = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "monitoring_vm"
ADOPTED = [
    "fleet-edge-probe.yml",
    "node-placement.yml",
    "node-thermal-alerts.yml",
    "prometheus-capacity.yml",
    "pve-host-incident.yml",
    "pve-recovery-alerts.yml",
    "pve-storage-capacity.yml",
    "public-edge-critical.yml",
    "restore-drill.yml",
    "tier0-standby.yml",
    "pbs-usage.yml",
    "netpolicy.yml",
    "fleet-postgres-unit.yml",
    "fleet-image-gc.yml",
    "domainscope-search.yml",
    "domainscope-drive-refresh.yml",
    "fleet-apikey-wave.yml",
    "agent-history.yml",
    "fleet-job-caches-trim.yml",
    "proxmox-host-memory-budget.yml",
    "fleet-ci-cache-prune.yml",
]


def test_the_role_ships_exactly_the_adopted_files() -> None:
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["monitoring_prometheus_adopted_rule_files"] == ADOPTED
    tasks = yaml.safe_load((ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    copies = [t for t in tasks if t.get("loop") == "{{ monitoring_prometheus_adopted_rule_files }}"]
    assert len(copies) == 1
    copy = copies[0]["ansible.builtin.copy"]
    assert copy["src"].endswith("/config/prometheus/rules/{{ item }}")
    assert copy["dest"].endswith("/{{ item }}")
    assert (copy["owner"], copy["group"], copy["mode"]) == ("root", "prometheus", "0640")
    assert copies[0]["notify"] == "Reload Prometheus configuration"


@pytest.mark.parametrize("name", ADOPTED)
def test_every_adopted_file_is_a_valid_rule_file_with_complete_alerts(name: str) -> None:
    data = yaml.safe_load((RULES / name).read_text(encoding="utf-8"))
    rules = [rule for group in data["groups"] for rule in group["rules"]]
    assert rules, name
    for rule in rules:
        if "alert" in rule:
            assert rule["expr"] and rule["labels"]["severity"] in {"info", "warning", "critical"}, (name, rule["alert"])
            assert rule["annotations"]["summary"], (name, rule["alert"])
        else:
            assert rule["record"] and rule["expr"], name


@pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")
@pytest.mark.parametrize("name", ADOPTED)
def test_promtool_accepts_every_adopted_file(name: str) -> None:
    result = subprocess.run(
        ["promtool", "check", "rules", str(RULES / name)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")
def test_node_placement_unit_tests_pass() -> None:
    result = subprocess.run(
        ["promtool", "test", "rules", str(REPO_ROOT / "tests" / "promtool" / "node_placement_rules_test.yml")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_contention_alert_only_looks_at_guests_of_the_monitored_hypervisor() -> None:
    data = yaml.safe_load((RULES / "node-placement.yml").read_text(encoding="utf-8"))
    rule = next(r for g in data["groups"] for r in g["rules"] if r.get("alert") == "FleetHypervisorContentionMismatch")
    expr = " ".join(rule["expr"].split())
    # A bare `and on()` made any hot hypervisor alert for EVERY idle host (26 at once on 2026-10-14).
    assert 'fleet="0docker"' in expr and "on(host)" in expr
    assert "and on() (fleet:hypervisor_node_cpu_busy_percent > 70)" in expr
