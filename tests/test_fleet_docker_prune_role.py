"""Tests for the fleet_docker_prune role: the rendered prune script, its units and the inventory wiring.

Nothing here contacts a host. The script is executed with bash against a stub `docker` and `df`, so the prune filters,
the metric file and the safety properties (only image/builder prune, never containers or volumes) are proven offline.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

import fleet_observability_render as fleet

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE = "fleet_docker_prune"


def _render(template: str, **overrides: object) -> str:
    context = dict(fleet.role_defaults(ROLE))
    context.update(overrides)
    return fleet._render(ROLE, template, context)


def _run_script(tmp_path: Path, **overrides: object) -> tuple[subprocess.CompletedProcess[str], Path, list[str]]:
    textfile = tmp_path / "textfile"
    textfile.mkdir()
    overrides.setdefault("fleet_docker_prune_textfile_dir", str(textfile))
    script = tmp_path / "prune.sh"
    script.write_text(_render("fleet-docker-prune.sh.j2", **overrides), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    counter = tmp_path / "df-count"
    (bin_dir / "docker").write_text(
        f"""#!/usr/bin/env bash
echo "$@" >> {log}
if [ "$1" = info ]; then echo {tmp_path}; fi
""",
        encoding="utf-8",
    )
    # First df call reports 100 used bytes, the second 40, so 60 bytes were reclaimed.
    (bin_dir / "df").write_text(
        f"""#!/usr/bin/env bash
