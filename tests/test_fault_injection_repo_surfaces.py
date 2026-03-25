from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_fault_injection_workflow_is_cataloged() -> None:
    workflow_catalog = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text())
    workflow = workflow_catalog["workflows"]["fault-injection"]

    assert workflow["preferred_entrypoint"]["target"] == "fault-injection"
    assert workflow["owner_runbook"] == "docs/runbooks/fault-injection.md"
    assert "config/fault-scenarios.yaml" in workflow["implementation_refs"]


def test_fault_injection_windmill_surfaces_are_seeded() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_paths = {entry["path"] for entry in defaults["windmill_seed_schedules"]}

    assert "f/lv3/fault-injection" in script_paths
    assert "f/lv3/fault-injection-first-sunday" in schedule_paths


def test_workstream_registry_tracks_adr_0171() -> None:
    registry = (REPO_ROOT / "workstreams.yaml").read_text()

    assert "id: adr-0171-controlled-fault-injection" in registry
    assert "branch: codex/adr-0171-fault-injection" in registry


def test_fault_injection_script_runs_as_direct_entrypoint() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "fault_injection.py"),
            "--repo-path",
            str(REPO_ROOT),
            "--scenario-names",
            "fault:keycloak-unavailable",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "planned"
    assert payload["selected_scenarios"] == ["fault:keycloak-unavailable"]
