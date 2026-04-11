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
    / "openfga_postgres"
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
    / "openfga_postgres"
    / "tasks"
    / "main.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_openfga_postgres_defaults_point_to_local_artifacts() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["openfga_database_name"] == "openfga"
    assert defaults["openfga_database_user"] == "openfga"
    assert defaults["openfga_local_artifact_dir"].endswith("/.local/openfga")
    assert defaults["openfga_database_password_local_file"].endswith("/.local/openfga/database-password.txt")


def test_openfga_postgres_role_generates_and_mirrors_password() -> None:
    tasks = load_tasks()

    generate_task = next(task for task in tasks if task.get("name") == "Generate the OpenFGA database password")
    mirror_task = next(
        task for task in tasks if task.get("name") == "Mirror the OpenFGA database password to the control machine"
    )
    persist_task = next(
        task for task in tasks if task.get("name") == "Persist the OpenFGA database password on the current guest"
    )

    assert generate_task["delegate_to"] == "localhost"
    assert mirror_task["ansible.builtin.copy"]["dest"] == "{{ openfga_database_password_local_file }}"
    assert persist_task["ansible.builtin.copy"]["dest"] == "{{ openfga_postgres_password_file }}"