n=$(cat {counter} 2>/dev/null || echo 0); echo $((n+1)) > {counter}
echo Used
if [ "$n" = 0 ]; then echo 100; else echo 40; fi
""",
        encoding="utf-8",
    )
    for path in (bin_dir / "docker", bin_dir / "df"):
        path.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env, check=False)
    return result, textfile, log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_script_prunes_only_unused_images_and_old_build_cache(tmp_path: Path) -> None:
    result, textfile, calls = _run_script(tmp_path)

    assert result.returncode == 0, result.stderr
    assert calls[1:] == ["image prune -af --filter until=168h", "builder prune -af --filter until=168h"]
    joined = " ".join(calls)
    for forbidden in ("container prune", "volume prune", "system prune", "network prune", " rm ", " rmi ", "--volumes"):
        assert forbidden not in joined


def test_script_writes_atomic_textfile_metrics(tmp_path: Path) -> None:
    result, textfile, _ = _run_script(tmp_path)

    assert result.returncode == 0, result.stderr
    prom = (textfile / "fleet_docker_prune.prom").read_text(encoding="utf-8")
    assert "fleet_docker_prune_reclaimed_bytes 60" in prom
    assert "fleet_docker_prune_last_success_timestamp_seconds " in prom
    assert [p.name for p in textfile.iterdir()] == ["fleet_docker_prune.prom"]  # no temp file left behind


def test_failed_prune_writes_no_success_metric(tmp_path: Path) -> None:
    textfile = tmp_path / "textfile"
    textfile.mkdir()
    script = tmp_path / "prune.sh"
    script.write_text(_render("fleet-docker-prune.sh.j2", fleet_docker_prune_textfile_dir=str(textfile)), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text("#!/usr/bin/env bash\n[ \"$1\" = info ] && echo /var/lib/docker; [ \"$1\" = image ] && exit 1; exit 0\n", encoding="utf-8")
    (bin_dir / "df").write_text("#!/usr/bin/env bash\necho Used; echo 1\n", encoding="utf-8")
    for path in bin_dir.iterdir():
        path.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env, check=False)

    assert result.returncode != 0
    assert list(textfile.iterdir()) == []  # a stale timestamp would hide the failure from the alert


def test_metrics_are_skipped_without_a_textfile_dir(tmp_path: Path) -> None:
    text = _render("fleet-docker-prune.sh.j2", fleet_docker_prune_textfile_dir="")
    assert "fleet_docker_prune_last_success" not in text and "mktemp" not in text


def test_units_run_the_script_daily_and_survive_missed_runs() -> None:
    service = _render("fleet-docker-prune.service.j2")
    timer = _render("fleet-docker-prune.timer.j2")
    assert "Type=oneshot" in service and "ExecStart=/usr/local/sbin/fleet-docker-prune" in service
    assert "OnCalendar=*-*-* 04:30:00" in timer and "Persistent=true" in timer and "RandomizedDelaySec=30m" in timer
    assert "WantedBy=timers.target" in timer


def test_inventory_applies_the_role_to_docker_build_only() -> None:
    groups, hostvars, _ = fleet.inventory_model()
    assert groups["fleet_docker_prune_hosts"] == {"0mcp_docker_build"}
    assert hostvars["0mcp_docker_build"]["fleet_docker_prune_textfile_dir"].startswith("/")
    artifacts = fleet.render_host("0mcp_docker_build")
    paths = {a.path for a in artifacts if a.role == ROLE}
    assert paths == {
        "/usr/local/sbin/fleet-docker-prune",
        "/etc/systemd/system/fleet-docker-prune.service",
        "/etc/systemd/system/fleet-docker-prune.timer",
    }


def test_disk_alert_rules_cover_low_space_fast_fill_and_stale_prune() -> None:
    rules = yaml.safe_load((REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-disk.yml").read_text(encoding="utf-8"))
    alerts = {rule["alert"]: rule for group in rules["groups"] for rule in group["rules"]}
    assert {"FleetRootFilesystemLow", "FleetRootFilesystemCritical", "FleetRootFilesystemFillingFast", "FleetDockerPruneStale"} <= set(alerts)
    assert alerts["FleetRootFilesystemCritical"]["labels"]["severity"] == "critical"
    assert alerts["FleetRootFilesystemLow"]["labels"]["severity"] == "warning"
    for name in ("FleetRootFilesystemLow", "FleetRootFilesystemCritical", "FleetRootFilesystemFillingFast"):
        assert 'mountpoint="/"' in alerts[name]["expr"]
        assert "tmpfs" in alerts[name]["expr"]  # virtual filesystems must not page
    for alert in alerts.values():
        assert alert["annotations"]["summary"] and alert["annotations"]["description"]


def test_pbs_datastore_capacity_alerts_and_exporter_override() -> None:
    rules = yaml.safe_load((REPO_ROOT / "config" / "prometheus" / "rules" / "fleet-disk.yml").read_text(encoding="utf-8"))
    alerts = {rule["alert"]: rule for group in rules["groups"] for rule in group["rules"] if group["name"] == "pbs_datastore_capacity"}
    assert set(alerts) == {"PBSDatastoreFilesystemHigh", "PBSDatastoreFilesystemCritical", "PBSDatastoreWillFillWithin5Days", "PBSDatastoreMetricMissing"}
    assert "> 0.80" in alerts["PBSDatastoreFilesystemHigh"]["expr"] and alerts["PBSDatastoreFilesystemHigh"]["labels"]["severity"] == "warning"
    assert "> 0.90" in alerts["PBSDatastoreFilesystemCritical"]["expr"] and alerts["PBSDatastoreFilesystemCritical"]["labels"]["severity"] == "critical"
    assert "predict_linear" in alerts["PBSDatastoreWillFillWithin5Days"]["expr"] and "5 * 86400" in alerts["PBSDatastoreWillFillWithin5Days"]["expr"]
    for alert in alerts.values():
        assert 'mountpoint="/mnt/pbs-datastore"' in alert["expr"]
    # The Debian default exporter flag hides /mnt, so the series only exists with the inventory override.
    _, hostvars, _ = fleet.inventory_model()
    flags = hostvars["0own_pbs"]["fleet_node_exporter_extra_args"]
    exclude = next(flag for flag in flags if flag.startswith("--collector.filesystem.mount-points-exclude="))
    assert "mnt" not in exclude
