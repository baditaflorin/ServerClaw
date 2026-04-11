from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "step_ca_runtime"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "step_ca_runtime"
    / "tasks"
    / "main.yml"
)
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "step_ca_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)


def test_step_ca_runtime_defaults_anchor_service_topology_to_proxmox_hostvars() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["step_ca_service_topology"] == "{{ hostvars['proxmox_florin'].platform_service_topology }}"
    assert (
        defaults["step_ca_api_port"] == "{{ step_ca_service_topology | platform_service_port('step_ca', 'internal') }}"
    )
    assert (
        defaults["step_ca_internal_url"]
        == "{{ step_ca_service_topology | platform_service_url('step_ca', 'internal') }}"
    )
    assert (
        defaults["step_ca_controller_url"]
        == "{{ step_ca_service_topology | platform_service_url('step_ca', 'controller') }}"
    )
    assert defaults["step_ca_default_network_name"] == "{{ step_ca_site_dir | basename }}_default"
    assert defaults["step_ca_server_names"][2] == "{{ step_ca_service_topology | platform_service_host('step_ca') }}"
    assert defaults["step_ca_pull_recovery_retries"] == 10
    assert defaults["step_ca_pull_recovery_delay_seconds"] == 2


def test_step_ca_runtime_recovers_detached_empty_default_network_before_compose_up() -> None:
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "Inspect the managed step-ca default network before compose up" in tasks
    assert "Remove the detached managed step-ca default network before compose up" in tasks
    assert "step_ca_default_network_inspect.stdout | from_json | first" in tasks
    assert ".Containers | default({})" in tasks
    assert "      - network\n      - rm" in tasks


def test_runtime_control_network_policy_allows_step_ca_from_peer_guests_and_local_docker_workloads() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    rules = host_vars["network_policy"]["guests"]["runtime-control-lv3"]["allowed_inbound"]

    assert any(rule["source"] == "all_guests" and 9000 in rule["ports"] for rule in rules)
    assert any(rule["source"] == "172.16.0.0/12" and 9000 in rule["ports"] for rule in rules)
    assert any(rule["source"] == "192.168.0.0/16" and 9000 in rule["ports"] for rule in rules)


def test_step_ca_runtime_uses_shared_docker_bridge_chain_checks_before_startup() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))

    chain_task = next(
        task
        for task in tasks
        if task["name"] == "Ensure Docker bridge networking chains are ready before step-ca startup"
    )

    assert chain_task["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert chain_task["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert chain_task["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert chain_task["vars"]["common_docker_bridge_chains_require_nat_chain"] is True


def test_step_ca_runtime_recovers_docker_daemon_failures_during_image_pull() -> None:
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "Pull the step-ca container image and recover Docker daemon availability" in tasks
    assert "Cannot connect to the Docker daemon" in tasks
    assert "- name: Restart Docker before retrying the step-ca image pull" in tasks
    assert "common_docker_daemon_restart_reason: step-ca image pull recovery" in tasks
    assert "step_ca_docker_info_after_pull_recovery" in tasks
    assert "step_ca_pull_recovery_retries" in tasks
    assert "step_ca_pull_recovery_delay_seconds" in tasks
    assert "Retry pulling the step-ca container image after Docker recovery" in tasks


def test_step_ca_compose_template_overrides_image_healthcheck_with_repo_managed_probe() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "healthcheck:" in template
    assert "curl -fsS https://127.0.0.1:{{ step_ca_api_port }}{{ step_ca_healthcheck_path }}" in template
    assert "--cacert {{ step_ca_home }}/certs/root_ca.crt >/dev/null" in template
    assert "start_period: 10s" in template
