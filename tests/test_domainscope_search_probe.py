"""The DomainScope search probe job on CT108: scripts/domainscope-search-probe-run, its units, its installer and its alerts
(config/prometheus/rules/domainscope-search.yml).

The wrapper is run for real against a local git repository standing in for go-url-categorizer-api, holding a FAKE probe (a script that
writes metrics and exits as the test says), with a temporary textfile directory. What matters: the probe comes from origin/main on every run;
a run that leaves no valid metrics (crash, timeout, a probe that cannot write them, metrics of other families) is recorded as a failed run
(success 0), never as green and never as silence; a failed search check is exit 2 (an alert, not a failed unit); a failed fetch still checks
production with the last probe fetched. The promtool unit tests (tests/promtool/domainscope_search_rules_test.yml) run when promtool is
installed (the monitoring VM), the rest anywhere with git, bash and coreutils `timeout`.
"""
from __future__ import annotations

import configparser
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "scripts" / "domainscope-search-probe-run"
INSTALL = ROOT / "scripts" / "domainscope-search-probe-install.sh"
SERVICE = ROOT / "config" / "systemd" / "domainscope-search-probe.service"
TIMER = ROOT / "config" / "systemd" / "domainscope-search-probe.timer"
RULES = ROOT / "config" / "prometheus" / "rules" / "domainscope-search.yml"
PROMTOOL_TEST = ROOT / "tests" / "promtool" / "domainscope_search_rules_test.yml"
RUNBOOK = ROOT / "docs" / "runbooks" / "domainscope-search-probe.md"
ROLE_DEFAULTS = ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "monitoring_vm" / "defaults" / "main.yml"

# The families the DomainScope probe writes (go-url-categorizer-api scripts/search-probe.sh --metrics-file); the wrapper's own record of a
# failed run writes the same ones.
FAMILIES = {
    "domainscope_search_probe_success", "domainscope_search_probe_failed_checks", "domainscope_search_probe_checks_total",
    "domainscope_search_probe_known_failing_checks", "domainscope_search_probe_known_failing_failed_checks",
    "domainscope_search_probe_duration_seconds", "domainscope_search_probe_last_run_timestamp_seconds",
}

needs_tools = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("git", "bash", "timeout")), reason="needs git, bash and coreutils timeout"
)

FAKE_PROBE = r"""#!/usr/bin/env bash
# fake scripts/search-probe.sh: understands --metrics-file; does what CTRL/mode says
printf '%s\n' "$*" > "CTRL/args"
env > "CTRL/env"
mf=""
while [ $# -gt 0 ]; do case "$1" in --metrics-file) mf="$2"; shift 2 ;; *) shift ;; esac; done
write() {
  for kv in "success $1" "failed_checks $2" "checks_total 45" "known_failing_checks 1" "known_failing_failed_checks 1" "duration_seconds 3" "last_run_timestamp_seconds $(date +%s)"; do
    printf '# TYPE domainscope_search_probe_%s gauge\ndomainscope_search_probe_%s{target="https://domainscope.scrapetheworld.org"} %s\n' "${kv%% *}" "${kv%% *}" "${kv#* }"
  done > "$mf"
}
case "$(cat CTRL/mode)" in
  pass) write 1 0; exit 0 ;;
  fail) write 0 3; exit 1 ;;
  crash) exit 7 ;;
  inject) write 1 0; echo 'node_load1 99' >> "$mf"; exit 0 ;;
  sleep) sleep 20; write 1 0; exit 0 ;;
esac
"""

OLD_PROBE = "#!/usr/bin/env bash\n# an older probe: no metrics option\necho 'Search probe passed'\nexit 0\n"


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def commit_probe(origin: Path, text: str, message: str) -> None:
    (origin / "scripts" / "search-probe.sh").write_text(text)
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", message)


