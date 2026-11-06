"""CI cache prune alerts (config/prometheus/rules/fleet-ci-cache-prune.yml), added 2026-11-02 after go-build ended every nightly prune above its
cap from 10-21 to 11-01 on the Woodpecker pilot agent and nothing alerted: scripts/ci-cache/prune.sh (services-registry PR #806) logged a line and
exited 0. The metrics are the node-exporter textfile that `prune.sh --prom FILE` writes.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-ci-cache-prune.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_ci_cache_prune_rules_test.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "fleet-observability.md"
ROLE_DEFAULTS = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "monitoring_vm" / "defaults" / "main.yml"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")
# The four series services-registry scripts/ci-cache/prune.sh --prom writes (its own tests pin them); a rule that reads any other name never fires.
PRUNE_SH_METRICS = {
    "ci_cache_prune_last_run_timestamp_seconds",
    "ci_cache_prune_size_bytes",
    "ci_cache_prune_cap_bytes",
    "ci_cache_prune_over_cap",
}


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
        "CiCacheOverCap": ("5m", "warning"),
        "CiCachePruneStale": ("30m", "warning"),
        "CiCachePruneMissing": ("3d", "warning"),
    }
    assert set(alerts) == set(expected)
    for name, (delay, severity) in expected.items():
        assert alerts[name]["for"] == delay and alerts[name]["labels"] == {"severity": severity, "service": "fleet_ci_cache_prune"}, name
        assert alerts[name]["annotations"]["runbook_url"].endswith("#ci-cache-prune-alerts"), name
    assert "## CI cache prune alerts" in RUNBOOK.read_text(encoding="utf-8")


def test_the_alerts_name_the_host_and_the_cache_and_merge_duplicate_series() -> None:
    alerts = _alerts()
    assert " ".join(alerts["CiCacheOverCap"]["expr"].split()) == "max by (host, cache) (ci_cache_prune_over_cap) == 1"
    assert " ".join(alerts["CiCachePruneStale"]["expr"].split()) == "time() - max by (host) (ci_cache_prune_last_run_timestamp_seconds) > 36 * 3600"


def test_a_check_that_reads_nothing_cannot_stay_green() -> None:
    assert _alerts()["CiCachePruneMissing"]["expr"].strip() == "absent(ci_cache_prune_last_run_timestamp_seconds)"


def test_the_rules_only_read_metrics_that_prune_sh_writes() -> None:
    used = {name for rule in _alerts().values() for name in re.findall(r"\bci_cache_prune_\w+", rule["expr"])}
    assert used and used <= PRUNE_SH_METRICS, used - PRUNE_SH_METRICS


def test_the_monitoring_vm_role_ships_the_rule_file() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))
    assert "fleet-ci-cache-prune.yml" in defaults["monitoring_prometheus_adopted_rule_files"]
