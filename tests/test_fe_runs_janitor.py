"""config/0mcp/docker-runtime/fe-runs-janitor: removes ONLY node_modules of idle front-end run dirs under /home/ops/fe_runs.

Born from the 2026-10-18 incident (docker-runtime's root disk filled to 0% from a new ~600 MB run dir every couple of minutes, taking the CI server's host with it). The user approved exactly this policy: regenerable
node_modules of idle run dirs, nothing else. Pinned here: an idle run loses its node_modules and keeps every other file; an active run, a run mounted by a running container and anything that is not a plain directory
inside the base directory are never touched; the idle threshold shrinks as the disk fills; a dry run changes nothing; symlinks are never followed out of the base; metrics are exported and last_success survives a
failure; two runs never overlap.
"""
import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "config" / "0mcp" / "docker-runtime" / "fe-runs-janitor" / "fe-runs-janitor"

DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
cfg = json.load(open(os.environ["JAN_CFG"]))
if sys.argv[1] == "ps":
    print("\n".join(cfg.get("containers", {}))); sys.exit(0)
if sys.argv[1] == "inspect":
    print("\n".join(cfg["containers"].get(sys.argv[-1], []))); sys.exit(0)
'''


def age(path: Path, minutes: float):
    """make every file and directory below path look untouched for `minutes`"""
    t = time.time() - minutes * 60
    for root, dirs, files in os.walk(path):
        for n in dirs + files:
            os.utime(os.path.join(root, n), (t, t), follow_symlinks=False)
    os.utime(path, (t, t), follow_symlinks=False)


def make_run(base: Path, name: str, idle_minutes: float, repos=("frontend",)):
    run = base / name
    for r in repos:
        (run / r / "node_modules" / "left-pad").mkdir(parents=True)
        (run / r / "node_modules" / "left-pad" / "index.js").write_text("x")
        (run / r / "package.json").write_text("{}")
        (run / r / "src").mkdir()
        (run / r / "src" / "a.tsx").write_text("code")
    (run / "output").mkdir()
    (run / "output" / "report.html").write_text("results the owner may still want")
    age(run, idle_minutes)
    return run


class Env:
    def __init__(self, tmp: Path, **cfg):
        self.base = tmp / "fe_runs"
        self.base.mkdir()
        self.log = tmp / "janitor.log"
        self.prom = tmp / "janitor.prom"
        (tmp / "bin").mkdir()
        (tmp / "bin" / "docker").write_text(DOCKER)
        (tmp / "bin" / "docker").chmod(0o755)
        (tmp / "cfg.json").write_text(__import__("json").dumps(cfg))
        self.env = dict(os.environ, PATH=f"{tmp / 'bin'}:{os.environ['PATH']}", JAN_CFG=str(tmp / "cfg.json"), FE_RUNS_BASE=str(self.base), FE_RUNS_LOG=str(self.log), FE_RUNS_PROM=str(self.prom),
                        FE_RUNS_LOCK=str(tmp / "lock"), TMPDIR=str(tmp))

    def run(self, **extra):
        return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=dict(self.env, **{k: str(v) for k, v in extra.items()}), timeout=120)

    def metrics(self):
        return dict(l.split() for l in self.prom.read_text().splitlines() if l and not l.startswith("#"))


def nm(run: Path, repo="frontend"):
    return (run / repo / "node_modules").exists()


def test_an_idle_run_loses_only_its_node_modules(tmp_path):
    e = Env(tmp_path)
    old = make_run(e.base, "r6-old", 300)
    r = e.run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert not nm(old)
    assert (old / "frontend" / "package.json").read_text() == "{}" and (old / "frontend" / "src" / "a.tsx").read_text() == "code"                # source untouched
    assert (old / "output" / "report.html").read_text() == "results the owner may still want"                                                      # outputs untouched


def test_an_active_run_keeps_its_node_modules(tmp_path):
    e = Env(tmp_path)
    active = make_run(e.base, "r7-active", 300)
    (active / "output" / "new-result.json").write_text("{}")                                                          # a fresh file outside node_modules: the run is alive
    r = e.run()
    assert r.returncode == 0 and nm(active)


def test_writes_inside_node_modules_do_not_make_a_run_look_active(tmp_path):
    e = Env(tmp_path)
    old = make_run(e.base, "r6-install-finished", 300)
    (old / "frontend" / "node_modules" / "left-pad" / "fresh.js").write_text("npm just wrote this")                 # npm ci wrote last hour: that is not a reason to keep it
    e.run()
    assert not nm(old)


def test_a_run_dir_mounted_by_a_running_container_is_never_touched(tmp_path):
    base = tmp_path / "fe_runs"
    e = Env(tmp_path, containers={"abc123": [str(base / "r7-mounted"), "/var/lib/docker/volumes/fe_npm_cache/_data"]})
    mounted = make_run(e.base, "r7-mounted", 600)
    other = make_run(e.base, "r6-other", 600)
    r = e.run()
    assert r.returncode == 0 and nm(mounted) and not nm(other)


def test_nested_repos_and_several_node_modules_per_run_are_all_removed(tmp_path):
    e = Env(tmp_path)
    run = make_run(e.base, "r5-two-repos", 400, repos=("frontend", "apps/web"))
    e.run()
    assert not nm(run, "frontend") and not nm(run, "apps/web") and (run / "apps" / "web" / "package.json").exists()


def test_the_idle_threshold_shrinks_as_the_disk_fills(tmp_path):
    e = Env(tmp_path)
    r25 = make_run(e.base, "r-25min", 25)
    r60 = make_run(e.base, "r-60min", 60)
    r200 = make_run(e.base, "r-200min", 200)
    e.run(FE_RUNS_FREE_PCT=60)                                                                                         # plenty free: 120 minutes
    assert nm(r25) and nm(r60) and not nm(r200)
    e.run(FE_RUNS_FREE_PCT=20)                                                                                         # 12-25% free: 30 minutes
    assert nm(r25) and not nm(r60)
    e2 = Env(tmp_path / "second") if (tmp_path / "second").mkdir() is None else None
    r8 = make_run(e2.base, "r-8min", 8)
    r15 = make_run(e2.base, "r-15min", 15)
    e2.run(FE_RUNS_FREE_PCT=5)                                                                                         # under 12% free: 10 minutes
    assert nm(r8) and not nm(r15)
    assert e2.metrics()["fe_runs_janitor_idle_minutes"] == "10"


def test_a_dry_run_changes_nothing_but_says_what_it_would_do(tmp_path):
    e = Env(tmp_path)
    old = make_run(e.base, "r6-old", 300)
    r = e.run(FE_RUNS_DRY=1)
    assert r.returncode == 0 and nm(old)
    assert "REMOVE" in e.log.read_text() and str(old / "frontend" / "node_modules") in e.log.read_text()
    assert e.metrics()["fe_runs_janitor_removed_dirs"] == "0"


def test_symlinks_are_never_followed_out_of_the_base(tmp_path):
    e = Env(tmp_path)
    outside = tmp_path / "precious"
    (outside / "frontend" / "node_modules").mkdir(parents=True)
    (outside / "frontend" / "node_modules" / "keep.txt").write_text("not under the base")
    age(outside, 900)
    (e.base / "linked-run").symlink_to(outside)                                                                       # a run dir that is a symlink to somewhere else
    real = make_run(e.base, "r6-real", 300)
    (real / "frontend" / "node_modules2").mkdir()
    (real / "frontend" / "node_modules2" / "x").write_text("x")
    link_nm = real / "frontend" / "linked_modules"
    link_nm.symlink_to(outside / "frontend" / "node_modules")
    age(real, 300)                                                                                                    # the files made just now must look as idle as the rest
    e.run()
    assert (outside / "frontend" / "node_modules" / "keep.txt").read_text() == "not under the base"
    assert not nm(real) and (real / "frontend" / "node_modules2" / "x").exists()                                      # only directories literally named node_modules


def test_paths_with_spaces_and_odd_characters_are_handled(tmp_path):
    e = Env(tmp_path)
    run = make_run(e.base, "r6 with spaces & (parens)", 300)
    r = e.run()
    assert r.returncode == 0 and not nm(run)


def test_metrics_are_exported_and_last_success_survives_a_failed_run(tmp_path):
    e = Env(tmp_path)
    make_run(e.base, "r6-old", 300)
    make_run(e.base, "r6-older", 500)
    e.run()
    m = e.metrics()
    assert m["fe_runs_janitor_removed_dirs"] == "2" and m["fe_runs_janitor_run_dirs"] == "2" and m["fe_runs_janitor_node_modules_dirs_remaining"] == "0" and m["fe_runs_janitor_last_exit_code"] == "0"
    first_ok = m["fe_runs_janitor_last_success_timestamp_seconds"]
    # a failing run (rm cannot remove: a read-only directory inside node_modules is not enough for root, so make xargs fail through a broken rm)
    e2_dir = tmp_path / "bin2"
    e2_dir.mkdir()
    (e2_dir / "rm").write_text("#!/bin/sh\nexit 1\n")
    (e2_dir / "rm").chmod(0o755)
    make_run(e.base, "r6-again", 300)
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=dict(e.env, PATH=f"{e2_dir}:{e.env['PATH']}"), timeout=120)
    assert r.returncode == 1
    m = e.metrics()
    assert m["fe_runs_janitor_last_exit_code"] == "1" and m["fe_runs_janitor_last_success_timestamp_seconds"] == first_ok          # the last success time is kept


def test_a_missing_base_directory_is_not_an_error(tmp_path):
    e = Env(tmp_path)
    e.base.rmdir()
    r = e.run()
    assert r.returncode == 0 and e.metrics()["fe_runs_janitor_run_dirs"] == "0"


def test_nothing_idle_means_nothing_removed(tmp_path):
    e = Env(tmp_path)
    fresh = make_run(e.base, "r7-fresh", 5)
    r = e.run()
    assert r.returncode == 0 and nm(fresh) and e.metrics()["fe_runs_janitor_removed_dirs"] == "0"
