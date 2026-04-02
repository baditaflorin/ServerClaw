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
ROLE_DEFAULTS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "linux_guest_firewall"
    / "defaults"
    / "main.yml"
)


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def test_linux_guest_firewall_reasserts_docker_bridge_chains_after_firewall_evaluation() -> None:
    tasks = load_tasks()
    task_names = [task["name"] for task in tasks]
    defaults = load_defaults()

    assert task_names.index("Wait for guest SSH after nftables changes") < task_names.index(
        "Ensure Docker bridge networking remains available after firewall evaluation"
    )
    ensure_task = next(
        task
        for task in tasks
        if task["name"] == "Ensure Docker bridge networking remains available after firewall evaluation"
    )
    include_role = next(
        task
        for task in ensure_task["block"]
        if task["name"] == "Assert Docker bridge chains remain available after guest firewall evaluation"
    )["ansible.builtin.include_role"]
    reset_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"] == "Reset Docker failed state before guest firewall bridge-chain recovery restart"
    )
    restart_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"] == "Restart Docker to restore bridge chains after guest firewall evaluation"
    )
    reassert_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"] == "Re-assert Docker bridge chains after guest firewall recovery restart"
    )
    fail_task = next(
        task
        for task in ensure_task["rescue"]
        if task["name"] == "Surface Docker bridge-chain failures after guest firewall evaluation when recovery is disabled"
    )
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert ensure_task["block"][0]["vars"]["common_docker_bridge_chains_service_name"] == (
        "{{ linux_guest_firewall_docker_bridge_chain_service_name }}"
    )
    assert reset_task["ansible.builtin.command"]["argv"] == [
        "systemctl",
        "reset-failed",
        "{{ linux_guest_firewall_docker_bridge_chain_service_name }}.service",
    ]
    assert reset_task["when"] == "linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert restart_task["ansible.builtin.service"] == {
        "name": "{{ linux_guest_firewall_docker_bridge_chain_service_name }}",
        "state": "restarted",
    }
    assert restart_task["when"] == "linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert reassert_task["vars"]["common_docker_bridge_chains_service_name"] == (
        "{{ linux_guest_firewall_docker_bridge_chain_service_name }}"
    )
    assert reassert_task["when"] == "linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert fail_task["when"] == "not linux_guest_firewall_recover_missing_docker_bridge_chains | bool"
    assert defaults["linux_guest_firewall_docker_bridge_chain_service_name"] == "docker"
    assert defaults["linux_guest_firewall_recover_missing_docker_bridge_chains"] is False

HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "linux_guest_firewall"
    / "templates"
    / "nftables.conf.j2"
)


def test_container_forwarding_guests_use_the_source_only_forward_path() -> None:
    template = TEMPLATE_PATH.read_text()

    assert "guest_policy.allow_container_forwarding | default(false)" in template
    assert "docker_runtime_container_forward_source_cidrs" in template
    assert "linux_guest_firewall_container_forward_source_cidrs" in template


def test_linux_guest_firewall_defaults_cover_all_governed_docker_bridge_cidrs() -> None:
    defaults = load_defaults()

    assert defaults["linux_guest_firewall_container_forward_source_cidrs"] == [
        "172.16.0.0/12",
        "192.168.0.0/16",
        "10.200.0.0/16",
    ]


def test_coolify_guest_policy_enables_container_forwarding_for_published_ports() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    coolify_policy = host_vars["network_policy"]["guests"]["coolify-lv3"]

    assert coolify_policy["allow_container_forwarding"] is True

    published_sources = {
        rule["source"]: tuple(rule["ports"])
        for rule in coolify_policy["allowed_inbound"]
        if rule["source"] == "nginx-lv3"
    }
    assert published_sources["nginx-lv3"] == (80, 443, 8000, 8096)


def test_livekit_guest_policy_allows_edge_signalling_and_public_media_ingress() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]

    assert any(
        rule["source"] == "nginx-lv3" and rule["protocol"] == "tcp" and 7880 in rule["ports"]
        for rule in docker_runtime_rules
    )
    assert any(
        rule["source"] == "public" and rule["protocol"] == "tcp" and 7881 in rule["ports"]
        for rule in docker_runtime_rules
    )
    assert any(
        rule["source"] == "public" and rule["protocol"] == "udp" and 7882 in rule["ports"]
        for rule in docker_runtime_rules
    )