@pytest.fixture()
def world(tmp_path):
    ctrl = tmp_path / "ctrl"
    ctrl.mkdir()
    (ctrl / "mode").write_text("pass")
    origin = tmp_path / "origin"
    for rel in ("scripts", "src/internal/marketcell", "frontend/src/features/market-cells"):
        (origin / rel).mkdir(parents=True)
    git(origin, "init", "-q", "-b", "main")
    (origin / "scripts" / "search-golden-queries.tsv").write_text("smart\t10\tdeploy\tq\n")
    (origin / "src/internal/marketcell/catalog.json").write_text("{}")
    (origin / "frontend/src/features/market-cells/marketCells.snapshot.json").write_text("{}")
    (origin / "README").write_text("not shipped to the probe\n")
    commit_probe(origin, FAKE_PROBE.replace("CTRL", str(ctrl)), "probe")
    textfile = tmp_path / "textfile"
    textfile.mkdir()
    env = {
        "PATH": os.environ["PATH"], "HOME": str(tmp_path), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        "DSPROBE_STATE": str(tmp_path / "state"), "DSPROBE_TEXTFILE_DIR": str(textfile), "DSPROBE_REPO_URL": f"file://{origin}",
        "DSPROBE_USER": "",  # the test runs as whoever runs it (root in CI): no switch to nobody, whose path to tmp_path may be closed
    }
    return {"env": env, "origin": origin, "ctrl": ctrl, "prom": textfile / "domainscope_search_probe.prom", "textfile": textfile,
            "state": tmp_path / "state"}


def run(world, mode: str | None = None, **over: str) -> subprocess.CompletedProcess:
    if mode:
        (world["ctrl"] / "mode").write_text(mode)
    return subprocess.run(["bash", str(RUN)], capture_output=True, text=True, env={**world["env"], **over}, timeout=120)


def metrics(path: Path) -> dict[str, float]:
    out = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            name_labels, value = line.rsplit(" ", 1)
            out[name_labels.split("{")[0]] = float(value)
    return out


@needs_tools
def test_a_passing_probe_is_exit_0_and_its_metrics_land_in_the_textfile_directory(world):
    r = run(world, "pass")
    assert r.returncode == 0, r.stdout + r.stderr
    m = metrics(world["prom"])
    assert m["domainscope_search_probe_success"] == 1 and set(m) == FAMILIES
    args = (world["ctrl"] / "args").read_text().split()
    assert args[:3] == ["--all", "--markets", "20"] and args[3] == "--metrics-file" and args[-1] == "https://domainscope.scrapetheworld.org"
    assert sorted(p.name for p in world["textfile"].iterdir()) == ["domainscope_search_probe.prom"], "no temp file left behind"
    shipped = sorted(str(p.relative_to(world["state"] / "tree")) for p in (world["state"] / "tree").rglob("*") if p.is_file())
    assert shipped == [".sha", "frontend/src/features/market-cells/marketCells.snapshot.json", "scripts/search-golden-queries.tsv",
                       "scripts/search-probe.sh", "src/internal/marketcell/catalog.json"], "only the four files the probe reads"
    assert "from main against https://domainscope.scrapetheworld.org" in r.stdout


@needs_tools
def test_the_probe_runs_with_an_empty_environment(world):
    run(world, "pass", SECRET_LOOKING_VAR="x")
    seen = dict(line.split("=", 1) for line in (world["ctrl"] / "env").read_text().splitlines() if "=" in line)
    assert "SECRET_LOOKING_VAR" not in seen and "DSPROBE_STATE" not in seen
    assert seen["TMPDIR"].endswith("/run/tmp") and seen["HOME"].endswith("/run/tmp")


@needs_tools
def test_a_failed_search_check_is_exit_2_with_the_probes_own_metrics(world):
    r = run(world, "fail")
    assert r.returncode == 2, r.stdout + r.stderr
    m = metrics(world["prom"])
    assert m["domainscope_search_probe_success"] == 0 and m["domainscope_search_probe_failed_checks"] == 3


@needs_tools
@pytest.mark.parametrize("mode", ["crash", "inject"])
def test_a_probe_that_leaves_no_valid_metrics_is_a_failed_run_never_green(world, mode):
    assert run(world, "pass").returncode == 0
    r = run(world, mode)
    assert r.returncode == 3, r.stdout + r.stderr
    text = world["prom"].read_text()
    assert "node_load1" not in text, "only the probe's own families are accepted"
    m = metrics(world["prom"])
    assert set(m) == FAMILIES
    assert m["domainscope_search_probe_success"] == 0 and m["domainscope_search_probe_failed_checks"] == 1
    assert "without valid metrics" in r.stderr


