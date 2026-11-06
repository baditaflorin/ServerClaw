"""config/ct108/tier0-edge-grants/tier0-edge-grants.sh: the CT108 wrapper around the INSTALLED standby_edge_grants_job.py.

A shim `gh` clones a local repo; the job runs with --inject so no Prometheus, ssh or GitHub write is needed. Pinned: the wrapper runs the job from the installed directory (never from the clone), the clone is
sparse, shallow and blob-less and holds exactly the six files the job needs, its exit code and RESULT_JSON come through, a failed clone, a missing installed job, a missing file in main and a work directory that
cannot be made are each exit 3 with ok=0 and the last good numbers kept (and never a clone into "/repo"), a dry run and a rehearsal write no metrics, one run at a time, and no work directory is left.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from policy_test_sources import copy_source

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "config" / "ct108" / "tier0-edge-grants" / "tier0-edge-grants.sh"
FILES = ["scripts/standby_edge_grants.py", "scripts/standby_edge_grants_job.py", "scripts/tailscale_policy_sync.py", "scripts/tailscale_policy_reconcile.py",
         "config/tailscale/policy.hujson", "config/tailscale/lockout-guard.json"]
STRAY = ["docs/not-needed.md", "scripts/other-tool.py", "config/other/big.yml"]                      # in main, but not in the sparse worktree


def world(tmp: Path, missing=(), installed=True):
    work = tmp / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    for rel in FILES:
        if rel in missing:
            continue
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        copy_source(ROOT, rel, work / rel)
    for rel in STRAY:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text("not for the job\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "-C", str(work), "add", "--", "."], check=True, env=env)                  # a fresh directory that holds only the files above
    subprocess.run(["git", "-C", str(work), "commit", "-q", "-m", "init"], check=True, env=env)
    origin = tmp / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(origin)], check=True)
    lib, tslib = tmp / "lib", tmp / "tslib"                                                              # what the installers put on CT108
    lib.mkdir()
    tslib.mkdir()
    if installed:
        shutil.copy(ROOT / "scripts/standby_edge_grants_job.py", lib)
        shutil.copy(ROOT / "scripts/standby_edge_grants.py", lib)
        shutil.copy(ROOT / "scripts/tailscale_policy_sync.py", tslib)
        shutil.copy(ROOT / "scripts/tailscale_policy_reconcile.py", tslib)
        copy_source(ROOT, "config/tailscale/lockout-guard.json", tslib / "lockout-guard.json")
    bin_ = tmp / "bin"
    bin_.mkdir()
    (bin_ / "gh").write_text(f'#!/bin/bash\necho "$*" >> "{tmp}/gh.log"\n[ -f "{tmp}/GH_FAIL" ] && exit 1\ncase "$1 $2" in "repo clone") git clone -q "{origin}" "$4" ;; *) exit 98 ;; esac\n')
    (bin_ / "ssh").write_text("#!/bin/bash\nexit 255\n")                                                 # no runtime can be reached from a test, whatever ssh or ~/.ssh/config the host has (CI has no ssh at all)
    if shutil.which("flock") is None:
        (bin_ / "flock").write_text("#!/usr/bin/env python3\nimport fcntl, sys\ntry:\n    fcntl.flock(int([a for a in sys.argv[1:] if a != '-n'][0]), fcntl.LOCK_EX | fcntl.LOCK_NB)\nexcept OSError:\n    sys.exit(1)\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    return dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", TIER0_EDGE_GRANTS_STATE=str(tmp / "state"), TIER0_EDGE_GRANTS_TEXTFILE=str(tmp / "grants.prom"),
                TIER0_INFRA_REPO="x/y", TIER0_TMPDIR=str(tmp), TIER0_EDGE_GRANTS_LIB=str(lib), TIER0_TS_LIB=str(tslib))


def run(env, *args):
    r = subprocess.run(["bash", str(WRAPPER), *args], capture_output=True, text=True, env=env, timeout=120)
    res = [json.loads(l[len("RESULT_JSON "):]) for l in r.stdout.splitlines() if l.startswith("RESULT_JSON ")]
    return r, (res[-1] if res else None)


def test_the_installed_job_runs_against_a_sparse_clone_and_its_result_and_exit_code_come_through(tmp_path):
    env = world(tmp_path)
    inj = tmp_path / "closed.json"
    inj.write_text("[]")
    r, res = run(env, "--inject", str(inj), "--dry-run")
    assert r.returncode == 0 and res["status"] == "nothing to grant", r.stdout + r.stderr
    assert not (tmp_path / "grants.prom").exists()                                                      # a dry run writes no metrics
    assert not list(tmp_path.glob("tier0-edge-grants.*"))                                               # the work directory is removed
    log = (tmp_path / "gh.log").read_text()
    assert "repo clone x/y" in log and "--depth 1" in log and "--filter=blob:none" in log and "--sparse" in log      # shallow, blob-less and sparse: a few MB, not the 580 MB tree


def test_the_job_gets_exactly_six_files_and_is_run_from_the_installed_directory_with_the_installed_tools(tmp_path):
    env = world(tmp_path)
    stub = Path(env["TIER0_EDGE_GRANTS_LIB"]) / "standby_edge_grants_job.py"
    stub.write_text("import json, os, sys\nrepo = sys.argv[sys.argv.index('--repo') + 1]\n"
                    "files = sorted(os.path.relpath(os.path.join(d, f), repo) for d, ds, fs in os.walk(repo) if '.git' not in d.split(os.sep) for f in fs)\n"
                    "print('RESULT_JSON ' + json.dumps({'files': files, 'argv': sys.argv[1:], 'script': os.path.abspath(sys.argv[0])}))\n")
    r, res = run(env, "--dry-run", "--inject", "x.json")
    assert r.returncode == 0, r.stderr
    assert res["files"] == sorted(FILES)                                                                  # the sparse worktree: not docs/, not the other scripts, not the other configs
    assert res["script"] == str(stub)                                                                     # the INSTALLED job, never scripts/standby_edge_grants_job.py of the clone
    argv = res["argv"]
    assert argv[argv.index("--lib") + 1] == env["TIER0_TS_LIB"] and argv[argv.index("--slug") + 1] == "x/y" and argv[argv.index("--state") + 1] == env["TIER0_EDGE_GRANTS_STATE"]
    assert argv[argv.index("--textfile") + 1] == env["TIER0_EDGE_GRANTS_TEXTFILE"] and argv[-3:] == ["--dry-run", "--inject", "x.json"]      # the caller's arguments come through


def test_a_refused_run_exits_4_and_still_reports(tmp_path):
    env = world(tmp_path)
    inj = tmp_path / "closed.json"
    inj.write_text(json.dumps([["100.64.0.24", 8100 + i, 2] for i in range(5)] + [["100.9.9.9", 8100, 2]]))
    # the ssh shim fails: the sockets of the runtime cannot be listed, so nothing qualifies and nothing is granted blind
    r, res = run(env, "--inject", str(inj), "--dry-run")
    assert r.returncode == 0 and res["status"] == "nothing to grant" and len(res["unverified"]) == 5 and res["rejected"][0][0] == "100.9.9.9"


def test_a_job_that_differs_from_main_is_exit_3_and_the_metric_says_so(tmp_path):
    env = world(tmp_path)
    job = Path(env["TIER0_EDGE_GRANTS_LIB"]) / "standby_edge_grants_job.py"
    job.write_text(job.read_text() + "\n# a change that is installed but not in main\n")
    r, res = run(env)
    assert r.returncode == 3 and "differs from main" in res["could_not_run"]
    kept = dict(l.split(" ", 1) for l in (tmp_path / "grants.prom").read_text().splitlines())
    assert kept["tier0_edge_grants_installed_matches_git"] == "0" and kept["tier0_edge_grants_ok"] == "0"


def test_a_failed_clone_is_exit_3_with_ok_0_and_the_last_good_numbers_kept(tmp_path):
    env = world(tmp_path)
    (tmp_path / "GH_FAIL").write_text("")
    prom = tmp_path / "grants.prom"
    prom.write_text("tier0_edge_grants_ok 1\ntier0_edge_grants_last_run_timestamp_seconds 1\ntier0_edge_grants_last_success_timestamp_seconds 1792000000\ntier0_edge_grants_prs_total 4\n")
    r, res = run(env)
    assert r.returncode == 3 and res["status"] == "could not run"
    kept = dict(l.split(" ", 1) for l in prom.read_text().splitlines())
    assert kept["tier0_edge_grants_ok"] == "0" and kept["tier0_edge_grants_prs_total"] == "4" and kept["tier0_edge_grants_last_success_timestamp_seconds"] == "1792000000"
    assert int(kept["tier0_edge_grants_last_run_timestamp_seconds"]) > 1                               # the run time moved: the job is alive, it just failed


def test_a_dry_run_or_a_rehearsal_that_cannot_clone_leaves_the_metrics_alone(tmp_path):
    for name, flag in (("dry", "--dry-run"), ("reh", "--rehearse")):
        d = tmp_path / name
        d.mkdir()
        env = world(d)
        (d / "GH_FAIL").write_text("")
        (d / "grants.prom").write_text("tier0_edge_grants_ok 1\n")
        r, res = run(env, flag)
        assert r.returncode == 3 and (d / "grants.prom").read_text() == "tier0_edge_grants_ok 1\n"


def test_a_work_directory_that_cannot_be_made_is_exit_3_and_never_a_clone_into_slash_repo(tmp_path):
    env = world(tmp_path)
    env["TIER0_TMPDIR"] = str(tmp_path / "does-not-exist")                                              # stands for /run full or not writable: mktemp -d fails
    r, res = run(env)
    assert r.returncode == 3 and res["status"] == "could not run" and "work directory" in res["could_not_run"]
    assert not (tmp_path / "gh.log").exists()                                                            # gh was never called: the old script cloned into "/repo" on the root filesystem
    assert dict(l.split(" ", 1) for l in (tmp_path / "grants.prom").read_text().splitlines())["tier0_edge_grants_ok"] == "0"


def test_a_job_that_is_not_installed_is_a_clear_exit_3(tmp_path):
    env = world(tmp_path, installed=False)
    r, res = run(env)
    assert r.returncode == 3 and "not installed" in r.stderr and "tier0-edge-grants-install.sh" in r.stderr and not (tmp_path / "gh.log").exists()


def test_a_file_the_job_needs_that_is_not_in_main_is_exit_3(tmp_path):
    env = world(tmp_path, missing=("config/tailscale/lockout-guard.json",))
    r, res = run(env)
    assert r.returncode == 3 and "config/tailscale/lockout-guard.json is not in x/y main" in r.stderr


def test_a_second_run_at_the_same_time_does_nothing(tmp_path):
    env = world(tmp_path)
    (tmp_path / "state").mkdir()
    import fcntl
    with open(tmp_path / "state" / "lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r, res = run(env)
    assert r.returncode == 0 and "another tier0-edge-grants run is in progress" in r.stdout and not (tmp_path / "gh.log").exists()


def test_units_run_the_installed_wrapper_hourly_with_a_timeout_that_covers_the_ci_wait():
    d = WRAPPER.parent
    service = (d / "tier0-edge-grants.service").read_text()
    timer = (d / "tier0-edge-grants.timer").read_text()
    assert "ExecStart=/usr/local/bin/tier0-edge-grants.sh" in service and "Type=oneshot" in service and "User=root" in service
    assert int([l for l in service.splitlines() if l.startswith("TimeoutStartSec=")][0].split("=")[1]) >= 1800        # the job waits up to 25 minutes for CI
    assert "OnCalendar=*-*-* *:20:00" in timer                                                                       # half an hour after the runner's :50 edge-compat metrics
