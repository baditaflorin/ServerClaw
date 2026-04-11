from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "nextcloud_runtime" / "tasks" / "main.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "nextcloud_runtime" / "defaults" / "main.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "nextcloud_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = REPO_ROOT / "roles" / "nextcloud_runtime" / "templates" / "nextcloud.env.ctmpl.j2"
VERIFY_TASKS = REPO_ROOT / "roles" / "nextcloud_runtime" / "tasks" / "verify.yml"
OCC_COMMAND_TASKS = REPO_ROOT / "roles" / "nextcloud_runtime" / "tasks" / "occ_command.yml"
POSTGRES_TASKS = REPO_ROOT / "roles" / "nextcloud_postgres" / "tasks" / "main.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_runtime_defaults_pin_public_hostname_and_local_artifacts() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())
    assert (
        defaults["nextcloud_port"] == "{{ platform_service_topology | platform_service_port('nextcloud', 'internal') }}"
    )
    assert defaults["nextcloud_public_hostname"] == "{{ platform_service_topology.nextcloud.public_hostname }}"
    assert (
        defaults["nextcloud_database_host"]
        == "{{ hostvars[hostvars['proxmox_florin'].postgres_ha.initial_primary].ansible_host }}"
    )
    assert defaults["nextcloud_admin_password_local_file"].endswith("/.local/nextcloud/admin-password.txt")
    assert defaults["nextcloud_redis_password_local_file"].endswith("/.local/nextcloud/redis-password.txt")
    assert defaults["nextcloud_occ_command_retries"] == 5
    assert defaults["nextcloud_occ_command_delay_seconds"] == 5


def test_runtime_uses_openbao_secret_injection_for_database_admin_and_redis_passwords() -> None:
    template = ENV_TEMPLATE.read_text()
    assert "kv/data/{{ nextcloud_openbao_secret_path }}" in template
    assert "POSTGRES_PASSWORD" in template
    assert "NEXTCLOUD_ADMIN_PASSWORD" in template
    assert "REDIS_HOST_PASSWORD" in template


def test_compose_template_exposes_nextcloud_port_and_cron_sidecar() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert '"{{ nextcloud_port }}:80"' in template
    assert "{{ nextcloud_data_dir }}:/var/www/html" in template
    assert "entrypoint:" in template
    assert "/cron.sh" in template


def test_verify_tasks_check_status_admin_and_background_job_mode() -> None:
    tasks = load_tasks(VERIFY_TASKS)
    status_task = next(task for task in tasks if task.get("name") == "Verify the Nextcloud local status endpoint")
    admin_task = next(task for task in tasks if task.get("name") == "Verify the bootstrap Nextcloud admin exists")
    background_task = next(
        task for task in tasks if task.get("name") == "Verify Nextcloud background jobs run in cron mode"
    )

    assert status_task["ansible.builtin.uri"]["url"] == "{{ nextcloud_internal_base_url }}/status.php"
    assert admin_task["ansible.builtin.command"]["argv"][-3:] == [
        "user:info",
        "{{ nextcloud_admin_user }}",
        "--output=json",
    ]
    assert admin_task["retries"] == "{{ nextcloud_occ_command_retries | int }}"
    assert admin_task["delay"] == "{{ nextcloud_occ_command_delay_seconds | int }}"
    assert admin_task["until"] == "nextcloud_verify_admin.rc == 0"
    assert background_task["ansible.builtin.command"]["argv"][-4:] == [
        "occ",
        "config:app:get",
        "core",
        "backgroundjobs_mode",
    ]
    assert background_task["retries"] == "{{ nextcloud_occ_command_retries | int }}"
    assert background_task["delay"] == "{{ nextcloud_occ_command_delay_seconds | int }}"
    assert background_task["until"] == "nextcloud_verify_background_jobs.rc == 0"


