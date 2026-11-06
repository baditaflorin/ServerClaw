"""The DomainScope Drive data room refresh job on CT108: scripts/domainscope-drive-refresh-run, its units, its installer and its alerts
(config/prometheus/rules/domainscope-drive-refresh.yml).

The wrapper is run for real against a local git repository standing in for go-url-categorizer-api (holding the paths the tool needs), a FAKE
go that "builds" a fake tool, a fake vault helper and a temporary textfile directory. What matters: the tool is built from origin/main on every
run; the service account key reaches the tool on standard input and nowhere else (never an argument, never the environment); a dry run writes
no metrics; a run that cannot reach the documents (fetch, build, vault, a crashed tool) is recorded as ok 0 with the last success time carried
forward, never as green and never as silence; a failed document is exit 1 (the unit still ran), a run that could not start is exit 3. The
promtool unit tests (tests/promtool/domainscope_drive_refresh_rules_test.yml) run when promtool is installed (the monitoring VM).
"""
from __future__ import annotations

import configparser
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "scripts" / "domainscope-drive-refresh-run"
INSTALL = ROOT / "scripts" / "domainscope-drive-refresh-install.sh"
SERVICE = ROOT / "config" / "systemd" / "domainscope-drive-refresh.service"
TIMER = ROOT / "config" / "systemd" / "domainscope-drive-refresh.timer"
RULES = ROOT / "config" / "prometheus" / "rules" / "domainscope-drive-refresh.yml"
PROMTOOL_TEST = ROOT / "tests" / "promtool" / "domainscope_drive_refresh_rules_test.yml"
RUNBOOK = ROOT / "docs" / "runbooks" / "domainscope-drive-refresh.md"

needs_git = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="needs git and bash")

KEY = "FAKE-SERVICE-ACCOUNT-KEY-0123456789"

# What `go build -o OUT ./cmd/drive-refresh` writes as OUT: a tool that records how it was called and acts as CTRL/mode says.
FAKE_TOOL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" > "CTRL/args"
cat > "CTRL/stdin"
env > "CTRL/env"
# like the real tool: no key on stdin is a failure before any document (and it leaves the metrics alone: the wrapper records the failure)
[ -s "CTRL/stdin" ] || exit 1
mf=""
prev=""
for a in "$@"; do if [ "$prev" = "-metrics-out" ]; then mf="$a"; fi; prev="$a"; done
write() {
  [ -n "$mf" ] || return 0
  { echo "domainscope_drive_refresh_last_run_timestamp_seconds $(date +%s)"
    echo "domainscope_drive_refresh_last_success_timestamp_seconds $(date +%s)"
    echo "domainscope_drive_refresh_ok $1"; } > "$mf"
}
case "$(cat CTRL/mode)" in
  pass) write 1; exit 0 ;;
  docfail) write 0; exit 1 ;;
  usage) exit 2 ;;
  crash) exit 7 ;;
