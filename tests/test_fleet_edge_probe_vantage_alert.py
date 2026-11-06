"""FleetEdgeProbeVantageStale: a dead edge probe vantage is named even when another vantage keeps the whole-probe alert quiet (2026-10-19).

FleetEdgeProbeStale takes max() over every vantage, so it only fires when the whole probe is blind. On 2026-10-18 02:54Z the CT108 vantage started exiting 2 on every run
("no eligible services matched filters": /etc/default/fleet-edge-probe still said EDGE_PROBE_RUNTIME=coolify after the Coolify migration left no such runtime in the
registry) and stayed dead for 26 hours while the monitoring VM's vantage kept the max fresh: nothing fired. Pinned: the per-vantage alert exists with its delay and its
pointer to the cause, the whole-probe alert is unchanged, and (when promtool is installed) the rule file passes promtool check and its unit tests.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-edge-probe.yml"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts() -> dict[str, dict]:
    return {r["alert"]: r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"] if "alert" in r}


def test_the_per_vantage_alert_exists_with_its_delay_and_names_the_cause() -> None:
    r = _alerts()["FleetEdgeProbeVantageStale"]
    assert r["expr"] == "(time() - max by (vantage) (fleet_edge_probe_last_run)) > 3600" and r["for"] == "10m" and r["labels"]["severity"] == "warning"
    assert "{{ $labels.vantage }}" in r["annotations"]["summary"]
    assert "EDGE_PROBE_RUNTIME" in r["annotations"]["description"] and "no eligible services matched filters" in r["annotations"]["description"]


def test_the_whole_probe_alert_is_unchanged() -> None:
    r = _alerts()["FleetEdgeProbeStale"]
    assert r["expr"] == "(time() - max(fleet_edge_probe_last_run)) > 3600" and r["for"] == "10m" and r["labels"]["severity"] == "warning"


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(REPO / "tests" / "promtool" / "fleet_edge_probe_rules_test.yml")]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr
