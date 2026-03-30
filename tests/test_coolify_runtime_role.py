from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "coolify_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
VERIFY_PATH = ROLE_ROOT / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = ROLE_ROOT / "templates" / "coolify.env.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_use_service_topology_urls_and_local_artifact_contract() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    assert defaults["coolify_dashboard_port"] == "{{ platform_service_topology | platform_service_port('coolify', 'internal') }}"
    assert defaults["coolify_proxy_port"] == "{{ platform_service_topology | platform_service_port('coolify_apps', 'internal') }}"
    assert defaults["coolify_controller_url"] == "{{ platform_service_topology | platform_service_url('coolify', 'controller') }}"
    assert defaults["coolify_private_url"] == "http://{{ ansible_host }}:{{ coolify_dashboard_port }}"
    assert defaults["coolify_public_url"] == "https://coolify.lv3.org"
    assert defaults["coolify_apps_public_url"] == "https://apps.lv3.org"
    assert defaults["coolify_proxy_service_name"] == "coolify-proxy"
    assert defaults["coolify_proxy_image"] == "traefik:v3.6"
    assert defaults["coolify_proxy_path"] == "{{ coolify_data_root }}/proxy"
    assert defaults["coolify_bridge_subnet"] == "172.18.0.0/16"
    assert defaults["coolify_bridge_gateway"] == "172.18.0.1"
    assert defaults["coolify_api_allowed_ips"] == ["127.0.0.1", "{{ coolify_bridge_gateway }}", "10.10.10.1"]
    assert defaults["coolify_server_proxy_type"] == "TRAEFIK"
    assert defaults["coolify_root_password_local_file"] == "{{ coolify_local_artifact_dir }}/root-password.txt"
    assert defaults["coolify_api_token_local_file"] == "{{ coolify_local_artifact_dir }}/api-token.txt"
    assert defaults["coolify_server_key_local_file"] == "{{ coolify_local_artifact_dir }}/server-key"
    assert defaults["coolify_admin_auth_local_file"] == "{{ coolify_local_artifact_dir }}/admin-auth.json"
    assert defaults["coolify_smoke_domain"] == "http://apps.lv3.org"
    assert defaults["coolify_smoke_alias_domain"] == "http://repo-smoke.apps.lv3.org"


def test_main_tasks_bootstrap_api_token_and_local_server_registration() -> None:
    tasks = load_yaml(TASKS_PATH)
    task_names = [task["name"] for task in tasks]
    names = {task["name"] for task in tasks}
    assert "Ensure the Coolify deployment SSH key exists locally" in names
    assert "Ensure the Coolify root account and API settings are enforced" in names
    assert "Register the Coolify deployment SSH key and local server" in names
    assert "Wait for the guest-local Coolify health endpoint" in names
    assert "Rotate the Coolify API token and persist it locally" in names
    assert "Persist the Coolify controller auth locally" in names

    wait_for_port_idx = task_names.index("Wait for Coolify to listen on the guest dashboard port")
    bootstrap_idx = task_names.index("Ensure the Coolify root account and API settings are enforced")
    register_idx = task_names.index("Register the Coolify deployment SSH key and local server")
    assert_local_server_idx = task_names.index("Assert the Coolify local deployment server is usable")
    health_idx = task_names.index("Wait for the guest-local Coolify health endpoint")

    bootstrap_task = next(task for task in tasks if task["name"] == "Ensure the Coolify root account and API settings are enforced")
    register_task = next(task for task in tasks if task["name"] == "Register the Coolify deployment SSH key and local server")
    record_task = next(task for task in tasks if task["name"] == "Record the Coolify server registration payload")
    emit_assert_task = next(task for task in tasks if task["name"] == "Assert the Coolify server registration payload was emitted")
    token_task = next(task for task in tasks if task["name"] == "Rotate the Coolify API token and persist it locally")
    assert wait_for_port_idx < bootstrap_idx < register_idx < assert_local_server_idx < health_idx
    assert "InstanceSettings" in bootstrap_task["ansible.builtin.shell"]
    assert "allowed_ips" in bootstrap_task["ansible.builtin.shell"]
    assert '"__LV3_BOOTSTRAP__"' in bootstrap_task["ansible.builtin.shell"]
    assert '$server->proxy->set("type", "{{ coolify_server_proxy_type }}");' in register_task["ansible.builtin.shell"]
    assert '$server->proxy->set("status", "exited");' in register_task["ansible.builtin.shell"]
    assert "ValidateServer::run($server)" in register_task["ansible.builtin.shell"]
    assert 'StandaloneDocker::where("server_id", $server->id)' in register_task["ansible.builtin.shell"]
    assert '"__LV3_SERVER_REGISTRATION__"' in register_task["ansible.builtin.shell"]
    assert "coolify_server_registration.stdout_lines" in record_task["ansible.builtin.set_fact"]["coolify_server_registration_payload"]
    assert "^__LV3_SERVER_REGISTRATION__" in record_task["ansible.builtin.set_fact"]["coolify_server_registration_payload"]
    assert emit_assert_task["ansible.builtin.assert"]["that"] == ["coolify_server_registration_payload | length > 0"]
    assert "$user->tokens()->where(\"name\", \"{{ coolify_api_token_name }}\")->delete();" in token_task["ansible.builtin.shell"]


def test_templates_render_upstream_like_runtime_contract() -> None:
    compose = COMPOSE_TEMPLATE.read_text()
    env_template = ENV_TEMPLATE.read_text()
    assert "container_name: {{ coolify_proxy_service_name }}" in compose
    assert "image: {{ coolify_proxy_image }}" in compose
    assert '"{{ coolify_proxy_port }}:80"' in compose
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in compose
    assert "{{ coolify_proxy_path }}:/traefik" in compose
    assert "--providers.docker=true" in compose
    assert "host.docker.internal:host-gateway" in compose
    assert "{{ coolify_env_file }}" in compose
    assert "{{ coolify_data_root }}/applications:/var/www/html/storage/app/applications" in compose
    assert '"{{ coolify_dashboard_port }}:8080"' in compose
    assert "subnet: {{ coolify_bridge_subnet }}" in compose
    assert "gateway: {{ coolify_bridge_gateway }}" in compose
    assert "coolify-db:/var/lib/postgresql/data" in compose
    assert "redis-server --save 20 1 --loglevel warning --requirepass {{ coolify_redis_password }}" in compose
    assert "APP_KEY={{ coolify_app_key }}" in env_template
    assert "ROOT_USER_PASSWORD={{ coolify_root_password }}" in env_template


def test_verify_checks_private_controller_api_visibility() -> None:
    verify = load_yaml(VERIFY_PATH)
    version_task = next(task for task in verify if task["name"] == "Verify the private controller API version endpoint")
    team_task = next(task for task in verify if task["name"] == "Verify the private controller can read the current team")
    servers_task = next(task for task in verify if task["name"] == "Read the private controller server inventory")
    assert_task = next(
        task
        for task in verify
        if task["name"] == "Assert the registered Coolify deployment server is visible through the private controller"
    )
    assert version_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ coolify_dashboard_port }}/api/v1/version"
    assert team_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ coolify_dashboard_port }}/api/v1/teams/current"
    assert servers_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ coolify_dashboard_port }}/api/v1/servers"
    assert "(coolify_controller_version.content | default('') | trim) | length > 0" in assert_task["ansible.builtin.assert"]["that"]
    assert "(coolify_current_team.json.name | default('') | trim) | length > 0" in assert_task["ansible.builtin.assert"]["that"]
