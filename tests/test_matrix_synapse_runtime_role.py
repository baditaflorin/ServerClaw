from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "defaults" / "main.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "matrix-synapse.env.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "matrix-synapse.env.ctmpl.j2"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "docker-compose.yml.j2"
HOMESERVER_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "homeserver.yaml.j2"
TASKS_FILE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "tasks" / "main.yml"
PUBLIC_VERIFY_FILE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "tasks" / "public_verify.yml"
VERIFY_FILE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "tasks" / "verify.yml"
DISCORD_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "mautrix-discord-config.yaml.j2"
WHATSAPP_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "mautrix-whatsapp-config.yaml.j2"


def test_matrix_synapse_runtime_defaults_expose_internal_controller_and_public_urls() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert (
        defaults["matrix_synapse_port"]
        == "{{ hostvars['proxmox-host'].platform_service_topology | platform_service_port('matrix_synapse', 'internal') }}"
    )
    assert (
        defaults["matrix_synapse_host_proxy_port"]
        == "{{ hostvars['proxmox-host'].platform_service_topology | platform_service_port('matrix_synapse', 'controller') }}"
    )
    assert (
        defaults["matrix_synapse_internal_base_url"]
        == "{{ hostvars['proxmox-host'].platform_service_topology | platform_service_url('matrix_synapse', 'internal') }}"
    )
    assert (
        defaults["matrix_synapse_controller_url"]
        == "{{ hostvars['proxmox-host'].platform_service_topology | platform_service_url('matrix_synapse', 'controller') }}"
    )
    assert (
        defaults["matrix_synapse_public_base_url"]
        == "{{ hostvars['proxmox-host'].platform_service_topology.matrix_synapse.urls.public }}/"
    )
    assert defaults["matrix_synapse_container_data_dir"] == "/data"
    assert (
        defaults["matrix_synapse_ops_access_token_local_file"]
        == "/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/matrix-synapse/ops-access-token.txt"
    )
    assert (
        defaults["matrix_synapse_log_config_container_file"]
        == "{{ matrix_synapse_container_data_dir }}/{{ matrix_synapse_server_name }}.log.config"
    )
    assert (
        defaults["matrix_synapse_signing_key_container_file"]
        == "{{ matrix_synapse_container_data_dir }}/{{ matrix_synapse_server_name }}.signing.key"
    )
    assert (
        defaults["matrix_synapse_mautrix_discord_image"]
        == "{{ container_image_catalog.images.matrix_mautrix_discord_runtime.ref }}"
    )
    assert (
        defaults["matrix_synapse_mautrix_whatsapp_image"]
        == "{{ container_image_catalog.images.matrix_mautrix_whatsapp_runtime.ref }}"
    )
    assert defaults["matrix_synapse_public_smoke_bot_user_ids"] == [
        "{{ matrix_synapse_mautrix_discord_bot_user_id }}",
        "{{ matrix_synapse_mautrix_whatsapp_bot_user_id }}",
    ]


def test_matrix_synapse_env_templates_pin_the_homeserver_config_path() -> None:
    env_template = ENV_TEMPLATE.read_text()
    ctmpl_template = CTMPL_TEMPLATE.read_text()

    assert "SYNAPSE_CONFIG_PATH=/data/homeserver.yaml" in env_template
    assert "SYNAPSE_CONFIG_PATH=/data/homeserver.yaml" in ctmpl_template
    assert "MATRIX_SYNAPSE_DATABASE_PASSWORD={{ matrix_synapse_database_password }}" in env_template
    assert "[[ .Data.data.MATRIX_SYNAPSE_DATABASE_PASSWORD ]]" in ctmpl_template


def test_matrix_synapse_compose_template_only_exposes_the_client_listener() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()

    assert 'ports:\n      - "{{ matrix_synapse_port }}:8008"' in compose_template
    assert "8448" not in compose_template
    assert "openbao-agent:" in compose_template
    assert (
        "{{ matrix_synapse_mautrix_discord_registration_file }}:/appservices/mautrix-discord-registration.yaml:ro"
        in compose_template
    )
    assert (
        "{{ matrix_synapse_mautrix_whatsapp_registration_file }}:/appservices/mautrix-whatsapp-registration.yaml:ro"
        in compose_template
    )
    assert "mautrix-discord:" in compose_template
    assert "mautrix-whatsapp:" in compose_template


def test_matrix_synapse_homeserver_template_is_client_only_and_x_forwarded() -> None:
    homeserver_template = HOMESERVER_TEMPLATE.read_text()

    assert "x_forwarded: true" in homeserver_template
    assert "- client" in homeserver_template
    assert "allow_public_rooms_over_federation: false" in homeserver_template
    assert 'public_baseurl: "{{ matrix_synapse_public_base_url }}"' in homeserver_template
    assert 'log_config: "{{ matrix_synapse_log_config_container_file }}"' in homeserver_template
    assert 'signing_key_path: "{{ matrix_synapse_signing_key_container_file }}"' in homeserver_template
    assert "app_service_config_files:" in homeserver_template


