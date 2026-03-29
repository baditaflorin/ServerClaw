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
    / "docker_runtime"
    / "tasks"
    / "main.yml"
)
ROLE_DEFAULTS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "defaults"
    / "main.yml"
)
ROLE_VERIFY = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "docker_runtime"
    / "tasks"
    / "verify.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def load_verify() -> list[dict]:
    return yaml.safe_load(ROLE_VERIFY.read_text())


def test_docker_runtime_patches_nftables_before_starting_docker() -> None:
    task_names = [task["name"] for task in load_tasks()]
    assert task_names.index("Reload nftables after forward compatibility patch") < task_names.index(
        "Ensure Docker service is enabled and running"
    )


def test_docker_runtime_rechecks_nat_and_forward_chains() -> None:
    tasks = load_tasks()
    defaults = load_defaults()
    task_names = {task["name"] for task in tasks}
    assert "Flush Docker handlers before chain health checks" in task_names
    assert "Ensure Docker bridge networking chains are present" in task_names
    ensure_task = next(task for task in tasks if task["name"] == "Ensure Docker bridge networking chains are present")
    include_role = ensure_task["ansible.builtin.include_role"]
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert ensure_task["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert ensure_task["vars"]["common_docker_bridge_chains_require_nat_chain"] == "{{ docker_runtime_require_nat_chain }}"
    assert defaults["docker_runtime_chain_recheck_retries"] == 30
    assert defaults["docker_runtime_chain_recheck_delay_seconds"] == 2
    assert ensure_task["vars"]["common_docker_bridge_chains_retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert ensure_task["vars"]["common_docker_bridge_chains_delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"


def test_docker_runtime_patches_nftables_rule_block_once() -> None:
    tasks = load_tasks()
    build_rules = next(task for task in tasks if task["name"] == "Build the Docker bridge forward-compat rule block")
    patch_rules = next(task for task in tasks if task["name"] == "Patch nftables forward policy for Docker bridge egress")
    reload_rules = next(task for task in tasks if task["name"] == "Reload nftables after forward compatibility patch")

    assert "docker_runtime_container_forward_rule_block" in build_rules["ansible.builtin.set_fact"]
    assert patch_rules["ansible.builtin.lineinfile"]["line"] == "    {{ docker_runtime_container_forward_rule_block }}"
    assert "loop" not in patch_rules
    assert reload_rules["changed_when"] == "docker_runtime_nftables_forward_patch.changed"


def test_docker_runtime_pins_public_edge_hostnames_and_address_pools() -> None:
    tasks = load_tasks()
    pin_hosts = next(task for task in tasks if task["name"] == "Pin public edge hostnames to the internal edge for Docker guests")

    assert pin_hosts["loop"] == "{{ docker_runtime_public_edge_host_aliases | default([]) }}"


def test_docker_runtime_defaults_pin_governed_resolvers_and_registry_mirror() -> None:
    defaults = load_defaults()
    daemon_config = defaults["docker_runtime_daemon_config"]

    assert defaults["docker_runtime_registry_mirrors"] == ["https://mirror.gcr.io"]
    assert defaults["docker_runtime_publication_assurance_script_path"] == "/usr/local/bin/lv3-docker-publication-assurance"
    assert defaults["docker_runtime_insecure_registries"] == []
    assert daemon_config["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert daemon_config["registry-mirrors"] == "{{ docker_runtime_registry_mirrors }}"
    assert daemon_config["insecure-registries"] == "{{ docker_runtime_insecure_registries }}"
    assert daemon_config["default-address-pools"] == [
        {"base": "172.16.0.0/12", "size": 24},
        {"base": "192.168.0.0/16", "size": 24},
        {"base": "10.200.0.0/16", "size": 24},
    ]


def test_docker_runtime_installs_publication_assurance_helper_before_chain_checks() -> None:
    tasks = load_tasks()
    install_task = next(task for task in tasks if task["name"] == "Install the Docker publication assurance helper")
    nftables_check_task = next(task for task in tasks if task["name"] == "Check whether nftables config exists")

    assert install_task["ansible.builtin.copy"]["dest"] == "{{ docker_runtime_publication_assurance_script_path }}"
    assert "scripts/docker_publication_assurance.py" in install_task["ansible.builtin.copy"]["content"]
    assert tasks.index(install_task) < tasks.index(nftables_check_task)


def test_docker_runtime_verify_checks_publication_assurance_helper_is_executable() -> None:
    verify_tasks = load_verify()
    verify_task = next(
        task for task in verify_tasks if task["name"] == "Verify the Docker publication assurance helper is installed"
    )

    assert verify_task["ansible.builtin.command"]["argv"] == [
        "test",
        "-x",
        "{{ docker_runtime_publication_assurance_script_path }}",
    ]
    assert verify_task["changed_when"] is False
