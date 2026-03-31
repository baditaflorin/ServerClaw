from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
ROLE_DEFAULTS = ROLE_ROOT / "gitea_runtime" / "defaults" / "main.yml"
ROLE_TASKS = ROLE_ROOT / "gitea_runtime" / "tasks" / "main.yml"
RUNNER_DEFAULTS = ROLE_ROOT / "gitea_runner" / "defaults" / "main.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "gitea_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = ROLE_ROOT / "gitea_runtime" / "templates" / "runtime.env.j2"
ENV_CTEMPLATE = ROLE_ROOT / "gitea_runtime" / "templates" / "runtime.env.ctmpl.j2"
RUNNER_COMPOSE_TEMPLATE = ROLE_ROOT / "gitea_runner" / "templates" / "docker-compose.yml.j2"
BOOTSTRAP_TEMPLATE = ROLE_ROOT / "gitea_runtime" / "templates" / "bootstrap-gitea.sh.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def test_gitea_defaults_reference_private_service_topology() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert "service_topology_get('gitea')" in defaults
    assert "service_topology_get('keycloak')" in defaults
    assert "service_topology_get('minio')" in defaults
    assert "gitea-oauth" in defaults
    assert "playbook_execution_host_patterns.postgres[playbook_execution_env]" in defaults
    assert ".local/gitea/minio-secret-key.txt" in defaults
    assert "gitea_minio_bucket_name: gitea-lfs" in defaults
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


def test_runner_defaults_use_mirrored_registration_token() -> None:
    defaults = RUNNER_DEFAULTS.read_text()
    assert "gitea_runner_compose_bin: docker" in defaults
    assert ".local/gitea/runner-registration-token.txt" in defaults
    assert "docker-build-lv3" in defaults


def test_runner_compose_uses_registration_token_env() -> None:
    template = RUNNER_COMPOSE_TEMPLATE.read_text()
    assert "GITEA_RUNNER_REGISTRATION_TOKEN" in template
    assert "/var/run/docker.sock:/var/run/docker.sock" in template
    assert "subnet: {{ gitea_runner_network_subnet }}" in template


def test_runner_tasks_use_docker_compose_plugin() -> None:
    runner_tasks = yaml.safe_load((ROLE_ROOT / "gitea_runner" / "tasks" / "main.yml").read_text())
    task_names = {task["name"] for task in runner_tasks}
    assert "Verify Docker Compose plugin is available" in task_names

    pull_task = next(task for task in runner_tasks if task["name"] == "Pull the Gitea runner image")
    up_task = next(
        task
        for task in runner_tasks
        if task["name"] == "Start the Gitea runner stack and recover stale compose-network failures"
    )
    start_task = next(task for task in up_task["block"] if task["name"] == "Start the Gitea runner stack")
    assert pull_task["ansible.builtin.command"]["argv"][:2] == ["{{ gitea_runner_compose_bin }}", "compose"]
    assert start_task["ansible.builtin.command"]["argv"][:2] == ["{{ gitea_runner_compose_bin }}", "compose"]


def test_runtime_tasks_require_oidc_secret_and_database_password() -> None:
    tasks = load_tasks()
    names = {task["name"] for task in tasks}
    assert "Ensure the Gitea database password exists on the control machine" in names
    assert "Ensure the Gitea OIDC client secret exists on the control machine" in names
    assert "Ensure the Gitea MinIO secret key exists on the control machine" in names
    assert "Ensure the release-bundle Cosign private key exists on the control machine" in names
    assert "Ensure the release-bundle Cosign password exists on the control machine" in names
    assert "Mirror the Gitea admin token to the control machine" in names
    assert "Mirror the Gitea runner registration token to the control machine" in names