def test_matrix_synapse_runtime_generates_signing_material_and_bootstrap_user() -> None:
    tasks = yaml.safe_load(TASKS_FILE.read_text())
    task_file = TASKS_FILE.read_text()
    bootstrap_pull_task = next(
        task
        for task in tasks
        if task.get("name") == "Pre-pull the Matrix Synapse image when bootstrap artifacts are missing"
    )
    generate_task = next(
        task
        for task in tasks
        if task.get("name") == "Generate the initial Matrix Synapse signing material and log config"
    )
    compose_pull_task = next(task for task in tasks if task.get("name") == "Pull the Matrix Synapse image")
    startup_block = next(
        task
        for task in tasks
        if task.get("name") == "Start the Matrix Synapse stack and recover stale compose networks"
    )
    retry_start_task = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Retry Matrix Synapse startup after resetting stale compose resources"
    )
    recreate_start_task = next(
        task
        for task in startup_block["block"]
        if task.get("name") == "Recreate the Matrix Synapse stack when config-backed files changed"
    )
    normal_start_task = next(
        task for task in startup_block["block"] if task.get("name") == "Start the Matrix Synapse stack"
    )
    docker_info_task = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Wait for the Docker daemon to answer after Matrix Synapse network recovery"
    )
    remove_broken_container_task = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Remove the broken Matrix Synapse container before retrying startup"
    )
    admin_login_probe_task = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Matrix Synapse ops admin already accepts the bootstrap password"
    )
    admin_registration_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Ensure the Matrix Synapse ops admin exists when the bootstrap password does not work yet"
    )
    admin_login_ready_task = next(
        task for task in tasks if task.get("name") == "Confirm the Matrix Synapse ops admin password login succeeds"
    )

    assert "Generate the initial Matrix Synapse signing material and log config" in task_file
    assert "register_new_matrix_user" in task_file
    assert "--exists-ok" in task_file
    assert "/_matrix/client/v3/login" in task_file
    assert "Mirror the Matrix Synapse signing key to the control machine" in task_file
    assert bootstrap_pull_task["retries"] == 3
    assert bootstrap_pull_task["until"] == "matrix_synapse_initial_pull.rc == 0"
    assert tasks.index(bootstrap_pull_task) < tasks.index(generate_task)
    assert compose_pull_task["retries"] == 3
    assert compose_pull_task["until"] == "matrix_synapse_pull.rc == 0"
    assert "Assert Matrix Synapse bootstrap generation produced the required artifacts" in task_file
    assert "matrix_synapse_generate.rc == 0" in task_file
    assert "Generate the mautrix Discord registration when needed" in task_file
    assert "Generate the mautrix WhatsApp registration when needed" in task_file
    assert "Ensure the mautrix bridge registrations are readable by Synapse" in task_file
    assert "Decide whether the Matrix Synapse stack must be force-recreated for config-backed changes" in task_file
    assert (
        "Flag Docker bridge-chain and stale Matrix Synapse compose network failures after startup failure" in task_file
    )
    assert "failed to create endpoint" in task_file
    assert docker_info_task["until"] == "matrix_synapse_docker_info.rc == 0"
    assert remove_broken_container_task["ansible.builtin.command"]["argv"][-1] == "{{ matrix_synapse_container_name }}"
    assert recreate_start_task["when"] == "matrix_synapse_force_recreate_stack"
    assert recreate_start_task["ansible.builtin.command"]["argv"][-4:] == [
        "up",
        "-d",
        "--remove-orphans",
        "--force-recreate",
    ]
    assert normal_start_task["when"] == "not matrix_synapse_force_recreate_stack"
    assert retry_start_task["ansible.builtin.command"]["argv"][-4:] == [
        "up",
        "-d",
        "--remove-orphans",
        "--force-recreate",
    ]
    assert admin_login_probe_task["failed_when"] is False
    assert admin_registration_task["when"] == "matrix_synapse_admin_login_probe.status != 200"
    assert admin_registration_task["failed_when"] is False
    assert admin_login_ready_task["until"] == "matrix_synapse_admin_login_ready.status == 200"
    assert admin_login_ready_task["ansible.builtin.uri"]["status_code"] == 200


def test_matrix_synapse_bridge_templates_and_public_verify_cover_discord_and_whatsapp() -> None:
    public_verify = PUBLIC_VERIFY_FILE.read_text()
    verify = VERIFY_FILE.read_text()
    discord_template = DISCORD_TEMPLATE.read_text()
    whatsapp_template = WHATSAPP_TEMPLATE.read_text()

    assert "matrix_admin_register.py" in public_verify
    assert "matrix_bridge_smoke.py" in public_verify
    assert "--access-token-file" in public_verify
    assert "stdout_lines == ['running', 'running']" in verify
    assert "command_prefix: '!discord'" in discord_template
    assert "command_prefix: '!wa'" in whatsapp_template
