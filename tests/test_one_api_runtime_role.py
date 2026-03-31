from pathlib import Path

import json
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "one_api_runtime"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "one_api_runtime"
    / "tasks"
    / "main.yml"
)
VERIFY_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "one_api_runtime"
    / "tasks"
    / "verify.yml"
)
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "one_api_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)
ENV_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "one_api_runtime"
    / "templates"
    / "one-api.env.ctmpl.j2"
)
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "one-api.yml"
BOOTSTRAP_CONFIG_PATH = REPO_ROOT / "config" / "one-api" / "bootstrap.json"


def load_tasks() -> list[dict]:
    return yaml.safe_load(TASKS_PATH.read_text(encoding="utf-8"))


def find_task(tasks: list[dict], name: str) -> dict:
    for task in tasks:
        if task.get("name") == name:
            return task
        for key in ("block", "rescue", "always"):
            nested = task.get(key)
            if isinstance(nested, list):
                try:
                    return find_task(nested, name)
                except StopIteration:
                    continue
    raise StopIteration(name)


def test_one_api_runtime_defaults_use_private_controller_url() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["one_api_image"] == "{{ container_image_catalog.images.one_api_runtime.ref }}"
    assert "| urlencode" in defaults["one_api_sql_dsn"]
    assert defaults["one_api_controller_url"].startswith("http://{{ hostvars['proxmox_florin'].management_tailscale_ipv4 }}")
    assert "one_api_host_proxy_port" in defaults["one_api_controller_url"]
    assert defaults["one_api_root_access_token_local_file"].endswith("/.local/one-api/root-access-token.txt")


def test_one_api_runtime_bootstraps_openbao_env_and_root_contract() -> None:
    tasks = load_tasks()

    secret_payload_task = find_task(tasks, "Record the One-API runtime secrets")
    openbao_helper = find_task(tasks, "Prepare OpenBao agent runtime secret injection for One-API")
    openbao_agent_up_task = find_task(tasks, "Start the One-API OpenBao agent")
    runtime_env_wait_task = find_task(tasks, "Wait for the One-API runtime env file")
    bridge_helper = find_task(tasks, "Ensure Docker bridge chains are healthy before One-API startup")
    up_task = find_task(tasks, "Converge the One-API runtime stack")
    force_recreate_task = find_task(tasks, "Force-recreate the One-API runtime stack")

    runtime_secret_payload = secret_payload_task["ansible.builtin.set_fact"]["one_api_runtime_secret_payload"]
    assert runtime_secret_payload["INITIAL_ROOT_ACCESS_TOKEN"] == (
        "{{ lookup('ansible.builtin.file', one_api_root_access_token_local_file) | trim }}"
    )
    assert runtime_secret_payload["PORT"] == "{{ one_api_internal_http_port | string }}"
    assert runtime_secret_payload["MEMORY_CACHE_ENABLED"] == "true"
    assert "| urlencode" in runtime_secret_payload["SQL_DSN"]
    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert openbao_agent_up_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "openbao-agent"]
    assert runtime_env_wait_task["ansible.builtin.shell"].startswith("set -euo pipefail")
    assert 'grep -Fqx "PORT={{ one_api_internal_http_port }}" "{{ one_api_env_file }}"' in runtime_env_wait_task["ansible.builtin.shell"]
    assert bridge_helper["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert up_task["ansible.builtin.command"]["argv"][-2:] == ["-d", "--remove-orphans"]
    assert force_recreate_task["ansible.builtin.command"]["argv"][-1] == "--force-recreate"


def test_one_api_verify_task_checks_status_and_authenticated_admin_api() -> None:
    tasks = yaml.safe_load(VERIFY_PATH.read_text(encoding="utf-8"))

    status_task = next(task for task in tasks if task.get("name") == "Verify One-API responds on the local status endpoint")
    admin_task = next(
        task for task in tasks if task.get("name") == "Verify the One-API admin API accepts the repo-managed root access token"
    )
    assert_task = next(task for task in tasks if task.get("name") == "Assert One-API status and authenticated admin access are working")

    assert status_task["ansible.builtin.uri"]["url"] == "{{ one_api_local_url }}/api/status"
    assert admin_task["ansible.builtin.uri"]["headers"]["Authorization"] == "{{ one_api_root_access_token }}"
    assert "one_api_verify_status.status == 200" in assert_task["ansible.builtin.assert"]["that"]
    assert "one_api_verify_root_user.json.data.username == 'root'" in assert_task["ansible.builtin.assert"]["that"]


def test_one_api_compose_template_uses_openbao_agent_and_runtime_env() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "  openbao-agent:" in template
    assert "  one-api:" in template
    assert "      - {{ one_api_env_file }}" in template
    assert '"{{ one_api_internal_http_port }}:{{ one_api_internal_http_port }}"' in template


def test_one_api_env_template_renders_expected_runtime_keys() -> None:
    template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'SQL_DSN=[[ with secret "kv/data/{{ one_api_openbao_secret_path }}" ]][[ .Data.data.SQL_DSN ]][[ end ]]' in template
    assert "INITIAL_ROOT_ACCESS_TOKEN" in template
    assert "SESSION_SECRET" in template
    assert "MEMORY_CACHE_ENABLED" in template


def test_one_api_playbook_bootstraps_channels_and_tokens_from_localhost() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))

    bootstrap_play = next(
        play
        for play in plays
        if play["name"] == "Bootstrap One-API channels, tokens, and consumer provider env files from the controller"
    )
    task = bootstrap_play["tasks"][0]

    assert task["ansible.builtin.command"]["argv"][0] == "python3"
    assert task["ansible.builtin.command"]["argv"][1] == "{{ one_api_bootstrap_script }}"
    assert "--root-access-token-file" in task["ansible.builtin.command"]["argv"]
    assert "--root-password-file" in task["ansible.builtin.command"]["argv"]
    assert task["retries"] == 5
    assert task["delay"] == 3


def test_one_api_bootstrap_config_declares_chat_fallback_embedding_and_consumer_tokens() -> None:
    config = json.loads(BOOTSTRAP_CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["root_user"]["username"] == "root"
    assert [channel["name"] for channel in config["channels"]] == [
        "ollama-primary-chat",
        "ollama-fallback-chat",
        "ollama-embedding",
    ]
    assert config["channels"][0]["priority"] > config["channels"][1]["priority"]
    assert config["verification"]["chat_model"] == "gpt-4o-mini"
    assert config["verification"]["embedding_model"] == "text-embedding-3-small"
    assert any(token["name"] == "open-webui" for token in config["tokens"])
    assert any(token["name"] == "serverclaw" for token in config["tokens"])
