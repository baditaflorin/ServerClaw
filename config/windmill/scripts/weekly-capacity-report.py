#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _load_capacity_report(repo_root: Path):
    scripts_dir = repo_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import capacity_report

    return capacity_report


def _run_capacity_report_with_uv(repo_root: Path, no_live_metrics: bool) -> dict[str, object]:
    inline_program = """
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
no_live_metrics = sys.argv[2] == "1"
scripts_dir = repo_root / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import capacity_report

model = capacity_report.load_capacity_model(repo_root / "config" / "capacity-model.json")
report = capacity_report.build_report(model, with_live_metrics=not no_live_metrics)
print(json.dumps({
    "metrics_source": report.metrics_source,
    "markdown": capacity_report.render_markdown(report),
}))
"""
    result = subprocess.run(
        ["uv", "run", "--with", "pyyaml", "python", "-", str(repo_root), "1" if no_live_metrics else "0"],
        input=inline_program,
        text=True,
        capture_output=True,
        check=False,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return {
            "status": "error",
            "reason": "capacity report uv fallback failed",
            "returncode": result.returncode,
            "stderr": result.stderr.strip(),
            "stdout": result.stdout.strip(),
        }
    payload = json.loads(result.stdout)
    return {
        "status": "ok",
        "channel": "#platform-ops",
        "metrics_source": payload["metrics_source"],
        "markdown": payload["markdown"],
    }


def main(repo_path: str = "/srv/proxmox_florin_server", no_live_metrics: bool = False) -> dict[str, object]:
    repo_root = Path(repo_path)
    model_path = repo_root / "config" / "capacity-model.json"
    if not model_path.exists():
        return {
            "status": "blocked",
            "reason": f"missing capacity model at {model_path}",
        }

    capacity_report = _load_capacity_report(repo_root)
    try:
        model = capacity_report.load_capacity_model(model_path)
        report = capacity_report.build_report(model, with_live_metrics=not no_live_metrics)
        return {
            "status": "ok",
            "channel": "#platform-ops",
            "metrics_source": report.metrics_source,
            "markdown": capacity_report.render_markdown(report),
        }
    except RuntimeError as exc:
        if "Missing dependency: PyYAML" not in str(exc):
            raise
        return _run_capacity_report_with_uv(repo_root, no_live_metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render the weekly LV3 capacity report payload.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--no-live-metrics", action="store_true")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path, no_live_metrics=args.no_live_metrics), indent=2))
