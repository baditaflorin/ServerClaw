"""Tests for the backup freshness alerts (config/prometheus/rules/fleet-backup-freshness.yml) and the PBS collector
(scripts/pbs_backup_metrics.py) that feeds them.

The promtool unit tests (tests/promtool/fleet_backup_freshness_rules_test.yml) run when promtool is installed; the rest runs
anywhere with only the standard library and PyYAML.
"""

from __future__ import annotations

import importlib.util
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
    assert "> 93600" in by_name["PgBackupStale"]["expr"] and "> 180000" in by_name["PgBackupStaleCritical"]["expr"]
    assert "> 93600" in by_name["PbsBackupGroupStale"]["expr"] and "> 180000" in by_name["PbsBackupGroupStaleCritical"]["expr"]
    assert 'method="vzdump"' in by_name["PgBackupStale"]["expr"]
    for rule in rules:
        assert rule["labels"]["severity"] in {"info", "warning", "critical"}, rule["alert"]
        assert rule["labels"]["service"] in {"pg_backup", "pbs_backup"}, rule["alert"]
        assert rule["annotations"]["runbook_url"] == "docs/runbooks/pbs-0own-backups.md", rule["alert"]
    assert (REPO_ROOT / "docs" / "runbooks" / "pbs-0own-backups.md").is_file()
    # The ratio alerts are info only: size_bytes is the dirty-bitmap "transferred" figure and moves with write volume.
    assert by_name["PgBackupSizeShrank"]["labels"]["severity"] == "info"
    assert by_name["PgBackupDurationHigh"]["labels"]["severity"] == "info"


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


def test_collector_writes_the_textfile_atomically_and_refuses_a_missing_store(tmp_path: Path) -> None:
    collector = _load_collector()
    textfile = tmp_path / "textfile"
    textfile.mkdir()
    store = tmp_path / "store"
    (store / "vm" / "1" / "2026-10-13T00:00:00Z").mkdir(parents=True)
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