@needs_tools
def test_a_probe_past_its_timeout_is_stopped_and_recorded_as_a_failed_run(world):
    r = run(world, "sleep", DSPROBE_TIMEOUT_SECONDS="1")
    assert r.returncode == 3 and "ran past 1s" in r.stderr, r.stdout + r.stderr
    assert metrics(world["prom"])["domainscope_search_probe_success"] == 0


@needs_tools
def test_the_probe_is_taken_from_origin_main_on_every_run(world):
    assert run(world, "pass").returncode == 0
    first = (world["state"] / "tree" / ".sha").read_text().strip()
    (world["origin"] / "scripts" / "search-golden-queries.tsv").write_text("smart\t10\tdeploy\tnew query\n")
    git(world["origin"], "commit", "-q", "-am", "new golden query")
    assert run(world, "pass").returncode == 0
    assert (world["state"] / "tree" / "scripts" / "search-golden-queries.tsv").read_text() == "smart\t10\tdeploy\tnew query\n"
    assert (world["state"] / "tree" / ".sha").read_text().strip() != first


@needs_tools
def test_a_probe_on_main_without_the_metrics_option_is_a_failed_run_not_silence_and_not_green(world):
    commit_probe(world["origin"], OLD_PROBE, "main has an old probe")
    r = run(world, "pass")
    assert r.returncode == 3 and "has no --metrics-file" in r.stderr, r.stdout + r.stderr
    assert metrics(world["prom"])["domainscope_search_probe_success"] == 0


@needs_tools
def test_the_capability_check_survives_a_probe_larger_than_a_pipe_with_the_flag_at_the_top(world):
    """2026-10-21: `git show | grep -q` under pipefail: grep exits at the first match, git gets SIGPIPE, the pipeline is 141, the wrapper said
    "has no --metrics-file" on about 4 runs in 10. With 2 MB after the match the old check failed every time."""
    fake = FAKE_PROBE.replace("CTRL", str(world["ctrl"]))
    head, rest = fake.split("\n", 1)
    commit_probe(world["origin"], head + "\n# usage: [--metrics-file PATH]\n" + rest + ("# padding\n" * 200_000), "big probe")
    for _ in range(3):
        r = run(world, "pass")
        assert r.returncode == 0 and "from main against" in r.stdout, r.stdout + r.stderr


@needs_tools
def test_the_capability_check_passes_against_mains_real_probe(world):
    """The real scripts/search-probe.sh of go-url-categorizer-api main (a copy in tests/fixtures), run for real against a closed port: the
    check must find --metrics-file, the probe fails its one check (exit 2, not 3) and its own metrics are accepted."""
    real = ROOT / "tests" / "fixtures" / "domainscope-search-probe" / "search-probe.sh"
    (world["origin"] / "scripts" / "search-golden-queries.tsv").write_text("# no golden rows: only the uncached semantic check runs\n")
    commit_probe(world["origin"], real.read_text(), "the real probe")
    r = run(world, DSPROBE_MARKETS="0", DSPROBE_BASE_URL="http://127.0.0.1:9")
    assert "has no --metrics-file" not in r.stderr and "from main against http://127.0.0.1:9" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 2, r.stdout + r.stderr
    m = metrics(world["prom"])
    assert set(m) == FAMILIES and m["domainscope_search_probe_success"] == 0 and m["domainscope_search_probe_checks_total"] == 1


@needs_tools
def test_a_failed_fetch_runs_the_last_fetched_probe_and_says_so(world, tmp_path):
    assert run(world, "pass").returncode == 0
    r = run(world, "fail", DSPROBE_REPO_URL=f"file://{tmp_path}/gone")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "running the last fetched probe" in r.stderr
    assert metrics(world["prom"])["domainscope_search_probe_success"] == 0, "production was still checked"


@needs_tools
def test_a_failed_first_fetch_is_exit_3_and_writes_nothing(world, tmp_path):
    r = run(world, "pass", DSPROBE_REPO_URL=f"file://{tmp_path}/gone")
    assert r.returncode == 3 and "no probe was fetched before" in r.stderr
    assert not world["prom"].exists(), "no made-up result: the stale alert covers it"


