"""Tests for the fleet_hypervisor_memory_reclaim role: rendered script (run against a stub /proc), units, inventory wiring."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

import fleet_observability_render as fleet

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE = "fleet_hypervisor_memory_reclaim"


def _render(template: str, **overrides: object) -> str:
    context = dict(fleet.role_defaults(ROLE))
    context.update(overrides)
    return fleet._render(ROLE, template, context)


def _run(tmp_path: Path, avail_kb: int, **overrides: object) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    textfile = tmp_path / "textfile"
    textfile.mkdir()
    overrides.setdefault("fleet_hypervisor_memory_reclaim_textfile_dir", str(textfile))
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "meminfo").write_text(f"MemTotal: 1000000 kB\nMemFree: 100000 kB\nMemAvailable: {avail_kb} kB\n", encoding="utf-8")
    drop = proc / "drop_caches"
    drop.write_text("", encoding="utf-8")
    script = _render("fleet-hypervisor-memory-reclaim.sh.j2", **overrides)
    script = script.replace("/proc/meminfo", str(proc / "meminfo")).replace("/proc/sys/vm/drop_caches", str(drop)).replace("sleep 3", "true")
    path = tmp_path / "reclaim.sh"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(["bash", str(path)], capture_output=True, text=True, check=False)
    return result, textfile, drop


def test_the_shrinkers_run_only_under_the_threshold(tmp_path: Path) -> None:
    result, textfile, drop = _run(tmp_path, avail_kb=50_000)  # 5% < 10%
    assert result.returncode == 0, result.stderr
    assert drop.read_text(encoding="utf-8").strip() == "2"
    metrics = (textfile / "fleet_hypervisor_memory_reclaim.prom").read_text(encoding="utf-8")
    assert "fleet_hypervisor_memory_reclaim_last_ran 1" in metrics

    quiet = tmp_path / "quiet"
    quiet.mkdir()
    result, textfile, drop = _run(quiet, avail_kb=400_000)  # 40%
    assert result.returncode == 0, result.stderr
    assert drop.read_text(encoding="utf-8") == ""
    assert "fleet_hypervisor_memory_reclaim_last_ran 0" in (textfile / "fleet_hypervisor_memory_reclaim.prom").read_text(encoding="utf-8")


def test_the_script_only_drops_slab_never_page_cache_or_guests() -> None:
    script = _render("fleet-hypervisor-memory-reclaim.sh.j2")
    assert "echo 2 > /proc/sys/vm/drop_caches" in script
    assert "echo 1 >" not in script and "echo 3 >" not in script and "qm " not in script and "swapoff" not in script


def test_units_and_inventory_wiring() -> None:
    service = _render("fleet-hypervisor-memory-reclaim.service.j2")
    timer = _render("fleet-hypervisor-memory-reclaim.timer.j2")
    assert "Type=oneshot" in service and "OnUnitActiveSec=5min" in timer
    groups, hostvars, _ = fleet.inventory_model()
    assert groups["fleet_hypervisor_memory_reclaim_hosts"] == {"operator-bastion"}
    assert hostvars["operator-bastion"]["fleet_hypervisor_memory_reclaim_textfile_dir"] == "/var/lib/prometheus/node-exporter/textfile"
    playbook = yaml.safe_load((REPO_ROOT / "playbooks" / "fleet-observability.yml").read_text(encoding="utf-8"))
    play = next(p for p in playbook if p.get("hosts") == "fleet_hypervisor_memory_reclaim_hosts")
    assert play["serial"] == 1 and play["tags"] == ["memory-reclaim"]
