from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_all_workflow_catalog_windmill_wrappers_are_seeded() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )
    catalog = json.loads((REPO_ROOT / "config/workflow-catalog.json").read_text())

    seeded_files = {
        entry["local_file"].replace("{{ inventory_dir }}/../", "").replace("{{ playbook_dir }}/../", "")
        for entry in defaults["windmill_seed_scripts"]
        if isinstance(entry, dict) and "local_file" in entry
    }
    workflow_wrappers = sorted(
        {
            ref
            for workflow in catalog["workflows"].values()
            for ref in workflow.get("implementation_refs", [])
            if isinstance(ref, str) and ref.startswith("config/windmill/scripts/")
        }
    )

    assert workflow_wrappers
    assert sorted(seeded_files.intersection(workflow_wrappers)) == workflow_wrappers


def test_default_operations_surface_verification_paths_are_declared() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )
    verify_tasks = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "windmill_runtime"
        / "tasks"
        / "verify.yml"
    ).read_text()

    expected_paths = {
        "f/lv3/post_merge_gate",
        "f/lv3/nightly_integration_tests",
        "f/lv3/runbook_executor",
        "f/lv3/continuous_drift_detection",
        "f/lv3/subdomain_exposure_audit",
        "f/lv3/weekly_capacity_report",
        "f/lv3/weekly_security_scan",
        "f/lv3/security_posture_scan",
        "f/lv3/audit_token_inventory",
        "f/lv3/token_exposure_response",
        "f/lv3/collection_publish",
        "f/lv3/packer_template_rebuild",
        "f/lv3/fixture_expiry_reaper",
        "f/lv3/maintenance_window",
    }

    assert expected_paths.issubset(set(defaults["windmill_default_operations_surface_script_paths"]))
    assert "windmill_default_operations_surface_script_paths" in verify_tasks
    assert "/api/w/{{ windmill_workspace_id }}/scripts/get/p/" in verify_tasks
