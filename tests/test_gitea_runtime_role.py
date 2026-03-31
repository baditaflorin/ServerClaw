from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
ROLE_DEFAULTS = ROLE_ROOT / "gitea_runtime" / "defaults" / "main.yml"
ROLE_TASKS = ROLE_ROOT / "gitea_runtime" / "tasks" / "main.yml"
RUNNER_DEFAULTS = ROLE_ROOT / "gitea_runner" / "defaults" / "main.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "gitea_runtime" / "templates" / "docker-compose.yml.j2"
RUNNER_COMPOSE_TEMPLATE = ROLE_ROOT / "gitea_runner" / "templates" / "docker-compose.yml.j2"
BOOTSTRAP_TEMPLATE = ROLE_ROOT / "gitea_runtime" / "templates" / "bootstrap-gitea.sh.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def test_gitea_defaults_reference_private_service_topology() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert "service_topology_get('gitea')" in defaults
    assert "service_topology_get('keycloak')" in defaults
    assert "gitea-oauth" in defaults
    assert "playbook_execution_host_patterns.postgres[playbook_execution_env]" in defaults
    assert 'gitea_oidc_internal_discovery_url: "http://{{ gitea_keycloak_service_topology.private_ip }}:8091/realms/lv3/.well-known/openid-configuration"' in defaults


def test_gitea_compose_mounts_data_volume_and_openbao_env() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert "gitea-openbao-agent" in template
    assert 'user: "0:0"' in template
    assert 'BAO_SKIP_DROP_ROOT: "true"' in template
    assert "/var/lib/gitea" in template
    assert "env_file:" in template
    assert "subnet: {{ gitea_network_subnet }}" in template


def test_gitea_bootstrap_script_creates_admin_token_and_runner_token() -> None:
    template = BOOTSTRAP_TEMPLATE.read_text()
    assert 'oidc_internal_discovery="{{ gitea_oidc_internal_discovery_url }}"' in template
    assert '--auto-discover-url "${oidc_internal_discovery}"' in template
    assert 'gitea admin auth list' in template
    assert "generate-access-token" in template
    assert "--raw" in template
    assert "generate-runner-token" in template
    assert "RELEASE_BUNDLE_COSIGN_PRIVATE_KEY" in template
    assert "RELEASE_BUNDLE_REPO_TOKEN" in template
    assert "/actions/secrets/" in template
    assert 'renovate_user="{{ gitea_renovate_username }}"' in template
    assert 'GITEA_RENOVATE_PASSWORD' in template
    assert '/collaborators/${renovate_user}' in template
    assert '\\"permission\\":\\"${renovate_repo_permission}\\"' in template


def test_runner_defaults_use_mirrored_registration_token() -> None:
    defaults = RUNNER_DEFAULTS.read_text()
    assert "gitea_runner_compose_bin: docker" in defaults
    assert ".local/gitea/runner-registration-token.txt" in defaults
    assert "docker-build-lv3" in defaults
    assert "service_topology_get('openbao')" in defaults
    assert "service_topology_get('gitea')" in defaults
    assert "platform_service_topology.gitea" in defaults
    assert ".local/gitea/renovate-password.txt" in defaults
    assert "services/gitea-runner/renovate-runtime" in defaults
    assert "gitea_runner_renovate_clone_host" in defaults
    assert "gitea_runner_renovate_clone_host_address" in defaults
    assert "gitea_runner_renovate_clone_host_port" in defaults
    assert "gitea_runner_renovate_clone_target_host" in defaults
    assert "gitea_runner_renovate_clone_target_port" in defaults
    assert "gitea_runner_renovate_clone_host_address: 127.0.0.1" in defaults


def test_runner_compose_uses_registration_token_env() -> None:
    template = RUNNER_COMPOSE_TEMPLATE.read_text()
    assert "GITEA_RUNNER_REGISTRATION_TOKEN" in template
    assert "GITEA_RUNNER_HOST_DATA_DIR" in template
    assert "/var/run/docker.sock:/var/run/docker.sock" in template
    assert "gitea_runner_renovate_credential_dir_in_container" in template
    assert "subnet: {{ gitea_runner_network_subnet }}" in template


def test_runner_config_exports_host_data_dir_to_jobs() -> None:
    template = (ROLE_ROOT / "gitea_runner" / "templates" / "config.yaml.j2").read_text()
    assert "GITEA_RUNNER_HOST_DATA_DIR: {{ gitea_runner_data_dir }}" in template


def test_runner_tasks_use_docker_compose_plugin() -> None:
    runner_tasks = yaml.safe_load((ROLE_ROOT / "gitea_runner" / "tasks" / "main.yml").read_text())
    task_names = {task["name"] for task in runner_tasks}
    assert "Verify Docker Compose plugin is available" in task_names
    assert "Record whether the Gitea runner stack needs a force recreate" in task_names

    pull_task = next(task for task in runner_tasks if task["name"] == "Pull the Gitea runner image")
    up_task = next(task for task in runner_tasks if task["name"] == "Start the Gitea runner stack")
    assert pull_task["ansible.builtin.command"]["argv"][:2] == ["{{ gitea_runner_compose_bin }}", "compose"]
    up_argv = up_task["ansible.builtin.command"]["argv"]
    assert "gitea_runner_force_recreate" in up_argv
    assert "--force-recreate" in up_argv


