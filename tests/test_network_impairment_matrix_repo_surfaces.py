from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_network_impairment_matrix_workflow_is_cataloged() -> None:
    workflow_catalog = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text())
    workflow = workflow_catalog["workflows"]["network-impairment-matrix"]

    assert workflow["preferred_entrypoint"]["target"] == "network-impairment-matrix"
    assert workflow["owner_runbook"] == "docs/runbooks/network-impairment-matrix.md"
    assert "config/network-impairment-matrix.yaml" in workflow["implementation_refs"]


def test_network_impairment_matrix_windmill_surface_is_seeded() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT
            / "collections"
            / "ansible_collections"
            / "lv3"
            / "platform"
            / "roles"
            / "windmill_runtime"
            / "defaults"
            / "main.yml"
        ).read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}

    assert "f/lv3/network-impairment-matrix" in script_paths


def test_workstream_registry_tracks_ws_0189_live_apply() -> None:
    registry = (REPO_ROOT / "workstreams.yaml").read_text()

    assert "id: ws-0189-live-apply" in registry
    assert "branch: codex/ws-0189-live-apply" in registry


def test_network_impairment_matrix_script_runs_as_direct_entrypoint() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "network_impairment_matrix.py"),
            "--repo-path",
            str(REPO_ROOT),
            "--target-class",
            "staging",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "planned"
    assert payload["target_class"] == "staging"
