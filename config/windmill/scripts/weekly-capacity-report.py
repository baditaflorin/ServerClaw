#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capacity_report import build_report, load_capacity_model, render_markdown


def main(repo_path: str = "/srv/proxmox_florin_server", no_live_metrics: bool = False) -> dict[str, object]:
    repo_root = Path(repo_path)
    model_path = repo_root / "config" / "capacity-model.json"
    if not model_path.exists():
        return {
            "status": "blocked",
            "reason": f"missing capacity model at {model_path}",
        }

    model = load_capacity_model(model_path)
    report = build_report(model, with_live_metrics=not no_live_metrics)
    return {
        "status": "ok",
        "channel": "#platform-ops",
        "metrics_source": report.metrics_source,
        "markdown": render_markdown(report),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render the weekly LV3 capacity report payload.")
    parser.add_argument("--repo-path", default="/srv/proxmox_florin_server")
    parser.add_argument("--no-live-metrics", action="store_true")
    args = parser.parse_args()
    print(json.dumps(main(repo_path=args.repo_path, no_live_metrics=args.no_live_metrics), indent=2))
