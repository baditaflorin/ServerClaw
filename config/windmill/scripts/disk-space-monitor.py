#!/usr/bin/env python3
"""Windmill workflow: Disk Space Monitor.

Queries disk usage across all platform VMs via the shared disk_metrics
module and flags VMs that exceed a configurable threshold.  Returns a
structured payload suitable for ntfy / Mattermost notification.

Schedule: every 6 hours (recommended).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _load_disk_metrics(repo_root: Path):
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import disk_metrics

    return disk_metrics


def _run_with_uv(repo_root: Path, threshold_percent: float) -> dict[str, object]:
    """Fallback: run via uv when PyYAML is missing from the Windmill worker."""
    inline_program = """
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
threshold = float(sys.argv[2])
scripts_dir = repo_root / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import disk_metrics

report = disk_metrics.query_disk_usage(repo_root=repo_root)
print(json.dumps({
    "report": report.to_dict(),
    "markdown": disk_metrics.render_markdown(report, threshold),
}))
"""
    result = subprocess.run(
        ["uv", "run", "--with", "pyyaml", "python", "-", str(repo_root), str(threshold_percent)],
        input=inline_program,
        text=True,
        capture_output=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return {
            "status": "error",
            "reason": "disk metrics uv fallback failed",
            "returncode": result.returncode,
            "stderr": result.stderr.strip(),
        }
    payload = json.loads(result.stdout)
    return _build_response(payload["report"], payload["markdown"], threshold_percent)


def _build_response(
    report_dict: dict[str, object],
    markdown: str,
    threshold_percent: float,
) -> dict[str, object]:
    alerts: list[dict[str, object]] = []
    for vm in report_dict.get("vms", []):
        for mount in vm.get("mounts", []):
            pct = mount.get("used_percent")
            if pct is not None and pct > threshold_percent:
                alerts.append({
                    "vm": vm["name"],
                    "vmid": vm["vmid"],
                    "path": mount["path"],
                    "used_percent": pct,
                    "used_gb": mount.get("used_gb"),
                    "total_gb": mount.get("total_gb"),
                    "budget_gb": vm.get("budget_disk_gb"),
                })

    return {
        "status": "alert" if alerts else "ok",
        "channel": "#platform-ops",
        "source": report_dict.get("source", "unknown"),
        "alert_count": len(alerts),
        "alerts": alerts,
        "vm_count": len(report_dict.get("vms", [])),
        "markdown": markdown,
    }


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    threshold_percent: float = 85.0,
) -> dict[str, object]:
    repo_root = Path(repo_path)
    model_path = repo_root / "config" / "capacity-model.json"
    if not model_path.exists():
        return {
            "status": "blocked",
            "reason": f"missing capacity model at {model_path}",
        }

    dm = _load_disk_metrics(repo_root)
    try:
        report = dm.query_disk_usage(repo_root=repo_root)
        markdown = dm.render_markdown(report, threshold_percent)
        return _build_response(report.to_dict(), markdown, threshold_percent)
    except RuntimeError as exc:
        if "Missing dependency: PyYAML" not in str(exc):
            raise
        return _run_with_uv(repo_root, threshold_percent)
