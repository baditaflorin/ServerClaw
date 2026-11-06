"""config/0own/ct-names/: the three host-prep scripts for the ct-names data disk on the 0own runtime VM.

The scripts run for real against fake `qm` / `zfs` shims (a call log tells what a run would have changed), so these tests pin the
guards that keep a run harmless: plan-only by default, one disk per slot, a free-space floor, only our own disk is ever detached,
and the IO probe refuses to start (and writes nothing) when the IO pressure is already high.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parent.parent / "config" / "0own" / "ct-names"
ATTACH = DIR / "attach-data-disk.sh"
PREPARE = DIR / "prepare-data-disk.sh"
PROBE = DIR / "io-probe.sh"

QM = """#!/bin/bash
echo "qm $*" >> "$SHIM_LOG"
case "$1 $2" in
  "status "*) echo "status: ${VM_STATUS:-running}" ;;
  "config "*) printf '%s\\n' "${VM_CONFIG:-scsi0: local-zfs:vm-660-disk-0,size=160G}"; cat "$SHIM_LOG.state" 2>/dev/null ;;
  "set "*) case "$3" in --delete) ;; *) echo "${3#--}: $4" >> "$SHIM_LOG.state" ;; esac ;;
esac
exit 0
"""
ZFS = """#!/bin/bash
echo "zfs $*" >> "$SHIM_LOG"
if [ "$1" = "list" ] && [ "$2" = "-Hp" ]; then echo "${POOL_AVAIL_BYTES:-3178000000000}"; exit 0; fi
if [ "$1" = "list" ] && [ "$2" = "-H" ]; then
  for last; do :; done
  case " ${EXISTING_VOLS:-vm-660-disk-0} " in *"/${last##*/} "*) echo "$last"; exit 0 ;; esac
  case "${EXISTING_VOLS:-vm-660-disk-0}" in *"${last##*/}"*) echo "$last"; exit 0 ;; esac
  exit 1
