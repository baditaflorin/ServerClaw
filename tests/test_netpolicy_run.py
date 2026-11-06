"""scripts/netpolicy-run: what the CT108 timer runs. Real script, a local git repository as origin, a fake ssh.

What matters: it compares against the policy at origin/main (not a stale copy), an unreadable hypervisor or a failed fetch is exit 3 and
never "in sync", drift is exit 2 (an alert, not a failed unit), and the metrics land in the textfile directory.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import netpolicy as np  # noqa: E402
from test_netpolicy import VM_FW, snapshot  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="needs git and bash")
RUN = ROOT / "scripts" / "netpolicy-run"


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


@pytest.fixture()
def world(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    policy = np.build_policy(snapshot())
    policy["collect"] = {"ssh": "hv-fake"}
    (origin / "config" / "network-policy").mkdir(parents=True)
    np.write_policy(policy, origin / "config" / "network-policy" / "t.yaml")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "policy")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "ssh").write_text('#!/bin/bash\ncat > /dev/null\ncase "$*" in *hv-down*) FAKE_SSH=down ;; esac\n[ "${FAKE_SSH:-ok}" = down ] && { echo "Connection timed out" >&2; exit 255; }\ncat "$FAKE_SNAPSHOT"\n')
    (fake / "ssh").chmod(0o755)
    # Exec the exact interpreter: symlinking a venv's launcher from another
    # directory can lose its pyvenv.cfg and therefore its PyYAML installation.
    (fake / "python3").write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    (fake / "python3").chmod(0o755)
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps(snapshot()))
    env = {
        "PATH": f"{fake}:{os.environ['PATH']}", "HOME": os.environ.get("HOME", str(tmp_path)), "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1", "NETPOLICY_LIB": str(ROOT / "scripts"),
        "NETPOLICY_STATE": str(tmp_path / "state"), "NETPOLICY_TEXTFILE_DIR": str(tmp_path / "prom"),
        "NETPOLICY_REPO_URL": str(origin), "FAKE_SNAPSHOT": str(snap),
    }
    return {"env": env, "origin": origin, "snap": snap, "prom": tmp_path / "prom" / "netpolicy_t.prom"}


def run(world, **over):
    return subprocess.run(["bash", str(RUN)], capture_output=True, text=True, env={**world["env"], **over})


def test_in_sync_is_exit_0_and_writes_the_metrics(world):
    r = run(world)
    assert r.returncode == 0, r.stdout + r.stderr
    text = world["prom"].read_text()
    assert 'netpolicy_vm_in_sync{hypervisor="t",vm="191"} 1' in text and 'netpolicy_could_not_look{hypervisor="t"} 0' in text
    assert "policy at " in r.stdout


def test_drift_is_exit_2_and_an_alertable_metric(world):
    drifted = snapshot(vm_fw=VM_FW + "IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 8080\n")
    world["snap"].write_text(json.dumps(drifted))
    r = run(world)
    assert r.returncode == 2, r.stdout + r.stderr
    assert 'netpolicy_vm_in_sync{hypervisor="t",vm="191"} 0' in world["prom"].read_text()
    assert "10.10.10.77 tcp/8080" in r.stdout


def test_an_unreadable_hypervisor_is_exit_3_and_never_in_sync(world):
    r = run(world, FAKE_SSH="down")
    assert r.returncode == 3
    text = world["prom"].read_text()
    assert 'netpolicy_could_not_look{hypervisor="t"} 1' in text and "netpolicy_vm_in_sync" not in text


def test_the_policy_is_read_at_origin_main_on_every_run_not_from_a_stale_copy(world):
    assert run(world).returncode == 0
    policy = np.load_policy(world["origin"] / "config" / "network-policy" / "t.yaml")
    policy["vms"]["191"]["groups"].append({"from": ["10.10.10.200"], "proto": "tcp", "ports": ["8443"], "layers": ["pve"], "purpose": "new"})
    np.write_policy(policy, world["origin"] / "config" / "network-policy" / "t.yaml")
    git(world["origin"], "commit", "-q", "-am", "add a rule")
    r = run(world)
    assert r.returncode == 2 and "10.10.10.200 tcp/8443" in r.stdout, "the merged change is what the live state is judged against"


def test_missing_configuration_is_exit_3_with_a_clear_message_and_a_failed_clone_too(world, tmp_path):
    r = run(world, NETPOLICY_REPO_URL="")
    assert r.returncode == 3 and "NETPOLICY_REPO_URL is not set" in r.stderr
    assert "clone failed" not in r.stderr and not (Path(world["env"]["NETPOLICY_STATE"]) / "repo").exists(), "it stops before touching git"
    r = run(world, NETPOLICY_REPO_URL=str(tmp_path / "does-not-exist"))
    assert r.returncode == 3 and "clone failed" in r.stderr and not world["prom"].exists()


def test_a_fetch_that_fails_after_a_good_run_is_exit_3_and_does_not_judge_against_the_old_copy(world):
    assert run(world).returncode == 0
    first = world["prom"].read_text()
    shutil.rmtree(world["origin"])  # the origin is gone: the next fetch fails
    r = run(world)
    assert r.returncode == 3 and "fetch failed" in r.stderr
    assert world["prom"].read_text() == first, "no new metrics: the dead-man alert, not a made-up 'in sync'"


def test_a_repository_without_a_policy_directory_is_exit_3(world):
    shutil.rmtree(world["origin"] / "config")
    git(world["origin"], "add", "-A")
    git(world["origin"], "commit", "-q", "-m", "remove")
    r = run(world)
    assert r.returncode == 3 and "no policy" in r.stderr


@pytest.mark.parametrize("down_names", [["a-down"], ["z-down"], ["a-down", "z-down"]])
def test_with_several_hypervisors_could_not_look_outranks_drift_whatever_the_order(world, down_names):
    policies = world["origin"] / "config" / "network-policy"
    for name in down_names:
        pol = np.load_policy(policies / "t.yaml")
        pol["host"], pol["collect"] = name, {"ssh": "hv-down"}
        np.write_policy(pol, policies / f"{name}.yaml")
    git(world["origin"], "add", "-A")
    git(world["origin"], "commit", "-q", "-m", "more hypervisors")
    world["snap"].write_text(json.dumps(snapshot(vm_fw=VM_FW + "IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 8080\n")))
    r = run(world)
    assert r.returncode == 3, "t drifts (2) and another cannot be read (3), whichever sorts first or last: the worst wins, not the last"
    prom = world["prom"].parent
    assert 'netpolicy_vm_in_sync{hypervisor="t",vm="191"} 0' in (prom / "netpolicy_t.prom").read_text()
    for name in down_names:
        assert f'netpolicy_could_not_look{{hypervisor="{name}"}} 1' in (prom / f"netpolicy_{name.replace('-', '_')}.prom").read_text()


def test_drift_alone_is_2_even_with_several_hypervisors_in_sync(world):
    policies = world["origin"] / "config" / "network-policy"
    for name in ("a-ok", "z-ok"):
        pol = np.load_policy(policies / "t.yaml")
        pol["host"] = name
        np.write_policy(pol, policies / f"{name}.yaml")
    git(world["origin"], "add", "-A")
    git(world["origin"], "commit", "-q", "-m", "more hypervisors")
    assert run(world).returncode == 0
    world["snap"].write_text(json.dumps(snapshot(vm_fw=VM_FW + "IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 8080\n")))
    assert run(world).returncode == 2, "all three drift (the fake ssh answers the same), never 0 because the last one was fine"


def test_a_policy_directory_without_a_policy_file_is_exit_3(world):
    for f in (world["origin"] / "config" / "network-policy").glob("*.yaml"):
        f.unlink()
    (world["origin"] / "config" / "network-policy" / "README.md").write_text("no policy here\n")
    git(world["origin"], "add", "-A")
    git(world["origin"], "commit", "-q", "-m", "only a readme")
    r = run(world)
    assert r.returncode == 3 and "no policy file" in r.stderr
