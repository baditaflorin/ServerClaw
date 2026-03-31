from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_postgres_backend"
)
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def test_openbao_postgres_backend_defaults_reserve_a_managed_connection_path() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["openbao_postgres_admin_role"] == "openbao_rotator"
    assert defaults["openbao_postgres_connect_role"] == "lv3_openbao_connect_all"
    assert defaults["openbao_postgres_reserved_connection_role"] == "pg_use_reserved_connections"


def test_openbao_postgres_backend_grants_reserved_connection_capability() -> None:
    tasks = load_tasks()

    reserved_role_task = next(
        task
        for task in tasks
        if task.get("name") == "Grant reserved PostgreSQL connection capability to the OpenBao rotator role"
    )

    assert reserved_role_task["ansible.builtin.command"]["argv"][-1] == (
        "GRANT {{ openbao_postgres_reserved_connection_role }} TO {{ openbao_postgres_admin_role }} WITH ADMIN OPTION"
    )