def test_runtime_tasks_recover_stale_compose_network_during_gitea_startup() -> None:
    tasks = load_tasks()
    start_block = next(
        task
        for task in tasks
        if task.get("name") == "Start the Gitea stack and recover stale compose-network failures"
    )
    rescue_names = [task["name"] for task in start_block["rescue"]]
    recovery_fact = next(
        task
        for task in start_block["rescue"]
        if task.get("name") == "Flag stale Gitea compose-network failures during startup"
    )

    assert "Flag stale Gitea compose-network failures during startup" in rescue_names
    assert "Reset Docker failed state before nat-chain recovery retry" in rescue_names
    assert "Restart Docker to restore nat chain before retrying Gitea startup" in rescue_names
    assert "Wait for Docker nat chain to return before retrying Gitea startup" in rescue_names
    assert "Reset stale Gitea compose resources before retrying startup" in rescue_names
    assert "Retry Gitea stack startup after compose-network recovery" in rescue_names
    assert "Unable to enable DNAT rule" in recovery_fact["ansible.builtin.set_fact"]["gitea_docker_nat_chain_missing"]
    assert "No chain/target/match by that name" in recovery_fact["ansible.builtin.set_fact"]["gitea_docker_nat_chain_missing"]


def test_runner_tasks_recover_stale_compose_network_during_startup() -> None:
    runner_tasks = yaml.safe_load((ROLE_ROOT / "gitea_runner" / "tasks" / "main.yml").read_text())
    start_block = next(
        task
        for task in runner_tasks
        if task["name"] == "Start the Gitea runner stack and recover stale compose-network failures"
    )
    rescue_names = [task["name"] for task in start_block["rescue"]]

    assert "Flag stale Gitea runner compose-network failures during startup" in rescue_names
    assert "Reset stale Gitea runner compose resources before retrying startup" in rescue_names
    assert "Retry Gitea runner stack startup after compose-network recovery" in rescue_names


def test_gitea_waits_on_the_published_service_address() -> None:
    tasks = load_tasks()
    wait_task = next(task for task in tasks if task["name"] == "Wait for Gitea to listen locally")
    oidc_wait_task = next(
        task
        for task in tasks
        if task["name"] == "Wait for the Keycloak OIDC discovery endpoint used by Gitea bootstrap"
    )
    assert wait_task["ansible.builtin.wait_for"]["host"] == "{{ ansible_host }}"
    assert oidc_wait_task["ansible.builtin.uri"]["url"] == "{{ gitea_oidc_internal_discovery_url }}"


def test_gitea_defaults_include_release_bundle_signing_paths() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert ".local/gitea/release-bundle-cosign.key" in defaults
    assert ".local/gitea/release-bundle-cosign.password.txt" in defaults
    assert "keys/gitea-release-bundle-cosign.pub" in defaults
    assert "RELEASE_BUNDLE_REPO_TOKEN" in defaults


def test_runtime_env_templates_enable_lfs_on_shared_minio() -> None:
    template = ENV_TEMPLATE.read_text()
    ctemplate = ENV_CTEMPLATE.read_text()

    assert "GITEA__server__LFS_START_SERVER=true" in template
    assert "GITEA__lfs__STORAGE_TYPE=minio" in template
    assert "GITEA__lfs__MINIO_ENDPOINT={{ gitea_minio_endpoint }}" in template
    assert "GITEA__lfs__MINIO_ACCESS_KEY_ID={{ gitea_minio_access_key_id }}" in template
    assert "GITEA__lfs__MINIO_SECRET_ACCESS_KEY={{ gitea_minio_secret_key }}" in template
    assert "GITEA__lfs__MINIO_BUCKET={{ gitea_minio_bucket_name }}" in template
    assert "GITEA__lfs__MINIO_BUCKET_LOOKUP_TYPE=path" in template

    assert "GITEA__lfs__STORAGE_TYPE=minio" in ctemplate
    assert "GITEA__lfs__MINIO_ENDPOINT={{ gitea_minio_endpoint }}" in ctemplate
    assert "GITEA__lfs__MINIO_SECRET_ACCESS_KEY=[[ with secret " in ctemplate