def test_runtime_occ_mutations_retry_when_docker_exec_is_transiently_unavailable() -> None:
    tasks = load_tasks(ROLE_TASKS)
    trusted_domains_task = next(
        task for task in tasks if task.get("name") == "Ensure Nextcloud trusted domains include the public hostname"
    )
    redis_password_task = next(
        task for task in tasks if task.get("name") == "Ensure Nextcloud Redis password is configured"
    )
    occ_helper_tasks = load_tasks(OCC_COMMAND_TASKS)
    run_command_task = next(
        task for task in occ_helper_tasks if task.get("name") == "{{ nextcloud_occ_command_description }}"
    )
    recovery_fact = next(
        task
        for task in occ_helper_tasks
        if task.get("name") == "Detect whether the Nextcloud OCC command needs runtime recovery"
    )
    recover_block = next(
        task
        for task in occ_helper_tasks
        if task.get("name") == "Recover the Nextcloud runtime after a concurrent interruption"
    )
    retry_after_recovery = next(
        task
        for task in recover_block["block"]
        if task.get("name") == "Retry the Nextcloud OCC command after runtime recovery"
    )

    assert trusted_domains_task["ansible.builtin.include_tasks"] == "occ_command.yml"
    assert trusted_domains_task["vars"]["nextcloud_occ_command_description"] == (
        "Ensure Nextcloud trusted domains include the public hostname"
    )
    assert trusted_domains_task["vars"]["nextcloud_occ_command_argv"][-3:] == [
        "trusted_domains",
        "1",
        "--value={{ nextcloud_public_hostname }}",
    ]
    assert redis_password_task["ansible.builtin.include_tasks"] == "occ_command.yml"
    assert redis_password_task["vars"]["nextcloud_occ_command_no_log"] is True
    assert run_command_task["retries"] == "{{ nextcloud_occ_command_retries | int }}"
    assert run_command_task["delay"] == "{{ nextcloud_occ_command_delay_seconds | int }}"
    assert run_command_task["until"] == "nextcloud_occ_command_result.rc == 0"
    recovery_text = recovery_fact["ansible.builtin.set_fact"]["nextcloud_occ_command_recovery_needed"]
    assert "is not running" in recovery_text
    assert "Cannot connect to the Docker daemon" in recovery_text
    assert "context deadline exceeded" in recovery_text
    assert recover_block["when"] == "nextcloud_occ_command_recovery_needed"
    wait_for_docker = next(
        task
        for task in recover_block["block"]
        if task.get("name") == "Wait for Docker to be active before recovering the Nextcloud runtime"
    )
    assert wait_for_docker["ansible.builtin.command"]["argv"] == ["systemctl", "is-active", "docker"]
    assert wait_for_docker["until"] == "nextcloud_docker_active_after_occ_failure.stdout | trim == 'active'"
    assert wait_for_docker["retries"] == 30
    assert retry_after_recovery["until"] == "nextcloud_occ_command_retry_result.rc == 0"
    assert retry_after_recovery["retries"] == "{{ nextcloud_occ_command_retries | int }}"
    assert retry_after_recovery["delay"] == "{{ nextcloud_occ_command_delay_seconds | int }}"


