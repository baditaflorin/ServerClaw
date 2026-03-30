from pathlib import Path

import json
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "defaults" / "main.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "templates" / "docker-compose.yml.j2"
STALWART_TEMPLATE_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "templates" / "stalwart-config.toml.j2"
TASKS_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "tasks" / "main.yml"
ROTATE_TASKS_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "tasks" / "rotate.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
CONTROL_PLANE_LANES_PATH = REPO_ROOT / "config" / "control-plane-lanes.json"


def test_defaults_define_private_submission_port() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    assert defaults["mail_platform_docker_network_name"] == "mail-platform_default"
    assert defaults["mail_platform_internal_submission_port"] == (
        "{{ hostvars['proxmox_florin'].platform_port_assignments.mail_platform_internal_submission_port | default(1587) }}"
    )


def test_stalwart_template_adds_private_submission_listener() -> None:
    template = STALWART_TEMPLATE_PATH.read_text()
    assert "[server.listener.internal_submission]" in template
    assert 'bind = "[::]:{{ mail_platform_internal_submission_port }}"' in template
    assert "tls.enable = false" in template
    assert """{ if = "listener == 'internal_submission'", then = "[plain, login]" }""" in template
    assert 'allow-plain-text = true' in template


def test_compose_template_publishes_private_submission_port_on_vm_ip() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text()
    assert '"{{ ansible_host }}:{{ mail_platform_internal_submission_port }}:{{ mail_platform_internal_submission_port }}"' in template


def test_host_firewall_only_opens_private_submission_for_local_docker_networks() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    relay_rules = [rule for rule in docker_runtime_rules if 1587 in rule["ports"]]
    assert {rule["source"] for rule in relay_rules} == {"172.16.0.0/12", "192.168.0.0/16"}


def test_control_plane_lane_points_at_private_submission_relay() -> None:
    lanes = json.loads(CONTROL_PLANE_LANES_PATH.read_text())
    message_surfaces = lanes["lanes"]["message"]["current_surfaces"]
    submission = next(surface for surface in message_surfaces if surface["id"] == "mail-platform-submission")
    assert submission["endpoint"] == "10.10.10.20:1587"


def test_mail_platform_runtime_verifies_plaintext_private_submission_auth() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())
    verify_task = next(
        task
        for task in tasks
        if task.get("name") == "Verify the private mail submission relay keeps STARTTLS disabled and accepts auth"
    )
    shell = verify_task["ansible.builtin.shell"]
    assert "starttls" in shell
    assert 'mail_platform_mailbox_password_file' in shell
    assert 'mail_platform_mailbox_login' in shell


def test_mail_platform_verify_role_checks_plaintext_private_submission_auth() -> None:
    verify_tasks = yaml.safe_load((REPO_ROOT / "roles" / "mail_platform_runtime" / "tasks" / "verify.yml").read_text())
    verify_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Verify the private mail submission relay keeps STARTTLS disabled and accepts auth"
    )
    shell = verify_task["ansible.builtin.shell"]
    assert "starttls" in shell
    assert 'mail_platform_mailbox_password_file' in shell


