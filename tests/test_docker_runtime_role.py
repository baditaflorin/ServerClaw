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


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def test_docker_runtime_patches_nftables_before_starting_docker() -> None:
    task_names = [task["name"] for task in load_tasks()]
    assert task_names.index("Apply Docker bridge forward-compat rules live without reloading nftables") < task_names.index(
        "Ensure Docker service is enabled and running"
    )


def test_docker_runtime_rechecks_nat_and_forward_chains() -> None:
    tasks = load_tasks()
    defaults = load_defaults()
    task_names = {task["name"] for task in tasks}
    assert "Flush Docker handlers before chain health checks" in task_names
    assert "Check whether Docker nat chain exists" in task_names
    assert "Check whether Docker forward chain exists" in task_names
    assert "Restart Docker when required chains are missing" in task_names
    nat_recheck = next(task for task in tasks if task["name"] == "Recheck Docker nat chain after restart")
    forward_recheck = next(task for task in tasks if task["name"] == "Recheck Docker forward chain after restart")
    assert defaults["docker_runtime_chain_recheck_retries"] == 30
    assert defaults["docker_runtime_chain_recheck_delay_seconds"] == 2
    assert nat_recheck["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert nat_recheck["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert nat_recheck["until"] == "docker_runtime_nat_chain_recheck.rc == 0"
    assert forward_recheck["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert forward_recheck["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert forward_recheck["until"] == "docker_runtime_forward_chain_recheck.rc == 0"
    fallback_restart = next(task for task in tasks if task["name"] == "Restart Docker when required chains remain unstable after recheck")
    nat_final_recheck = next(task for task in tasks if task["name"] == "Final recheck Docker nat chain after fallback restart")
    forward_final_recheck = next(task for task in tasks if task["name"] == "Final recheck Docker forward chain after fallback restart")
    nat_final_assert = next(task for task in tasks if task["name"] == "Final assert Docker nat chain is present")
    forward_final_assert = next(task for task in tasks if task["name"] == "Final assert Docker filter forward chain is present")
    nat_assert = next(task for task in tasks if task["name"] == "Assert Docker nat chain is present")
    forward_assert = next(task for task in tasks if task["name"] == "Assert Docker filter forward chain is present")
    assert nat_assert["ansible.builtin.command"] == "iptables -t nat -S DOCKER"
    assert nat_assert["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert nat_assert["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert nat_assert["until"] == "docker_runtime_nat_chain_assert.rc == 0"
    assert forward_assert["ansible.builtin.command"] == "iptables -t filter -S DOCKER-FORWARD"
    assert forward_assert["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert forward_assert["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert forward_assert["until"] == "docker_runtime_forward_chain_assert.rc == 0"
    assert fallback_restart["ansible.builtin.systemd"]["name"] == "docker"
    assert nat_final_recheck["until"] == "docker_runtime_nat_chain_final_recheck.rc == 0"
    assert nat_final_recheck["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert nat_final_recheck["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert forward_final_recheck["until"] == "docker_runtime_forward_chain_final_recheck.rc == 0"
    assert forward_final_recheck["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert forward_final_recheck["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert nat_final_assert["ansible.builtin.command"] == "iptables -t nat -S DOCKER"
    assert nat_final_assert["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert nat_final_assert["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert nat_final_assert["until"] == "docker_runtime_nat_chain_final_assert.rc == 0"
    assert forward_final_assert["ansible.builtin.command"] == "iptables -t filter -S DOCKER-FORWARD"
    assert forward_final_assert["retries"] == "{{ docker_runtime_chain_recheck_retries }}"
    assert forward_final_assert["delay"] == "{{ docker_runtime_chain_recheck_delay_seconds }}"
    assert forward_final_assert["until"] == "docker_runtime_forward_chain_final_assert.rc == 0"


def test_docker_runtime_patches_nftables_rule_block_once() -> None:
    tasks = load_tasks()
    build_rules = next(task for task in tasks if task["name"] == "Build the Docker bridge forward-compat rule block")
    patch_rules = next(task for task in tasks if task["name"] == "Patch nftables forward policy for Docker bridge egress")
    live_rules = next(
        task for task in tasks if task["name"] == "Apply Docker bridge forward-compat rules live without reloading nftables"
    )

    assert "docker_runtime_container_forward_rule_lines" in build_rules["ansible.builtin.set_fact"]
    assert "docker_runtime_container_forward_rule_block" in build_rules["ansible.builtin.set_fact"]
    assert patch_rules["ansible.builtin.lineinfile"]["line"] == "    {{ docker_runtime_container_forward_rule_block }}"
    assert "loop" not in patch_rules
    assert live_rules["loop"] == "{{ docker_runtime_container_forward_source_cidrs }}"
    assert live_rules["ansible.builtin.command"]["argv"][:6] == ["nft", "add", "rule", "inet", "filter", "forward"]


def test_docker_runtime_pins_public_edge_hostnames_and_address_pools() -> None:
    tasks = load_tasks()
    pin_hosts = next(task for task in tasks if task["name"] == "Pin public edge hostnames to the internal edge for Docker guests")

    assert pin_hosts["loop"] == "{{ docker_runtime_public_edge_host_aliases | default([]) }}"


def test_docker_runtime_defaults_pin_governed_resolvers_and_registry_mirror() -> None:
    defaults = load_defaults()
    daemon_config = defaults["docker_runtime_daemon_config"]

    assert defaults["docker_runtime_registry_mirrors"] == ["https://mirror.gcr.io"]
    assert defaults["docker_runtime_insecure_registries"] == []
    assert daemon_config["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert daemon_config["registry-mirrors"] == "{{ docker_runtime_registry_mirrors }}"
    assert daemon_config["insecure-registries"] == "{{ docker_runtime_insecure_registries }}"
    assert daemon_config["default-address-pools"] == [
        {"base": "172.16.0.0/12", "size": 24},
        {"base": "192.168.0.0/16", "size": 24},
        {"base": "10.200.0.0/16", "size": 24},
    ]
