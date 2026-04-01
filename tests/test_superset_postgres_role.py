from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "superset_postgres" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "superset_postgres" / "tasks" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "superset_postgres" / "meta" / "argument_specs.yml"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_defaults_define_metadata_schema_reader_role_and_catalog_paths() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["superset_database_name"] == "postgres"
    assert defaults["superset_database_schema"] == "superset"
    assert defaults["superset_database_user"] == "superset"
    assert defaults["superset_reader_user"] == "superset_reader"
    assert defaults["superset_postgres_secret_dir"] == "/etc/lv3/superset"
    assert defaults["superset_database_password_local_file"] == "{{ superset_local_artifact_dir }}/database-password.txt"
    assert defaults["superset_reader_password_local_file"] == "{{ superset_local_artifact_dir }}/reader-password.txt"
    assert (
        defaults["superset_postgres_database_catalog_local_file"]
        == "{{ superset_local_artifact_dir }}/postgres-databases.json"
    )


def test_argument_spec_requires_schema_roles_and_local_artifacts() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["superset_database_name"]["type"] == "str"
    assert options["superset_database_schema"]["type"] == "str"
    assert options["superset_postgres_secret_dir"]["type"] == "path"
    assert options["superset_database_password_local_file"]["type"] == "path"
    assert options["superset_reader_password_local_file"]["type"] == "path"
    assert options["superset_postgres_database_catalog_local_file"]["type"] == "path"


def test_tasks_create_roles_schema_and_database_catalog() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Create the Superset metadata role" in names
    assert "Create the Superset datasource reader role" in names
    assert "Ensure the Superset metadata schema owner is correct" in names
    assert "Ensure the Superset metadata role defaults to the managed schema" in names
    assert "Ensure the Superset reader inherits the cluster-wide read-all-data capability" in names
    assert "Persist the Superset PostgreSQL database catalog on the control machine" in names

    schema_task = next(task for task in tasks if task["name"] == "Ensure the Superset metadata database is reachable and the schema exists")
    assert "CREATE SCHEMA IF NOT EXISTS {{ superset_database_schema }}" in schema_task["ansible.builtin.command"]["argv"][-1]

    search_path_task = next(task for task in tasks if task["name"] == "Ensure the Superset metadata role defaults to the managed schema")
    assert "ALTER ROLE {{ superset_database_user }} IN DATABASE {{ superset_database_name }}" in search_path_task["ansible.builtin.command"]["argv"][-1]
    assert "SET search_path TO {{ superset_database_schema }}, public" in search_path_task["ansible.builtin.command"]["argv"][-1]

    reader_grant_task = next(task for task in tasks if task["name"] == "Ensure the Superset reader inherits the cluster-wide read-all-data capability")
    assert reader_grant_task["ansible.builtin.command"]["argv"][-1] == "GRANT pg_read_all_data TO {{ superset_reader_user }}"
