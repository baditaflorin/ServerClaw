from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "outline_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "outline_runtime" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "outline_runtime" / "tasks" / "verify.yml"
PUBLISH_PATH = REPO_ROOT / "roles" / "outline_runtime" / "tasks" / "publish.yml"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "outline_runtime" / "templates" / "outline.env.j2"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "outline_runtime" / "templates" / "docker-compose.yml.j2"
ENV_CTEMPLATE_PATH = REPO_ROOT / "roles" / "outline_runtime" / "templates" / "outline.env.ctmpl.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_public_oidc_and_local_artifacts() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    assert defaults["outline_public_base_url"] == "https://{{ outline_service_topology.public_hostname }}"
    assert defaults["outline_session_authority"] == "{{ platform_session_authority }}"
    assert defaults["outline_public_edge_private_ip"] == "{{ hostvars['proxmox_florin'].proxmox_public_edge_ipv4 }}"
    assert (
        defaults["outline_public_hostname_overrides"][0]["hostname"] == "{{ outline_service_topology.public_hostname }}"
    )
    assert defaults["outline_public_hostname_overrides"][0]["address"] == "{{ outline_public_edge_private_ip }}"
    assert (
        defaults["outline_public_hostname_overrides"][1]["hostname"]
        == "{{ hostvars['proxmox_florin'].lv3_service_topology.keycloak.public_hostname }}"
    )
    assert (
        defaults["outline_internal_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.outline_port }}"
    )
    assert defaults["outline_internal_base_url"] == "http://127.0.0.1:{{ outline_internal_port }}"
    assert (
        defaults["outline_database_host"]
        == "{{ hostvars[hostvars['proxmox_florin'].postgres_ha.initial_primary].ansible_host }}"
    )
    assert defaults["outline_keycloak_client_id"] == "outline"
    assert defaults["outline_keycloak_logout_uri"] == (
        "{{ outline_session_authority.keycloak_logout_url }}"
        "?client_id={{ outline_keycloak_client_id }}"
        "&post_logout_redirect_uri={{ outline_session_authority.shared_proxy_cleanup_url | urlencode }}"
    )
    assert defaults["outline_keycloak_scopes"] == "openid profile email"
    assert defaults["outline_bootstrap_username"] == "outline.automation"
    assert defaults["outline_api_token_local_file"].endswith("/.local/outline/api-token.txt")
    assert defaults["outline_operator_password_local_file"].endswith("/.local/keycloak/outline.automation-password.txt")
    assert "collections.delete" in defaults["outline_api_token_scopes"]
    assert "documents.delete" in defaults["outline_api_token_scopes"]


def test_runtime_role_only_requires_runtime_secrets_before_edge_publish() -> None:
    tasks = load_yaml(TASKS_PATH)
    validate_task = next(task for task in tasks if task.get("name") == "Validate Outline runtime inputs")
    package_task = next(task for task in tasks if task.get("name") == "Ensure the Outline runtime packages are present")
    secret_fact = next(task for task in tasks if task.get("name") == "Record the Outline runtime secrets")
    verify_import = next(task for task in tasks if task.get("name") == "Verify the Outline runtime")
    task_names = {task["name"] for task in tasks}

    assert "outline_operator_password_local_file | length > 0" not in validate_task["ansible.builtin.assert"]["that"]
    assert package_task["ansible.builtin.apt"]["name"] == ["openssl"]
    assert (
        "replace('/', '%2F')" in secret_fact["ansible.builtin.set_fact"]["outline_runtime_secret_payload"]["REDIS_URL"]
    )
    assert "Check whether the Outline operator password exists on the control machine" not in task_names
    assert verify_import["ansible.builtin.import_tasks"] == "verify.yml"


def test_runtime_role_recovers_docker_nat_chain_before_outline_startup() -> None:
    tasks = load_yaml(TASKS_PATH)
    pull_images = next(task for task in tasks if task.get("name") == "Pull the Outline images")
    nat_check = next(
        task for task in tasks if task.get("name") == "Check whether the Docker nat chain exists before Outline startup"
    )
    pre_restart_ids = next(
        task
        for task in tasks
        if task.get("name") == "Record container ids that are running before the Outline-triggered Docker restart"
    )
    pre_restart_reinspect = next(
        task
        for task in tasks
        if task.get("name") == "Re-inspect pre-restart containers after the Outline-triggered Docker restart"
    )
    recover_stopped = next(
        task
        for task in tasks
        if task.get("name")
        == "Recover pre-restart containers that remained stopped after the Outline-triggered Docker restart"
    )
    confirm_recovered = next(
        task
        for task in tasks
        if task.get("name") == "Confirm pre-restart containers recovered after the Outline-triggered Docker restart"
    )
    nat_restore = next(
        task
        for task in tasks
        if task.get("name") == "Restore Docker networking when the nat chain is missing before Outline startup"
    )
    nat_recheck = next(
        task for task in tasks if task.get("name") == "Recheck the Docker nat chain before Outline startup"
    )
    docker_info = next(
        task for task in tasks if task.get("name") == "Wait for the Docker daemon to answer after networking recovery"
    )
    env_render = next(task for task in tasks if task.get("name") == "Render the Outline environment file")
    compose_render = next(task for task in tasks if task.get("name") == "Render the Outline compose file")
    local_port_probe = next(
        task for task in tasks if task.get("name") == "Check whether the Outline local port is already published"
    )
    health_probe = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the current Outline local health endpoint is healthy before startup"
    )
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the Outline runtime stack after Docker networking recovery"
    )

    assert pull_images["until"] == "outline_pull.rc == 0"
    assert pull_images["retries"] == 3
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert pre_restart_ids["ansible.builtin.command"]["argv"] == ["docker", "ps", "-q", "--no-trunc"]
    assert pre_restart_ids["when"] == "outline_docker_nat_chain.rc != 0"
    assert pre_restart_reinspect["register"] == "outline_post_restart_container_status"
    assert recover_stopped["register"] == "outline_recover_stopped_containers"
    assert recover_stopped["when"] == [
        "outline_docker_nat_chain.rc != 0",
        "outline_stopped_pre_restart_container_names | default([]) | length > 0",
    ]
    assert "def is_local_openbao_group(" in recover_stopped["ansible.builtin.command"]["argv"][2]
    assert 'normalized_working_dir == "/opt/openbao"' in recover_stopped["ansible.builtin.command"]["argv"][2]
    assert '"lv3-openbao" in container_names' in recover_stopped["ansible.builtin.command"]["argv"][2]
    assert (
        'if "openbao-agent" in services and not local_openbao_group:'
        in recover_stopped["ansible.builtin.command"]["argv"][2]
    )
    assert confirm_recovered["register"] == "outline_recovered_container_inspect"
    assert confirm_recovered["until"] == "outline_recovered_container_inspect.rc == 0"
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert nat_recheck["until"] == "outline_docker_nat_chain_recheck.rc == 0"
    assert docker_info["ansible.builtin.command"]["argv"] == [
        "docker",
        "info",
        "--format",
        '{{ "{{.ServerVersion}}" }}',
    ]
    assert env_render["register"] == "outline_env_template"
    assert compose_render["register"] == "outline_compose_template"
    assert local_port_probe["ansible.builtin.wait_for"]["port"] == "{{ outline_internal_port }}"
    assert health_probe["ansible.builtin.uri"]["url"] == "{{ outline_internal_base_url }}/_health"
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
    assert force_recreate["register"] == "outline_force_recreate_up"
    assert force_recreate["until"] == "outline_force_recreate_up.rc == 0"
    force_recreate_expression = tasks[tasks.index(force_recreate) - 1]["ansible.builtin.set_fact"][
        "outline_force_recreate"
    ]
    assert "outline_env_template.changed" in force_recreate_expression
    assert "outline_compose_template.changed" in force_recreate_expression
    assert "outline_pull.changed" in force_recreate_expression


