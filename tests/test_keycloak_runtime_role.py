from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "main.yml"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text())


def test_defaults_define_private_mail_submission_for_realm_mail() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    smtp_server = defaults["keycloak_realm_smtp_server"]
    assert defaults["keycloak_database_host"] == "{{ hostvars[hostvars['proxmox_florin'].postgres_ha.initial_primary].ansible_host }}"
    assert defaults["keycloak_mail_platform_submission_port"] == (
        "{{ hostvars['proxmox_florin'].platform_port_assignments.mail_platform_internal_submission_port | default(1587) }}"
    )
    assert smtp_server["port"] == "{{ keycloak_mail_platform_submission_port }}"
    assert smtp_server["user"] == "{{ keycloak_mail_platform_submission_username }}"
    assert smtp_server["starttls"] is False
    assert smtp_server["ssl"] is False


def test_role_requires_local_mail_submission_secret() -> None:
    tasks = load_tasks()
    stat_task = next(task for task in tasks if task.get("name") == "Ensure the Keycloak mail submission password exists on the control machine")
    fail_task = next(task for task in tasks if task.get("name") == "Fail if the Keycloak mail submission password is missing locally")
    assert stat_task["ansible.builtin.stat"]["path"] == "{{ keycloak_mail_platform_submission_password_local_file }}"
    assert "password-reset and required-action mail" in fail_task["ansible.builtin.fail"]["msg"]


def test_realm_task_applies_repo_managed_smtp_settings() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    realm_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the LV3 realm exists")
    assert realm_task["community.general.keycloak_realm"]["smtp_server"] == "{{ keycloak_realm_smtp_server }}"


def test_role_restores_docker_nat_chain_before_startup() -> None:
    tasks = load_tasks()
    nat_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker nat chain exists before recreating Keycloak published ports"
    )
    nat_restore = next(
        task
        for task in tasks
        if task.get("name") == "Restore Docker networking when the nat chain is missing before Keycloak startup"
    )
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the Keycloak stack after Docker networking recovery"
    )
    readiness_probe = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the current Keycloak readiness endpoint is healthy before startup"
    )
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert readiness_probe["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ keycloak_local_management_port }}/health/ready"
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