@needs_tools
def test_bad_numbers_are_refused_before_anything_runs(world):
    r = run(world, "pass", DSPROBE_MARKETS="twenty")
    assert r.returncode == 3 and "whole numbers" in r.stderr and not world["prom"].exists()


def test_the_timer_runs_every_15_minutes_without_a_catch_up_at_boot():
    timer = configparser.ConfigParser(strict=False)
    timer.read_string(TIMER.read_text())
    assert timer["Timer"]["OnCalendar"] == "*:04/15"
    assert timer["Timer"]["Persistent"] == "false"
    assert "OnBootSec" not in timer["Timer"]


def test_the_service_runs_the_installed_wrapper_once_at_a_time_and_treats_a_failed_check_as_done():
    text = SERVICE.read_text()
    service = configparser.ConfigParser(strict=False, interpolation=None)
    service.optionxform = str
    service.read_string(text)
    s = service["Service"]
    assert s["Type"] == "oneshot" and s["SuccessExitStatus"] == "2"
    assert s["ExecStart"] == "/usr/bin/flock -n /run/lock/domainscope-search-probe.lock /usr/local/bin/domainscope-search-probe-run"
    assert s["TimeoutStartSec"] == "15min"
    assert "TIMEOUT=${DSPROBE_TIMEOUT_SECONDS:-720}" in RUN.read_text(), "the wrapper stops the probe at 12 minutes, before the unit's 15"


def test_the_installer_ships_exactly_the_wrapper_and_the_units_and_only_from_origin_main():
    text = INSTALL.read_text()
    files = re.search(r"^files=\((.*)\)$", text, re.M).group(1).split()
    assert files == ["scripts/domainscope-search-probe-run", "config/systemd/domainscope-search-probe.service",
                     "config/systemd/domainscope-search-probe.timer"]
    assert all((ROOT / f).exists() for f in files)
    assert "diff --quiet origin/main" in text and ".bak-$ts" in text and "systemd-analyze verify" in text


def _rules() -> list[dict]:
    return [r for g in yaml.safe_load(RULES.read_text())["groups"] for r in g["rules"]]


def test_the_alerts_are_the_two_named_warnings_with_the_runbook():
    rules = _rules()
    assert [r["alert"] for r in rules] == ["DomainScopeSearchBroken", "DomainScopeSearchProbeStale"]
    runbook = RUNBOOK.read_text()
    for rule in rules:
        assert rule["labels"] == {"severity": "warning", "service": "domainscope"}, rule["alert"]
        assert rule["annotations"]["runbook_url"] == "docs/runbooks/domainscope-search-probe.md"
        assert rule["alert"] in runbook


def test_the_rules_read_only_metrics_the_probe_writes():
    used = {m for r in _rules() for m in re.findall(r"domainscope_search_probe_[a-z_]+", r["expr"])}
    assert used and used <= FAMILIES


def test_every_alert_has_a_promtool_case_and_the_rule_file_is_shipped_to_the_monitoring_vm():
    tests = yaml.safe_load(PROMTOOL_TEST.read_text())
    assert [(PROMTOOL_TEST.parent / f).resolve() for f in tests["rule_files"]] == [RULES]
    fired = {c["alertname"] for t in tests["tests"] for c in t["alert_rule_test"] if c["exp_alerts"]}
    assert fired == {r["alert"] for r in _rules()}
    adopted = yaml.safe_load(ROLE_DEFAULTS.read_text())["monitoring_prometheus_adopted_rule_files"]
    assert "domainscope-search.yml" in adopted


def test_the_stale_alert_outlasts_the_nightly_backup_stop_of_the_builder():
    stale = {r["alert"]: r for r in _rules()}["DomainScopeSearchProbeStale"]
    assert "> 3 * 3600" in stale["expr"] and "last_over_time(" in stale["expr"] and "absent_over_time(" in stale["expr"]


@pytest.mark.skipif(shutil.which("promtool") is None, reason="promtool is not installed")
def test_rules_pass_promtool_check_and_unit_tests():
    for args in (("check", "rules", str(RULES)), ("test", "rules", str(PROMTOOL_TEST))):
        result = subprocess.run(["promtool", *args], cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
