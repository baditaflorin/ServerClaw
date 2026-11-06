"""Alert rules for the agent-history store (config/prometheus/rules/agent-history.yml, ADR 0494).

The store (agent-store) exports its metrics on /metrics; a bridge on the guest copies them, with agent_history_scrape_success and agent_history_scrape_timestamp_seconds,
into the node exporter's textfile directory, and the nightly canary scan adds agent_history_canary_*. Pinned here: every alert exists with the severity and delay the unit tests
(tests/promtool/agent_history_rules_test.yml) assume, no alert is critical (the owner's decision of 2026-10-29 on question 16: warning only, including for a canary leak),
the ingest-lag and query metrics are read as histograms, the metric names are the ones the store and agent-eval export, both data-disk alerts select the same mount point, each alert
carries a runbook link, the unit-test file covers each alert firing and not firing, and (when promtool is installed) the rules pass `promtool check` and the unit tests.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "agent-history.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "agent_history_rules_test.yml"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")

# alert -> (severity, for)
EXPECTED = {
    "AgentHistoryStoreDown": ("warning", "10m"),
    "AgentHistoryMetricsStale": ("warning", "5m"),
    "AgentHistoryIngestLagHigh": ("warning", "30m"),
    "AgentHistorySpoolDepthHigh": ("warning", "30m"),
    "AgentHistoryCollectorSilent": ("warning", "1h"),
    "AgentHistoryRedactionHit": ("warning", "0m"),
    "AgentHistoryQuerySlow": ("warning", "15m"),
    "AgentHistoryParseErrors": ("info", "0m"),
    "AgentHistoryRejectedLines": ("info", "0m"),
    "AgentHistoryClockSkew": ("info", "30m"),
    "AgentHistoryCanaryLeak": ("warning", "0m"),
    "AgentHistoryCanaryStale": ("warning", "1h"),
    "AgentHistoryCanaryMissing": ("info", "24h"),
    "AgentHistoryDataDiskLow": ("warning", "30m"),
    "AgentHistoryDataDiskFillingFast": ("warning", "30m"),
    "AgentHistoryBackupMissing": ("warning", "36h"),
}
# Names agent-store exports (internal/metrics/metrics.go) and agent-eval writes (internal/canary/metrics.go); the bridge adds the two scrape series.
EXPORTED = {
    "agent_history_scrape_success",
    "agent_history_scrape_timestamp_seconds",
    "agent_history_ingest_lag_seconds_bucket",
    "agent_history_spool_depth",
    "agent_history_collector_last_seen_seconds",
    "agent_history_redactions_total",
    "agent_history_query_seconds_bucket",
    "agent_history_parse_errors_total",
    "agent_history_rejected_lines_total",
    "agent_history_clock_skew_seconds",
    "agent_history_canary_leaks",
    "agent_history_canary_last_success_timestamp_seconds",
}


def _alerts() -> dict[str, dict]:
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_exactly_these_alerts_exist_with_the_severity_and_delay_the_unit_tests_assume() -> None:
    alerts = _alerts()
    assert set(alerts) == set(EXPECTED)
    for name, (severity, delay) in EXPECTED.items():
        rule = alerts[name]
        assert rule["labels"]["severity"] == severity, name
        assert rule["labels"]["service"] == "agent_history", name
        assert rule["for"] == delay, name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name


def test_nothing_is_critical_because_the_owner_decided_warning_only() -> None:
    severities = {name: rule["labels"]["severity"] for name, rule in _alerts().items()}
    assert "critical" not in severities.values(), "question 16: warning only, no paging, including for a canary leak"
    assert severities["AgentHistoryCanaryLeak"] == "warning"
    assert severities["AgentHistoryRedactionHit"] == "warning"
    assert "TODO(ADR 0494 question 16)" not in RULES.read_text(encoding="utf-8"), "the question is answered"


def test_every_alert_links_a_runbook() -> None:
    for name, rule in _alerts().items():
        assert rule["annotations"]["runbook_url"].startswith("docs/runbooks/"), name


def test_the_ingest_lag_and_the_query_time_are_read_as_histograms() -> None:
    alerts = _alerts()
    for name, bucket in (
        ("AgentHistoryIngestLagHigh", "agent_history_ingest_lag_seconds_bucket"),
        ("AgentHistoryQuerySlow", "agent_history_query_seconds_bucket"),
    ):
        expr = alerts[name]["expr"]
        assert "histogram_quantile(0.95" in expr and f"rate({bucket}[" in expr and "sum by (le)" in expr, name


def test_the_expressions_use_only_names_the_store_and_the_canary_export() -> None:
    names: set[str] = set()
    for rule in _alerts().values():
        names |= set(re.findall(r"\b(agent_history_[a-z_]+)\b", rule["expr"]))
    assert names == EXPORTED, names ^ EXPORTED


def test_both_data_disk_alerts_select_the_same_mount_point_and_filesystems() -> None:
    alerts = _alerts()
    selector = 'mountpoint="/srv/agent-history",fstype!~"tmpfs|overlay|squashfs|ramfs"'
    low = alerts["AgentHistoryDataDiskLow"]["expr"].replace(" ", "")
    fast = alerts["AgentHistoryDataDiskFillingFast"]["expr"].replace(" ", "")
    assert low.count(selector) == 2 and fast.count(selector) == 1
    assert "<0.20" in low and "predict_linear(" in fast and "14*86400" in fast


def test_the_backup_alert_covers_only_the_gap_the_generic_pbs_alerts_cannot() -> None:
    expr = " ".join(_alerts()["AgentHistoryBackupMissing"]["expr"].split())
    assert expr.startswith("absent(pbs_backup_group_last_snapshot_timestamp_seconds{")
    assert 'backup_type="vm"' in expr and 'backup_id="155"' in expr and 'namespace=""' in expr
    assert "and on() (agent_history_scrape_timestamp_seconds > 0)" in expr, (
        "silent until the guest reports metrics at all"
    )


def test_the_canary_alerts_follow_the_names_agent_eval_writes() -> None:
    alerts = _alerts()
    assert alerts["AgentHistoryCanaryLeak"]["expr"].strip() == "agent_history_canary_leaks > 0"
    assert "36 * 3600" in alerts["AgentHistoryCanaryStale"]["expr"]
    assert (
        alerts["AgentHistoryCanaryMissing"]["expr"]
        .strip()
        .startswith("absent(agent_history_canary_last_success_timestamp_seconds)")
    )


def test_the_promtool_test_file_covers_every_alert_firing_and_not_firing() -> None:
    doc = yaml.safe_load(PROMTOOL_TEST.read_text(encoding="utf-8"))
    seen: dict[str, set[bool]] = {name: set() for name in EXPECTED}
    for case in doc["tests"]:
        for check in case["alert_rule_test"]:
            seen[check["alertname"]].add(bool(check["exp_alerts"]))
    assert all(flags == {True, False} for flags in seen.values()), {n: f for n, f in seen.items() if f != {True, False}}