def test_mail_platform_runtime_restores_docker_nat_chain_before_startup_and_rotation() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())
    rotate_tasks = yaml.safe_load(ROTATE_TASKS_PATH.read_text())
    nat_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker nat chain exists before recreating mail-platform published ports"
    )
    nat_restore = next(
        task
        for task in tasks
        if task.get("name") == "Restore Docker networking when the nat chain is missing before mail-platform startup"
    )
    nat_recheck = next(
        task
        for task in tasks
        if task.get("name") == "Recheck the Docker nat chain before mail-platform startup"
    )
    docker_info = next(
        task
        for task in tasks
        if task.get("name") == "Wait for the Docker daemon to answer after networking recovery"
    )
    health_probe = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the current mail gateway health endpoint is healthy before startup"
    )
    cleanup_task = next(
        task
        for task in tasks
        if task.get("name") == "Remove stale mail-platform compose resources before force recreate"
    )
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the mail platform stack after Docker networking recovery"
    )
    force_recreate_assert = next(
        task for task in tasks if task.get("name") == "Assert the mail platform force-recreate succeeded"
    )
    network_consumers = next(
        task
        for task in tasks
        if task.get("name") == "Read external mail-platform network consumers before forced network reset"
    )
    network_remove = next(
        task
        for task in tasks
        if task.get("name") == "Remove the shared mail-platform network before retrying the force recreate"
    )
    network_reset_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Re-run the mail platform force recreate after rebuilding the shared network"
    )
    start_task = next(task for task in tasks if task.get("name") == "Start the mail platform stack")
    startup_assert = next(task for task in tasks if task.get("name") == "Assert the mail platform startup succeeded")
    rotate_nat_check = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Check whether the Docker nat chain exists before mail-platform rotation recreates published ports"
    )
    rotate_nat_restore = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Restore Docker networking when the nat chain is missing before mail-platform rotation"
    )
    rotate_nat_recheck = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Recheck the Docker nat chain before mail-platform rotation"
    )
    rotate_docker_info = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Wait for the Docker daemon to answer after networking recovery for mail-platform rotation"
    )
    rotate_cleanup_task = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Remove stale mail-platform compose resources before rotation force recreate"
    )
    rotate_force_recreate = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Force-recreate the mail platform runtime with rotated secret material after Docker networking recovery"
    )
    rotate_force_recreate_assert = next(
        task for task in rotate_tasks if task.get("name") == "Assert the mail platform rotation force-recreate succeeded"
    )
    rotate_start_task = next(
        task for task in rotate_tasks if task.get("name") == "Restart the mail platform runtime with rotated secret material"
    )
    rotate_assert = next(
        task for task in rotate_tasks if task.get("name") == "Assert the mail platform rotation restart succeeded"
    )
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert nat_recheck["until"] == "mail_platform_docker_nat_chain_recheck.rc == 0"
    assert docker_info["ansible.builtin.command"]["argv"] == ["docker", "info", "--format", '{{ "{{.ServerVersion}}" }}']
    assert health_probe["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ mail_platform_gateway_port }}/healthz"
    assert cleanup_task["ansible.builtin.command"]["argv"][-6:] == [
        "rm",
        "--stop",
        "--force",
        "openbao-agent",
        "stalwart",
        "mail-gateway",
    ]
    assert cleanup_task["when"] == "mail_platform_force_recreate"
    assert cleanup_task["failed_when"] is False
    assert "docker compose --file" in force_recreate["ansible.builtin.shell"]
    assert "rm --stop --force openbao-agent stalwart mail-gateway || true" in force_recreate["ansible.builtin.shell"]
    assert "up -d --force-recreate --remove-orphans" in force_recreate["ansible.builtin.shell"]
    assert force_recreate["until"] == "mail_platform_up.rc == 0"
    assert network_consumers["ansible.builtin.command"]["argv"][:4] == ["docker", "network", "inspect", "{{ mail_platform_docker_network_name }}"]
    assert network_remove["ansible.builtin.command"]["argv"] == ["docker", "network", "rm", "{{ mail_platform_docker_network_name }}"]
    assert "up -d --force-recreate --remove-orphans" in network_reset_recreate["ansible.builtin.shell"]
    assert network_reset_recreate["until"] == "mail_platform_up_network_reset.rc == 0"
    assert force_recreate_assert["when"] == "mail_platform_force_recreate"
    assert force_recreate_assert["ansible.builtin.assert"]["that"] == [
        "mail_platform_up.rc == 0 or (mail_platform_up_network_reset.rc | default(1)) == 0"
    ]
    assert start_task["until"] == "mail_platform_up.rc == 0"
    assert startup_assert["when"] == "not mail_platform_force_recreate"
    assert startup_assert["ansible.builtin.assert"]["that"] == ["mail_platform_up.rc == 0"]
    assert rotate_nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert rotate_nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert rotate_nat_recheck["until"] == "mail_platform_rotation_docker_nat_chain_recheck.rc == 0"
    assert rotate_docker_info["ansible.builtin.command"]["argv"] == ["docker", "info", "--format", '{{ "{{.ServerVersion}}" }}']
    assert rotate_cleanup_task["ansible.builtin.command"]["argv"][-5:] == [
        "rm",
        "--stop",
        "--force",
        "stalwart",
        "mail-gateway",
    ]
    assert rotate_cleanup_task["when"] == "mail_platform_rotation_docker_nat_chain.rc != 0"
    assert rotate_cleanup_task["failed_when"] is False
    assert "docker compose --file" in rotate_force_recreate["ansible.builtin.shell"]
    assert "rm --stop --force stalwart mail-gateway || true" in rotate_force_recreate["ansible.builtin.shell"]
    assert "up -d --force-recreate stalwart mail-gateway" in rotate_force_recreate["ansible.builtin.shell"]
    assert rotate_force_recreate["until"] == "mail_platform_rotation_up.rc == 0"
    assert rotate_force_recreate_assert["when"] == "mail_platform_rotation_docker_nat_chain.rc != 0"
    assert rotate_force_recreate_assert["ansible.builtin.assert"]["that"] == ["mail_platform_rotation_up.rc == 0"]
    assert rotate_start_task["until"] == "mail_platform_rotation_up.rc == 0"
    assert rotate_assert["when"] == "mail_platform_rotation_docker_nat_chain.rc == 0"
    assert rotate_assert["ansible.builtin.assert"]["that"] == ["mail_platform_rotation_up.rc == 0"]


def test_mail_platform_runtime_force_recreates_when_runtime_inputs_change() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())
    force_recreate_fact = next(
        task
        for task in tasks
        if task.get("name") == "Record whether the mail platform startup needs a force recreate"
    )
    expression = force_recreate_fact["ansible.builtin.set_fact"]["mail_platform_force_recreate"]
    assert "mail_platform_stalwart_config.changed" in expression
    assert "mail_platform_gateway_env.changed" in expression
    assert "mail_platform_gateway_profiles.changed" in expression
    assert "mail_platform_compose.changed" in expression
    assert "mail_platform_gateway_build.changed" in expression
    assert "mail_platform_gateway_health_probe.status" in expression


def test_mail_platform_runtime_stages_openbao_env_template_locally() -> None:
    tasks_text = TASKS_PATH.read_text()
    assert "Create a controller-local staging path for the mail gateway OpenBao agent runtime env template" in tasks_text
    assert "Render the mail gateway OpenBao agent runtime env template to a controller-local file" in tasks_text
    assert 'common_openbao_compose_env_agent_template_local_file: "{{ mail_platform_openbao_agent_template_local.path }}"' in tasks_text
    assert "Remove the controller-local mail gateway OpenBao agent runtime env template staging file" in tasks_text
    assert "common_openbao_compose_env_agent_template_src: mail-gateway.env.ctmpl.j2" not in tasks_text


def test_mail_platform_defaults_resolve_otlp_endpoint_from_proxmox_service_topology() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    assert defaults["mail_platform_gateway_trace_otlp_endpoint"] == (
        "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_url('grafana', 'otlp_http') }}"
    )
