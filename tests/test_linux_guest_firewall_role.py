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
    / "linux_guest_firewall"
    / "tasks"
    / "main.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def test_linux_guest_firewall_reasserts_docker_bridge_chains_after_firewall_evaluation() -> None:
    tasks = load_tasks()
    task_names = [task["name"] for task in tasks]

    assert task_names.index("Wait for guest SSH after nftables changes") < task_names.index(
        "Ensure Docker bridge networking remains available after firewall evaluation"
    )
    ensure_task = next(
        task
        for task in tasks
        if task["name"] == "Ensure Docker bridge networking remains available after firewall evaluation"
    )
    include_role = ensure_task["ansible.builtin.include_role"]
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert ensure_task["vars"]["common_docker_bridge_chains_service_name"] == "docker"
