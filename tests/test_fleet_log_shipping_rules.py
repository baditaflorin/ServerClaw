"""Hypervisor log shipping alerts (config/prometheus/rules/fleet-log-shipping.yml) and their probe, added 2026-11-01.

0mcp, 0infer and 0pipe shipped nothing to OpenObserve for weeks until 2026-10-30 and nothing noticed.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-log-shipping.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_log_shipping_rules_test.yml"
PROBE = REPO / "config" / "0own" / "openobserve" / "log-freshness" / "openobserve-log-freshness.py"
RUNBOOK = REPO / "docs" / "runbooks" / "fleet-observability.md"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


def _probe():
    spec = importlib.util.spec_from_file_location("openobserve_log_freshness", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_alerts_exist_with_the_severity_delay_and_runbook_the_unit_tests_assume() -> None:
    alerts = _alerts()
    expected = {"HypervisorLogShippingSilent": "10m", "LogFreshnessProbeBlind": "15m"}
    assert set(alerts) == set(expected)
    for name, delay in expected.items():
        assert alerts[name]["for"] == delay, name
        assert alerts[name]["labels"] == {"severity": "warning", "service": "fleet_log_shipping"}, name
        assert alerts[name]["annotations"]["runbook_url"].endswith("#hypervisor-log-shipping-alerts"), name
    assert "## Hypervisor log shipping alerts" in RUNBOOK.read_text(encoding="utf-8")


def test_a_host_missing_from_the_window_is_written_with_timestamp_zero(tmp_path, monkeypatch) -> None:
    mod = _probe()
    out = tmp_path / "x.prom"
    monkeypatch.setattr(mod, "OUT", str(out))
    monkeypatch.setattr(mod, "last_events", lambda: {"0pipe": 1_700_000_000, "0mcp": 1_700_000_100})
    assert mod.main() == 0
    text = out.read_text()
    assert "openobserve_log_freshness_up 1" in text
    assert 'host="0pipe",role="hypervisor"} 1700000000' in text
    assert 'host="0infer",role="hypervisor"} 0' in text
    assert text.count("openobserve_log_last_event_timestamp_seconds{") == len(mod.HYPERVISORS)


def test_a_failing_query_writes_up_zero_and_no_host_series(tmp_path, monkeypatch) -> None:
    mod = _probe()
    out = tmp_path / "x.prom"
    monkeypatch.setattr(mod, "OUT", str(out))

    def boom():
        raise OSError("connection refused")

    monkeypatch.setattr(mod, "last_events", boom)
    assert mod.main() == 1
    text = out.read_text()
    assert "openobserve_log_freshness_up 0" in text
    assert "openobserve_log_last_event_timestamp_seconds{" not in text
