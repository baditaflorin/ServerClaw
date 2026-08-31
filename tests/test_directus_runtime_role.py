from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "directus_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "directus_runtime" / "tasks" / "main.yml"
VERIFY_TASKS_PATH = REPO_ROOT / "roles" / "directus_runtime" / "tasks" / "verify.yml"
PUBLISH_TASKS_PATH = REPO_ROOT / "roles" / "directus_runtime" / "tasks" / "publish.yml"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "directus_runtime" / "templates" / "runtime.env.j2"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "directus_runtime" / "templates" / "docker-compose.yml.j2"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_directus_defaults_define_runtime_and_publication_contract() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())

    assert defaults["directus_service_topology"] == (
        "{{ hostvars[platform_topology_host].platform_service_topology | service_topology_get('directus') }}"
    )
    assert defaults["directus_session_authority"] == "{{ platform_session_authority }}"
    assert defaults["directus_public_base_url"] == "https://{{ directus_service_topology.public_hostname }}"
    assert defaults["directus_compose_project_name"] == "directus"
    assert defaults["directus_compose_network_name"] == "{{ directus_compose_project_name }}_default"
    assert defaults["directus_container_port"] == "{{ directus_internal_port }}"
    assert defaults["directus_health_path"] == "/server/health"
    assert defaults["directus_ping_path"] == "/server/ping"
    assert defaults["directus_openapi_path"] == "/server/specs/oas"
    assert defaults["directus_local_artifact_dir"] == "{{ repo_shared_local_root }}/directus"
    assert (
        defaults["directus_database_password_local_file"] == "{{ directus_local_artifact_dir }}/database-password.txt"
    )
    assert defaults["directus_authentik_client_secret_local_file"] == (
        "{{ repo_shared_local_root }}/authentik/directus-client-secret.txt"
    )
    assert defaults["directus_service_registry_token_local_file"] == (
        "{{ directus_local_artifact_dir }}/service-registry-token.txt"
    )
    assert defaults["directus_bootstrap_collection_name"] == "service_registry"


def test_directus_runtime_requires_database_oidc_and_service_token_inputs() -> None:
    tasks = load_tasks(TASKS_PATH)
    derive_task = next(
        task for task in tasks if task.get("name") == "Derive Directus conventional defaults from the service registry"
    )
    validate_task = next(task for task in tasks if task.get("name") == "Validate Directus runtime inputs")
    required_inputs = validate_task["ansible.builtin.assert"]["that"]
    converge_task = next(task for task in tasks if task.get("name") == "Converge the Directus Docker stack")
    bootstrap_task = next(
        task for task in tasks if task.get("name") == "Bootstrap the Directus governed schema against the local runtime"
    )
    verify_names = [task["name"] for task in tasks if task.get("ansible.builtin.import_tasks") == "verify.yml"]

    assert derive_task["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert derive_task["ansible.builtin.include_role"]["tasks_from"] == "derive_service_defaults"
    assert derive_task["vars"]["common_derive_service_name"] == "directus"
    assert "directus_database_password_local_file | length > 0" in required_inputs
    assert "directus_authentik_client_secret_local_file | length > 0" in required_inputs
    assert "directus_service_registry_token_local_file | length > 0" in required_inputs
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert converge_task["ansible.builtin.include_role"]["tasks_from"] == "docker_compose_converge"
    assert converge_task["vars"]["common_docker_compose_converge_service_name"] == "directus"
    assert (
        converge_task["vars"]["common_docker_compose_converge_health_url"]
        == "{{ directus_internal_base_url }}{{ directus_health_path }}"
    )
    assert bootstrap_task["retries"] == 12
    assert bootstrap_task["delay"] == 5
    assert bootstrap_task["until"] == "directus_schema_bootstrap.rc == 0"
    assert (
        "{{ playbook_dir | dirname }}/../scripts/directus_bootstrap.py bootstrap"
        in bootstrap_task["ansible.builtin.script"]
    )
    assert "no_log" not in bootstrap_task
    assert verify_names == [
        "Verify the Directus runtime before schema bootstrap",
        "Verify the Directus runtime after schema bootstrap",
    ]


def test_directus_verify_and_publish_tasks_use_expected_contract_endpoints() -> None:
    verify_tasks = load_tasks(VERIFY_TASKS_PATH)
    publish_tasks = load_tasks(PUBLISH_TASKS_PATH)

    health_task = next(task for task in verify_tasks if task.get("name") == "Verify the Directus runtime")
    health_include = health_task["ansible.builtin.include_role"]
    health_vars = health_task["vars"]
    public_health_task = next(
        task for task in publish_tasks if task.get("name") == "Wait for the Directus public health endpoint"
    )
    public_verify_task = next(
        task
        for task in publish_tasks
        if task.get("name") == "Verify the public Directus publication and token-based API paths"
    )

    assert health_include["name"] == "lv3.platform.common"
    assert health_include["tasks_from"] == "verify_service_health"
    assert health_vars["common_verify_service_name"] == "directus"
    assert health_vars["common_verify_port"] == "{{ directus_internal_port }}"
    assert health_vars["common_verify_health_url"] == "{{ directus_internal_base_url }}{{ directus_health_path }}"
    extra_endpoints = health_vars["common_verify_extra_endpoints"]
    assert extra_endpoints[0]["url"] == "{{ directus_internal_base_url }}{{ directus_ping_path }}"
    assert extra_endpoints[1]["url"] == "{{ directus_internal_base_url }}{{ directus_openapi_path }}"
    assert (
        public_health_task["ansible.builtin.uri"]["url"] == "{{ directus_public_base_url }}{{ directus_health_path }}"
    )
    assert public_verify_task["ansible.builtin.command"]["argv"] == [
        "python3",
        "{{ playbook_dir }}/../scripts/directus_bootstrap.py",
        "verify-public",
        "--base-url",
        "{{ directus_public_base_url }}",
        "--api-token-file",
        "{{ directus_service_registry_token_local_file }}",
        "--collection",
        "{{ directus_bootstrap_collection_name }}",
        "--expected-service-name",
        "directus",
        "--expected-sso-host",
        "id.{{ platform_domain }}",
    ]


def test_directus_templates_include_public_url_and_oidc_settings() -> None:
    env_template = ENV_TEMPLATE_PATH.read_text()
    compose_template = COMPOSE_TEMPLATE_PATH.read_text()

    assert "PUBLIC_URL={{ directus_public_base_url }}" in env_template
    assert "AUTH_PROVIDERS=authentik" in env_template
    assert "AUTH_AUTHENTIK_DRIVER=openid" in env_template
    assert "AUTH_AUTHENTIK_ROLE_MAPPING={{ directus_authentik_role_mapping_json }}" in env_template
    assert "image: {{ directus_image }}" in compose_template
    assert "{{ ansible_host }}:{{ directus_internal_port }}:{{ directus_container_port }}" in compose_template
    assert "127.0.0.1:{{ directus_internal_port }}:{{ directus_container_port }}" in compose_template
    assert "{% if directus_public_hostname_overrides | default([]) | length > 0 %}" in compose_template
    assert "extra_hosts:" in compose_template
