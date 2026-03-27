from pathlib import Path

import generate_platform_vars


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "openbao_runtime"
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
    / "openbao_runtime"
    / "tasks"
    / "main.yml"
)


def test_openbao_runtime_defaults_use_postgres_primary_address() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "openbao_postgres_host:" in defaults
    assert "postgres_ha.initial_primary" in defaults
    assert "ansible_host" in defaults
    assert "@{{ openbao_postgres_host }}:5432/postgres?sslmode=disable" in defaults
    assert 'CREATE ROLE "{{name}}" WITH LOGIN PASSWORD \'{{password}}\' VALID UNTIL \'{{expiration}}\';' in defaults
    assert 'GRANT pg_read_all_data TO "{{name}}";' in defaults
    assert 'DROP ROLE IF EXISTS "{{name}}";' in defaults


def test_generated_platform_vars_pin_openbao_to_postgres_primary_ip() -> None:
    platform_vars = generate_platform_vars.build_platform_vars()
    host_vars = generate_platform_vars.load_yaml(generate_platform_vars.HOST_VARS_PATH)
    primary_inventory_host = host_vars["postgres_ha"]["initial_primary"]
    primary_guest = next(guest for guest in host_vars["proxmox_guests"] if guest["name"] == primary_inventory_host)

    assert platform_vars["openbao_postgres_host"] == primary_guest["ipv4"]
    assert platform_vars["platform_postgres_host"] == "database.lv3.org"


def test_openbao_rotation_catalog_is_loaded_before_derived_facts() -> None:
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "- name: Load the rotatable secret catalog and controller secret manifest" in tasks
    assert "- name: Derive OpenBao secret rotation facts from the loaded catalog" in tasks
    assert "openbao_rotatable_secret_catalog: \"{{ lookup('ansible.builtin.file', openbao_secret_catalog_file) | from_json }}\"" in tasks
    assert "openbao_rotation_metadata: >-" in tasks
