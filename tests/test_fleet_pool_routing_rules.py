"""The alert that watches whether the pools' replicas still take traffic (config/prometheus/rules/fleet-pool-routing.yml).

2026-10-22: a bulk nginx-render push from a host without the private service-pools.json took 282 services off their pools on the gateway and no per-pool signal
noticed. Pinned here: the alert exists with the severity and delay the unit tests assume, it counts the POOLS whose replicas (never the Docker host) get under 5 % of the
traffic although their weights give them more than 30 % (a count of pools does not depend on how many pools carry traffic: the first version, an average against its 24 h
maximum, fired at 18:51Z for a healthy fleet when the pools with a measured share fell from 131 to 10), it stays quiet on a frozen balancer file, it points to a runbook that
exists and names the restore, and (when promtool is installed) the rules pass `promtool check` and their unit tests.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-pool-routing.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_pool_routing_rules_test.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "pool-routing-collapse.md"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_alerts_exist_with_the_severity_and_delay_the_unit_tests_assume() -> None:
    a = _alerts()
    assert set(a) == {"FleetPoolReplicaShareCollapsed", "FleetPoolBalanceStuck", "FleetPoolBalanceEnvGuardHolding"}
    # FleetPoolBalanceEnvGuardHolding has no delay of its own: its expression already asks for 6 of the last 8 hours (the value only changes on the hour)
    assert "for" not in a["FleetPoolBalanceEnvGuardHolding"]
    for name, delay in (("FleetPoolReplicaShareCollapsed", "30m"), ("FleetPoolBalanceStuck", "2h"), ("FleetPoolBalanceEnvGuardHolding", None)):
        rule = a[name]
        assert rule["labels"] == {"severity": "warning", "service": "fleet_pool_routing"}, name
        if delay is not None:
            assert rule["for"] == delay, name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name
        assert rule["annotations"]["runbook_url"] == "docs/runbooks/pool-routing-collapse.md", name


def test_the_stuck_alert_needs_many_proposals_nothing_applied_apply_on_and_a_fresh_file() -> None:
    """2026-10-22 10:31-14:31Z: 200-257 pending proposals against a normal 3-5, none applied. A frozen file (the balancer starved of its lock) must not alert: the freshness term."""
    expr = " ".join(_alerts()["FleetPoolBalanceStuck"]["expr"].split())
    assert "max(fleet_pool_balance_proposals_pending) > 30" in expr
    assert "max(fleet_pool_balance_applied) == 0" in expr
    assert "max(fleet_pool_balance_apply_enabled) == 1" in expr
    assert "(time() - max(fleet_pool_balance_last_run_timestamp_seconds)) < 1800" in expr


def test_it_counts_the_pools_whose_replicas_get_almost_nothing_although_their_weights_give_them_a_lot() -> None:
    expr = " ".join(_alerts()["FleetPoolReplicaShareCollapsed"]["expr"].split())
    measured = 'sum by (service) (fleet_pool_balance_member_measured_share_pct{target!="dockerhost"})'
    configured = 'sum by (service) (fleet_pool_balance_member_configured_share_pct{target!="dockerhost"})'
    # per pool, replicas only: under 5 % arrives although the weights give more than 30 %, and the pool count is over 5 (1-4 pools are normal)
    assert f"count( ({measured} < 5) and on (service) ({configured} > 30) ) > 5" in expr
    # the Docker host's own share must never be counted (it rises when the replicas stop taking traffic and would mask the collapse)
    assert expr.count('{target!="dockerhost"}') == 2 and 'target="dockerhost"' not in expr
    # a count of pools, not an average against a baseline: at low traffic only ~10 pools have a measured share (131 during the bulk scan) and an
    # average against its own 24 h maximum described two different sets of pools (false alarm at 18:51Z on 2026-10-22)
    for forbidden in ("avg(", "max_over_time", "offset"):
        assert forbidden not in expr, forbidden


def test_a_frozen_balancer_file_does_not_raise_the_share_alert() -> None:
    """The pool guardian's 31 minute runs hold the shared lock, the balancer then keeps its last numbers: the file must be fresh (FleetPoolBalanceSilent owns the frozen case)."""
    expr = " ".join(_alerts()["FleetPoolReplicaShareCollapsed"]["expr"].split())
    assert "and on () (time() - max(fleet_pool_balance_last_run_timestamp_seconds)) < 1800" in expr


def test_the_runbook_exists_names_the_cause_and_the_restore() -> None:
    rule = _alerts()["FleetPoolReplicaShareCollapsed"]
    assert rule["annotations"]["runbook_url"] == "docs/runbooks/pool-routing-collapse.md"
    text = RUNBOOK.read_text(encoding="utf-8")
    for needle in ("nginx-render --exact-filter", "--service-pools", "--push --reload", "balance.lock", "fleet_pool_", "--allow-unpool", "2026-10-22", "FleetPoolBalanceStuck"):
        assert needle in text, needle


def test_the_env_guard_alert_takes_the_hourly_maximum_share_of_the_planned_pools_for_six_of_eight_hours() -> None:
    """2026-10-24/25: the guard held 66-95 % of 282 pools in a full planning run in 23 of 27 hours while a few pools an hour were still applied (FleetPoolBalanceStuck needs applied == 0).

    The number per run is heavy-tailed (1 in a batch run, 186-267 in a full run): an instant value or an average would miss it, so the rule takes the maximum over each hour.
    """
    expr = " ".join(_alerts()["FleetPoolBalanceEnvGuardHolding"]["expr"].split())
    assert "max by (instance) (max_over_time(fleet_pool_balance_skipped_env_contract[1h]))" in expr
    assert "max by (instance) (max_over_time(fleet_pool_balance_pools[1h]))" in expr
    assert "> bool 0.4" in expr and ")[8h:1h] ) >= 6" in expr
    assert "(max by (instance) (fleet_pool_balance_apply_enabled) == 1)" in expr
    assert "(time() - max(fleet_pool_balance_last_run_timestamp_seconds)) < 1800" in expr
    # an average over the planning runs would hide a run that holds most pools among quick runs that hold one
    for forbidden in ("avg(", "avg_over_time", "quantile"):
        assert forbidden not in expr, forbidden


def test_the_runbook_has_a_section_for_the_env_guard_alert_with_the_check_and_the_causes() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "## FleetPoolBalanceEnvGuardHolding" in text
    for needle in ("balance_skipped", "balanceHarmlessEnv", "fleet_pool_balance_skipped_env_contract", "v0.7.717", "APIKEY_SERVICE_URLS", "Do not turn the guard off"):
        assert needle in text, needle


def test_the_collapse_alert_has_no_traffic_floor_because_a_bypass_starts_with_a_few_low_traffic_pools() -> None:
    """2026-10-26 02:14Z: 16 pools at 0.02-0.074 requests a second were the first pools of the DomainScope colocation bypass (124 ids by noon, 113 of 132 pools collapsed, the Docker host overloaded).

    A floor of 0.1 requests a second (#588) kept the alert silent for the first eight hours and was reverted. The runbook says why and how to tell a bypass from a dead pool.
    """
    expr = " ".join(_alerts()["FleetPoolReplicaShareCollapsed"]["expr"].split())
    assert "fleet_pool_balance_pool_requests_per_second" not in expr
    text = RUNBOOK.read_text(encoding="utf-8")
    for needle in ("FLEET_COLOCATE_SERVICES", "A few pools can be the start of a bigger bypass", "http_requests_total"):
        assert needle in text, needle

