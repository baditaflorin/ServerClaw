"""scripts/tier0-edge-grants-install.sh: installs the tier0-edge-grants job on CT108 from an up-to-date main, or checks what is installed against main.

The script runs for real inside a throwaway repository with a local `origin`; `ssh` is a shim that runs the remote command on this machine, with every install root (lib, bin, units, backups, the
reconciler's lib) pointed at temporary directories and `systemctl` a logging shim. Pinned: it refuses anything that is not identical to origin/main, it installs byte-identical files with the
right modes, it keeps what it replaces in the backup directory and not next to the scripts, it never touches PAUSE or the timer's enablement, it compiles before it installs, --check is read-only
and its exit code says whether the job would refuse to run, and the files it shares with the reconciler are compared and never installed.
"""
import os
import shutil
import subprocess
from pathlib import Path

from policy_test_sources import copy_source

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "tier0-edge-grants-install.sh"
FILES = ["scripts/standby_edge_grants_job.py", "scripts/standby_edge_grants.py", "scripts/tailscale_policy_sync.py", "scripts/tailscale_policy_reconcile.py", "config/tailscale/lockout-guard.json",
         "config/ct108/tier0-edge-grants/tier0-edge-grants.sh", "config/ct108/tier0-edge-grants/tier0-edge-grants.service", "config/ct108/tier0-edge-grants/tier0-edge-grants.timer"]


def git(*args, cwd, env):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env)


def world(tmp: Path, mutate=None):
    """A repository with the installer and the eight files, pushed to a local origin/main; returns (script path, env, dirs)."""
    work = tmp / "work"
    work.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    git("init", "-q", "-b", "main", cwd=work, env=env)
    for rel in FILES + ["scripts/tier0-edge-grants-install.sh"]:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        copy_source(ROOT, rel, work / rel)
    (work / "scripts/tier0-edge-grants-install.sh").chmod(0o755)
    if mutate:
        mutate(work)
    git("add", "--", *(FILES + ["scripts/tier0-edge-grants-install.sh"]), cwd=work, env=env)
    git("commit", "-q", "-m", "init", cwd=work, env=env)
    origin = tmp / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(origin)], check=True)
    git("remote", "add", "origin", str(origin), cwd=work, env=env)
    git("fetch", "-q", "origin", "main", cwd=work, env=env)
    bin_ = tmp / "bin"
    bin_.mkdir()
    (bin_ / "ssh").write_text('#!/bin/bash\nwhile [ "${1#-}" != "$1" ]; do [ "$1" = -o ] && shift; shift; done\nshift\necho "ssh $*" >> "$TIER0_TEST_LOG"\nexec bash -c "$*"\n')
    (bin_ / "systemctl").write_text('#!/bin/bash\necho "systemctl $*" >> "$TIER0_TEST_LOG"\n')
    if shutil.which("sha256sum") is None:                                                                # macOS: the remote side is Linux, where it exists
        (bin_ / "sha256sum").write_text('#!/usr/bin/env python3\nimport hashlib, sys\nfor f in sys.argv[1:]:\n    print(hashlib.sha256(open(f, "rb").read()).hexdigest() + "  " + f)\n')
    for f in bin_.iterdir():
        f.chmod(0o755)
    dirs = {k: tmp / "root" / k for k in ("lib", "tslib", "bin", "units", "backups")}
    for d in dirs.values():
        d.parent.mkdir(exist_ok=True)
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", TIER0_TEST_LOG=str(tmp / "calls.log"), T0_LIB=str(dirs["lib"]), T0_TSLIB=str(dirs["tslib"]), T0_BIN=str(dirs["bin"]),
               T0_UNITS=str(dirs["units"]), T0_BACKUPS=str(dirs["backups"]), T0_SYSTEMCTL=str(bin_ / "systemctl"), TIER0_GRANTS_HOST="builder-test")
    return work / "scripts/tier0-edge-grants-install.sh", env, dirs


def install_tools(dirs, same=True):
    """What scripts/tailscale-policy-reconcile-install.sh leaves on CT108."""
    dirs["tslib"].mkdir(parents=True, exist_ok=True)
    for rel in ("scripts/tailscale_policy_sync.py", "scripts/tailscale_policy_reconcile.py", "config/tailscale/lockout-guard.json"):
        copy_source(ROOT, rel, dirs["tslib"] / Path(rel).name)
    if not same:
        (dirs["tslib"] / "tailscale_policy_sync.py").write_text("# an older sync tool\n")


def run(script, env, *args):
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, env=env, timeout=120)


