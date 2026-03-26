from __future__ import annotations

import json
from pathlib import Path

import yaml

from platform.config_merge import validate_merge_eligible_catalog
from platform.events import load_topic_index


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_merge_eligible_catalog_validates() -> None:
    catalog = validate_merge_eligible_catalog(REPO_ROOT / "config" / "merge-eligible-files.yaml")
    assert "config/service-capability-catalog.json" in catalog
    assert catalog["config/workflow-catalog.json"].collection_type == "mapping"
    assert catalog["config/agent-policies.yaml"].collection_path == ()


def test_windmill_defaults_seed_config_merge_script_and_schedule() -> None:
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
        ).read_text(encoding="utf-8")
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_paths = {entry["path"] for entry in defaults["windmill_seed_schedules"]}

    assert "f/lv3/config_merge/merge_config_changes" in script_paths
    assert "f/lv3/config_merge/merge_config_changes_every_minute" in schedule_paths


def test_windmill_script_delete_task_allows_missing_rows() -> None:
    tasks = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "windmill_runtime"
        / "tasks"
        / "main.yml"
    ).read_text(encoding="utf-8")

    assert "Delete existing repo-managed Windmill scripts before reseeding" in tasks
    assert "status_code:\n      - 200\n      - 400\n      - 404" in tasks
    assert "Assert repo-managed Windmill script deletes only returned accepted statuses" in tasks
    assert "'no rows returned' in (item.content | default('') | lower)" in tasks


def test_migration_and_workflow_contracts_exist() -> None:
    migration = (REPO_ROOT / "migrations" / "0016_config_merge_schema.sql").read_text(encoding="utf-8")
    workflows = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))["workflows"]

    assert "CREATE TABLE IF NOT EXISTS config_change_staging" in migration
    assert "merge-config-changes" in workflows
    assert workflows["merge-config-changes"]["preferred_entrypoint"]["target"] == "merge-config-changes"


def test_event_taxonomy_registers_config_merge_topics() -> None:
    topics = load_topic_index()
    assert topics["platform.config.merged"]["status"] == "active"
    assert topics["platform.config.merge_conflict"]["status"] == "active"
