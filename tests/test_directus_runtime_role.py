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

    assert (
        defaults["directus_internal_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.directus_port }}"
    )
    assert defaults["directus_internal_base_url"] == "http://127.0.0.1:{{ directus_internal_port }}"
    assert defaults["directus_public_base_url"] == "https://{{ directus_service_topology.public_hostname }}"
    assert defaults["directus_image"] == "{{ container_image_catalog.images.directus_runtime.ref }}"
    assert defaults["directus_database_password_local_file"].endswith("/.local/directus/database-password.txt")
    assert defaults["directus_keycloak_client_secret_local_file"].endswith(
        "/.local/keycloak/directus-client-secret.txt"
    )
    assert defaults["directus_service_registry_token_local_file"].endswith(
        "/.local/directus/service-registry-token.txt"
    )
    assert defaults["directus_bootstrap_collection_name"] == "service_registry"


def test_directus_runtime_requires_database_oidc_and_service_token_inputs() -> None:
    tasks = load_tasks(TASKS_PATH)
    validate_task = next(task for task in tasks if task.get("name") == "Validate Directus runtime inputs")
    pull_task = next(task for task in tasks if task.get("name") == "Pull the Directus image")
    required_inputs = validate_task["ansible.builtin.assert"]["that"]
    bootstrap_task = next(
        task for task in tasks if task.get("name") == "Bootstrap the Directus governed schema against the local runtime"
    )
    nat_verify_task = next(
        task
        for task in tasks
        if task.get("name") == "Verify the Docker nat chain after networking recovery before Directus startup"
    )
    nat_assert_task = next(
        task for task in tasks if task.get("name") == "Assert Docker nat chain is present before Directus startup"
    )

    assert "directus_database_password_local_file | length > 0" in required_inputs
    assert "directus_keycloak_client_secret_local_file | length > 0" in required_inputs
    assert "directus_service_registry_token_local_file | length > 0" in required_inputs
    assert pull_task["retries"] == 5
    assert pull_task["delay"] == 5
    assert pull_task["until"] == "directus_pull.rc == 0"
    assert bootstrap_task["retries"] == 12
    assert bootstrap_task["delay"] == 5
    assert bootstrap_task["until"] == "directus_schema_bootstrap.rc == 0"
    assert "{{ playbook_dir }}/../scripts/directus_bootstrap.py bootstrap" in bootstrap_task["ansible.builtin.script"]
    assert "no_log" not in bootstrap_task
    assert nat_verify_task["register"] == "directus_docker_nat_chain_verify"
    assert nat_verify_task["when"] == "directus_docker_nat_chain.rc != 0"
    assert nat_assert_task["ansible.builtin.assert"]["that"] == [
        "directus_docker_nat_chain.rc == 0 or (directus_docker_nat_chain_verify.rc | default(1)) == 0"
    ]


def test_directus_verify_and_publish_tasks_use_expected_contract_endpoints() -> None:
    verify_tasks = load_tasks(VERIFY_TASKS_PATH)
    publish_tasks = load_tasks(PUBLISH_TASKS_PATH)

    health_task = next(task for task in verify_tasks if task.get("name") == "Verify the Directus health endpoint")
    ping_task = next(task for task in verify_tasks if task.get("name") == "Verify the Directus ping endpoint")
    openapi_task = next(
        task for task in verify_tasks if task.get("name") == "Verify the Directus OpenAPI document is served locally"
    )
    public_verify_task = next(
        task
        for task in publish_tasks
        if task.get("name") == "Verify the public Directus publication and token-based API paths"
    )

    assert health_task["ansible.builtin.uri"]["url"] == "{{ directus_internal_base_url }}{{ directus_health_path }}"
    assert ping_task["ansible.builtin.uri"]["url"] == "{{ directus_internal_base_url }}{{ directus_ping_path }}"
    assert openapi_task["ansible.builtin.uri"]["url"] == "{{ directus_internal_base_url }}{{ directus_openapi_path }}"
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
        "sso.lv3.org",
    ]


def test_directus_templates_include_public_url_and_oidc_settings() -> None:
    env_template = ENV_TEMPLATE_PATH.read_text()
    compose_template = COMPOSE_TEMPLATE_PATH.read_text()

    assert "PUBLIC_URL={{ directus_public_base_url }}" in env_template
    assert "AUTH_PROVIDERS=keycloak" in env_template
    assert "AUTH_KEYCLOAK_DRIVER=openid" in env_template
    assert "AUTH_KEYCLOAK_ROLE_MAPPING={{ directus_keycloak_role_mapping_json }}" in env_template
    assert "image: {{ directus_image }}" in compose_template
    assert "{{ ansible_host }}:{{ directus_internal_port }}:{{ directus_container_port }}" in compose_template
    assert "127.0.0.1:{{ directus_internal_port }}:{{ directus_container_port }}" in compose_template