def test_install_puts_the_files_identical_to_main_in_place_with_the_right_modes_and_reloads_systemd(tmp_path):
    script, env, d = world(tmp_path)
    install_tools(d)
    r = run(script, env)
    assert r.returncode == 0, r.stdout + r.stderr
    for rel, dst, mode in (("scripts/standby_edge_grants_job.py", d["lib"] / "standby_edge_grants_job.py", 0o644), ("scripts/standby_edge_grants.py", d["lib"] / "standby_edge_grants.py", 0o644),
                           ("config/ct108/tier0-edge-grants/tier0-edge-grants.sh", d["bin"] / "tier0-edge-grants.sh", 0o755),
                           ("config/ct108/tier0-edge-grants/tier0-edge-grants.service", d["units"] / "tier0-edge-grants.service", 0o644),
                           ("config/ct108/tier0-edge-grants/tier0-edge-grants.timer", d["units"] / "tier0-edge-grants.timer", 0o644)):
        assert dst.read_bytes() == (ROOT / rel).read_bytes() and (dst.stat().st_mode & 0o777) == mode, dst
    assert "systemctl daemon-reload" in (tmp_path / "calls.log").read_text()
    assert not d["backups"].exists()                                                                     # nothing was replaced, so nothing to keep
    assert "NOTE" not in r.stdout and "tier0-edge-grants.sh" in r.stdout                                 # the sha256 lines of what is installed
    assert "not set" in r.stdout or "PAUSE" in r.stdout


def test_what_is_replaced_is_kept_in_the_backup_directory_and_pause_and_state_are_never_touched(tmp_path):
    script, env, d = world(tmp_path)
    install_tools(d)
    d["lib"].mkdir(parents=True)
    d["bin"].mkdir(parents=True)
    (d["lib"] / "standby_edge_grants_job.py").write_text("# the old job\n")
    (d["bin"] / "tier0-edge-grants.sh").write_text("#!/bin/bash\n# the old wrapper\n")
    state = tmp_path / "state"
    state.mkdir()
    (state / "PAUSE").write_text("")
    r = run(script, env)
    assert r.returncode == 0, r.stdout + r.stderr
    kept = sorted(p for p in d["backups"].glob("tier0-edge-grants-*/*"))
    assert [p.name for p in kept] == ["standby_edge_grants_job.py", "tier0-edge-grants.sh"]
    assert (kept[0].read_text(), kept[1].read_text()) == ("# the old job\n", "#!/bin/bash\n# the old wrapper\n")
    assert (d["lib"] / "standby_edge_grants_job.py").read_bytes() == (ROOT / "scripts/standby_edge_grants_job.py").read_bytes()
    assert (state / "PAUSE").exists()
    assert not list(d["lib"].glob("*.bak*")) and not list(d["bin"].glob("*.bak*")) and not list(d["units"].glob("*.bak*"))     # never a copy next to what it replaced


def test_it_refuses_anything_that_is_not_identical_to_origin_main_and_calls_nothing(tmp_path):
    script, env, d = world(tmp_path)
    install_tools(d)
    job = script.parent / "standby_edge_grants_job.py"
    job.write_text(job.read_text() + "\n# an uncommitted change\n")
    r = run(script, env)
    assert r.returncode == 1 and "refusing" in r.stderr and "origin/main" in r.stderr
    assert not (tmp_path / "calls.log").exists() and not d["lib"].exists()


def test_a_script_that_does_not_compile_is_not_installed(tmp_path):
    def break_job(work):
        (work / "scripts/standby_edge_grants_job.py").write_text("def broken(:\n")                       # merged to main like that: identical to origin/main, but it cannot run
    script, env, d = world(tmp_path, mutate=break_job)
    install_tools(d)
    r = run(script, env)
    assert r.returncode != 0 and not (d["lib"] / "standby_edge_grants_job.py").exists() and not (d["bin"] / "tier0-edge-grants.sh").exists()


def test_check_is_read_only_and_its_exit_code_says_whether_the_job_would_refuse_to_run(tmp_path):
    script, env, d = world(tmp_path)
    install_tools(d)
    assert run(script, env, "--check").returncode == 1                                                   # nothing installed yet: the job would refuse
    assert not d["lib"].exists() and not d["bin"].exists()                                               # --check wrote nothing
    assert run(script, env).returncode == 0
    ok = run(script, env, "--check")
    assert ok.returncode == 0 and "everything the job runs equals main" in ok.stdout and "DIFFERS" not in ok.stdout and "MISSING" not in ok.stdout
    (d["lib"] / "standby_edge_grants.py").write_text("# tampered\n")
    bad = run(script, env, "--check")
    assert bad.returncode == 1 and "DIFFERS" in bad.stdout and "standby_edge_grants.py" in bad.stdout and "would refuse" in bad.stdout
    assert (d["lib"] / "standby_edge_grants.py").read_text() == "# tampered\n"                         # and --check did not repair it


def test_the_reconciler_tools_are_compared_never_installed_and_the_install_says_when_they_are_behind(tmp_path):
    script, env, d = world(tmp_path)
    install_tools(d, same=False)
    r = run(script, env)
    assert r.returncode == 0 and "DIFFERS" in r.stdout and "NOTE: the reconciler tools" in r.stdout and "tailscale-policy-reconcile-install.sh" in r.stdout
    assert (d["tslib"] / "tailscale_policy_sync.py").read_text() == "# an older sync tool\n"            # not this installer's to touch
    chk = run(script, env, "--check")
    assert chk.returncode == 1 and "would refuse" in chk.stdout


def test_an_unknown_argument_is_a_usage_error(tmp_path):
    script, env, d = world(tmp_path)
    r = run(script, env, "--enable")
    assert r.returncode == 2 and "usage" in r.stderr
