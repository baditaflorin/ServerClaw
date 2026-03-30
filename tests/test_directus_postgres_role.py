from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ACCESS_MODEL_TASKS_PATH = REPO_ROOT / "roles" / "directus_postgres" / "tasks" / "access_model.yml"
ACCESS_MODEL_TEMPLATE_PATH = REPO_ROOT / "roles" / "directus_postgres" / "templates" / "access_model.sql.j2"


def test_directus_access_model_seed_file_is_owned_by_postgres() -> None:
    tasks = yaml.safe_load(ACCESS_MODEL_TASKS_PATH.read_text())
    render_task = next(task for task in tasks if task.get("name") == "Render the Directus access-model SQL seed")

    template_task = render_task["ansible.builtin.template"]
    assert template_task["dest"] == "/tmp/directus-access-model.sql"
    assert template_task["owner"] == "postgres"
    assert template_task["group"] == "postgres"
    assert template_task["mode"] == "0600"


def test_directus_access_model_quotes_reserved_user_column() -> None:
    template = ACCESS_MODEL_TEMPLATE_PATH.read_text()

    assert 'INSERT INTO directus_access (id, role, "user", policy, sort)' in template
    assert '"user" = EXCLUDED."user"' in template