esac
"""

FAKE_GO = r"""#!/usr/bin/env bash
# fake go: `go build -trimpath -o OUT ./cmd/drive-refresh`
echo "$*" >> "CTRL/go-calls"
[ "$(cat CTRL/gomode)" = "fail" ] && { echo "build failed" >&2; exit 2; }
out=""; prev=""
for a in "$@"; do if [ "$prev" = "-o" ]; then out="$a"; fi; prev="$a"; done
cp "CTRL/fake-tool" "$out" && chmod 755 "$out"
"""

FAKE_FV = r"""#!/usr/bin/env bash
echo "$*" > "CTRL/fv-args"
[ "$(cat CTRL/fvmode)" = "fail" ] && exit 1
printf '%s' "FAKEKEY"
"""


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


class Env:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.ctrl = tmp / "CTRL"
        self.ctrl.mkdir()
        self.remote = tmp / "remote"
        self.state = tmp / "state"
        self.text = tmp / "textfile"
        self.text.mkdir()
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.remote.mkdir()
        git(self.remote, "init", "-q", "-b", "main")
        git(self.remote, "config", "uploadpack.allowFilter", "true")
        git(self.remote, "config", "uploadpack.allowAnySHA1InWant", "true")
        for rel, body in {
            "src/go.mod": "module url-categorizer\n", "src/go.sum": "",
            "src/cmd/drive-refresh/main.go": "package main\n",
            "docs/investor/data-room.json": "{}\n", "docs/investor/drive-refresh.manifest.json": "{}\n",
            "src/other/unrelated.go": "package other\n",
        }.items():
            p = self.remote / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        git(self.remote, "add", "-A")
        git(self.remote, "commit", "-q", "-m", "init")
        for name, body in {"go": FAKE_GO, "fv.sh": FAKE_FV, "fake-tool": FAKE_TOOL}.items():
            target = self.ctrl / name if name == "fake-tool" else self.bin / name
            target.write_text(body.replace("CTRL", str(self.ctrl)))
            target.chmod(0o755)
        for name, val in {"mode": "pass", "gomode": "ok", "fvmode": "ok"}.items():
            (self.ctrl / name).write_text(val)
        self.figures = self.ctrl / "current-data-room.json"
        self.figures.write_text(json.dumps({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "catalogue": {"available": True, "figures": [
                {"key": "domains_catalogued", "value": 200, "as_of": dt.datetime.now(dt.timezone.utc).date().isoformat()},
                {"key": "embedded", "value": 100, "as_of": dt.datetime.now(dt.timezone.utc).date().isoformat()},
            ]},
        }))

    def set(self, **kv: str) -> None:
        for k, v in kv.items():
            (self.ctrl / k).write_text(v)

    def run(self, apply: str = "1", extra: dict | None = None, args=None) -> subprocess.CompletedProcess:
        env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}", "HOME": str(self.tmp),
            "DSDRIVE_STATE": str(self.state), "DSDRIVE_TEXTFILE_DIR": str(self.text),
            "DSDRIVE_REPO_URL": f"file://{self.remote}", "DSDRIVE_FV": str(self.bin / "fv.sh"),
            "DSDRIVE_GO": str(self.bin / "go"), "DSDRIVE_APPLY": apply,
            "DSDRIVE_FIGURES_HELPER": str(ROOT / "scripts" / "domainscope-drive-figures.py"),
            "DSDRIVE_FIGURES_FILE": str(self.figures),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        }
        env.update(extra or {})
        env = {k: v for k, v in env.items() if v is not None}
        if shutil.which("timeout") is None:  # macOS: a pass-through stands in (the real one is on the builder)
            shim = self.bin / "timeout"
            shim.write_text('#!/usr/bin/env bash\nshift\nexec "$@"\n')
            shim.chmod(0o755)
        return subprocess.run(["bash", str(RUN)] + (args or []), env=env, capture_output=True, text=True, timeout=120)

    @property
    def prom(self) -> Path:
        return self.text / "domainscope_drive_refresh.prom"

    def read(self, name: str) -> str:
        return (self.ctrl / name).read_text()


@pytest.fixture()
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


@needs_git
def test_pass_builds_from_origin_main_and_gives_the_key_on_stdin_only(env: Env) -> None:
    r = env.run()
    assert r.returncode == 0, r.stderr + r.stdout
    assert "-apply" in env.read("args") and "-key-stdin" in env.read("args") and "-metrics-out" in env.read("args")
    assert str(env.state / "current-data-room.json") in env.read("args")
    assert (env.state / "current-data-room.json").stat().st_mode & 0o777 == 0o600
    assert env.read("stdin") == "FAKEKEY"
    for leaked in (env.read("args"), env.read("env"), r.stdout, r.stderr):
        assert "FAKEKEY" not in leaked
    assert env.read("fv-args").strip() == "raw domainscope-drive-sa-key"
    # The reviewed tool and manifest come from git; the stale committed report does not.
    repo = env.state / "repo"
    assert (repo / "src" / "cmd" / "drive-refresh" / "main.go").exists()
    assert not (repo / "src" / "other" / "unrelated.go").exists()
    assert not (repo / "docs" / "investor" / "data-room.json").exists()
    assert "ok 1" in env.prom.read_text()


@needs_git
def test_the_tool_is_rebuilt_from_the_newest_main_on_every_run(env: Env) -> None:
    assert env.run().returncode == 0
    (env.remote / "src" / "cmd" / "drive-refresh" / "main.go").write_text("package main // newer\n")
    git(env.remote, "commit", "-q", "-am", "newer")
    assert env.run().returncode == 0
    assert (env.state / "repo" / "src" / "cmd" / "drive-refresh" / "main.go").read_text().endswith("newer\n")
    assert len(env.read("go-calls").strip().splitlines()) == 2


@needs_git
def test_a_dry_run_applies_nothing_and_writes_no_metrics(env: Env) -> None:
    r = env.run(apply="0")
    assert r.returncode == 0, r.stderr
    assert "-apply" not in env.read("args") and "-metrics-out" not in env.read("args")
    assert not env.prom.exists()
    # and a failed dry run does not write a failed-run metric either
    env.set(gomode="fail")
    assert env.run(apply="0").returncode == 3
    assert not env.prom.exists()


@needs_git
def test_explicit_dry_run_overrides_an_apply_environment(env: Env) -> None:
    r = env.run(apply="1", args=["--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "-apply" not in env.read("args") and "-metrics-out" not in env.read("args")
    assert not env.prom.exists()


@needs_git
@pytest.mark.parametrize("bad", ["empty", "oversized", "stale", "invalid", "inconsistent"])
def test_bad_current_figures_fail_before_build_and_credential_read(env: Env, bad: str) -> None:
    figures = json.loads(env.figures.read_text())
    if bad == "empty":
        env.figures.write_text("")
    elif bad == "oversized":
        env.figures.write_text(" " * (1024 * 1024 + 1))
    elif bad == "invalid":
        env.figures.write_text("not JSON")
    else:
        if bad == "stale":
            figures["generated_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=9)).isoformat()
        else:
            figures["catalogue"]["figures"][1]["value"] = 201
        env.figures.write_text(json.dumps(figures))
    r = env.run()
    assert r.returncode == 3, r.stdout + r.stderr
    assert not (env.ctrl / "fv-args").exists()
    assert not (env.ctrl / "go-calls").exists()
    assert not (env.state / "current-data-room.json").exists()
    assert "domainscope_drive_refresh_ok 0" in env.prom.read_text()


@needs_git
def test_a_failed_document_is_exit_1_and_the_unit_still_ran(env: Env) -> None:
    env.set(mode="docfail")
    r = env.run()
    assert r.returncode == 1
    assert "ok 0" in env.prom.read_text()


@needs_git
@pytest.mark.parametrize("what", ["build", "vault", "crash", "usage", "fetch", "figures"])
def test_a_run_that_cannot_reach_the_documents_is_a_failed_run_never_green(env: Env, what: str) -> None:
    assert env.run().returncode == 0  # a good run first: its success time must survive
    good = env.prom.read_text()
    last = [ln for ln in good.splitlines() if "last_success_timestamp_seconds" in ln][0]
    if what == "build":
        env.set(gomode="fail")
    elif what == "vault":
        env.set(fvmode="fail")
    elif what == "crash":
        env.set(mode="crash")
    elif what == "usage":
        env.set(mode="usage")
    elif what == "figures":
        env.figures.write_text("{}")
    else:
        shutil.rmtree(env.remote)
    r = env.run()
    assert r.returncode == 3, (what, r.returncode, r.stderr)
    text = env.prom.read_text()
    assert "domainscope_drive_refresh_ok 0" in text
    assert last in text, "the last success time was not carried forward"
    assert "FAKEKEY" not in r.stdout + r.stderr


@needs_git
def test_the_first_run_failing_has_no_success_time(env: Env) -> None:
    env.set(gomode="fail")
    assert env.run().returncode == 3
    text = env.prom.read_text()
    assert "ok 0" in text and "last_success" not in text and "last_run_timestamp_seconds" in text


@needs_git
def test_a_main_without_the_tool_is_a_failed_run_naming_it(env: Env) -> None:
    git(env.remote, "rm", "-q", "-r", "src/cmd/drive-refresh")
    git(env.remote, "commit", "-q", "-m", "tool moved")
    r = env.run()
    assert r.returncode == 3 and "src/cmd/drive-refresh" in r.stderr


@needs_git
def test_bad_settings_are_refused(env: Env) -> None:
    assert env.run(apply="2").returncode == 3
    assert env.run(extra={"DSDRIVE_TIMEOUT_SECONDS": "soon"}).returncode == 3


def test_go_is_found_where_a_service_has_no_login_path() -> None:
    # systemd gives a service no login PATH, and on the builder Go lives in /usr/local/go/bin: the wrapper and the installer must look there.
    run, install = RUN.read_text(), INSTALL.read_text()
    assert "/usr/local/go/bin/go" in run and 'DSDRIVE_GO:-$(command -v go ||' in run
    assert "/usr/local/go/bin/go" in install


@needs_git
def test_go_defaults_to_the_one_on_the_path(env: Env) -> None:
    # DSDRIVE_GO unset (None removes it): the go found on PATH builds the tool, as it does under the unit.
    r = env.run(extra={"DSDRIVE_GO": None})
    assert r.returncode == 0, r.stderr
    assert (env.ctrl / "go-calls").exists() and "build" in env.read("go-calls")


def test_the_units_are_what_the_wrapper_expects() -> None:
    svc = configparser.ConfigParser(strict=False, interpolation=None)
    svc.optionxform = str
    svc.read(SERVICE)
    s = svc["Service"]
    assert s["Type"] == "oneshot" and s["User"] == "root"
    assert s["SuccessExitStatus"] == "1"
    assert "flock -n /run/lock/domainscope-drive-refresh.lock /usr/local/bin/domainscope-drive-refresh-run" in s["ExecStart"]
    assert s["EnvironmentFile"] == "-/etc/default/domainscope-drive-refresh"
    tim = configparser.ConfigParser(strict=False, interpolation=None)
    tim.optionxform = str
    tim.read(TIMER)
    t = tim["Timer"]
    assert t["OnCalendar"] == "*-*-* 07:30:00 UTC"
    assert t["Persistent"] == "false"
    assert "OnBootSec" not in t
    assert tim["Install"]["WantedBy"] == "timers.target"


def test_the_installer_only_installs_merged_files_and_is_valid_shell() -> None:
    subprocess.run(["bash", "-n", str(INSTALL)], check=True)
    subprocess.run(["bash", "-n", str(RUN)], check=True)
    text = INSTALL.read_text()
    assert "refusing: these files differ from origin/main" in text
    for f in ("scripts/domainscope-drive-refresh-run", "domainscope-drive-refresh.service", "domainscope-drive-refresh.timer"):
        assert f in text
    assert "scripts/domainscope-drive-figures.py" in text
    assert "--dry-run" in text and "systemctl set-environment" not in text
    assert "--property=TimeoutStartSec=25min" in text
    assert "--property=User=root" in text and "--setenv=HOME=/root" in text
    assert "search" not in text


def test_the_rules_and_the_runbook_agree() -> None:
    groups = yaml.safe_load(RULES.read_text())["groups"]
    alerts = {r["alert"]: r for g in groups for r in g["rules"]}
    assert set(alerts) == {"DomainScopeDriveRefreshFailing", "DomainScopeDriveRefreshStale"}
    for a in alerts.values():
        assert a["annotations"]["runbook_url"] == "docs/runbooks/domainscope-drive-refresh.md"
    assert RUNBOOK.exists()
    for name in alerts:
        assert name in RUNBOOK.read_text()
    # the metric names the rules read are the ones the tool writes (domainscope_drive_refresh_*)
    exprs = " ".join(a["expr"] for a in alerts.values())
    assert "domainscope_drive_refresh_ok" in exprs and "domainscope_drive_refresh_last_success_timestamp_seconds" in exprs


@pytest.mark.skipif(shutil.which("promtool") is None, reason="needs promtool (the monitoring VM)")
def test_promtool_rules_and_unit_tests() -> None:
    subprocess.run(["promtool", "check", "rules", str(RULES)], check=True, capture_output=True)
    subprocess.run(["promtool", "test", "rules", str(PROMTOOL_TEST)], check=True, capture_output=True, cwd=ROOT)