def test_runtime_resets_stale_compose_networks_before_retrying_startup() -> None:
    tasks = load_tasks(ROLE_TASKS)
    network_inspect = next(
        task for task in tasks if task.get("name") == "Check whether the Nextcloud compose network exists"
    )
    container_inspect = next(
        task for task in tasks if task.get("name") == "Check whether the Nextcloud app container already exists"
    )
    reset_task = next(
        task
        for task in tasks
        if task.get("name") == "Reset stale Nextcloud compose resources when the compose network is missing"
    )
    startup = next(
        task for task in tasks if task.get("name") == "Start the Nextcloud runtime and recover stale compose networks"
    )

    assert network_inspect["ansible.builtin.command"]["argv"] == ["docker", "network", "inspect", "nextcloud_default"]
    assert container_inspect["ansible.builtin.command"]["argv"] == [
        "docker",
        "inspect",
        "{{ nextcloud_container_name }}",
    ]
    assert reset_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert reset_task["when"] == [
        "nextcloud_container_inspect.rc == 0",
        "nextcloud_compose_network_inspect.rc != 0",
    ]

    start_task = next(task for task in startup["block"] if task.get("name") == "Start the Nextcloud runtime")
    recovery_fact = next(
        task
        for task in startup["rescue"]
        if task.get("name")
        == "Flag Docker bridge-chain and stale Nextcloud compose network failures after startup failure"
    )
    unexpected_failure = next(
        task for task in startup["rescue"] if task.get("name") == "Surface unexpected Nextcloud startup failures"
    )
    retry_reset = next(
        task
        for task in startup["rescue"]
        if task.get("name") == "Reset stale Nextcloud compose resources after startup failure"
    )
    restart_docker = next(
        task
        for task in startup["rescue"]
        if task.get("name")
        == "Fail closed before an unsafe Docker daemon restart while repairing Nextcloud bridge chains"
    )
    reassert_chains = next(
        task
        for task in startup["rescue"]
        if task.get("name") == "Ensure Docker bridge networking chains are present before retrying Nextcloud startup"
    )
    retry_start = next(
        task
        for task in startup["rescue"]
        if task.get("name") == "Retry Nextcloud startup after resetting stale compose resources"
    )

    assert start_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "--remove-orphans"]
    assert (
        "No chain/target/match by that name"
        in recovery_fact["ansible.builtin.set_fact"]["nextcloud_docker_bridge_chain_missing"]
    )
    assert (
        "Unable to enable ACCEPT OUTGOING rule"
        in recovery_fact["ansible.builtin.set_fact"]["nextcloud_docker_bridge_chain_missing"]
    )
    assert "failed to create endpoint" in recovery_fact["ansible.builtin.set_fact"]["nextcloud_compose_network_missing"]
    assert "does not exist" in recovery_fact["ansible.builtin.set_fact"]["nextcloud_compose_network_missing"]
    assert unexpected_failure["when"] == (
        "not nextcloud_docker_bridge_chain_missing and not nextcloud_compose_network_missing"
    )
    assert retry_reset["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert retry_reset["when"] == "nextcloud_compose_network_missing"
    assert retry_reset["failed_when"] is False
    restart_helper = restart_docker["ansible.builtin.include_role"]
    assert restart_helper["name"] == "lv3.platform.common"
    assert restart_helper["tasks_from"] == "docker_daemon_restart"
    assert restart_docker["vars"]["common_docker_daemon_restart_service_name"] == "docker"
    assert restart_docker["vars"]["common_docker_daemon_restart_reason"] == "Nextcloud startup bridge-chain recovery"
    assert restart_docker["when"] == "nextcloud_docker_bridge_chain_missing"
    include_role = reassert_chains["ansible.builtin.include_role"]
    assert include_role["name"] == "lv3.platform.common"
    assert include_role["tasks_from"] == "docker_bridge_chains"
    assert reassert_chains["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert reassert_chains["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    assert reassert_chains["when"] == "nextcloud_docker_bridge_chain_missing"
    assert retry_start["ansible.builtin.command"]["argv"][-4:] == ["up", "-d", "--remove-orphans", "--force-recreate"]
    assert retry_start["when"] == "nextcloud_docker_bridge_chain_missing or nextcloud_compose_network_missing"


def test_runtime_force_recreates_nextcloud_when_network_attachment_is_missing() -> None:
    tasks = load_tasks(ROLE_TASKS)
    network_check = next(
        task for task in tasks if task.get("name") == "Check whether Nextcloud has an attached Docker network"
    )
    recovery_block = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate Nextcloud when Docker network attachment is missing"
    )
    network_cleanup = next(
        task
        for task in recovery_block["block"]
        if task.get("name") == "Remove the stale Nextcloud compose network before retrying startup"
    )
    retry_up = next(
        task
        for task in recovery_block["block"]
        if task.get("name") == "Force-recreate Nextcloud after local network attachment recovery"
    )
    network_recheck = next(task for task in tasks if task.get("name") == "Recheck Nextcloud Docker network attachment")

    assert "{{json .NetworkSettings.Networks}}" in network_check["ansible.builtin.shell"]
    assert recovery_block["when"] == "nextcloud_network_attachment_check.stdout | trim in ['', '{}', 'null']"
    assert "^{{ nextcloud_site_dir | basename }}_default$" in network_cleanup["ansible.builtin.shell"]
    assert retry_up["ansible.builtin.command"]["argv"][-4:] == ["up", "-d", "--remove-orphans", "--force-recreate"]
    assert network_recheck["until"] == "nextcloud_network_attachment_recheck.stdout | trim not in ['', '{}', 'null']"


def test_postgres_role_provisions_named_database_and_role() -> None:
    tasks = load_tasks(POSTGRES_TASKS)
    create_role = next(task for task in tasks if task.get("name") == "Create the Nextcloud database role")
    create_db = next(task for task in tasks if task.get("name") == "Create the Nextcloud PostgreSQL database")
    assert (
        "CREATE ROLE {{ nextcloud_database_user }} LOGIN PASSWORD" in create_role["ansible.builtin.command"]["argv"][-1]
    )
    assert (
        create_db["ansible.builtin.command"]["argv"][-1]
        == "CREATE DATABASE {{ nextcloud_database_name }} OWNER {{ nextcloud_database_user }}"
    )


def test_host_network_policy_allows_edge_and_private_nextcloud_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    nginx_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "nginx-lv3" and 8084 in rule["ports"])
    guest_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 8084 in rule["ports"])
    assert nginx_rule["description"].lower().startswith("reverse proxy access")
    assert guest_rule["description"].lower().startswith("private guest-to-guest")