def test_runtime_tasks_require_oidc_secret_and_database_password() -> None:
    tasks = load_tasks()
    names = {task["name"] for task in tasks}
    assert "Ensure the Gitea database password exists on the control machine" in names
    assert "Ensure the Gitea OIDC client secret exists on the control machine" in names
    assert "Ensure the release-bundle Cosign private key exists on the control machine" in names
    assert "Ensure the release-bundle Cosign password exists on the control machine" in names
    assert "Generate the Gitea Renovate bot password when missing" in names
    assert "Mirror the Gitea Renovate bot password to the control machine" in names
    assert "Mirror the Gitea admin token to the control machine" in names
    assert "Mirror the Gitea runner registration token to the control machine" in names


def test_runner_tasks_render_the_openbao_backed_renovate_bundle() -> None:
    runner_tasks = yaml.safe_load((ROLE_ROOT / "gitea_runner" / "tasks" / "main.yml").read_text())
    names = {task["name"] for task in runner_tasks}

    assert "Ensure the Gitea Renovate bot password exists on the control machine" in names
    assert "Prepare the Renovate credential bundle for the Gitea runner" in names
    assert "Confirm the Renovate credential bundle rendered successfully" in names
    prepare_task = next(
        task for task in runner_tasks if task["name"] == "Prepare the Renovate credential bundle for the Gitea runner"
    )
    secret_payload = prepare_task["vars"]["common_openbao_systemd_credentials_secret_payload"]
    assert secret_payload["RENOVATE_GIT_CLONE_HOST"] == "{{ gitea_runner_renovate_clone_host }}"
    assert secret_payload["RENOVATE_GIT_CLONE_HOST_ADDRESS"] == "{{ gitea_runner_renovate_clone_host_address }}"
    assert secret_payload["RENOVATE_GIT_CLONE_HOST_PORT"] == "{{ gitea_runner_renovate_clone_host_port }}"
    assert secret_payload["RENOVATE_GIT_CLONE_TARGET_HOST"] == "{{ gitea_runner_renovate_clone_target_host }}"
    assert secret_payload["RENOVATE_GIT_CLONE_TARGET_PORT"] == "{{ gitea_runner_renovate_clone_target_port }}"


def test_gitea_waits_on_the_published_service_address() -> None:
    tasks = load_tasks()
    wait_task = next(task for task in tasks if task["name"] == "Wait for Gitea to listen locally")
    assert wait_task["ansible.builtin.wait_for"]["host"] == "{{ ansible_host }}"


def test_gitea_waits_for_internal_keycloak_oidc_before_bootstrap() -> None:
    tasks = load_tasks()
    wait_task = next(
        task
        for task in tasks
        if task["name"] == "Wait for the internal Keycloak OIDC discovery document before bootstrapping Gitea"
    )
    assert wait_task["ansible.builtin.uri"]["url"] == "{{ gitea_oidc_internal_discovery_url }}"
    assert wait_task["retries"] == 48
    assert wait_task["delay"] == 5


def test_gitea_runtime_recovers_stale_docker_networking() -> None:
    tasks = load_tasks()
    names = {task["name"] for task in tasks}

    assert "Check whether the Docker nat chain exists before Gitea startup" in names
    assert "Check whether the Gitea local port is already published" in names
    assert "Check whether the current Gitea sign-in page is healthy before startup" in names
    assert "Record whether the Gitea startup needs a force recreate" in names
    assert "Reset the Gitea stack before a force recreate" in names
    assert "Remove stale Gitea compose networks after the reset" in names
    assert "Remove stale Gitea containers before recovery" in names
    assert "Force-recreate the Gitea stack after Docker networking recovery" in names

    network_cleanup_task = next(task for task in tasks if task["name"] == "Remove stale Gitea compose networks after the reset")
    network_cleanup_script = network_cleanup_task["ansible.builtin.shell"]
    assert 'docker network inspect "${network_id}"' in network_cleanup_script
    assert 'payload[0].get("Containers")' in network_cleanup_script

    force_recreate_task = next(
        task for task in tasks if task["name"] == "Record whether the Gitea startup needs a force recreate"
    )
    force_recreate_expr = force_recreate_task["ansible.builtin.set_fact"]["gitea_force_recreate"]
    assert "gitea_docker_nat_chain.rc != 0" in force_recreate_expr
    assert "gitea_local_port_probe.failed" in force_recreate_expr
    assert "gitea_login_probe.status" in force_recreate_expr


def test_gitea_defaults_include_release_bundle_signing_paths() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert ".local/gitea/release-bundle-cosign.key" in defaults
    assert ".local/gitea/release-bundle-cosign.password.txt" in defaults
    assert "keys/gitea-release-bundle-cosign.pub" in defaults
    assert "RELEASE_BUNDLE_REPO_TOKEN" in defaults
    assert "gitea_renovate_username: renovate-bot" in defaults
    assert ".local/gitea/renovate-password.txt" in defaults