def test_publish_tasks_wait_for_public_health_then_bootstrap_sync_and_verify() -> None:
    tasks = load_yaml(PUBLISH_PATH)
    health_task = next(task for task in tasks if task.get("name") == "Wait for the Outline public health endpoint")
    bootstrap_task = next(task for task in tasks if task.get("name") == "Bootstrap the Outline API token when needed")
    sync_task = next(task for task in tasks if task.get("name") == "Sync the Outline landing and index documents")
    verify_task = next(
        task for task in tasks if task.get("name") == "Verify the Outline public living knowledge surface"
    )

    assert health_task["ansible.builtin.uri"]["url"] == "{{ outline_public_base_url }}/_health"
    assert bootstrap_task["ansible.builtin.command"]["argv"] == [
        "python3",
        "{{ inventory_dir }}/../scripts/sync_docs_to_outline.py",
        "bootstrap-token",
        "--base-url",
        "{{ outline_public_base_url }}",
        "--username",
        "{{ outline_bootstrap_username }}",
        "--password-file",
        "{{ outline_operator_password_local_file }}",
        "--token-name",
        "{{ outline_api_token_name }}",
        "--token-file",
        "{{ outline_api_token_local_file }}",
        "--scope",
        "{{ outline_api_token_scopes | join(',') }}",
    ]
    assert sync_task["ansible.builtin.command"]["argv"][2:] == [
        "sync",
        "--repo-root",
        "{{ inventory_dir }}/..",
        "--base-url",
        "{{ outline_public_base_url }}",
        "--api-token-file",
        "{{ outline_api_token_local_file }}",
    ]
    assert verify_task["ansible.builtin.command"]["argv"][2:] == [
        "verify",
        "--repo-root",
        "{{ inventory_dir }}/..",
        "--base-url",
        "{{ outline_public_base_url }}",
        "--api-token-file",
        "{{ outline_api_token_local_file }}",
    ]


