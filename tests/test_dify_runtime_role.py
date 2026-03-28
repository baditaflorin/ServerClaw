from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "dify_runtime" / "tasks" / "main.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "dify.env.j2"
DEFAULT_CONF_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "default.conf.template.j2"
PROXY_CONF_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "proxy.conf.template.j2"
SANDBOX_CONFIG_TEMPLATE = REPO_ROOT / "roles" / "dify_runtime" / "templates" / "sandbox-config.yaml.j2"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


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
