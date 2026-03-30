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
    assert catalog["config/correction-loops.json"].key_field == "id"
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
    seed_scripts = defaults["windmill_seed_scripts"]
    script_paths = {entry["path"] for entry in seed_scripts}
    schedule_map = {entry["path"]: entry for entry in defaults["windmill_seed_schedules"]}
    script_map = {entry["path"]: entry for entry in seed_scripts}

    assert "f/lv3/config_merge/merge_config_changes" in script_paths
    assert "f/lv3/config_merge/merge_config_changes_every_minute" in schedule_map
    assert schedule_map["f/lv3/config_merge/merge_config_changes_every_minute"]["args"]["dsn"] == "{{ windmill_database_dsn }}"
    assert len(script_paths) == len(seed_scripts)
    assert (
        script_map["f/lv3/scheduler_watchdog_loop"]["local_file"]
        == "{{ windmill_seed_script_root_local_dir }}/scheduler-watchdog-loop.py"
    )
    assert (
        script_map["f/lv3/scheduler_watchdog"]["local_file"]
        == "{{ windmill_seed_repo_root_local_dir }}/windmill/scheduler/watchdog-loop.py"
    )


def test_windmill_script_sync_uses_manifest_helper() -> None:
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

    assert "Create a local manifest path for repo-managed Windmill scripts" in tasks
    assert "Render the repo-managed Windmill script manifest locally" in tasks
    assert "{{ windmill_worker_checkout_repo_root_local_dir }}/scripts/sync_windmill_seed_scripts.py" in tasks
    assert "uv" in tasks
    assert "--with" in tasks
    assert "pyyaml" in tasks
    assert "{{ windmill_seed_script_manifest_local.path }}" in tasks
    assert '--max-attempts' in tasks
    assert '"20"' in tasks
    assert '--settle-interval' in tasks
    assert '"2.0"' in tasks
    assert "{{ windmill_worker_checkout_repo_root_local_dir }}/scripts/sync_windmill_seed_schedules.py" in tasks
    assert tasks.count("pyyaml") >= 2
    assert "{{ windmill_seed_schedule_manifest_local.path }}" in tasks
    assert tasks.count('{{ windmill_base_url }}') == 2
    assert tasks.count('{{ windmill_private_base_url }}') == 5


def test_make_converge_windmill_forwards_extra_args() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    target_start = makefile.index("converge-windmill:")
    next_target = makefile.index("\nconverge-coolify:", target_start)
    target_block = makefile[target_start:next_target]

    assert "$(EXTRA_ARGS)" in target_block
    assert "--playbook $(REPO_ROOT)/playbooks/windmill.yml" in target_block


def test_windmill_defaults_use_git_common_dir_for_shared_local_artifacts() -> None:
    runtime_defaults = yaml.safe_load(
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
    postgres_defaults = yaml.safe_load(
        (
            REPO_ROOT
            / "collections"
            / "ansible_collections"
            / "lv3"
            / "platform"
            / "roles"
            / "windmill_postgres"
            / "defaults"
            / "main.yml"
        ).read_text(encoding="utf-8")
    )

    expected_lookup = "rev-parse --path-format=absolute --git-common-dir"
    assert expected_lookup in runtime_defaults["windmill_controller_repo_common_root"]
    assert expected_lookup in postgres_defaults["windmill_local_artifact_dir"]
    assert runtime_defaults["windmill_local_artifact_dir"] == "{{ windmill_controller_repo_common_root ~ '/.local/windmill' }}"
    assert "/.local/windmill" in postgres_defaults["windmill_local_artifact_dir"]
    assert runtime_defaults["windmill_database_password_local_file"] == "{{ windmill_local_artifact_dir }}/database-password.txt"
    assert runtime_defaults["windmill_database_dsn"].startswith("postgres://{{ windmill_database_user }}:")


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