def test_verify_task_checks_the_local_health_endpoint() -> None:
    verify = load_yaml(VERIFY_PATH)
    health_task = next(task for task in verify if task.get("name") == "Verify the Outline local health endpoint")
    assert health_task["ansible.builtin.uri"]["url"] == "{{ outline_internal_base_url }}/_health"


def test_outline_templates_enable_collaboration_and_private_s3_storage() -> None:
    env_template = ENV_TEMPLATE_PATH.read_text()
    env_ctemplate = ENV_CTEMPLATE_PATH.read_text()
    compose_template = COMPOSE_TEMPLATE_PATH.read_text()
    assert "SERVICES=web,worker,collaboration" in env_template
    assert "FILE_STORAGE=s3" in env_template
    assert (
        "REDIS_URL=redis://:{{ outline_redis_password | urlencode | replace('/', '%2F') }}@redis:6379/0" in env_template
    )
    assert "AWS_S3_UPLOAD_BUCKET_URL=http://minio:9000" in env_template
    assert (
        'AWS_S3_UPLOAD_BUCKET_URL=[[ with secret "kv/data/{{ outline_openbao_secret_path }}" ]][[ .Data.data.AWS_S3_UPLOAD_BUCKET_URL ]][[ end ]]'
        in env_ctemplate
    )
    assert "OIDC_CLIENT_ID={{ outline_keycloak_client_id }}" in env_template
    assert "OIDC_LOGOUT_URI={{ outline_keycloak_logout_uri }}" in env_template
    assert "redis:" in compose_template
    assert "minio:" in compose_template
    assert '      - "{{ ansible_host }}:{{ outline_internal_port }}:3000"' in compose_template
    assert '      - "127.0.0.1:{{ outline_internal_port }}:3000"' in compose_template
    assert '      - "{{ item.hostname }}:{{ item.address }}"' in compose_template