fi
exit 0
"""


@pytest.fixture
def env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("qm", QM), ("zfs", ZFS)):
        p = bindir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.log"
    log.write_text("")
    e = dict(os.environ)
    e.update({"PATH": f"{bindir}:{e['PATH']}", "SHIM_LOG": str(log), "BACKUP_DIR": str(tmp_path / "backups"),
              "PSI_FILE": str(tmp_path / "psi")})
    (tmp_path / "psi").write_text("some avg10=1.00 avg60=1.00 avg300=1.00 total=1\nfull avg10=1.00 avg60=1.00 avg300=1.00 total=1\n")
    return e, log


def run(script, env, *args, check_rc=None):
    r = subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True, timeout=60)
    if check_rc is not None:
        assert r.returncode == check_rc, (r.returncode, r.stdout, r.stderr)
    return r


def writes(log: Path) -> list[str]:
    return [l for l in log.read_text().splitlines() if l.startswith("zfs create") or l.startswith("qm set")]


def test_scripts_are_executable_and_parse():
    for s in (ATTACH, PREPARE, PROBE, DIR / "verify-data-dir.sh"):
        assert os.access(s, os.X_OK), s
        subprocess.run(["bash", "-n", str(s)], check=True)


def test_attach_is_plan_only_by_default(env):
    e, log = env
    r = run(ATTACH, e, check_rc=0)
    assert "Plan only" in r.stdout
    assert writes(log) == []


def test_attach_apply_creates_thin_capped_disk_on_next_free_volume(env):
    e, log = env
    run(ATTACH, e, "--apply", check_rc=0)
    w = writes(log)
    assert len(w) == 2
    assert w[0] == "zfs create -s -V 1024G -o volblocksize=64k rpool/data/vm-660-disk-1"  # disk-0 exists in the shim
    s = w[1]
    assert s.startswith("qm set 660 --scsi1 local-zfs:vm-660-disk-1,")
    for needle in ("backup=0", "serial=CTNAMES0", "mbps_wr=15", "mbps_rd=30", "iops_wr=100", "iops_rd=200", "discard=on", "iothread=1"):
        assert needle in s, needle
    assert list((Path(e["BACKUP_DIR"])).glob("qm-660.conf.pre-attach-*")), "the VM config must be saved first"


def test_attach_refuses_a_used_slot(env):
    e, log = env
    e["VM_CONFIG"] = "scsi0: local-zfs:vm-660-disk-0,size=160G\nscsi1: local-zfs:vm-660-disk-2,size=1T"
    r = run(ATTACH, e, "--apply", check_rc=1)
    assert "already in use" in r.stderr and writes(log) == []


def test_attach_refuses_low_pool_space(env):
    e, log = env
    e["POOL_AVAIL_BYTES"] = str(1000 * 1024**3)
    r = run(ATTACH, e, "--apply", check_rc=1)
    assert "too little free space" in r.stderr and writes(log) == []


def test_attach_refuses_a_stopped_vm(env):
    e, log = env
    e["VM_STATUS"] = "stopped"
    run(ATTACH, e, "--apply", check_rc=1)
    assert writes(log) == []


def test_undo_only_touches_our_own_disk(env):
    e, log = env
    e["VM_CONFIG"] = "scsi1: local-zfs:vm-660-disk-3,size=50G"
    r = run(ATTACH, e, "--undo", check_rc=1)
    assert "not the ct-names disk" in r.stderr and writes(log) == []
    e["VM_CONFIG"] = "scsi1: local-zfs:vm-660-disk-1,serial=CTNAMES0,backup=0"
    r = run(ATTACH, e, "--undo", check_rc=0)
    assert "qm set 660 --delete scsi1" in log.read_text()
    assert "zfs destroy" in r.stdout and "zfs destroy" not in log.read_text()  # printed for a person, never run


def test_prepare_refuses_without_the_disk(env):
    e, _ = env
    e["SERIAL"] = "NOSUCHDISK0"
    r = run(PREPARE, e, "--apply", check_rc=1)
    assert "not found" in r.stderr


def test_probe_refuses_to_start_under_io_pressure_and_writes_nothing(env, tmp_path):
    e, _ = env
    (tmp_path / "psi").write_text("some avg10=60.00 avg60=1 avg300=1 total=1\nfull avg10=47.02 avg60=1 avg300=1 total=1\n")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    r = run(PROBE, e, "--dir", str(scratch), check_rc=3)
    assert "ABORT" in r.stderr
    assert list(scratch.iterdir()) == []


def test_probe_rejects_a_large_test(env, tmp_path):
    e, _ = env
    run(PROBE, e, "--dir", str(tmp_path), "--mb", "4096", check_rc=2)


@pytest.mark.skipif(sys.platform != "linux", reason="the probe uses GNU dd (fdatasync) and date +%N")
def test_probe_runs_small_and_cleans_up(env, tmp_path):
    e, _ = env
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    r = run(PROBE, e, "--dir", str(scratch), "--mb", "4", check_rc=0)
    assert "MB/s" in r.stdout and "synced writes" in r.stdout
    assert list(scratch.iterdir()) == []


# ---- install-log-shipper.sh -------------------------------------------------------------------------------------------------------

SHIPPER = DIR / "install-log-shipper.sh"
CREDS = '{"user":"ingest-user","password":"s3cr3t-value-for-test"}'

DOCKER = """#!/bin/bash
echo "docker $*" >> "$SHIM_LOG"
case "$1" in
  run) [ "${VALIDATE_FAILS:-0}" = 1 ] && exit 1; exit 0 ;;
  inspect) case "$*" in *State.Running*) echo "${PREV_RUNNING:-false}" ;; *State.Status*) echo "${NEW_STATUS:-running}" ;; esac ;;
  compose) [ "${COMPOSE_FAILS:-0}" = 1 ] && exit 1; exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def shipper_env(env, tmp_path):
    e, log = env
    d = Path(e["PATH"].split(":")[0]) / "docker"
    d.write_text(DOCKER)
    d.chmod(d.stat().st_mode | stat.S_IEXEC)
    e["INSTALL_DIR"] = str(tmp_path / "vector")
    return e, log


def run_shipper(e, *args, stdin=CREDS):
    return subprocess.run(["bash", str(SHIPPER), *args], env=e, input=stdin, capture_output=True, text=True, timeout=60)


def test_shipper_plan_writes_nothing_and_never_prints_the_password(shipper_env, tmp_path):
    e, log = shipper_env
    r = run_shipper(e)
    assert r.returncode == 0 and "Plan only" in r.stdout
    assert "s3cr3t" not in r.stdout + r.stderr
    assert not Path(e["INSTALL_DIR"]).exists()
    assert "docker" not in log.read_text()


def test_shipper_apply_ships_only_the_ct_names_container_with_a_root_only_config(shipper_env):
    e, log = shipper_env
    r = run_shipper(e, "--apply")
    assert r.returncode == 0, r.stderr
    assert "s3cr3t" not in r.stdout + r.stderr + log.read_text()
    conf = Path(e["INSTALL_DIR"]) / "vector.toml"
    text = conf.read_text()
    assert oct(conf.stat().st_mode & 0o777) == "0o600"
    assert 'include_containers = ["go-ct-names"]' in text
    assert 'exclude_containers' not in text and '.fleet = "0own"' in text and '.host = "0own-runtime"' in text
    assert 'auth.user = "ingest-user"' in text
    assert "docker compose up -d --force-recreate" in log.read_text()


def test_shipper_rejects_bad_credentials_before_touching_anything(shipper_env):
    e, log = shipper_env
    for bad in ("", "not json", '{"user":"a"}', '{"user":"","password":"x"}', '{"user":1,"password":"x"}'):
        r = run_shipper(e, "--apply", stdin=bad)
        assert r.returncode == 1, bad
    assert not Path(e["INSTALL_DIR"]).exists() and "docker" not in log.read_text()


