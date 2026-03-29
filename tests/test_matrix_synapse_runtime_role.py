from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "defaults" / "main.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "matrix-synapse.env.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "matrix-synapse.env.ctmpl.j2"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "docker-compose.yml.j2"
HOMESERVER_TEMPLATE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "templates" / "homeserver.yaml.j2"
TASKS_FILE = REPO_ROOT / "roles" / "matrix_synapse_runtime" / "tasks" / "main.yml"


def test_matrix_synapse_runtime_defaults_expose_internal_controller_and_public_urls() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["matrix_synapse_port"] == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_port('matrix_synapse', 'internal') }}"
    assert defaults["matrix_synapse_host_proxy_port"] == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_port('matrix_synapse', 'controller') }}"
    assert defaults["matrix_synapse_internal_base_url"] == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_url('matrix_synapse', 'internal') }}"
    assert defaults["matrix_synapse_controller_url"] == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_url('matrix_synapse', 'controller') }}"
    assert defaults["matrix_synapse_public_base_url"] == "{{ hostvars['proxmox_florin'].platform_service_topology.matrix_synapse.urls.public }}/"
    assert defaults["matrix_synapse_container_data_dir"] == "/data"
    assert defaults["matrix_synapse_log_config_container_file"] == "{{ matrix_synapse_container_data_dir }}/{{ matrix_synapse_server_name }}.log.config"
    assert defaults["matrix_synapse_signing_key_container_file"] == "{{ matrix_synapse_container_data_dir }}/{{ matrix_synapse_server_name }}.signing.key"


def test_matrix_synapse_env_templates_pin_the_homeserver_config_path() -> None:
    env_template = ENV_TEMPLATE.read_text()
    ctmpl_template = CTMPL_TEMPLATE.read_text()

    assert "SYNAPSE_CONFIG_PATH=/data/homeserver.yaml" in env_template
    assert "SYNAPSE_CONFIG_PATH=/data/homeserver.yaml" in ctmpl_template
    assert "MATRIX_SYNAPSE_DATABASE_PASSWORD={{ matrix_synapse_database_password }}" in env_template
    assert '[[ .Data.data.MATRIX_SYNAPSE_DATABASE_PASSWORD ]]' in ctmpl_template


def test_matrix_synapse_compose_template_only_exposes_the_client_listener() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()

    assert 'ports:\n      - "{{ matrix_synapse_port }}:8008"' in compose_template
    assert "8448" not in compose_template
    assert "openbao-agent:" in compose_template


def test_matrix_synapse_homeserver_template_is_client_only_and_x_forwarded() -> None:
    homeserver_template = HOMESERVER_TEMPLATE.read_text()

    assert "x_forwarded: true" in homeserver_template
    assert "- client" in homeserver_template
    assert "allow_public_rooms_over_federation: false" in homeserver_template
    assert "public_baseurl: \"{{ matrix_synapse_public_base_url }}\"" in homeserver_template
    assert 'log_config: "{{ matrix_synapse_log_config_container_file }}"' in homeserver_template
    assert 'signing_key_path: "{{ matrix_synapse_signing_key_container_file }}"' in homeserver_template


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
    compose_pull_task = next(
        task
        for task in tasks
        if task.get("name") == "Pull the Matrix Synapse image"
    )

    assert "Generate the initial Matrix Synapse signing material and log config" in task_file
    assert "register_new_matrix_user" in task_file
    assert "--exists-ok" in task_file
    assert "Mirror the Matrix Synapse signing key to the control machine" in task_file
    assert bootstrap_pull_task["retries"] == 3
    assert bootstrap_pull_task["until"] == "matrix_synapse_initial_pull.rc == 0"
    assert tasks.index(bootstrap_pull_task) < tasks.index(generate_task)
    assert compose_pull_task["retries"] == 3
    assert compose_pull_task["until"] == "matrix_synapse_pull.rc == 0"
    assert "Assert Matrix Synapse bootstrap generation produced the required artifacts" in task_file
    assert "matrix_synapse_generate.rc == 0" in task_file
