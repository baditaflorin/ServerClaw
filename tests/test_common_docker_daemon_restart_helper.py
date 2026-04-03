from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "tasks"
    / "docker_daemon_restart.yml"
)
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "defaults"
    / "main.yml"
)
ARGUMENT_SPECS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "meta"
    / "argument_specs.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(HELPER_TASKS.read_text())


def test_common_docker_daemon_restart_helper_protects_shared_runtime_hosts_by_default() -> None:
    tasks = load_tasks()
    task_names = [task["name"] for task in tasks]
    block_fact = next(
        task for task in tasks if task["name"] == "Decide whether the Docker daemon restart is blocked on this host"
    )
    fail_task = next(
        task
        for task in tasks
        if task["name"] == "Fail closed before an unsafe Docker daemon restart on a protected shared-runtime host"
    )
    restart_task = next(task for task in tasks if task["name"] == "Restart the managed Docker daemon")
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    specs = yaml.safe_load(ARGUMENT_SPECS_PATH.read_text())
    options = specs["argument_specs"]["docker_daemon_restart"]["options"]

    assert task_names[0] == "Validate common docker_daemon_restart entrypoint inputs"
    assert "inventory_hostname in common_docker_daemon_restart_protected_hosts" in block_fact["ansible.builtin.set_fact"][
        "common_docker_daemon_restart_blocked"
    ]
    assert "common_docker_daemon_restart_force | bool" in block_fact["ansible.builtin.set_fact"][
        "common_docker_daemon_restart_blocked"
    ]
    assert fail_task["when"] == "common_docker_daemon_restart_blocked | bool"
    assert "common_docker_daemon_restart_force=true" in fail_task["ansible.builtin.fail"]["msg"]
    assert restart_task["ansible.builtin.systemd_service"]["state"] == "restarted"
    assert restart_task["when"] == "not (common_docker_daemon_restart_blocked | bool)"
    assert defaults["common_docker_daemon_restart_service_name"] == "docker"
    assert defaults["common_docker_daemon_restart_reason"] == ""
    assert defaults["common_docker_daemon_restart_force"] is False
    assert defaults["common_docker_daemon_restart_protected_hosts"] == [
        "docker-runtime-lv3",
        "docker-runtime-staging-lv3",
    ]
    assert options["common_docker_daemon_restart_reason"]["required"] is True
    assert options["common_docker_daemon_restart_force"]["default"] is False
    assert options["common_docker_daemon_restart_protected_hosts"]["default"] == [
        "docker-runtime-lv3",
        "docker-runtime-staging-lv3",
    ]
