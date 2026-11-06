"""The alerts that watch the off-host copy of the small encrypted backup archives (config/prometheus/rules/fleet-backup-offhost.yml).

2026-10-22: the keystore-db archive was about to pass the sidecar's size cap and GitHub's 100 MB file limit and nothing would have said so. The metrics come from
config/0docker/fleet-backup-offhost-check (textfile on VM 100, scraped as job node_exporter). Pinned here: the six alerts exist with the severities and delays the unit tests assume,
the age alerts use `time() - <absolute timestamp>` (so a dead checker cannot freeze an old age), both dead-man alerts have an absent() branch with the job selector, every alert
points to a runbook that exists, and (when promtool is installed) the rules pass `promtool check` and their unit tests.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-backup-offhost.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_backup_offhost_rules_test.yml"
RUNBOOK = REPO / "docs" / "runbooks" / "fleet-backup-offhost-copy.md"
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_six_alerts_exist_with_the_severities_and_delays_the_unit_tests_assume() -> None:
    a = _alerts()
    want = {
        "FleetBackupOffhostCopyStale": ("warning", "30m"),
        "FleetBackupOffhostCopyVeryStale": ("critical", "30m"),
        "FleetBackupOffhostCopyBroken": ("warning", "1h"),
        "FleetBackupOffhostCheckStale": ("warning", "10m"),
        "FleetBackupOffhostDeepCheckFailed": ("critical", "5m"),
        "FleetBackupOffhostDeepCheckStale": ("warning", "1h"),
    }
    assert set(a) == set(want)
    for name, (severity, delay) in want.items():
        rule = a[name]
        assert rule["labels"]["severity"] == severity and rule["labels"]["service"] == "fleet_backup_offhost" and rule["for"] == delay, name
        assert rule["annotations"]["summary"] and rule["annotations"]["description"], name


def test_the_age_alerts_measure_from_an_absolute_timestamp_with_the_36_and_72_hour_limits() -> None:
    a = _alerts()
    assert a["FleetBackupOffhostCopyStale"]["expr"].strip() == "time() - fleet_backup_offhost_copy_timestamp_seconds > 129600"  # 36 h
    assert a["FleetBackupOffhostCopyVeryStale"]["expr"].strip() == "time() - fleet_backup_offhost_copy_timestamp_seconds > 259200"  # 72 h
    assert a["FleetBackupOffhostCopyBroken"]["expr"].strip() == "fleet_backup_offhost_copy_present == 0"


def test_both_dead_man_alerts_cover_a_stale_metric_and_a_missing_one() -> None:
    a = _alerts()
    check = a["FleetBackupOffhostCheckStale"]["expr"]
    assert "time() - fleet_backup_offhost_check_last_success_timestamp_seconds > 10800" in check
    assert 'absent(fleet_backup_offhost_check_last_success_timestamp_seconds{job="node_exporter"})' in check
    deep = a["FleetBackupOffhostDeepCheckStale"]["expr"]
    assert "time() - fleet_backup_offhost_deep_last_success_timestamp_seconds > 180000" in deep
    assert 'absent(fleet_backup_offhost_deep_last_success_timestamp_seconds{job="node_exporter"})' in deep


def test_the_deep_failure_alert_is_on_the_per_source_result() -> None:
    assert _alerts()["FleetBackupOffhostDeepCheckFailed"]["expr"].strip() == "fleet_backup_offhost_deep_source_ok == 0"


def test_every_alert_points_to_the_runbook_and_the_runbook_exists() -> None:
    assert RUNBOOK.is_file()
    text = RUNBOOK.read_text(encoding="utf-8")
    for name, rule in _alerts().items():
        assert rule["annotations"]["runbook_url"] == "docs/runbooks/fleet-backup-offhost-copy.md", name
    for needle in ("fleet-backup-sync", "state.tsv", "--undo", "cat payload/<source>.age.part-*", "CopyStale", "DeepCheckFailed"):
        assert needle in text, needle


def test_the_metric_names_in_the_rules_are_the_ones_the_tool_writes() -> None:
    tool = (REPO / "config" / "0docker" / "fleet-backup-offhost-check" / "fleet_backup_offhost_check.py").read_text(encoding="utf-8")
    exprs = " ".join(r["expr"] for r in _alerts().values())
    for metric in sorted({m for m in exprs.replace("(", " ").replace(")", " ").replace("{", " ").split() if m.startswith("fleet_backup_offhost_")}):
        assert f'"{metric}"' in tool, f"the rules use {metric} but the tool never writes it"


# Labels the monitoring Prometheus puts on every scraped node_exporter target (see the label sets of node_uname_info there: host, instance, job, fleet, identity, role, source, via,
# scanopy_id, vmid). A metric label with one of these names is renamed to exported_<name> and `{{ $labels.<name> }}` then shows the TARGET's value: the first deployment of these
# alerts on 2026-10-22 used `source` and every alert text would have said "scanopy_node".
TARGET_LABELS = {"host", "instance", "job", "fleet", "identity", "role", "source", "via", "scanopy_id", "vmid"}


def test_no_metric_label_of_the_tool_collides_with_a_scrape_target_label() -> None:
    import re

    tool = (REPO / "config" / "0docker" / "fleet-backup-offhost-check" / "fleet_backup_offhost_check.py").read_text(encoding="utf-8")
    used = set(re.findall(r"""f?'\{\{(\w+)="\{""", tool)) | set(re.findall(r'\{\{(\w+)=\\?"\{src\}', tool))
    assert "archive" in used, used
    assert not (used & TARGET_LABELS), used & TARGET_LABELS
    for name, rule in _alerts().items():
        refs = set(re.findall(r"\$labels\.(\w+)", rule["annotations"]["summary"] + rule["annotations"]["description"]))
        assert not (refs & TARGET_LABELS), (name, refs & TARGET_LABELS)
        assert "source" not in re.findall(r"\b(\w+)\s*(?:=|!=|=~)\s*\"", rule["expr"]) and 'source=' not in rule["expr"], name
