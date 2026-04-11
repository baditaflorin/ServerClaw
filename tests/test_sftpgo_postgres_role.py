from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "sftpgo_postgres" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "sftpgo_postgres" / "tasks" / "main.yml"
META_PATH = REPO_ROOT / "roles" / "sftpgo_postgres" / "meta" / "argument_specs.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_local_and_guest_password_mirrors() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    assert defaults["sftpgo_database_name"] == "sftpgo"
    assert defaults["sftpgo_database_user"] == "sftpgo"
    assert defaults["sftpgo_postgres_secret_dir"] == "/etc/lv3/sftpgo"
    assert defaults["sftpgo_postgres_password_file"] == "{{ sftpgo_postgres_secret_dir }}/database-password"
    assert defaults["sftpgo_database_password_local_file"].endswith("/.local/sftpgo/database-password.txt")


def test_postgres_role_provisions_named_database_and_role() -> None:
    tasks = load_yaml(TASKS_PATH)
    create_role = next(task for task in tasks if task.get("name") == "Create the SFTPGo database role")
    create_db = next(task for task in tasks if task.get("name") == "Create the SFTPGo PostgreSQL database")
    assert "CREATE ROLE {{ sftpgo_database_user }} LOGIN PASSWORD" in create_role["ansible.builtin.command"]["argv"][-1]
    assert (
        create_db["ansible.builtin.command"]["argv"][-1]
        == "CREATE DATABASE {{ sftpgo_database_name }} OWNER {{ sftpgo_database_user }}"
    )


def test_argument_specs_require_the_password_paths() -> None:
    specs = load_yaml(META_PATH)
    options = specs["argument_specs"]["main"]["options"]
    assert options["sftpgo_database_name"]["required"] is True
    assert options["sftpgo_database_user"]["required"] is True
    assert options["sftpgo_postgres_password_file"]["required"] is True
    assert options["sftpgo_database_password_local_file"]["required"] is True
