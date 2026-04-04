from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_VM_DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "postgres_vm"
    / "defaults"
    / "main.yml"
)
POSTGRES_VM_ARGUMENT_SPECS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "postgres_vm"
    / "meta"
    / "argument_specs.yml"
)
POSTGRES_VM_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "postgres_vm"
    / "templates"
    / "postgresql-lv3.conf.j2"
)
POSTGRES_VM_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "postgres_vm"
    / "tasks"
    / "main.yml"
)


def test_postgres_vm_defaults_raise_the_managed_connection_ceiling() -> None:
    defaults = yaml.safe_load(POSTGRES_VM_DEFAULTS_PATH.read_text())

    assert defaults["postgres_vm_max_connections"] == 200


def test_postgres_vm_argument_specs_declare_max_connections() -> None:
    argument_specs = yaml.safe_load(POSTGRES_VM_ARGUMENT_SPECS_PATH.read_text())
    option = argument_specs["argument_specs"]["main"]["options"]["postgres_vm_max_connections"]

    assert option["type"] == "int"
    assert option["required"] is True


def test_postgres_vm_template_renders_the_managed_connection_limit() -> None:
    template = POSTGRES_VM_TEMPLATE_PATH.read_text()

    assert "max_connections = {{ postgres_vm_max_connections }}" in template
    assert "superuser_reserved_connections = {{ postgres_vm_superuser_reserved_connections }}" in template
    assert "reserved_connections = {{ postgres_vm_reserved_connections }}" in template


def test_postgres_vm_refreshes_apt_cache_before_package_installs() -> None:
    tasks = POSTGRES_VM_TASKS_PATH.read_text()

    assert 'argv:\n      - apt-get\n      - update' in tasks
    assert tasks.count("update_cache: true") == 0
