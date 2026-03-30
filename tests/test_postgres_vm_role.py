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
    / "postgres_vm"
)
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
TEMPLATE_PATH = ROLE_ROOT / "templates" / "postgresql-lv3.conf.j2"


def test_postgres_vm_defaults_reserve_capacity_for_automation() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["postgres_vm_max_connections"] == 110
    assert defaults["postgres_vm_superuser_reserved_connections"] == 3
    assert defaults["postgres_vm_reserved_connections"] == 5


def test_postgres_vm_validation_guards_reserved_connection_budget() -> None:
    task_file = TASKS_PATH.read_text(encoding="utf-8")

    assert "postgres_vm_max_connections | int > 0" in task_file
    assert "postgres_vm_superuser_reserved_connections | int >= 0" in task_file
    assert "postgres_vm_reserved_connections | int >= 0" in task_file
    assert "postgres_vm_superuser_reserved_connections | int) + (postgres_vm_reserved_connections | int) < (postgres_vm_max_connections | int)" in task_file


def test_postgres_vm_template_renders_reserved_connection_settings() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "max_connections = {{ postgres_vm_max_connections }}" in template
    assert "superuser_reserved_connections = {{ postgres_vm_superuser_reserved_connections }}" in template
    assert "reserved_connections = {{ postgres_vm_reserved_connections }}" in template
