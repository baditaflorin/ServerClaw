import runpy
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "postgres_client"
    / "tasks"
    / "main.yml"
)
SECRET_FILTER = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "plugins" / "filter" / "generate_secret.py"
)


def _task(name_prefix: str) -> dict:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    return next(task for task in tasks if task["name"].startswith(name_prefix))


def test_password_generation_is_repo_anchored_and_preserves_existing_secrets() -> None:
    task = _task("Generate database password when missing")
    command = task["ansible.builtin.command"]

    assert command["argv"] == [
        "python3",
        "{{ playbook_dir | dirname }}/scripts/generate_secret_with_mask.py",
        "--service",
        "{{ postgres_client_service }}",
        "--type",
        "password",
        "--output",
        "{{ postgres_client_password_local_file }}",
        "--metadata",
        "{{ postgres_client_password_local_file | dirname }}/.masked-secret",
    ]
    assert command["creates"] == "{{ postgres_client_password_local_file }}"
    assert task["delegate_to"] == "localhost"
    assert task["become"] is False
    assert task["no_log"] is True


def test_generate_secret_filter_loads_the_repo_shared_utility() -> None:
    namespace = runpy.run_path(str(SECRET_FILTER))

    assert "secret" in namespace["FilterModule"]().filters()
