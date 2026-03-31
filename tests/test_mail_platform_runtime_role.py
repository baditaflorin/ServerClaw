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
    assert defaults["mail_platform_internal_submission_port"] == (
        "{{ hostvars['proxmox_florin'].platform_port_assignments.mail_platform_internal_submission_port | default(1587) }}"
    )


def test_defaults_define_submission_auth_retry_budget() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    assert defaults["mail_platform_submission_auth_retries"] == 12
    assert defaults["mail_platform_submission_auth_delay_seconds"] == 5


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


def test_defaults_resolve_mail_gateway_otlp_endpoint_from_canonical_host_topology() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    assert defaults["mail_platform_gateway_trace_otlp_endpoint"] == (
        "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_url('grafana', 'otlp_http') }}"
    )


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
    assert verify_task["register"] == "mail_platform_submission_auth_check"
    assert verify_task["retries"] == "{{ mail_platform_submission_auth_retries }}"
    assert verify_task["delay"] == "{{ mail_platform_submission_auth_delay_seconds }}"
    assert verify_task["until"] == "mail_platform_submission_auth_check.rc == 0"


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
    assert verify_task["register"] == "mail_platform_verify_submission_auth"
    assert verify_task["retries"] == "{{ mail_platform_submission_auth_retries }}"
    assert verify_task["delay"] == "{{ mail_platform_submission_auth_delay_seconds }}"
    assert verify_task["until"] == "mail_platform_verify_submission_auth.rc == 0"


def test_mail_platform_runtime_bootstraps_mail_principals_through_gateway_crud_api() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())
    readiness_task = next(
        task
        for task in tasks
        if task.get("name") == "Wait for the mail gateway CRUD API to answer before bootstrapping mail principals"
    )
    domain_task = next(
        task
        for task in tasks
        if task.get("name") == "Upsert the managed mail domain through the mail gateway CRUD API"
    )
    mailbox_task = next(
        task
        for task in tasks
        if task.get("name") == "Upsert the managed mailbox accounts through the mail gateway CRUD API"
    )
    assert readiness_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ mail_platform_gateway_port }}/v1/domains"
    assert readiness_task["retries"] == "{{ mail_platform_submission_auth_retries }}"
    assert readiness_task["delay"] == "{{ mail_platform_submission_auth_delay_seconds }}"
    assert readiness_task["until"] == "mail_platform_gateway_catalog_ready.status == 200"
    assert domain_task["ansible.builtin.uri"]["method"] == "PUT"
    assert "/v1/domains/" in domain_task["ansible.builtin.uri"]["url"]
    assert domain_task["ansible.builtin.uri"]["headers"]["X-API-Key"] == "{{ mail_platform_gateway_api_key }}"
    assert domain_task["changed_when"] == "mail_platform_domain_bootstrap.json.status != 'unchanged'"
    assert mailbox_task["ansible.builtin.uri"]["method"] == "PUT"
    assert "/v1/mailboxes/" in mailbox_task["ansible.builtin.uri"]["url"]
    assert mailbox_task["ansible.builtin.uri"]["body"]["password"] == "{{ item.password }}"
    assert mailbox_task["register"] == "mail_platform_mailbox_bootstrap"
    assert mailbox_task["changed_when"] == "mail_platform_mailbox_bootstrap.json.status != 'unchanged'"


def test_mail_platform_runtime_verifies_managed_catalog_through_gateway_crud_api() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())
    mailboxes_task = next(
        task
        for task in tasks
        if task.get("name") == "Verify the mail gateway CRUD API can list managed mailboxes"
    )
    domain_assert = next(task for task in tasks if task.get("name") == "Assert the managed mail domain is present")
    mailbox_assert = next(task for task in tasks if task.get("name") == "Assert the managed mailbox accounts are present")
    assert mailboxes_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ mail_platform_gateway_port }}/v1/mailboxes"
    assert "mail_platform_gateway_domains.json['items']" in domain_assert["ansible.builtin.assert"]["that"][0]
    assert "mail_platform_gateway_mailboxes.json['items']" in mailbox_assert["ansible.builtin.assert"]["that"][0]


def test_mail_platform_verify_role_checks_managed_catalog_through_gateway_crud_api() -> None:
    verify_tasks = yaml.safe_load((REPO_ROOT / "roles" / "mail_platform_runtime" / "tasks" / "verify.yml").read_text())
    mailboxes_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Verify the mail gateway CRUD API can list managed mailboxes"
    )
    domain_assert = next(task for task in verify_tasks if task.get("name") == "Assert the managed mail domain is present")
    mailbox_assert = next(task for task in verify_tasks if task.get("name") == "Assert the managed mailbox accounts are present")
    assert mailboxes_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ mail_platform_gateway_port }}/v1/mailboxes"
    assert "mail_platform_verify_gateway_domains.json['items']" in domain_assert["ansible.builtin.assert"]["that"][0]
    assert "mail_platform_verify_gateway_mailboxes.json['items']" in mailbox_assert["ansible.builtin.assert"]["that"][0]


