"""PostgresUnitNotActive and PostgresIoStall: the production database being down, or stalled on its disk, is named within minutes (2026-10-19).

PostgresIoStall (added the same afternoon): at 01:15-02:45Z the nightly snapshot backup of infer-pg-primary onto the slow PBS throttled the guest's writes (I/O wait 71-90 %, disk writes
about 0 MiB/s, a checkpoint 5258 s instead of ~810 s, DomainScope categorize effectively down for 80 minutes) while load stayed under 7 and blocked tasks under 4: nothing alerted.
Pinned: the rule reads the I/O wait pressure, starts at 60 % for 10 minutes (the periodic read bursts reach 20-37 %), is critical, and only judges hosts that run a Postgres cluster unit.


On 2026-10-19 at 11:31Z the kernel OOM killer shot the helper processes of the production DomainScope Postgres (infer-pg-primary, VM 701) after a burst of about 125
new connections on a 48 GB VM with no swap; systemd stopped the whole unit (OOMPolicy=stop, Restart=no) and it stayed down for 21 minutes. The only alert was
FleetServiceEdgeDown (critical, the edge probe, 15 minute hard-fail delay) at 11:48Z: no postgres exporter exists and no rule used node_systemd_unit_state, although the
unit's series showed failed=1 from 11:32Z. Pinned: the alert exists with its delay, severity and the cause it names, it matches only per-cluster units (not the umbrella
postgresql.service), the monitoring role ships the file, and (when promtool is installed) the rule file passes promtool check and its unit tests.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-postgres-unit.yml"
ROLE_DEFAULTS = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "monitoring_vm" / "defaults" / "main.yml"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts() -> dict[str, dict]:
    return {r["alert"]: r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"] if "alert" in r}


def test_the_alert_exists_with_its_delay_severity_and_names_the_cause() -> None:
    r = _alerts()["PostgresUnitNotActive"]
    assert r["for"] == "3m" and r["labels"]["severity"] == "critical" and r["labels"]["service"] == "postgres"
    assert "{{ $labels.name }}" in r["annotations"]["summary"] and "{{ $labels.host }}" in r["annotations"]["summary"]
    description = r["annotations"]["description"]
    assert "oom-kill" in description and "reset-failed" in description and "streaming" in description


def test_the_alert_matches_per_cluster_units_only_and_the_state_that_means_down() -> None:
    expr = _alerts()["PostgresUnitNotActive"]["expr"]
    assert 'name=~"postgresql@.+[.]service"' in expr, "the umbrella postgresql.service stays active (exited) when the cluster is down, so it must not be the signal"
    assert 'state="active"' in expr and expr.rstrip().endswith("== 0")
    assert "by (host, instance, name)" in expr


def test_the_io_stall_alert_reads_the_wait_pressure_and_only_judges_postgres_hosts() -> None:
    r = _alerts()["PostgresIoStall"]
    assert r["for"] == "10m" and r["labels"]["severity"] == "critical" and r["labels"]["service"] == "postgres"
    expr = r["expr"]
    assert "rate(node_pressure_io_waiting_seconds_total[5m])" in expr and "> 60" in expr
    assert "and on (instance)" in expr and 'name=~"postgresql@.+[.]service"' in expr and 'state="active"' in expr and "== 1" in expr
    assert "{{ $labels.host }}" in r["annotations"]["summary"]
    description = r["annotations"]["description"]
    assert "infer-pg-nightly-pbs" in description and "fleecing" in description and "Never cancel a running backup" in description
    assert "pvesh delete" not in description


def test_the_monitoring_role_ships_the_rule_file() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))
    assert "fleet-postgres-unit.yml" in defaults["monitoring_prometheus_adopted_rule_files"]


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(REPO / "tests" / "promtool" / "fleet_postgres_unit_rules_test.yml")]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr
