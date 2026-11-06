"""Tests for scripts/hostconf-scheduled.sh, the daily job that runs the read-only hostconf drift check on the operator's machine and ships the metrics
to the monitoring VM. The script runs for real, in a sandbox: a fake `hostconf.py` (exit code and output chosen by the test) and a shim `ssh` first on PATH
that records what it was asked to run and what came in on stdin. `launchctl` is never called here (install and uninstall are macOS only); the LaunchAgent
the script would write is checked as data.
"""

from __future__ import annotations

import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
JOB = REPO_ROOT / "scripts" / "hostconf-scheduled.sh"

needs_bash_and_perl = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("perl") is None, reason="needs bash and perl")

FAKE_TOOL = '''\
import os, pathlib, sys, time
args = sys.argv[1:]
assert args[:2] == ["drift", "--all"], args
out = pathlib.Path(args[args.index("--textfile-dir") + 1])
if os.environ.get("FAKE_NO_FILE") != "1":
    out.mkdir(parents=True, exist_ok=True)
    (out / "fleet_hostconf.prom").write_text('fleet_hostconf_drift_files{machine="a"} 0\\nfleet_hostconf_last_run_timestamp_seconds 1\\n')
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
print("fake drift --all ran")
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
'''

SSH_SHIM = '''#!/bin/bash
printf '%s\\n' "$*" >> "$SANDBOX/ssh.args"
if [ ! -t 0 ]; then cat > "$SANDBOX/ssh.stdin"; fi
exit "${FAKE_SSH_EXIT:-0}"
'''


LAUNCHCTL_SHIM = '''#!/bin/bash
printf '%s\\n' "$*" >> "$SANDBOX/launchctl.args"
exit "${FAKE_LAUNCHCTL_EXIT:-0}"
'''


class Sandbox:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.repo = tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "scripts" / "hostconf.py").write_text(FAKE_TOOL)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        for name, body in (("ssh", SSH_SHIM), ("launchctl", LAUNCHCTL_SHIM)):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        self.home = tmp / "home"
        self.home.mkdir()
        self.state = tmp / "state"
        self.log = tmp / "logs" / "hostconf-drift.log"

    def env(self, **extra: str) -> dict[str, str]:
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "SANDBOX": str(self.tmp),
            "HOSTCONF_REPO_DIR": str(self.repo),
            "HOSTCONF_STATE": str(self.state),
            "HOSTCONF_LOG": str(self.log),
            "HOSTCONF_MONITORING_SSH": "mon-test",
            "HOSTCONF_PYTHON": sys.executable,
            "HOSTCONF_PLIST": str(self.tmp / "agent.plist"),
            "HOSTCONF_INSTALL_DIR": str(self.tmp / "installed"),
        }
        env.update(extra)
        return env

    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(JOB), *args], env=self.env(**env), capture_output=True, text=True, timeout=60, check=False)

    @property
    def ssh_calls(self) -> list[str]:
        path = self.tmp / "ssh.args"
        return path.read_text().splitlines() if path.exists() else []

    @property
    def launchctl_calls(self) -> list[str]:
        path = self.tmp / "launchctl.args"
        return path.read_text().splitlines() if path.exists() else []

    @property
    def shipped(self) -> str | None:
        path = self.tmp / "ssh.stdin"
        return path.read_text() if path.exists() else None


@pytest.fixture()
def box(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


@needs_bash_and_perl
def test_a_run_ships_the_tools_metrics_to_the_monitoring_vm_atomically_and_exits_0(box: Sandbox) -> None:
    p = box.run("run")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "fake drift --all ran" in p.stdout and "shipped 2 metric lines" in p.stdout
    assert len(box.ssh_calls) == 1
    call = box.ssh_calls[0]
    assert "mon-test" in call and "BatchMode=yes" in call
    # written beside the target and renamed over it, so node_exporter never reads half a file; the temporary name is not *.prom
    assert "sudo -n tee '/var/lib/prometheus/node-exporter/.fleet_hostconf.prom.tmp'" in call
    assert "sudo -n mv -f '/var/lib/prometheus/node-exporter/.fleet_hostconf.prom.tmp' '/var/lib/prometheus/node-exporter/fleet_hostconf.prom'" in call
    assert box.shipped == 'fleet_hostconf_drift_files{machine="a"} 0\nfleet_hostconf_last_run_timestamp_seconds 1\n'
    assert not (box.state / "run.lock").exists()


@needs_bash_and_perl
@pytest.mark.parametrize("code", ["2", "3"])
def test_drift_and_unreachable_hosts_are_results_not_failures(box: Sandbox, code: str) -> None:
    """exit 2 (drift) and 3 (not everything reachable) must reach the alerts: the metrics say which machine and why."""
    p = box.run("run", FAKE_EXIT=code)
    assert p.returncode == 0, p.stdout + p.stderr
    assert box.shipped is not None and f"hostconf.py exit {code}" in p.stdout


@needs_bash_and_perl
@pytest.mark.parametrize("code", ["1", "4", "127"])
def test_a_crashed_tool_ships_nothing_and_fails_the_job(box: Sandbox, code: str) -> None:
    """exit 1 = invalid manifest or a crash: a stale file on the monitoring VM would then be refreshed by nothing, and HostconfCheckStale is how that is noticed."""
    p = box.run("run", FAKE_EXIT=code)
    assert p.returncode == 1
    assert f"hostconf.py exited {code}" in p.stdout and "nothing shipped" in p.stdout
    assert box.ssh_calls == []


@needs_bash_and_perl
def test_a_tool_that_writes_no_metrics_file_ships_nothing(box: Sandbox) -> None:
    p = box.run("run", FAKE_NO_FILE="1")
    assert p.returncode == 1 and "wrote no metrics file" in p.stdout
    assert box.ssh_calls == []


@needs_bash_and_perl
def test_a_failed_write_on_the_monitoring_vm_fails_the_job(box: Sandbox) -> None:
    p = box.run("run", FAKE_SSH_EXIT="255")
    assert p.returncode == 1 and "could not write /var/lib/prometheus/node-exporter/fleet_hostconf.prom on mon-test" in p.stdout


@needs_bash_and_perl
def test_a_tool_that_does_not_answer_is_killed_after_the_time_limit(box: Sandbox) -> None:
    p = box.run("run", FAKE_SLEEP="30", HOSTCONF_MAX_SECONDS="1")
    assert p.returncode == 1 and "exited 142" in p.stdout and "nothing shipped" in p.stdout
    assert box.ssh_calls == []


@needs_bash_and_perl
def test_a_second_run_while_one_is_active_does_nothing_and_a_stale_lock_is_replaced(box: Sandbox) -> None:
    lock = box.state / "run.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(str(os.getpid()))   # this test process is alive
    p = box.run("run")
    assert p.returncode == 0 and "another run is active" in p.stdout and box.ssh_calls == []
    (lock / "pid").write_text("999999")           # nobody has this pid
    p = box.run("run")
    assert p.returncode == 0 and box.shipped is not None


@needs_bash_and_perl
def test_the_log_is_cut_to_its_last_megabyte_when_it_passes_two(box: Sandbox) -> None:
    box.log.parent.mkdir(parents=True)
    box.log.write_text("x" * 2_100_000)
    assert box.run("run").returncode == 0
    size = box.log.stat().st_size
    assert size <= 1_000_000 + 10_000


def test_the_script_can_look_but_never_change_a_host() -> None:
    """The scheduled job runs unattended with the operator's ssh access: it may only use the read-only verb."""
    text = JOB.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"hostconf\.py[\"']?\s+(apply|adopt)", code)
    assert re.search(r"hostconf\.py\"?\s+drift --all --textfile-dir", code)
    for word in ("--yes", "password", "token", "secret", "ssh-add", "sudo -n sh", "rm -rf /"):
        assert word not in code.replace("sudo -n rm -f", ""), word
    # the only thing it runs with sudo is writing the one metrics file on the monitoring VM (and, in status, reading its mtime)
    assert set(re.findall(r"sudo -n (\w+)", code)) <= {"tee", "chmod", "mv", "rm", "stat"}


def test_the_launch_agent_runs_the_installed_copy_daily_without_secrets(box: Sandbox) -> None:
    p = box.run("plist")
    assert p.returncode == 0, p.stderr
    agent = plistlib.loads(p.stdout.encode())
    assert agent["Label"] == "org.baditaflorin.hostconf-drift"
    assert agent["ProgramArguments"] == ["/bin/bash", str(box.tmp / "installed" / "hostconf-scheduled.sh"), "run"]
    assert agent["StartCalendarInterval"] == {"Hour": 12, "Minute": 20}   # outside the 00-06Z backup windows
    assert agent["RunAtLoad"] is False
    assert "/opt/homebrew/bin" in agent["EnvironmentVariables"]["PATH"]    # git and gh live there
    assert agent["StandardOutPath"] == agent["StandardErrorPath"] == str(box.log)
    assert set(agent["EnvironmentVariables"]) == {"PATH"}


def test_install_copies_the_script_writes_the_agent_and_loads_it_and_uninstall_takes_it_away_again(box: Sandbox) -> None:
    p = box.run("install")
    assert p.returncode == 0, p.stdout + p.stderr
    installed = box.tmp / "installed" / "hostconf-scheduled.sh"
    assert installed.read_text() == JOB.read_text() and os.access(installed, os.X_OK)
    agent = plistlib.loads((box.tmp / "agent.plist").read_bytes())
    assert agent["ProgramArguments"] == ["/bin/bash", str(installed), "run"]
    uid = str(os.getuid())
    assert box.launchctl_calls == [f"bootout gui/{uid}/org.baditaflorin.hostconf-drift", f"bootstrap gui/{uid} {box.tmp / 'agent.plist'}"]
    assert "installed: runs daily at 12:20 local" in p.stdout
    # the installed copy is what launchd runs: it must work from where it was put
    assert box.run("status").returncode == 0

    p = box.run("uninstall")
    assert p.returncode == 0, p.stdout + p.stderr
    assert not installed.exists() and not (box.tmp / "agent.plist").exists()
    assert box.launchctl_calls[-1] == f"bootout gui/{uid}/org.baditaflorin.hostconf-drift"
    assert box.log.parent.exists() and box.state.exists()   # the log and the checkout stay


def test_an_install_that_cannot_fetch_main_leaves_no_agent_behind(box: Sandbox) -> None:
    """A plist left in ~/Library/LaunchAgents is loaded by launchd at the next login: it must not exist when the first checkout failed."""
    p = box.run("install", HOSTCONF_REPO_DIR="", HOSTCONF_REPO_URL=f"file://{box.tmp / 'no-such-origin'}")
    assert p.returncode == 1 and "could not make the first checkout" in p.stdout
    assert not (box.tmp / "agent.plist").exists() and not (box.tmp / "installed").exists()
    assert box.launchctl_calls == []


def test_an_unknown_command_is_a_usage_error(box: Sandbox) -> None:
    p = box.run("apply")
    assert p.returncode == 2 and "usage:" in p.stderr


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
@needs_bash_and_perl
def test_the_tool_and_the_manifest_come_from_main_as_a_sparse_depth_1_checkout_and_the_next_run_follows_main(box: Sandbox, tmp_path: Path) -> None:
    git_env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}

    def git(*args: str, cwd: Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, env=git_env, check=True, capture_output=True)

    origin = tmp_path / "origin"
    (origin / "scripts").mkdir(parents=True)
    (origin / "config" / "hostconf").mkdir(parents=True)
    (origin / "elsewhere").mkdir()
    (origin / "scripts" / "hostconf.py").write_text(FAKE_TOOL)
    (origin / "config" / "hostconf" / "hostconf.yaml").write_text("version: 1\n")
    (origin / "elsewhere" / "big.bin").write_text("not needed by the check\n")
    git("init", "-q", "-b", "main", cwd=origin)
    git("config", "uploadpack.allowFilter", "true", cwd=origin)
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=origin)
    git("add", "-A", cwd=origin)
    git("commit", "-q", "-m", "first", cwd=origin)

    env = dict(HOSTCONF_REPO_DIR="", HOSTCONF_REPO_URL=f"file://{origin}", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    p = box.run("run", **env)
    assert p.returncode == 0, p.stdout + p.stderr
    checkout = box.state / "repo"
    assert (checkout / "scripts" / "hostconf.py").is_file() and (checkout / "config" / "hostconf" / "hostconf.yaml").is_file()
    assert not (checkout / "elsewhere").exists()   # only the two paths the check needs

    (origin / "config" / "hostconf" / "hostconf.yaml").write_text("version: 2\n")
    git("commit", "-q", "-am", "second", cwd=origin)
    p = box.run("run", **env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (checkout / "config" / "hostconf" / "hostconf.yaml").read_text() == "version: 2\n"
