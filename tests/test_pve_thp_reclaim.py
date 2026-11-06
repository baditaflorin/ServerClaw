"""pve-thp-reclaim (config/0database/pve-thp-reclaim/), run against fake /proc files and a fake reclaim command.

The script gives back the memory that ballooned VMs leave on the kernel's deferred-split list (invisible to MemAvailable). Here its
paths point into tmp_path and the reclaim command is a stub that rewrites the fake /proc/vmstat, so the threshold, the metrics, the
back-off after an action that frees little, the persistent counters and the lock are exercised without touching a real kernel.
"""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIT_DIR = REPO_ROOT / "config" / "0database" / "pve-thp-reclaim"
SCRIPT = UNIT_DIR / "pve-thp-reclaim"
MB = 1024 * 1024

# Stands in for `echo 2 > /proc/sys/vm/drop_caches`: counts the call and, when FAKE_AFTER_MB is set, shrinks the fake gap to it.
RECLAIM_STUB = r"""#!/bin/bash
echo run >> "$FAKE_DIR/calls"
if [ -n "${FAKE_AFTER_MB:-}" ]; then
  printf 'nr_active_anon %d\nnr_anon_pages 1000000\n' $((1000000 + FAKE_AFTER_MB * 256)) > "$FAKE_DIR/vmstat"
fi
exit 0
"""


def _write_vmstat(path: Path, gap_mb: int) -> None:
    # gap in MB = (nr_active_anon - nr_anon_pages) * 4 KiB / 1 MiB, so one MB is 256 pages.
    path.write_text(f"nr_free_pages 123\nnr_active_anon {1_000_000 + gap_mb * 256}\nnr_inactive_anon 5\nnr_anon_pages 1000000\n", encoding="utf-8")