def test_mail_platform_runtime_recovers_gateway_publication_after_bridge_chain_loss() -> None:
    tasks = yaml.safe_load(TASKS_PATH.read_text())
    inspect_task = next(
        task
        for task in tasks
        if task.get("name") == "Inspect the mail gateway startup state before waiting on the API"
    )
    detect_task = next(
        task
        for task in tasks
        if task.get("name") == "Detect Docker bridge-chain loss during the mail gateway startup"
    )
    remove_task = next(
        task
        for task in tasks
        if task.get("name") == "Remove the stalled mail gateway container after Docker bridge-chain loss"
    )
    restart_task = next(
        task
        for task in tasks
        if task.get("name") == "Restart Docker to restore bridge networking before retrying the mail gateway startup"
    )
    bridge_task = next(
        task
        for task in tasks
        if task.get("name") == "Ensure Docker bridge networking chains are present before retrying the mail gateway startup"
    )
    retry_task = next(
        task
        for task in tasks
        if task.get("name") == "Retry the mail gateway startup after Docker networking recovery"
    )
    assert inspect_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "inspect",
        "--format",
        "{% raw %}{{.State.Status}}|{{.State.Error}}{% endraw %}",
        "{{ mail_platform_gateway_container_name }}",
    ]
    assert inspect_task["register"] == "mail_platform_gateway_start_state"
    assert "failed programming external connectivity" in detect_task["ansible.builtin.set_fact"][
        "mail_platform_gateway_bridge_chains_missing"
    ]
    assert "No chain/target/match by that name" in detect_task["ansible.builtin.set_fact"][
        "mail_platform_gateway_bridge_chains_missing"
    ]
    assert remove_task["ansible.builtin.command"]["argv"][-2:] == ["-f", "{{ mail_platform_gateway_container_name }}"]
    assert restart_task["ansible.builtin.service"]["name"] == "docker"
    assert bridge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert retry_task["ansible.builtin.command"]["argv"][-5:] == ["up", "-d", "--force-recreate", "--no-deps", "mail-gateway"]
    assert retry_task["until"] == "mail_platform_gateway_retry.rc == 0"


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
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the mail platform stack after Docker networking recovery"
    )
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
    rotate_force_recreate = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Force-recreate the mail platform runtime with rotated secret material after Docker networking recovery"
    )
    network_flag = next(
        task
        for task in tasks
        if task.get("name") == "Flag stale mail platform compose-network failures during startup"
    )
    network_reset = next(
        task
        for task in tasks
        if task.get("name") == "Reset stale mail platform compose resources before retrying startup"
    )
    network_cleanup = next(
        task
        for task in tasks
        if task.get("name") == "Remove the stale mail-platform compose network before retrying startup"
    )
    network_retry = next(
        task
        for task in tasks
        if task.get("name") == "Retry mail platform stack startup after compose-network recovery"
    )
    rotate_network_flag = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Flag stale mail platform compose-network failures during rotation"
    )
    rotate_network_reset = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Reset stale mail platform compose resources before retrying rotation"
    )
    rotate_network_cleanup = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Remove the stale mail-platform compose network before retrying rotation"
    )
    rotate_network_retry = next(
        task
        for task in rotate_tasks
        if task.get("name") == "Retry mail platform rotation after compose-network recovery"
    )
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
    assert force_recreate["failed_when"] is False
    assert "failed to create endpoint" in network_flag["ansible.builtin.set_fact"]["mail_platform_docker_network_missing"]
    assert network_reset["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert "{{ mail_platform_docker_network_name }}" in network_cleanup["ansible.builtin.shell"]
    assert network_cleanup["args"]["executable"] == "/bin/bash"
    assert network_retry["ansible.builtin.command"]["argv"][-2:] == ["--force-recreate", "--remove-orphans"]
    assert rotate_nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert rotate_nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert "--force-recreate" in rotate_force_recreate["ansible.builtin.shell"]
    assert rotate_force_recreate["failed_when"] is False
    assert "failed to create endpoint" in rotate_network_flag["ansible.builtin.set_fact"][
        "mail_platform_rotation_docker_network_missing"
    ]
    assert rotate_network_reset["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert "{{ mail_platform_docker_network_name }}" in rotate_network_cleanup["ansible.builtin.shell"]
    assert rotate_network_cleanup["args"]["executable"] == "/bin/bash"
    assert rotate_network_retry["ansible.builtin.command"]["argv"][-2:] == ["stalwart", "mail-gateway"]


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


def test_mail_platform_runtime_stages_openbao_env_template_locally_before_helper_include() -> None:
    tasks_text = TASKS_PATH.read_text()
    assert "Create a controller-local staging path for the mail platform OpenBao agent runtime env template" in tasks_text
    assert "mail_platform_openbao_agent_template_local" in tasks_text
    assert "Resolve the mail gateway OTLP endpoint before delegating the OpenBao env template render" in tasks_text
    assert "mail_platform_gateway_trace_otlp_endpoint_resolved" in tasks_text
    assert "mail-gateway.env.ctmpl.j2" in tasks_text
    assert "common_openbao_compose_env_agent_template_local_file" in tasks_text
    assert 'common_openbao_compose_env_agent_template_local_file: "{{ mail_platform_openbao_agent_template_local.path }}"' in tasks_text
    assert "Remove the controller-local mail platform OpenBao agent runtime env template staging file" in tasks_text
    assert "common_openbao_compose_env_agent_template_content" not in tasks_text
    assert "common_openbao_compose_env_agent_template_src: mail-gateway.env.ctmpl.j2" not in tasks_text
