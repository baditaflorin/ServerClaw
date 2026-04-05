from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "semaphore_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
ARGUMENT_SPECS_PATH = ROLE_ROOT / "meta" / "argument_specs.yml"
README_PATH = ROLE_ROOT / "README.md"


def load_tasks() -> list[dict]:
    raw_tasks = yaml.safe_load(TASKS_PATH.read_text())
    flattened: list[dict] = []

    def visit(task_list: list[dict]) -> None:
        for task in task_list:
            flattened.append(task)
            for nested_key in ("block", "rescue", "always"):
                nested_tasks = task.get(nested_key)
                if nested_tasks:
                    visit(nested_tasks)

    visit(raw_tasks)
    return flattened


def test_semaphore_defaults_define_controller_local_artifacts() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())

    assert defaults["semaphore_admin_username"] == "ops-semaphore"
    assert defaults["semaphore_admin_email"] == "ops-semaphore@lv3.org"
    assert defaults["semaphore_local_artifact_dir"] == "{{ playbook_dir }}/../.local/semaphore"
    assert defaults["semaphore_admin_password_local_file"] == "{{ semaphore_local_artifact_dir }}/admin-password.txt"
    assert defaults["semaphore_api_token_local_file"] == "{{ semaphore_local_artifact_dir }}/api-token.txt"
    assert defaults["semaphore_admin_auth_local_file"] == "{{ semaphore_local_artifact_dir }}/admin-auth.json"
    assert defaults["semaphore_bootstrap_spec_local_file"] == "{{ semaphore_local_artifact_dir }}/bootstrap-spec.json"


def test_semaphore_role_argument_specs_cover_controller_auth_paths() -> None:
    specs = yaml.safe_load(ARGUMENT_SPECS_PATH.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["semaphore_controller_url"]["required"] is True
    assert options["semaphore_private_base_url"]["required"] is True
    assert options["semaphore_admin_password_local_file"]["required"] is True
    assert options["semaphore_api_token_local_file"]["required"] is True
    assert options["semaphore_admin_auth_local_file"]["required"] is True
    assert options["semaphore_bootstrap_spec_local_file"]["required"] is True


def test_semaphore_role_recovers_stale_admin_password_before_bootstrap() -> None:
    tasks = load_tasks()
    names = {task["name"] for task in tasks}

    assert "Wait for the controller-facing Semaphore API to answer" in names
    assert "Check whether the controller-facing Semaphore login already accepts the desired admin password" in names
    assert "Reconcile the persisted Semaphore admin password when controller login rejects the desired password" in names
    assert "Recheck the controller-facing Semaphore login after reconciling the persisted admin password" in names
    assert "Bootstrap the Semaphore project and controller auth artifacts" in names

    preflight_task = next(
        task
        for task in tasks
        if task["name"] == "Check whether the controller-facing Semaphore login already accepts the desired admin password"
    )
    recovery_task = next(
        task
        for task in tasks
        if task["name"]
        == "Reconcile the persisted Semaphore admin password when controller login rejects the desired password"
    )
    recheck_task = next(
        task
        for task in tasks
        if task["name"] == "Recheck the controller-facing Semaphore login after reconciling the persisted admin password"
    )

    assert preflight_task["ansible.builtin.uri"]["url"] == "{{ semaphore_controller_url }}/api/auth/login"
    assert preflight_task["ansible.builtin.uri"]["body"] == {
        "auth": "{{ semaphore_admin_username }}",
        "password": "{{ semaphore_admin_password }}",
    }
    assert preflight_task["ansible.builtin.uri"]["status_code"] == [204, 401]
    assert preflight_task["register"] == "semaphore_controller_login_preflight"

    recovery_argv = recovery_task["ansible.builtin.command"]["argv"]
    assert recovery_argv[:6] == ["docker", "compose", "--file", "{{ semaphore_compose_file }}", "exec", "-T"]
    assert recovery_argv[6:9] == ["{{ semaphore_container_name }}", "sh", "-lc"]
    assert "/usr/local/bin/semaphore user change-by-login" in recovery_argv[9]
    assert '"$SEMAPHORE_ADMIN"' in recovery_argv[9]
    assert '"$SEMAPHORE_ADMIN_PASSWORD"' in recovery_argv[9]
    assert recovery_task["when"] == "semaphore_controller_login_preflight.status == 401"

    assert recheck_task["ansible.builtin.uri"]["status_code"] == 204
    assert recheck_task["when"] == "semaphore_controller_login_preflight.status == 401"


def test_semaphore_role_documentation_mentions_controller_auth_bootstrap() -> None:
    readme = README_PATH.read_text()

    assert "controller-local auth artifacts" in readme
    assert "seeded self-test Ansible project" in readme