def test_shipper_validation_failure_leaves_the_current_config(shipper_env):
    e, _ = shipper_env
    assert run_shipper(e, "--apply").returncode == 0
    conf = Path(e["INSTALL_DIR"]) / "vector.toml"
    before = conf.read_text()
    e["VALIDATE_FAILS"] = "1"
    r = run_shipper(e, "--apply", stdin='{"user":"other","password":"another-value"}')
    assert r.returncode == 1 and "validation failed" in r.stderr
    assert conf.read_text() == before
    assert not list(Path(e["INSTALL_DIR"]).glob("*.next"))


def test_shipper_restores_the_previous_config_when_the_new_agent_does_not_start(shipper_env):
    e, _ = shipper_env
    assert run_shipper(e, "--apply").returncode == 0
    conf = Path(e["INSTALL_DIR"]) / "vector.toml"
    before = conf.read_text()
    e["NEW_STATUS"] = "restarting"
    r = run_shipper(e, "--apply", stdin='{"user":"other","password":"another-value"}')
    assert r.returncode == 1 and "restoring" in r.stderr
    assert conf.read_text() == before


# ---- verify-data-dir.sh -----------------------------------------------------------------------------------------------------------

VERIFY = DIR / "verify-data-dir.sh"

MOUNTPOINT = """#!/bin/bash
[ "${MOUNTED:-1}" = 1 ]
"""
FINDMNT = """#!/bin/bash
case "$*" in
  *"-o SOURCE /"*|*"SOURCE /") echo "/dev/sda1" ;;
  *SOURCE*) echo "${DATA_SRC:-/dev/sdb}" ;;
  *FSTYPE*) echo ext4 ;;
esac
exit 0
"""


@pytest.fixture
def venv(tmp_path):
    bindir = tmp_path / "vbin"
    bindir.mkdir()
    for name, body in (("mountpoint", MOUNTPOINT), ("findmnt", FINDMNT)):
        p = bindir / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    mnt = tmp_path / "mnt"
    data = mnt / "data"
    data.mkdir(parents=True)
    data.chmod(0o750)
    fstab = tmp_path / "fstab"
    fstab.write_text(f"UUID=abc {mnt} ext4 defaults,noatime,nofail 0 2\n")
    e = dict(os.environ)
    e.update({"PATH": f"{bindir}:{e['PATH']}", "MOUNT": str(mnt), "DATA": str(data), "DATA_UID": str(os.getuid()), "DATA_GID": str(os.getgid()),
              "MIN_FREE_GB": "1", "FSTAB": str(fstab), "COMPOSE_ENV_GLOB": str(tmp_path / "none" / "*.env")})
    return e, data


@pytest.mark.skipif(sys.platform != "linux", reason="the check uses GNU stat, df and findmnt semantics")
def test_verify_passes_on_a_ready_disk(venv):
    e, _ = venv
    r = run(VERIFY, e, check_rc=0)
    assert "All checks passed" in r.stdout


@pytest.mark.skipif(sys.platform != "linux", reason="GNU stat")
def test_verify_refuses_when_the_disk_is_not_mounted(venv):
    e, _ = venv
    e["MOUNTED"] = "0"
    r = run(VERIFY, e, check_rc=1)
    assert "not a mount point" in r.stderr


@pytest.mark.skipif(sys.platform != "linux", reason="GNU stat")
def test_verify_refuses_data_on_the_root_filesystem(venv):
    e, _ = venv
    e["DATA_SRC"] = "/dev/sda1"
    r = run(VERIFY, e, check_rc=1)
    assert "root filesystem" in r.stderr


@pytest.mark.skipif(sys.platform != "linux", reason="GNU stat")
def test_verify_refuses_wrong_owner_and_low_space_and_missing_nofail(venv, tmp_path):
    e, _ = venv
    e["DATA_UID"] = str(os.getuid() + 12345)
    e["MIN_FREE_GB"] = "999999999"
    (tmp_path / "fstab").write_text("UUID=abc /srv/other ext4 defaults 0 2\n")
    r = run(VERIFY, e, check_rc=1)
    assert "owned" in r.stderr and "GiB free" in r.stderr and "nofail" in r.stderr


@pytest.mark.skipif(sys.platform != "linux", reason="GNU stat")
def test_verify_checks_the_deploy_env_when_it_exists(venv, tmp_path):
    e, data = venv
    d = tmp_path / "svc"
    d.mkdir()
    (d / ".env").write_text("CT_DATA_HOST_DIR=./data\n")
    e["COMPOSE_ENV_GLOB"] = str(d / ".env")
    r = run(VERIFY, e, check_rc=1)
    assert "CT_DATA_HOST_DIR" in r.stderr
    (d / ".env").write_text(f"CT_DATA_HOST_DIR={data}\n")
    run(VERIFY, e, check_rc=0)


@pytest.mark.skipif(sys.platform != "linux", reason="GNU stat")
def test_verify_leaves_nothing_behind(venv):
    e, data = venv
    run(VERIFY, e, check_rc=0)
    assert list(data.iterdir()) == []
