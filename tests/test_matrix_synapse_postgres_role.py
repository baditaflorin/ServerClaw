from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "matrix_synapse_postgres" / "defaults" / "main.yml"
TASKS_FILE = REPO_ROOT / "roles" / "matrix_synapse_postgres" / "tasks" / "main.yml"


def test_matrix_synapse_postgres_defaults_require_synapse_safe_locale() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["matrix_synapse_database_collation"] == "C"
    assert defaults["matrix_synapse_database_ctype"] == "C"
    assert defaults["matrix_synapse_database_template"] == "template0"


def test_matrix_synapse_postgres_role_recreates_empty_mis_collated_database() -> None:
    task_file = TASKS_FILE.read_text()

    assert "Record whether the Matrix Synapse database locale requires recreation" in task_file
    assert "Drop the Matrix Synapse database when locale correction is required" in task_file
    assert "TEMPLATE {{ matrix_synapse_database_template }}" in task_file
    assert "LC_COLLATE '{{ matrix_synapse_database_collation }}'" in task_file
    assert "LC_CTYPE '{{ matrix_synapse_database_ctype }}'" in task_file
    assert "Assert the Matrix Synapse database locale matches the required setting" in task_file
