from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "runtime-pool-capacity-rebalance.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "runtime-pool-capacity-rebalance.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_runtime_pool_capacity_rebalance_playbook_covers_host_replay_guest_verification_and_host_summary() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert playbook[0]["name"] == "Rebalance the existing runtime-supporting VMs on the Proxmox host"
    assert playbook[0]["hosts"] == "proxmox_hosts"
    assert playbook[0]["vars"]["runtime_pool_capacity_rebalance_vmids"] == [122, 121, 130, 180, 170, 120]
    assert playbook[0]["vars"]["runtime_pool_capacity_rebalance_restart_order"] == [122, 121, 130, 180, 170, 120]
    assert [role["role"] for role in playbook[0]["roles"]] == ["lv3.platform.proxmox_guests"]

    restart_task = next(
        task
        for task in playbook[0]["post_tasks"]
        if task["name"] == "Restart each rebalanced guest so the new memory setting takes effect"
    )
    assert restart_task["loop"] == "{{ runtime_pool_capacity_rebalance_restart_order }}"
    assert "runtime_pool_capacity_rebalance_guest.vmid" in restart_task["ansible.builtin.shell"]

    verify_qm_task = next(
        task for task in playbook[0]["post_tasks"] if task["name"] == "Verify the rebalanced guest memory from Proxmox"
    )
    assert verify_qm_task["ansible.builtin.command"]["argv"][:2] == ["qm", "config"]

    assert playbook[1]["name"] == "Verify the rebalanced guests come back with SSH and declared Docker runtimes"
    assert playbook[1]["hosts"] == "runtime-apps:runtime-comms:docker-build:artifact-cache:coolify:docker-runtime"
    assert playbook[1]["vars"]["runtime_pool_capacity_rebalance_docker_hosts"] == [
        "runtime-comms",
        "docker-build",
        "artifact-cache",
        "coolify",
        "docker-runtime",
    ]
    start_task = next(
        task for task in playbook[1]["tasks"] if task["name"] == "Ensure Docker is started on the rebalanced guest"
    )
    assert start_task["ansible.builtin.service"] == {"name": "docker", "state": "started"}
    assert start_task["when"] == "inventory_hostname in runtime_pool_capacity_rebalance_docker_hosts"
    docker_task = next(
        task for task in playbook[1]["tasks"] if task["name"] == "Verify Docker is active on the rebalanced guest"
    )
    assert docker_task["ansible.builtin.command"]["argv"] == ["systemctl", "is-active", "docker.service"]
    assert docker_task["retries"] == 10
    assert docker_task["delay"] == 3
    assert docker_task["when"] == "inventory_hostname in runtime_pool_capacity_rebalance_docker_hosts"

    assert playbook[2]["name"] == "Verify host free memory after the rebalance"
    assert playbook[2]["hosts"] == "proxmox_hosts"
    assert playbook[2]["tasks"][0]["ansible.builtin.command"]["argv"] == ["free", "-h"]


def test_runtime_pool_capacity_rebalance_service_wrapper_imports_the_root_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)

    assert wrapper == [{"import_playbook": "../runtime-pool-capacity-rebalance.yml"}]