class Host:
    def __init__(self, tmp_path: Path, gap_mb: int) -> None:
        self.dir = tmp_path
        self.vmstat = tmp_path / "vmstat"
        self.prom = tmp_path / "pve_thp_reclaim.prom"
        self.calls = tmp_path / "calls"
        self.stub = tmp_path / "reclaim.sh"
        self.stub.write_text(RECLAIM_STUB, encoding="utf-8")
        self.stub.chmod(0o755)
        self.calls.touch()
        _write_vmstat(self.vmstat, gap_mb)

    def run(self, now: int, after_mb: int | None = None, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PVE_THP_RECLAIM_VMSTAT": str(self.vmstat),
            "PVE_THP_RECLAIM_PROM": str(self.prom),
            "PVE_THP_RECLAIM_STATE_DIR": str(self.dir / "state"),
            "PVE_THP_RECLAIM_LOCK": str(self.dir / "lock"),
            "PVE_THP_RECLAIM_CMD": str(self.stub),
            "PVE_THP_RECLAIM_NOW": str(now),
            "FAKE_DIR": str(self.dir),
            **extra,
        }
        env.pop("FAKE_AFTER_MB", None)
        if shutil.which("flock") is None:  # a dev machine without util-linux: the lock test is skipped there, the rest needs a no-op flock
            stub_dir = self.dir / "bin"
            stub_dir.mkdir(exist_ok=True)
            (stub_dir / "flock").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            (stub_dir / "flock").chmod(0o755)
            env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
        if after_mb is not None:
            env["FAKE_AFTER_MB"] = str(after_mb)
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60, check=False)

    def metrics(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for line in self.prom.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                name, value = line.split()
                out[name] = int(value)
        return out

    def reclaims(self) -> int:
        return len(self.calls.read_text(encoding="utf-8").splitlines())


def test_a_small_gap_is_only_reported(tmp_path: Path) -> None:
    host = Host(tmp_path, gap_mb=300)
    result = host.run(now=1000)
    assert result.returncode == 0, result.stderr
    assert host.reclaims() == 0
    m = host.metrics()
    assert m["pve_thp_deferred_split_bytes"] == 300 * MB
    assert m["pve_thp_deferred_split_before_bytes"] == 300 * MB
    assert m["pve_thp_reclaim_threshold_bytes"] == 1024 * MB
    assert m["pve_thp_reclaim_runs_total"] == 1
    assert m["pve_thp_reclaim_actions_total"] == 0
    assert m["pve_thp_reclaim_last_run_timestamp_seconds"] == 1000
    assert m["pve_thp_reclaim_last_action_timestamp_seconds"] == 0
    assert m["pve_thp_reclaim_backoff_active"] == 0


def test_a_large_gap_is_reclaimed_and_counted(tmp_path: Path) -> None:
    host = Host(tmp_path, gap_mb=8169)  # what pve01 had on 2026-10-17 00:46Z
    result = host.run(now=2000, after_mb=34)
    assert result.returncode == 0, result.stderr
    assert host.reclaims() == 1
    assert "8169 MB -> 34 MB" in result.stdout
    m = host.metrics()
    assert m["pve_thp_deferred_split_before_bytes"] == 8169 * MB
    assert m["pve_thp_deferred_split_bytes"] == 34 * MB
    assert m["pve_thp_reclaim_reclaimed_bytes_total"] == (8169 - 34) * MB
    assert m["pve_thp_reclaim_actions_total"] == 1
    assert m["pve_thp_reclaim_ineffective_total"] == 0
    assert m["pve_thp_reclaim_last_action_timestamp_seconds"] == 2000
    assert m["pve_thp_reclaim_backoff_active"] == 0


def test_counters_survive_between_runs(tmp_path: Path) -> None:
    host = Host(tmp_path, gap_mb=2000)
    assert host.run(now=3000, after_mb=40).returncode == 0
    _write_vmstat(host.vmstat, 1500)
    assert host.run(now=3060, after_mb=20).returncode == 0
    m = host.metrics()
    assert host.reclaims() == 2
    assert m["pve_thp_reclaim_runs_total"] == 2
    assert m["pve_thp_reclaim_actions_total"] == 2
    assert m["pve_thp_reclaim_reclaimed_bytes_total"] == (1960 + 1480) * MB


def test_an_action_that_frees_little_backs_off_then_tries_again(tmp_path: Path) -> None:
    host = Host(tmp_path, gap_mb=2000)
    # The gap is not deferred-split memory: the reclaim changes nothing.
    assert host.run(now=1000).returncode == 0
    assert host.reclaims() == 1
    m = host.metrics()
    assert m["pve_thp_reclaim_ineffective_total"] == 1
    assert m["pve_thp_reclaim_backoff_active"] == 1
    # One minute later it must not act again.
    second = host.run(now=1060)
    assert second.returncode == 0
    assert host.reclaims() == 1
    assert "backing off" in second.stdout
    assert host.metrics()["pve_thp_reclaim_runs_total"] == 2
    assert host.metrics()["pve_thp_reclaim_backoff_active"] == 1
    # After the back-off (900 s) it tries again.
    assert host.run(now=1000 + 901).returncode == 0
    assert host.reclaims() == 2
    assert host.metrics()["pve_thp_reclaim_ineffective_total"] == 2


def test_the_threshold_comes_from_the_environment(tmp_path: Path) -> None:
    host = Host(tmp_path, gap_mb=600)
    assert host.run(now=1000, PVE_THP_RECLAIM_THRESHOLD_MB="512", after_mb=10).returncode == 0
    assert host.reclaims() == 1
    assert host.metrics()["pve_thp_reclaim_threshold_bytes"] == 512 * MB


def test_an_unreadable_vmstat_fails_and_writes_nothing(tmp_path: Path) -> None:
    host = Host(tmp_path, gap_mb=0)
    host.vmstat.write_text("nr_free_pages 1\n", encoding="utf-8")  # no nr_active_anon / nr_anon_pages
    result = host.run(now=1000)
    assert result.returncode == 1
    assert "cannot read" in result.stderr
    assert not host.prom.exists()
    assert host.reclaims() == 0


@pytest.mark.skipif(shutil.which("flock") is None, reason="needs util-linux flock")
def test_a_run_in_progress_makes_the_next_one_exit_quietly(tmp_path: Path) -> None:
    host = Host(tmp_path, gap_mb=5000)
    with open(tmp_path / "lock", "w", encoding="utf-8") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = host.run(now=1000, after_mb=10)
    assert result.returncode == 0
    assert host.reclaims() == 0
    assert not host.prom.exists()


def _unit(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            values.setdefault(key, value)
    return values


def test_the_units_run_the_script_every_minute() -> None:
    service = _unit(UNIT_DIR / "pve-thp-reclaim.service")
    timer = _unit(UNIT_DIR / "pve-thp-reclaim.timer")
    assert service["Type"] == "oneshot"
    assert service["ExecStart"] == "/usr/local/sbin/pve-thp-reclaim"
    assert timer["OnUnitActiveSec"] == "1min"
    assert timer["WantedBy"] == "timers.target"
    assert os.access(SCRIPT, os.X_OK)
