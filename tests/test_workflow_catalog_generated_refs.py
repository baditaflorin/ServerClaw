from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_workflows_reference_uptime_monitor_sources_not_ignored_generated_file() -> None:
    catalog = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
    workflows = catalog["workflows"]
    generated_monitor_file = "config/uptime-kuma/monitors.json"

    for workflow_id in (
        "converge-matrix-synapse",
        "converge-n8n",
        "converge-nextcloud",
        "uptime-kuma-manage",
    ):
        assert generated_monitor_file not in workflows[workflow_id]["implementation_refs"]

    uptime_workflow_refs = set(workflows["uptime-kuma-manage"]["implementation_refs"])
    assert "config/health-probe-catalog.json" in uptime_workflow_refs
    assert "scripts/uptime_contract.py" in uptime_workflow_refs
