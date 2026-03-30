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
    assert ".local/gitea/renovate-password.txt" in defaults
    assert "services/gitea-runner/renovate-runtime" in defaults


def test_runner_compose_uses_registration_token_env() -> None:
    template = RUNNER_COMPOSE_TEMPLATE.read_text()
    assert "GITEA_RUNNER_REGISTRATION_TOKEN" in template
    assert "GITEA_RUNNER_HOST_DATA_DIR" in template
    assert "/var/run/docker.sock:/var/run/docker.sock" in template
    assert "gitea_runner_renovate_credential_dir_in_container" in template
    assert "subnet: {{ gitea_runner_network_subnet }}" in template


def test_runner_tasks_use_docker_compose_plugin() -> None:
    runner_tasks = yaml.safe_load((ROLE_ROOT / "gitea_runner" / "tasks" / "main.yml").read_text())
    task_names = {task["name"] for task in runner_tasks}
    assert "Verify Docker Compose plugin is available" in task_names

    pull_task = next(task for task in runner_tasks if task["name"] == "Pull the Gitea runner image")
    up_task = next(task for task in runner_tasks if task["name"] == "Start the Gitea runner stack")
    assert pull_task["ansible.builtin.command"]["argv"][:2] == ["{{ gitea_runner_compose_bin }}", "compose"]
    assert up_task["ansible.builtin.command"]["argv"][:2] == ["{{ gitea_runner_compose_bin }}", "compose"]


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


def test_gitea_waits_on_the_published_service_address() -> None:
    tasks = load_tasks()
    wait_task = next(task for task in tasks if task["name"] == "Wait for Gitea to listen locally")
    assert wait_task["ansible.builtin.wait_for"]["host"] == "{{ ansible_host }}"


def test_gitea_defaults_include_release_bundle_signing_paths() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert ".local/gitea/release-bundle-cosign.key" in defaults
    assert ".local/gitea/release-bundle-cosign.password.txt" in defaults
    assert "keys/gitea-release-bundle-cosign.pub" in defaults
    assert "RELEASE_BUNDLE_REPO_TOKEN" in defaults
    assert "gitea_renovate_username: renovate-bot" in defaults
    assert ".local/gitea/renovate-password.txt" in defaults
