"""Tests for the backup freshness alerts (config/prometheus/rules/fleet-backup-freshness.yml) and the PBS collector
(scripts/pbs_backup_metrics.py) that feeds them.

The promtool unit tests (tests/promtool/fleet_backup_freshness_rules_test.yml) run when promtool is installed; the rest runs
anywhere with only the standard library and PyYAML.
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
RULES = REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-backup-freshness.yml"
SCRIPT = REPO_ROOT / "scripts" / "pbs_backup_metrics.py"

requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _load_collector():
    spec = importlib.util.spec_from_file_location("pbs_backup_metrics", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@requires_promtool
def test_rules_pass_promtool_check_and_unit_tests() -> None:
    for args in (("check", "rules", str(RULES)), ("test", "rules", str(PROMTOOL_DIR / "fleet_backup_freshness_rules_test.yml"))):
        result = subprocess.run(["promtool", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr


def test_every_alert_has_a_promtool_case_and_the_test_points_at_the_rule_file() -> None:
    tests = yaml.safe_load((PROMTOOL_DIR / "fleet_backup_freshness_rules_test.yml").read_text(encoding="utf-8"))
    assert [(PROMTOOL_DIR / item).resolve() for item in tests["rule_files"]] == [RULES]
    covered = {check["alertname"] for case in tests["tests"] for check in case["alert_rule_test"]}
    declared = {rule["alert"] for group in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for rule in group["rules"]}
    assert covered == declared, f"alerts without a promtool case: {sorted(declared - covered)}"


def test_thresholds_are_26_and_50_hours_and_every_alert_has_severity_service_and_runbook() -> None:
    rules = [r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"]]
    by_name = {r["alert"]: r for r in rules}
    assert "> 93600" in by_name["PbsBackupGroupStale"]["expr"] and "> 180000" in by_name["PbsBackupGroupStaleCritical"]["expr"]
    for rule in rules:
        assert rule["labels"]["severity"] in {"info", "warning", "critical"}, rule["alert"]
        assert rule["labels"]["service"] == "pbs_backup", rule["alert"]
        assert rule["annotations"]["runbook_url"] == "docs/runbooks/pbs-0own-backups.md", rule["alert"]
    assert (REPO_ROOT / "docs" / "runbooks" / "pbs-0own-backups.md").is_file()


def test_the_pg_backup_alerts_are_gone_with_their_only_source() -> None:
    """2026-10-21: pg_backup_* came from the vzdump hook of job pg-primary-daily-pbs (VM 100, retired with pve01). A rule on a series nothing
    writes any more only fires when its last sample goes stale, so a leftover one would page about a VM that is off on purpose."""
    text = RULES.read_text(encoding="utf-8")
    declared = {rule["alert"] for group in yaml.safe_load(text)["groups"] for rule in group["rules"]}
    assert not {name for name in declared if name.startswith("PgBackup")}
    assert "pg_backup_" not in re.sub(r"(?m)^\s*#.*$", "", text)


def test_the_retired_0database_namespace_is_skipped_by_the_daily_pair_and_nothing_else_is() -> None:
    """The 0database fleet (pve01) is being sunset: VMs 100, 101 and 103 are off (2026-10-21) and the rest follows, while the snapshots stay in PBS
    until someone prunes them, and a group that is not pruned goes stale for ever. The exclusion names the namespace only, so no other fleet
    loses its alert (the promtool case keeps a stale 0own group alerting)."""
    by_name = {r["alert"]: r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"]}
    for daily in ("PbsBackupGroupStale", "PbsBackupGroupStaleCritical"):
        assert 'unless on (namespace)\npbs_backup_group_snapshot_count{namespace="0database"}' in by_name[daily]["expr"], daily
    for other in ("PbsBackupGroupWeeklyStale", "PbsBackupGroupWeeklyStaleCritical", "PbsBackupMetricsStale", "PbsDatastoreDiskSaturated"):
        assert "0database" not in by_name[other]["expr"], other


def test_the_paused_0docker_vm_group_is_skipped_by_the_daily_pair_and_the_state_backup_failure_is_a_warning() -> None:
    """0docker/vm/100 (the Docker host, VM level) is frozen at 2026-10-18 on purpose; the file-level backup of the same host is its own group and stays watched."""
    by_name = {r["alert"]: r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"]}
    for daily in ("PbsBackupGroupStale", "PbsBackupGroupStaleCritical"):
        assert 'unless on (namespace, backup_type, backup_id)\npbs_backup_group_snapshot_count{namespace="0docker", backup_type="vm", backup_id="100"}' in by_name[daily]["expr"], daily
        assert 'host' not in by_name[daily]["expr"].split('namespace="0docker"')[1].split("}")[0], "the exclusion must not name the host group"
    failed = by_name["DockerhostStateBackupFailed"]
    assert failed["expr"] == "dockerhost_state_backup_last_status == 0" and failed["for"] == "30m" and failed["labels"]["severity"] == "warning"


def test_the_ci_build_vm_group_is_skipped_by_the_daily_pair_by_group_only() -> None:
    """2026-10-22: root vm/130 (docker-build-lv3) is excluded from the 0mcp nightly job (it rewrote ~326 GiB of its disk every night); its newest two snapshots stay, so the
    group goes stale on purpose. The exclusion names that one group, so no other root-namespace VM loses its alert."""
    by_name = {r["alert"]: r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"]}
    for daily in ("PbsBackupGroupStale", "PbsBackupGroupStaleCritical"):
        expr = by_name[daily]["expr"]
        assert 'unless on (namespace, backup_type, backup_id)\npbs_backup_group_snapshot_count{namespace="", backup_type="vm", backup_id="130"}' in expr, daily
        assert expr.count('backup_id="130"') == 1 and "130|" not in expr and "|130" not in expr, daily
    for other in ("PbsBackupGroupWeeklyStale", "PbsBackupGroupWeeklyStaleCritical"):
        assert "130" not in by_name[other]["expr"], other


def test_a_weekly_group_is_skipped_by_the_daily_pair_and_judged_by_a_weekly_pair_with_the_same_selector() -> None:
    """0own/vm/610 has a weekly job (own-build-worker-nightly-pbs, sun 11:00). Without the exclusion its daily alerts fire every
    week (the 50-hour critical pages on day three); without the weekly pair it is not watched at all. The four selectors must
    name the same group, so a typo in one of them cannot silently exempt another group or leave this one unwatched."""
    rules = [r for g in yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"] for r in g["rules"]]
    by_name = {r["alert"]: r for r in rules}
    selector = '{namespace="0own", backup_type="vm", backup_id="610"}'
    for daily in ("PbsBackupGroupStale", "PbsBackupGroupStaleCritical"):
        assert f"unless on (namespace, backup_type, backup_id)\npbs_backup_group_snapshot_count{selector}" in by_name[daily]["expr"], daily
    for weekly in ("PbsBackupGroupWeeklyStale", "PbsBackupGroupWeeklyStaleCritical"):
        assert f"pbs_backup_group_last_snapshot_timestamp_seconds{selector}" in by_name[weekly]["expr"], weekly
    assert f"> {8 * 86400}" in by_name["PbsBackupGroupWeeklyStale"]["expr"]
    assert f"> {15 * 86400}" in by_name["PbsBackupGroupWeeklyStaleCritical"]["expr"]
    assert by_name["PbsBackupGroupWeeklyStale"]["labels"]["severity"] == "warning"
    assert by_name["PbsBackupGroupWeeklyStaleCritical"]["labels"]["severity"] == "critical"


def test_collector_walks_root_and_nested_namespaces_and_ignores_non_snapshot_entries(tmp_path: Path) -> None:
    collector = _load_collector()
    store = tmp_path / "store"
    for rel in (
        "vm/100/2026-10-13T00:00:14Z", "vm/100/2026-10-12T00:00:10Z",       # root namespace group, two snapshots
        "ns/0own/vm/640/2026-10-13T01:00:00Z",                              # first-level namespace
        "ns/0own/ns/sub/ct/107/2026-10-11T02:30:10Z",                        # nested namespace (PBS layout ns/<a>/ns/<b>)
        "ns/0database/vm/100/not-a-timestamp",                              # ignored: not a snapshot name
        "ns/0docker/host/pve/2026-10-10T03:00:00Z",
    ):
        (store / rel).mkdir(parents=True)
        if collector.snap_epoch(rel.rsplit("/", 1)[1]) is not None:
            (store / rel / "index.json.blob").write_text("{}")             # PBS writes the manifest when a backup has finished
    (store / "vm" / "100" / "owner").write_text("backup@pbs")             # a file next to snapshots

    text = collector.render("own-pbs", str(store))

    def sample(metric: str, ns: str, btype: str, bid: str) -> int:
        label = f'datastore="own-pbs",namespace="{ns}",backup_type="{btype}",backup_id="{bid}"'
        (line,) = [l for l in text.splitlines() if l.startswith(f"{metric}{{{label}}}")]
        return int(line.rsplit(" ", 1)[1])

    last = "pbs_backup_group_last_snapshot_timestamp_seconds"
    count = "pbs_backup_group_snapshot_count"
    assert sample(last, "", "vm", "100") == collector.snap_epoch("2026-10-13T00:00:14Z")
    assert sample(count, "", "vm", "100") == 2
    assert sample(last, "0own", "vm", "640") == collector.snap_epoch("2026-10-13T01:00:00Z")
    assert sample(last, "0own/sub", "ct", "107") == collector.snap_epoch("2026-10-11T02:30:10Z")
    assert sample(last, "0docker", "host", "pve") == collector.snap_epoch("2026-10-10T03:00:00Z")
    assert "0database" not in text  # its only entry is not a snapshot
    assert 'pbs_backup_collect_timestamp_seconds{datastore="own-pbs"}' in text
    assert collector.snap_epoch("2026-10-13T00:00:14Z") == 1791849614


def test_a_backup_in_progress_does_not_count_as_a_fresh_snapshot(tmp_path: Path) -> None:
    """2026-10-19: a running (later aborted) backup of VM 100 made the group look 41 minutes old and hid PbsBackupGroupStale for as long as it ran."""
    collector = _load_collector()
    group = tmp_path / "store" / "ns" / "0docker" / "vm" / "100"
    for name, finished in (("2026-10-18T02:07:28Z", True), ("2026-10-19T07:43:22Z", False)):
        (group / name).mkdir(parents=True)
        (group / name / "drive-scsi0.img.fidx").write_text("partial")
        if finished:
            (group / name / "index.json.blob").write_text("{}")
    text = collector.render("own-pbs", str(tmp_path / "store"))
    label = 'datastore="own-pbs",namespace="0docker",backup_type="vm",backup_id="100"'
    assert f"pbs_backup_group_last_snapshot_timestamp_seconds{{{label}}} {collector.snap_epoch('2026-10-18T02:07:28Z')}" in text
    assert f"pbs_backup_group_snapshot_count{{{label}}} 1" in text
    only_unfinished = tmp_path / "store2" / "vm" / "7" / "2026-10-19T07:43:22Z"
    only_unfinished.mkdir(parents=True)
    assert 'backup_id="7"' not in collector.render("own-pbs", str(tmp_path / "store2"))  # a group with nothing finished has no sample (the stale alert then has nothing to age, the metrics-missing ones cover the rest)


def test_collector_writes_the_textfile_atomically_and_refuses_a_missing_store(tmp_path: Path) -> None:
    collector = _load_collector()
    textfile = tmp_path / "textfile"
    textfile.mkdir()
    store = tmp_path / "store"
    (store / "vm" / "1" / "2026-10-13T00:00:00Z").mkdir(parents=True)
    (store / "vm" / "1" / "2026-10-13T00:00:00Z" / "index.json.blob").write_text("{}")
    result = subprocess.run(
        ["python3", str(SCRIPT), "--store-path", str(store), "--textfile-dir", str(textfile)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert [p.name for p in textfile.iterdir()] == ["pbs_backup.prom"]
    assert "pbs_backup_group_last_snapshot_timestamp_seconds" in (textfile / "pbs_backup.prom").read_text()
    missing = subprocess.run(
        ["python3", str(SCRIPT), "--store-path", str(tmp_path / "nope"), "--textfile-dir", str(textfile)], capture_output=True, text=True, check=False
    )
    assert missing.returncode == 2
    assert collector.esc('a"b\\c') == 'a\\"b\\\\c'


def test_systemd_units_run_the_installed_script_every_five_minutes() -> None:
    service = (REPO_ROOT / "config" / "systemd" / "pbs-backup-metrics.service").read_text(encoding="utf-8")
    timer = (REPO_ROOT / "config" / "systemd" / "pbs-backup-metrics.timer").read_text(encoding="utf-8")
    assert "ExecStart=/usr/local/sbin/pbs-backup-metrics" in service and "Type=oneshot" in service
    assert "OnUnitActiveSec=5min" in timer and "WantedBy=timers.target" in timer


def test_openobserve_compose_copies_cap_every_container_log() -> None:
    for name, services in (("compose.yaml", ("postgres", "openobserve")), ("edge-compose.yaml", ("caddy",))):
        compose = yaml.safe_load((REPO_ROOT / "config" / "0own" / "openobserve" / name).read_text(encoding="utf-8"))
        for service in services:
            logging = compose["services"][service]["logging"]
            assert logging["driver"] == "json-file", (name, service)
            assert logging["options"] == {"max-size": "100m", "max-file": "5"}, (name, service)
