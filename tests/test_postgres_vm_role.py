from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "postgres_vm"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
VERIFY_PATH = ROLE_ROOT / "tasks" / "verify.yml"
TEMPLATE_PATH = ROLE_ROOT / "templates" / "postgresql-lv3.conf.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_enable_pgaudit_and_repo_managed_sensitive_table_catalog() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert defaults["postgres_vm_max_connections"] == 200
    assert defaults["postgres_vm_superuser_reserved_connections"] == 3
    assert defaults["postgres_vm_reserved_connections"] == 5
    assert defaults["postgres_vm_pgaudit_enabled"] is True
    assert defaults["postgres_vm_pgaudit_audit_role"] == "pgaudit_auditor"
    assert defaults["postgres_vm_pgaudit_sensitive_tables_file"] == (
        "{{ postgres_vm_repo_root }}/config/pgaudit/sensitive-tables.yaml"
    )
    assert defaults["postgres_vm_pgaudit_log"] == "ddl,role"
    assert defaults["postgres_vm_repo_root"] == "{{ lookup('env', 'PWD') }}"


def test_main_tasks_install_cluster_specific_pgaudit_package_and_extension() -> None:
    tasks = load_yaml(TASKS_PATH)
    package_task = next(task for task in tasks if task.get("name") == "Ensure PostgreSQL pgaudit package is present")
    extension_task = next(task for task in tasks if task.get("name") == "Create pgaudit extension in writable databases")

    assert package_task["ansible.builtin.apt"]["name"] == "postgresql-{{ postgres_vm_cluster_version }}-pgaudit"
    assert extension_task["ansible.builtin.command"]["argv"][-1] == "CREATE EXTENSION IF NOT EXISTS pgaudit"


def test_main_tasks_load_sensitive_table_catalog_and_grant_audit_role() -> None:
    tasks = load_yaml(TASKS_PATH)
    decode_task = next(task for task in tasks if task.get("name") == "Decode pgaudit sensitive-table catalog")
    grant_task = next(task for task in tasks if task.get("name") == "Grant sensitive-table privileges to the pgaudit audit role")

    assert "from_yaml" in decode_task["ansible.builtin.set_fact"]["postgres_vm_pgaudit_sensitive_tables"]
    assert "postgres_vm_pgaudit_audit_role" in grant_task["ansible.builtin.command"]["argv"][-1]
    assert "item.privileges" in grant_task["ansible.builtin.command"]["argv"][-1]


def test_template_enables_connection_logging_and_pgaudit_settings() -> None:
    template = TEMPLATE_PATH.read_text()

    assert "max_connections = {{ postgres_vm_max_connections }}" in template
    assert "superuser_reserved_connections = {{ postgres_vm_superuser_reserved_connections }}" in template
    assert "reserved_connections = {{ postgres_vm_reserved_connections }}" in template
    assert "log_connections = {{ 'on' if postgres_vm_log_connections else 'off' }}" in template
    assert "log_disconnections = {{ 'on' if postgres_vm_log_disconnections else 'off' }}" in template
    assert "shared_preload_libraries = '{{ postgres_vm_shared_preload_libraries | join(\",\") }}'" in template
    assert "pgaudit.log = '{{ postgres_vm_pgaudit_log }}'" in template
    assert "pgaudit.role = '{{ postgres_vm_pgaudit_audit_role }}'" in template


def test_verify_tasks_check_pgaudit_runtime_state() -> None:
    verify_tasks = load_yaml(VERIFY_PATH)
    preload_task = next(
        task for task in verify_tasks if task.get("name") == "Verify PostgreSQL shared_preload_libraries includes pgaudit"
    )
    log_task = next(task for task in verify_tasks if task.get("name") == "Verify PostgreSQL pgaudit session classes are configured")
    connection_task = next(task for task in verify_tasks if task.get("name") == "Verify PostgreSQL connection logging is enabled")

    assert preload_task["ansible.builtin.command"]["argv"][-1] == "SHOW shared_preload_libraries"
    assert log_task["ansible.builtin.command"]["argv"][-1] == "SHOW pgaudit.log"
    assert connection_task["ansible.builtin.command"]["argv"][-1] == "SHOW log_connections"


def test_verify_tasks_do_not_duplicate_pgaudit_runtime_checks() -> None:
    verify_tasks = load_yaml(VERIFY_PATH)
    task_names = [task.get("name") for task in verify_tasks]

    assert task_names.count("Verify PostgreSQL shared_preload_libraries includes pgaudit") == 1
    assert task_names.count("Verify PostgreSQL pgaudit session classes are configured") == 1
    assert task_names.count("Verify PostgreSQL connection logging is enabled") == 1


def test_template_declares_each_pgaudit_setting_once() -> None:
    template = TEMPLATE_PATH.read_text()

    assert template.count("max_connections = {{ postgres_vm_max_connections }}") == 1
    assert template.count("superuser_reserved_connections = {{ postgres_vm_superuser_reserved_connections }}") == 1
    assert template.count("reserved_connections = {{ postgres_vm_reserved_connections }}") == 1
    assert template.count("log_line_prefix = '{{ postgres_vm_log_line_prefix }}'") == 1
    assert template.count("log_connections = {{ 'on' if postgres_vm_log_connections else 'off' }}") == 1
    assert template.count("log_disconnections = {{ 'on' if postgres_vm_log_disconnections else 'off' }}") == 1
    assert template.count("shared_preload_libraries = '{{ postgres_vm_shared_preload_libraries | join(\",\") }}'") == 1
    assert template.count("pgaudit.log = '{{ postgres_vm_pgaudit_log }}'") == 1
    assert template.count("pgaudit.role = '{{ postgres_vm_pgaudit_audit_role }}'") == 1
