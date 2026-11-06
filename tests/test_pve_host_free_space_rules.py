"""The 24-hour-low warning for the hypervisor root filesystem (config/prometheus/rules/pve-host-incident.yml).

2026-10-25: CI admission is held under 14% free and PveHostFilesystemLowHeadroom warns at 15%, but the free fraction swings by several points within minutes, so the warning gives no
lead time and no memory. PveHostFilesystemDailyLowNarrow looks at the lowest value of the last 24 hours instead and fires when it is under 16%. Pinned here: the alert exists with the
severity and delay the unit tests assume, it selects the same scrape job, device and mount point as the two existing host-filesystem alerts (a typo in a label never fires and nothing notices),
its threshold sits above the 15% warning and the 14% hold, it reads a 24 hour window on a 5-minute grid, the unit-test file covers it firing and not firing, and (when promtool is installed) the
rules pass `promtool check` and tests/promtool/pve_host_free_space_rules_test.yml.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "pve-host-incident.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "pve_host_free_space_rules_test.yml"
ALERT = "PveHostFilesystemDailyLowNarrow"
SELECTOR = 'job="pve_0docker_host_node_exporter_via_tailscale",device="/dev/md3",mountpoint="/"'
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")


def _alerts():
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


def _threshold(expr: str) -> float:
    return float(re.search(r"<\s*([0-9.]+)\s*$", expr.strip()).group(1))


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_alert_exists_with_the_severity_and_delay_the_unit_tests_assume() -> None:
    rule = _alerts()[ALERT]
    assert rule["labels"] == {"severity": "warning", "service": "pve_storage"}
    assert rule["for"] == "0m", "the 24 hour memory is in the expression: a delay would only hide a dip"
    assert rule["annotations"]["summary"] and rule["annotations"]["description"]


def test_it_selects_the_same_job_device_and_mount_point_as_the_other_host_filesystem_alerts() -> None:
    a = _alerts()
    for name in ("PveHostFilesystemLowHeadroom", "PveHostFilesystemAdmissionHold", ALERT):
        assert SELECTOR in a[name]["expr"].replace(" ", ""), name
    expr = a[ALERT]["expr"]
    assert expr.count("node_filesystem_avail_bytes{") == 1 and expr.count("node_filesystem_size_bytes{") == 1
    assert expr.count(SELECTOR) == 2, "both the available and the total bytes must carry the same selector"


def test_the_threshold_sits_above_the_warning_and_the_hold() -> None:
    a = _alerts()
    hold, warning, narrow = (
        _threshold(a[n]["expr"]) for n in ("PveHostFilesystemAdmissionHold", "PveHostFilesystemLowHeadroom", ALERT)
    )
    assert hold < warning < narrow == 0.16, (hold, warning, narrow)


def test_it_reads_the_lowest_value_of_a_24_hour_window_on_a_5_minute_grid() -> None:
    expr = _alerts()[ALERT]["expr"]
    assert expr.startswith("min_over_time(") and "[24h:5m]" in expr


def test_the_promtool_test_file_covers_the_alert_firing_and_not_firing() -> None:
    doc = yaml.safe_load(PROMTOOL_TEST.read_text(encoding="utf-8"))
    seen: set[bool] = set()
    for case in doc["tests"]:
        for check in case["alert_rule_test"]:
            if check["alertname"] == ALERT:
                seen.add(bool(check["exp_alerts"]))
    assert seen == {True, False}, seen
