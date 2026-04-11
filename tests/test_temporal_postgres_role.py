from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_postgres"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "temporal_postgres"
    / "tasks"
    / "main.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_temporal_postgres_defaults_point_to_local_artifacts() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["temporal_database_name"] == "temporal"
    assert defaults["temporal_visibility_database_name"] == "temporal_visibility"
    assert defaults["temporal_database_user"] == "temporal"
    assert defaults["temporal_local_artifact_dir"].endswith("/.local/temporal")
    assert defaults["temporal_database_password_local_file"].endswith("/.local/temporal/database-password.txt")


def test_temporal_postgres_role_generates_and_mirrors_password_and_databases() -> None:
    tasks = load_tasks()

    generate_task = next(task for task in tasks if task.get("name") == "Generate the Temporal database password")
    mirror_task = next(
        task for task in tasks if task.get("name") == "Mirror the Temporal database password to the control machine"
    )
    persist_task = next(
        task for task in tasks if task.get("name") == "Persist the Temporal database password on the current guest"
    )
    database_check_task = next(
        task for task in tasks if task.get("name") == "Check whether the Temporal PostgreSQL databases already exist"
    )
    database_create_task = next(
        task for task in tasks if task.get("name") == "Create the Temporal PostgreSQL databases"
    )
    database_owner_check_task = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Temporal PostgreSQL database owners already match"
    )
    database_owner_task = next(
        task for task in tasks if task.get("name") == "Ensure the Temporal PostgreSQL database owners are correct"
    )

    assert generate_task["delegate_to"] == "localhost"
    assert mirror_task["ansible.builtin.copy"]["dest"] == "{{ temporal_database_password_local_file }}"
    assert persist_task["ansible.builtin.copy"]["dest"] == "{{ temporal_postgres_password_file }}"
    assert database_check_task["loop"] == [
        "{{ temporal_database_name }}",
        "{{ temporal_visibility_database_name }}",
    ]
    assert database_create_task["changed_when"] is True
    assert (
        "CREATE DATABASE {{ item.item }} OWNER {{ temporal_database_user }}"
        in database_create_task["ansible.builtin.command"]["argv"][-1]
    )
    assert database_owner_check_task["loop"] == [
        "{{ temporal_database_name }}",
        "{{ temporal_visibility_database_name }}",
    ]
    assert database_owner_task["loop"] == "{{ temporal_postgres_database_owner_checks.results | default([]) }}"
    assert database_owner_task["changed_when"] is True
