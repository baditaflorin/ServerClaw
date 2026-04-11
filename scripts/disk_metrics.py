#!/usr/bin/env python3
"""Shared disk metrics query module.

Queries InfluxDB for disk usage across all platform VMs and compares
against capacity-model.json budgets.  This single module is the query
layer for three consumers:

  1. Agent tool registry  (get-disk-usage handler)
  2. Platform-context API  (GET /v1/platform/disk-usage)
  3. Windmill workflow      (disk-space-monitor.py)

VM enumeration comes from capacity-model.json — when a VM is added or
removed there, all consumers see the change automatically.
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

try:
    from datetime import UTC
except ImportError:  # Python < 3.11
    from datetime import timezone

    UTC = timezone.utc  # type: ignore[assignment]
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Reuse infrastructure from capacity_report — SSH tunnel, InfluxDB queries,
# inventory loading, and capacity model parsing.
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from controller_automation_toolkit import REPO_ROOT
from platform.repo import TOPOLOGY_HOST


CAPACITY_MODEL_PATH = REPO_ROOT / "config" / "capacity-model.json"
INVENTORY_PATH = REPO_ROOT / "inventory" / "hosts.yml"
SSH_TIMEOUT_SECONDS = 10


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MountStatus:
    path: str
    total_gb: float | None = None
    used_gb: float | None = None
    available_gb: float | None = None
    used_percent: float | None = None
    over_budget: bool = False


@dataclass(frozen=True)
class VMDiskStatus:
    name: str
    vmid: int
    status: str
    mounts: tuple[MountStatus, ...]
    budget_disk_gb: float
    allocated_disk_gb: float
    total_used_gb: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["mounts"] = [asdict(m) for m in self.mounts]
        return d


@dataclass(frozen=True)
class DiskReport:
    timestamp: str
    source: str  # "ssh+influx" | "unavailable"
    vms: tuple[VMDiskStatus, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "vms": [vm.to_dict() for vm in self.vms],
        }


# ---------------------------------------------------------------------------
# Helpers extracted from / mirroring capacity_report.py
# ---------------------------------------------------------------------------


def _normalize_rows(raw_csv: str) -> list[dict[str, str]]:
    lines = [line for line in raw_csv.splitlines() if line and not line.startswith("#")]
    if not lines:
        return []
    reader = csv.DictReader(lines)
    return [row for row in reader if row]


def _bootstrap_key_path() -> Path | None:
    candidate = REPO_ROOT / ".local" / "ssh" / "hetzner_llm_agents_ed25519"
    if candidate.exists():
        return candidate
    secrets_path = REPO_ROOT / "config" / "controller-local-secrets.json"
    if not secrets_path.exists():
        return None
    secrets = json.loads(secrets_path.read_text())
    secret = secrets.get("secrets", {}).get("bootstrap_ssh_private_key")
    if isinstance(secret, dict):
        path = secret.get("path")
        if isinstance(path, str) and path.strip():
            resolved = Path(path)
            if resolved.exists():
                return resolved
    return None


def _load_inventory_hosts(path: Path | None = None) -> dict[str, str]:
    path = path or INVENTORY_PATH
    import yaml

    inventory = yaml.safe_load(path.read_text()) or {}
    children = (inventory.get("all") or {}).get("children", {})
    hosts: dict[str, str] = {}
    for group_name in ("proxmox_hosts", "lv3_guests"):
        group = children.get(group_name) or {}
        group_hosts = group.get("hosts") or {}
        for name, payload in group_hosts.items():
            payload = payload or {}
            if not isinstance(payload, dict):
                payload = {}
            if "ansible_host" in payload:
                hosts[name] = payload["ansible_host"]
    return hosts


def _ssh_monitoring_command() -> list[str] | None:
    key_path = _bootstrap_key_path()
    inventory_hosts = _load_inventory_hosts()
    jump_host = inventory_hosts.get(TOPOLOGY_HOST)
    monitoring_host = inventory_hosts.get("monitoring")
    if not key_path or not jump_host or not monitoring_host:
        return None
    proxy = (
        f"ssh -q -i {shlex.quote(str(key_path))} "
        "-o IdentitiesOnly=yes -o BatchMode=yes "
        f"-o ConnectTimeout={SSH_TIMEOUT_SECONDS} "
        "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        f"ops@{jump_host} -W %h:%p"
    )
    return [
        "ssh",
        "-q",
        "-i",
        str(key_path),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={SSH_TIMEOUT_SECONDS}",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        f"ProxyCommand={proxy}",
        f"ops@{monitoring_host}",
    ]


def _influx_query(command: list[str], flux: str) -> list[dict[str, str]]:
    """Run a Flux query via SSH and return all result rows."""
    remote_command = (
        "sudo influx query --raw --host http://127.0.0.1:8086 --org lv3 "
        '--token "$(sudo cat /etc/lv3/monitoring/influxdb-operator.token)" ' + shlex.quote(flux)
    )
    result = subprocess.run(
        [*command, remote_command],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return _normalize_rows(result.stdout)


def _build_host_filters(hosts: list[str]) -> str:
    return " or ".join(f'r.host == "{host}"' for host in hosts)


# ---------------------------------------------------------------------------
# Capacity model loading (lightweight — only the fields we need)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _GuestEntry:
    vmid: int
    name: str
    status: str
    metrics_host: str
    allocated_disk_gb: float
    budget_disk_gb: float
    disk_paths: tuple[str, ...]


def _load_guests(
    repo_root: Path | None = None,
) -> list[_GuestEntry]:
    model_path = (repo_root or REPO_ROOT) / "config" / "capacity-model.json"
    payload = json.loads(model_path.read_text())
    guests: list[_GuestEntry] = []
    for g in payload.get("guests", []):
        guests.append(
            _GuestEntry(
                vmid=g["vmid"],
                name=g["name"],
                status=g.get("status", "active"),
                metrics_host=g.get("metrics_host", g["name"]),
                allocated_disk_gb=g.get("allocated", {}).get("disk_gb", 0),
                budget_disk_gb=g.get("budget", {}).get("disk_gb", 0),
                disk_paths=tuple(g.get("disk_paths", ["/"])),
            )
        )
    return guests


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def query_disk_usage(
    repo_root: Path | None = None,
    vm_filter: list[str] | None = None,
) -> DiskReport:
    """Query disk usage for all (or filtered) active VMs from InfluxDB.

    Reads capacity-model.json for VM enumeration and budget thresholds.
    Returns structured report with per-VM, per-mount metrics.
    """
    guests = _load_guests(repo_root)
    if vm_filter:
        filter_set = set(vm_filter)
        guests = [g for g in guests if g.name in filter_set]

    active_guests = [g for g in guests if g.status == "active"]
    if not active_guests:
        return DiskReport(
            timestamp=datetime.now(UTC).isoformat(),
            source="no_active_vms",
            vms=(),
        )

    ssh_command = _ssh_monitoring_command()
    if not ssh_command:
        return DiskReport(
            timestamp=datetime.now(UTC).isoformat(),
            source="unavailable",
            vms=tuple(
                VMDiskStatus(
                    name=g.name,
                    vmid=g.vmid,
                    status=g.status,
                    mounts=(),
                    budget_disk_gb=g.budget_disk_gb,
                    allocated_disk_gb=g.allocated_disk_gb,
                )
                for g in active_guests
            ),
        )

    metric_hosts = sorted({g.metrics_host for g in active_guests})
    host_filter = _build_host_filters(metric_hosts)

    # Query disk used and total per host per path
    disk_used_flux = (
        'from(bucket: "proxmox") '
        "|> range(start: -24h) "
        '|> filter(fn: (r) => r._measurement == "disk" and r._field == "used" and '
        f"({host_filter})) "
        '|> group(columns: ["host", "path"]) '
        "|> last()"
    )
    disk_total_flux = (
        'from(bucket: "proxmox") '
        "|> range(start: -24h) "
        '|> filter(fn: (r) => r._measurement == "disk" and r._field == "total" and '
        f"({host_filter})) "
        '|> group(columns: ["host", "path"]) '
        "|> last()"
    )

    used_rows = _influx_query(ssh_command, disk_used_flux)
    total_rows = _influx_query(ssh_command, disk_total_flux)

    # Index: (host, path) -> bytes
    used_by_host_path: dict[tuple[str, str], float] = {}
    for row in used_rows:
        host = row.get("host")
        path = row.get("path")
        value = row.get("_value")
        if host and path and value not in {None, ""}:
            used_by_host_path[(host, path)] = float(value)

    total_by_host_path: dict[tuple[str, str], float] = {}
    for row in total_rows:
        host = row.get("host")
        path = row.get("path")
        value = row.get("_value")
        if host and path and value not in {None, ""}:
            total_by_host_path[(host, path)] = float(value)

    # Build results
    vm_statuses: list[VMDiskStatus] = []
    for guest in active_guests:
        mounts: list[MountStatus] = []
        total_used: float = 0.0
        has_data = False

        # Check all known paths for this guest, plus any discovered paths
        known_paths = set(guest.disk_paths)
        discovered_paths = {path for (host, path) in used_by_host_path if host == guest.metrics_host} | {
            path for (host, path) in total_by_host_path if host == guest.metrics_host
        }
        all_paths = sorted(known_paths | discovered_paths)

        for path in all_paths:
            used_bytes = used_by_host_path.get((guest.metrics_host, path))
            total_bytes = total_by_host_path.get((guest.metrics_host, path))

            used_gb = used_bytes / (1024**3) if used_bytes is not None else None
            total_gb = total_bytes / (1024**3) if total_bytes is not None else None
            available_gb = (total_gb - used_gb) if (total_gb is not None and used_gb is not None) else None
            used_percent = (used_gb / total_gb * 100.0) if (total_gb and used_gb is not None) else None

            if used_gb is not None:
                total_used += used_gb
                has_data = True

            mounts.append(
                MountStatus(
                    path=path,
                    total_gb=round(total_gb, 2) if total_gb is not None else None,
                    used_gb=round(used_gb, 2) if used_gb is not None else None,
                    available_gb=round(available_gb, 2) if available_gb is not None else None,
                    used_percent=round(used_percent, 1) if used_percent is not None else None,
                    over_budget=(used_gb > guest.budget_disk_gb) if used_gb is not None else False,
                )
            )

        vm_statuses.append(
            VMDiskStatus(
                name=guest.name,
                vmid=guest.vmid,
                status=guest.status,
                mounts=tuple(mounts),
                budget_disk_gb=guest.budget_disk_gb,
                allocated_disk_gb=guest.allocated_disk_gb,
                total_used_gb=round(total_used, 2) if has_data else None,
            )
        )

    return DiskReport(
        timestamp=datetime.now(UTC).isoformat(),
        source="ssh+influx",
        vms=tuple(vm_statuses),
    )


def render_markdown(report: DiskReport, threshold_percent: float = 85.0) -> str:
    """Render a disk report as a Markdown table."""
    lines = [
        "# Disk Usage Report",
        "",
        f"**Source:** {report.source} | **Time:** {report.timestamp}",
        "",
        "| VM | VMID | Mount | Used GB | Total GB | Used % | Budget GB | Status |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for vm in report.vms:
        if not vm.mounts:
            lines.append(f"| {vm.name} | {vm.vmid} | - | - | - | - | {vm.budget_disk_gb} | no data |")
            continue
        for mount in vm.mounts:
            status_parts = []
            if mount.over_budget:
                status_parts.append("OVER BUDGET")
            if mount.used_percent is not None and mount.used_percent > threshold_percent:
                status_parts.append(f">{threshold_percent}%")
            status = ", ".join(status_parts) if status_parts else "ok"

            used = f"{mount.used_gb:.1f}" if mount.used_gb is not None else "-"
            total = f"{mount.total_gb:.1f}" if mount.total_gb is not None else "-"
            pct = f"{mount.used_percent:.1f}" if mount.used_percent is not None else "-"
            lines.append(
                f"| {vm.name} | {vm.vmid} | {mount.path} | {used} | {total} | {pct} | {vm.budget_disk_gb} | {status} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Query disk usage across platform VMs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--vm", nargs="*", help="Filter to specific VM names")
    parser.add_argument("--threshold", type=float, default=85.0, help="Alert threshold percentage")
    parser.add_argument("--repo-root", type=Path, default=None, help="Override repo root")
    args = parser.parse_args()

    report = query_disk_usage(repo_root=args.repo_root, vm_filter=args.vm)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_markdown(report, args.threshold))


if __name__ == "__main__":
    main()
