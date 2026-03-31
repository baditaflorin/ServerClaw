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
    / "one_api_postgres"
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
    / "one_api_postgres"
    / "tasks"
    / "main.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_one_api_postgres_defaults_point_to_local_artifacts() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["one_api_database_name"] == "oneapi"
    assert defaults["one_api_database_user"] == "oneapi"
    assert defaults["one_api_local_artifact_dir"].endswith("/.local/one-api")
    assert defaults["one_api_database_password_local_file"].endswith("/.local/one-api/database-password.txt")


def test_one_api_postgres_role_generates_and_mirrors_password() -> None:
    tasks = load_tasks()

    generate_task = next(task for task in tasks if task.get("name") == "Generate the One-API database password")
    mirror_task = next(task for task in tasks if task.get("name") == "Mirror the One-API database password to the control machine")
    persist_task = next(task for task in tasks if task.get("name") == "Persist the One-API database password on the current guest")

    assert generate_task["delegate_to"] == "localhost"
    assert mirror_task["ansible.builtin.copy"]["dest"] == "{{ one_api_database_password_local_file }}"
    assert persist_task["ansible.builtin.copy"]["dest"] == "{{ one_api_postgres_password_file }}"
