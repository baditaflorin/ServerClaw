from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "dify_runtime" / "tasks" / "main.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "dify_runtime" / "defaults" / "main.yml"
PLAYBOOK_VARS = REPO_ROOT / "playbooks" / "vars" / "dify.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "dify.env.j2"
DEFAULT_CONF_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "default.conf.template.j2"
PROXY_CONF_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "proxy.conf.template.j2"
SANDBOX_CONFIG_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "sandbox-config.yaml.j2"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_dify_runtime_declares_pre_validation_compatibility_defaults() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["dify_site_dir"] == "/opt/dify"
    assert defaults["dify_data_dir"] == "{{ dify_site_dir }}/data"
    assert defaults["dify_secret_dir"] == "/etc/{{ platform_identity.unix_prefix }}/dify"
    assert defaults["dify_compose_file"] == "{{ dify_site_dir }}/docker-compose.yml"
    assert defaults["dify_env_file"] == "{{ compose_runtime_secret_root }}/dify/runtime.env"
    assert defaults["dify_internal_port"] == "{{ platform_service_registry.dify.internal_port }}"
    assert defaults["dify_local_artifact_dir"] == "{{ repo_shared_local_root }}/dify"
    assert defaults["dify_openbao_secret_path"] == "services/dify/runtime-env"
    assert defaults["dify_openbao_approle_name"] == "dify-runtime"
    assert defaults["dify_init_password_random_bytes"] == 12
    assert defaults["dify_init_password_max_length"] == 30
    assert defaults["dify_keycloak_client_id"] == "{{ platform_service_registry.dify.sso.client_id }}"
    assert (
        defaults["dify_keycloak_client_secret_local_file"]
        == "{{ repo_shared_local_root }}/keycloak/dify-client-secret.txt"
    )
    assert defaults["dify_keycloak_issuer"] == "{{ keycloak_oidc_issuer_url }}"


def test_dify_runtime_repairs_init_password_and_bootstraps_through_a_private_tunnel() -> None:
    tasks = load_tasks(ROLE_TASKS)
    secret_task = next(task for task in tasks if task.get("name") == "Manage Dify runtime secrets")
    generated = secret_task["vars"]["common_manage_service_secrets_generate"]
    init_secret = next(secret for secret in generated if secret["label"] == "dify-init-password")
    assert init_secret["value"] == "{{ 'dify' | secret(length=dify_init_password_random_bytes) }}"

    task_names = {task.get("name") for task in tasks}
    assert "Detect a Dify initialization password that exceeds the live API limit" in task_names
    assert "Persist the compatible Dify initialization password on the runtime host" in task_names
    assert "Mirror the compatible Dify initialization password to the controller" in task_names

    bootstrap = next(task for task in tasks if task.get("name") == "Bootstrap Dify SSO with Keycloak OIDC")
    argv = bootstrap["ansible.builtin.command"]["argv"]
    assert argv[:6] == ["uv", "run", "--with", "requests", "python", "{{ dify_scripts_dir }}/dify_sso_bootstrap.py"]
    assert "--admin-name" in argv
    assert "--init-password-file" in argv
    assert "--ssh-host" in argv
    assert "--ssh-jump-host" in argv
    assert "--ssh-private-key-file" in argv
    assert "--ssh-remote-port" in argv
    assert "dify_sso_bootstrap.rc == 0" in bootstrap["changed_when"]
    assert ".changed | bool" in bootstrap["changed_when"]


def test_dify_post_verify_probes_follow_the_selected_inventory_host() -> None:
    variables = yaml.safe_load(PLAYBOOK_VARS.read_text())
    probe = variables["playbook_execution_health_probe_overrides"]["dify"]
    base_url = "http://{{ ansible_host }}:{{ platform_service_registry.dify.internal_port }}"

    assert probe["startup"]["url"] == f"{base_url}/console/api/setup"
    assert probe["liveness"]["url"] == f"{base_url}/healthz"
    assert probe["readiness"]["url"] == f"{base_url}/console/api/setup"


def test_dify_runtime_renders_sandbox_config_before_startup() -> None:
    tasks = load_tasks(ROLE_TASKS)
    sandbox_task = next(task for task in tasks if task.get("name") == "Render the Dify sandbox configuration")

    assert sandbox_task["ansible.builtin.template"]["src"] == "sandbox-config.yaml.j2"
    assert sandbox_task["ansible.builtin.template"]["dest"] == "{{ dify_sandbox_dir }}/conf/config.yaml"


def test_dify_env_template_sets_plugin_and_code_execution_inputs() -> None:
    template = ENV_TEMPLATE.read_text()

    assert "CODE_EXECUTION_ENDPOINT=http://sandbox:{{ dify_sandbox_port }}" in template
    assert "CODE_EXECUTION_API_KEY={{ dify_sandbox_api_key }}" in template
    assert "SERVER_PORT={{ dify_plugin_daemon_port }}" in template
    assert "INNER_API_KEY_FOR_PLUGIN={{ dify_plugin_inner_api_key }}" in template
    assert "PLUGIN_REMOTE_INSTALLING_HOST=0.0.0.0" in template
    assert "PLUGIN_REMOTE_INSTALLING_PORT=5003" in template


def test_nginx_default_conf_uses_plain_envsubst_tokens() -> None:
    template = DEFAULT_CONF_TEMPLATE.read_text()

    assert "${NGINX_PORT}" in template
    assert "${NGINX_SERVER_NAME}" in template
    assert ":-" not in template


def test_nginx_proxy_conf_uses_plain_envsubst_tokens() -> None:
    template = PROXY_CONF_TEMPLATE.read_text()

    assert "${NGINX_PROXY_READ_TIMEOUT}" in template
    assert "${NGINX_PROXY_SEND_TIMEOUT}" in template
    assert ":-" not in template


def test_sandbox_config_template_matches_runtime_mount() -> None:
    config = SANDBOX_CONFIG_TEMPLATE.read_text()

    assert "app:" in config
    assert "port: {{ dify_sandbox_port }}" in config
    assert "key: {{ dify_sandbox_api_key }}" in config
    assert "python_path: /opt/python/bin/python3" in config
