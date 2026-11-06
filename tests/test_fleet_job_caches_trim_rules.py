"""Alerts for the build VM's Go build cache trim (config/prometheus/rules/fleet-job-caches-trim.yml), added 2026-11-04.

Step 3d of the 4-hourly GC on docker-build-lv3 (config/0mcp/docker-build-lv3/) trims the Go build cache inside the fleet-job-cache-* volumes and, at the end of
every full run, writes fleet_job_caches_trim.prom. Until these rules nothing read it: a failed or skipped run, a stopped timer, a missing file or a volume stuck
over its cap told nobody (on 2026-11-02 the step would have been skipped silently). The tests pin the rules to what the wrapper script and the timer really do.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "config" / "prometheus" / "rules" / "fleet-job-caches-trim.yml"
PROMTOOL_TEST = REPO / "tests" / "promtool" / "fleet_job_caches_trim_rules_test.yml"
BUILD_VM = REPO / "config" / "0mcp" / "docker-build-lv3"
WRAPPER = BUILD_VM / "files" / "usr" / "local" / "bin" / "fleet-job-caches-trim.sh"
GC_TIMER = BUILD_VM / "files" / "etc" / "systemd" / "system" / "docker-build-gc.timer"
GC_SERVICE = BUILD_VM / "files" / "etc" / "systemd" / "system" / "docker-build-gc.service"
README = BUILD_VM / "README.md"
RUNBOOK = REPO / "docs" / "runbooks" / "fleet-observability.md"
ROLE_DEFAULTS = (
    REPO
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "monitoring_vm"
    / "defaults"
    / "main.yml"
)
requires_promtool = pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")

HOST = "docker-build-lv3"
SERVICE = "fleet_job_caches_trim"
ANCHOR = "#build-host-cache-trim-alerts"
HOUR = 3600
# name: (delay in seconds, severity)
EXPECTED = {
    "FleetJobCachesTrimFailed": (1 * HOUR, "warning"),
    "FleetJobCachesTrimStale": (30 * 60, "warning"),
    "FleetJobCachesTrimMissing": (24 * HOUR, "warning"),
    "FleetJobCachesOverCap": (24 * HOUR, "info"),
}


def _alerts() -> dict[str, dict]:
    doc = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return {r["alert"]: r for g in doc["groups"] for r in g["rules"] if "alert" in r}


def _expr(name: str) -> str:
    return " ".join(_alerts()[name]["expr"].split())


def _seconds(duration: str) -> int:
    value, unit = re.fullmatch(r"(\d+)([mhd])", duration).groups()
    return int(value) * {"m": 60, "h": HOUR, "d": 24 * HOUR}[unit]


def _section(text: str, heading: str) -> str:
    """The text from `heading` to the next heading of the same or a higher level (a Markdown `#` heading)."""
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(heading)
    after = text[start + len(heading) :]
    end = re.search(rf"^#{{1,{level}}} ", after, re.M)
    return text[start : start + len(heading) + (end.start() if end else len(after))]


def _journalctl_without_sudo(text: str) -> list[str]:
    """Calls of `journalctl -u docker-build-gc` that do not start with `sudo -n `: without it the answer is "No entries" (ops is not in
    systemd-journal), which reads as a quiet run, not as an error."""
    return [
        text[max(0, m.start() - 20) : m.end()]
        for m in re.finditer(r"journalctl -u docker-build-gc", text)
        if text[m.start() - 8 : m.start()] != "sudo -n "
    ]


def _timer_period_seconds() -> int:
    """The GC timer fires at minute :23 of every Nth hour (`OnCalendar=*-*-* 00/4:23`)."""
    calendar = re.search(r"^OnCalendar=\*-\*-\* 00/(\d+):23$", GC_TIMER.read_text(encoding="utf-8"), re.M)
    assert calendar, "the GC timer no longer fires at minute 23 of every Nth hour: re-derive the delays of these rules"
    return int(calendar.group(1)) * HOUR


def _timer_jitter_seconds() -> int:
    return int(re.search(r"^RandomizedDelaySec=(\d+)$", GC_TIMER.read_text(encoding="utf-8"), re.M).group(1))


@requires_promtool
def test_the_rules_pass_promtool_check_and_the_unit_tests() -> None:
    for args in (["check", "rules", str(RULES)], ["test", "rules", str(PROMTOOL_TEST)]):
        r = subprocess.run(["promtool", *args], cwd=REPO, capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stdout + r.stderr


def test_the_alerts_exist_with_the_severity_delay_labels_and_runbook_the_unit_tests_assume() -> None:
    alerts = _alerts()
    assert set(alerts) == set(EXPECTED)
    for name, (delay, severity) in EXPECTED.items():
        assert _seconds(alerts[name]["for"]) == delay, name
        assert alerts[name]["labels"] == {"severity": severity, "service": SERVICE}, name
        assert alerts[name]["annotations"]["runbook_url"] == f"docs/runbooks/fleet-observability.md{ANCHOR}", name
        assert alerts[name]["annotations"]["summary"] and alerts[name]["annotations"]["description"], name


def test_the_expressions_name_the_host_and_merge_duplicate_series() -> None:
    assert (
        _expr("FleetJobCachesTrimFailed") == f'max by (host) (fleet_job_caches_trim_last_result{{host="{HOST}"}}) != 0'
    )
    assert _expr("FleetJobCachesTrimStale") == (
        f'time() - max by (host) (fleet_job_caches_trim_last_run_timestamp_seconds{{host="{HOST}"}}) > 9 * 3600'
    )
    assert (
        _expr("FleetJobCachesOverCap") == f'max by (host) (fleet_job_caches_trim_volumes_over_cap{{host="{HOST}"}}) > 0'
    )


def test_a_check_that_reads_nothing_cannot_stay_green() -> None:
    assert (
        _expr("FleetJobCachesTrimMissing")
        == f'absent(fleet_job_caches_trim_last_run_timestamp_seconds{{host="{HOST}"}})'
    )


def test_the_rules_only_read_metrics_that_the_wrapper_script_writes() -> None:
    written = set(re.findall(r"^# TYPE (fleet_job_caches_trim_\w+) gauge$", WRAPPER.read_text(encoding="utf-8"), re.M))
    assert len(written) == 4, written
    used = {name for rule in _alerts().values() for name in re.findall(r"\bfleet_job_caches_trim_\w+", rule["expr"])}
    assert used and used <= written, used - written
    # every gauge the script writes is read by a rule, except the bytes freed (a night run that frees nothing is normal)
    assert written - used == {"fleet_job_caches_trim_freed_bytes"}, written - used


def test_the_delays_follow_the_gc_timer() -> None:
    period, jitter = _timer_period_seconds(), _timer_jitter_seconds()
    stale_after = int(re.search(r"> (\d+) \* 3600$", _expr("FleetJobCachesTrimStale")).group(1)) * HOUR
    # fires when two runs were missed (a run is written about a minute after the timer, so two missed runs peak just over 2 periods plus the jitter) ...
    assert 2 * period + jitter < stale_after
    # ... but before a third missed run is due, so a dead timer is not reported later than three periods
    assert stale_after < 3 * period
    # a bad value is written by one run and stays one period: a longer delay than that could never fire for a single bad run
    assert _seconds(_alerts()["FleetJobCachesTrimFailed"]["for"]) <= period
    # a run of over-cap runs is a burst by design (the floor beats the cap); only a day of it is reported
    assert _seconds(_alerts()["FleetJobCachesOverCap"]["for"]) >= 24 * HOUR >= 4 * period
    # the missing rule waits at least as long as the stale one needs to give up on an old file
    assert _seconds(_alerts()["FleetJobCachesTrimMissing"]["for"]) >= stale_after


def test_the_results_the_alert_texts_describe_are_the_ones_the_wrapper_writes() -> None:
    script = WRAPPER.read_text(encoding="utf-8")
    assert "0 it ran, 1 a volume failed or docker or the report was wrong, 2 skipped" in script
    assert "report 2 0 0" in script and "report 1 0 0" in script
    text = _alerts()["FleetJobCachesTrimFailed"]["annotations"]
    assert "1 failed, 2 skipped" in text["summary"]
    assert "(1: a volume failed" in text["description"] and "2: skipped" in text["description"]


def test_the_alert_texts_name_files_and_units_that_exist_and_every_journalctl_uses_sudo() -> None:
    units = {p.name for p in GC_SERVICE.parent.iterdir()}
    script = WRAPPER.read_text(encoding="utf-8")
    assert "PROM_DIR=${CACHE_TRIM_PROM_DIR:-/var/lib/prometheus/node-exporter}" in script
    assert '"$PROM_DIR/fleet_job_caches_trim.prom"' in script
    for name, rule in _alerts().items():
        description = rule["annotations"]["description"]
        assert set(re.findall(r"[\w-]+\.(?:service|timer)\b", description)) <= units, name
        assert not _journalctl_without_sudo(description), name
        for path in re.findall(r"/usr/local/bin/[\w.-]+", description):
            assert (BUILD_VM / "files" / path.lstrip("/")).is_file(), (name, path)
        for path in re.findall(r"/var/lib/prometheus/node-exporter/[\w.-]+", description):
            assert path.rstrip(".").endswith(("/node-exporter/", "fleet_job_caches_trim.prom")), (name, path)


def test_the_runbook_and_the_readme_describe_each_alert() -> None:
    runbook = _section(RUNBOOK.read_text(encoding="utf-8"), "## Build host cache trim alerts")
    readme = _section(README.read_text(encoding="utf-8"), "### Alerts on the trim")
    for name in EXPECTED:
        # one table row per alert in both documents (a name mentioned in passing is not a description)
        assert re.search(rf"^\| `{name}` \|", runbook, re.M), name
        assert re.search(rf"^\| `{name}` \|", readme, re.M), name
    # the kill switch of step 3d (the undo of its apply step) makes the stale alert fire: the README must say what to do about it
    assert "sudo chmod -x /usr/local/bin/fleet-job-caches-trim.sh" in readme and "silence it in Alertmanager" in readme
    assert not _journalctl_without_sudo(readme)
    assert "config/0mcp/docker-build-lv3/README.md" in runbook


def test_the_monitoring_vm_role_ships_the_rule_file() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))
    assert "fleet-job-caches-trim.yml" in defaults["monitoring_prometheus_adopted_rule_files"]
