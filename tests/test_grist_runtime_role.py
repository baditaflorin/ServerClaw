from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "grist_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "grist_runtime" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "grist_runtime" / "tasks" / "verify.yml"
PUBLISH_PATH = REPO_ROOT / "roles" / "grist_runtime" / "tasks" / "publish.yml"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "grist_runtime" / "templates" / "grist.env.j2"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "grist_runtime" / "templates" / "docker-compose.yml.j2"
ENV_CTEMPLATE_PATH = REPO_ROOT / "roles" / "grist_runtime" / "templates" / "grist.env.ctmpl.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_public_oidc_and_local_artifacts() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    assert defaults["grist_public_base_url"] == "https://{{ grist_service_topology.public_hostname }}"
    assert defaults["grist_session_authority"] == "{{ platform_session_authority }}"
    assert defaults["grist_public_edge_private_ip"] == "{{ hostvars['proxmox_florin'].proxmox_public_edge_ipv4 }}"
    assert defaults["grist_public_hostname_overrides"][0]["hostname"] == "{{ grist_service_topology.public_hostname }}"
    assert defaults["grist_public_hostname_overrides"][1]["hostname"] == "{{ hostvars['proxmox_florin'].lv3_service_topology.keycloak.public_hostname }}"
    assert defaults["grist_internal_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.grist_port }}"
    assert defaults["grist_internal_base_url"] == "http://127.0.0.1:{{ grist_internal_port }}"
    assert defaults["grist_static_env_file"] == "{{ grist_site_dir }}/grist.env"
    assert defaults["grist_keycloak_client_id"] == "grist"
    assert defaults["grist_keycloak_issuer"] == "https://sso.lv3.org/realms/lv3"
    assert defaults["grist_keycloak_scopes"] == "openid profile email"
    assert defaults["grist_force_login"] is True
    assert defaults["grist_runtime_uid"] == "1001"
    assert defaults["grist_runtime_gid"] == "1001"
    assert defaults["grist_session_secret_local_file"].endswith("/.local/grist/session-secret.txt")
    assert defaults["grist_keycloak_client_secret_local_file"].endswith("/.local/keycloak/grist-client-secret.txt")


def test_runtime_role_requires_only_the_keycloak_client_secret_before_startup() -> None:
    tasks = load_yaml(TASKS_PATH)
    validate_task = next(task for task in tasks if task.get("name") == "Validate Grist runtime inputs")
    package_task = next(task for task in tasks if task.get("name") == "Ensure the Grist runtime packages are present")
    secret_fact = next(task for task in tasks if task.get("name") == "Record the Grist runtime secrets")
    verify_import = next(task for task in tasks if task.get("name") == "Verify the Grist runtime")

    assert "grist_static_env_file | length > 0" in validate_task["ansible.builtin.assert"]["that"]
    assert "grist_keycloak_client_secret_local_file | length > 0" in validate_task["ansible.builtin.assert"]["that"]
    assert "grist_runtime_uid | length > 0" in validate_task["ansible.builtin.assert"]["that"]
    assert "grist_runtime_gid | length > 0" in validate_task["ansible.builtin.assert"]["that"]
    assert "grist_session_secret_local_file | length > 0" not in validate_task["ansible.builtin.assert"]["that"]
    assert package_task["ansible.builtin.apt"]["name"] == ["openssl"]
    assert "GRIST_SESSION_SECRET" in secret_fact["ansible.builtin.set_fact"]["grist_runtime_secret_payload"]
    assert verify_import["ansible.builtin.import_tasks"] == "verify.yml"


def test_runtime_role_recovers_docker_nat_chain_before_grist_startup() -> None:
    tasks = load_yaml(TASKS_PATH)
    nat_check = next(task for task in tasks if task.get("name") == "Check whether the Docker nat chain exists before Grist startup")
    nat_restore = next(task for task in tasks if task.get("name") == "Restore Docker networking when the nat chain is missing before Grist startup")
    nat_recheck = next(task for task in tasks if task.get("name") == "Recheck the Docker nat chain before Grist startup")
    docker_info = next(task for task in tasks if task.get("name") == "Wait for the Docker daemon to answer after networking recovery")
    persist_dir = next(task for task in tasks if task.get("name") == "Ensure the Grist persist directory is writable by the runtime user")
    persist_recurse = next(task for task in tasks if task.get("name") == "Ensure existing Grist persist content is owned by the runtime user")
    env_render = next(task for task in tasks if task.get("name") == "Render the Grist environment file")
    compose_render = next(task for task in tasks if task.get("name") == "Render the Grist compose file")
    keycloak_discovery = next(task for task in tasks if task.get("name") == "Wait for the Keycloak issuer discovery document before Grist startup")
    local_port_probe = next(task for task in tasks if task.get("name") == "Check whether the Grist local port is already published")
    status_probe = next(task for task in tasks if task.get("name") == "Check whether the current Grist local status endpoint is healthy before startup")
    force_recreate_fact = next(task for task in tasks if task.get("name") == "Record whether the Grist startup needs a force recreate")
    replace_cleanup = next(task for task in tasks if task.get("name") == "Remove stale Grist compose replacement containers before recovery")
    openbao_recreate = next(task for task in tasks if task.get("name") == "Force-recreate the Grist OpenBao agent after Docker networking recovery")
    runtime_env_contract = next(task for task in tasks if task.get("name") == "Wait for the Grist runtime env file after OpenBao agent recovery")
    force_recreate = next(task for task in tasks if task.get("name") == "Force-recreate the Grist runtime stack after Docker networking recovery")
    network_flag = next(task for task in tasks if task.get("name") == "Flag stale Grist compose-network failures during force-recreate")
    network_reset = next(task for task in tasks if task.get("name") == "Reset stale Grist compose resources before retrying force-recreate")
    network_cleanup = next(task for task in tasks if task.get("name") == "Remove the stale Grist compose network before retrying force-recreate")
    bridge_chain_helper = next(
        task for task in tasks if task.get("name") == "Ensure Docker bridge networking chains are present before retrying Grist force-recreate"
    )
    network_retry = next(task for task in tasks if task.get("name") == "Retry Grist force-recreate after Docker networking recovery")

    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert nat_recheck["until"] == "grist_docker_nat_chain_recheck.rc == 0"
    assert docker_info["ansible.builtin.command"]["argv"] == ["docker", "info", "--format", '{{ "{{.ServerVersion}}" }}']
    assert persist_dir["ansible.builtin.file"]["path"] == "{{ grist_persist_dir }}"
    assert persist_dir["ansible.builtin.file"]["owner"] == "{{ grist_runtime_uid }}"
    assert persist_recurse["ansible.builtin.file"]["recurse"] is True
    assert env_render["register"] == "grist_env_template"
    assert env_render["ansible.builtin.template"]["dest"] == "{{ grist_static_env_file }}"
    assert compose_render["register"] == "grist_compose_template"
    assert keycloak_discovery["ansible.builtin.uri"]["url"] == "{{ grist_keycloak_issuer }}/.well-known/openid-configuration"
    assert "grist_keycloak_discovery.status == 200" in keycloak_discovery["until"]
    assert local_port_probe["ansible.builtin.wait_for"]["port"] == "{{ grist_internal_port }}"
    assert status_probe["ansible.builtin.uri"]["url"] == "{{ grist_internal_base_url }}/status"
    assert "com.docker.compose.replace" in replace_cleanup["ansible.builtin.shell"]
    assert openbao_recreate["ansible.builtin.command"]["argv"][-2:] == ["--force-recreate", "openbao-agent"]
    assert "GRIST_SESSION_SECRET=" in runtime_env_contract["ansible.builtin.shell"]
    assert runtime_env_contract["retries"] == 24
    assert runtime_env_contract["no_log"] is True
    assert "--force-recreate --no-deps grist" in force_recreate["ansible.builtin.shell"]
    assert force_recreate["register"] == "grist_force_recreate_up"
    assert force_recreate["failed_when"] is False
    assert "failed to create endpoint" in network_flag["ansible.builtin.set_fact"]["grist_force_recreate_network_missing"]
    assert network_reset["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert "grist_site_dir | basename" in network_cleanup["ansible.builtin.shell"]
    assert bridge_chain_helper["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    assert network_retry["ansible.builtin.command"]["argv"][-2:] == ["--force-recreate", "--remove-orphans"]
    force_recreate_expression = force_recreate_fact["ansible.builtin.set_fact"]["grist_force_recreate"]
    assert "grist_env_template.changed" in force_recreate_expression
    assert "grist_compose_template.changed" in force_recreate_expression
    assert "grist_pull.changed" in force_recreate_expression


def test_publish_tasks_wait_for_public_status_and_verify_login_gating() -> None:
    tasks = load_yaml(PUBLISH_PATH)
    status_task = next(task for task in tasks if task.get("name") == "Wait for the Grist public status endpoint")
    redirect_task = next(task for task in tasks if task.get("name") == "Verify the Grist public document route reaches the auth-controlled surface")
    assert_task = next(task for task in tasks if task.get("name") == "Assert the Grist public document route is login-gated")

    assert status_task["ansible.builtin.uri"]["url"] == "{{ grist_public_base_url }}/status"
    assert redirect_task["ansible.builtin.uri"]["url"] == "{{ grist_public_base_url }}/o/docs/"
    assert redirect_task["ansible.builtin.uri"]["follow_redirects"] == "none"
    assert redirect_task["ansible.builtin.uri"]["return_content"] is True
    assert 200 in redirect_task["ansible.builtin.uri"]["status_code"]
    assert 400 in redirect_task["ansible.builtin.uri"]["status_code"]
    assert 302 in redirect_task["ansible.builtin.uri"]["status_code"]
    login_gate_expression = assert_task["ansible.builtin.assert"]["that"][0]
    assert "grist_publish_auth_redirect.location is defined" in login_gate_expression
    assert "(grist_publish_auth_redirect.status | int) in [200, 400]" in login_gate_expression
    assert "'Loading... - Grist'" in login_gate_expression
    assert '\'"supportAnon":false\'' in login_gate_expression


def test_verify_task_checks_the_local_status_endpoint() -> None:
    verify = load_yaml(VERIFY_PATH)
    health_task = next(task for task in verify if task.get("name") == "Verify the Grist local status endpoint")
    auth_tasks = [task for task in verify if task.get("name") == "Verify the Grist local document route reaches the auth-controlled surface"]
    assert_tasks = [task for task in verify if task.get("name") == "Assert the Grist local document route is login-gated"]
    assert len(auth_tasks) == 1
    assert len(assert_tasks) == 1
    auth_task = auth_tasks[0]
    assert_task = assert_tasks[0]
    assert health_task["ansible.builtin.uri"]["url"] == "{{ grist_internal_base_url }}/status"
    assert auth_task["ansible.builtin.uri"]["url"] == "{{ grist_internal_base_url }}/o/docs/"
    assert auth_task["ansible.builtin.uri"]["headers"]["Host"] == "{{ grist_service_topology.public_hostname }}"
    assert 400 in auth_task["ansible.builtin.uri"]["status_code"]
    local_gate_expression = assert_task["ansible.builtin.assert"]["that"][0]
    assert "grist_verify_local_auth_surface.location is defined" in local_gate_expression
    assert "(grist_verify_local_auth_surface.status | int) in [200, 400]" in local_gate_expression


def test_grist_templates_enable_persistent_oidc_runtime() -> None:
    env_template = ENV_TEMPLATE_PATH.read_text()
    env_ctemplate = ENV_CTEMPLATE_PATH.read_text()
    compose_template = COMPOSE_TEMPLATE_PATH.read_text()
    assert "APP_HOME_URL={{ grist_public_base_url }}" in env_template
    assert "GRIST_FORCE_LOGIN={{ 'true' if grist_force_login else 'false' }}" in env_template
    assert "GRIST_OIDC_SP_HOST={{ grist_keycloak_sp_host }}" in env_template
    assert 'GRIST_SESSION_SECRET=[[ with secret "kv/data/{{ grist_openbao_secret_path }}" ]][[ .Data.data.GRIST_SESSION_SECRET ]][[ end ]]' in env_ctemplate
    assert 'GRIST_OIDC_IDP_CLIENT_SECRET=[[ with secret "kv/data/{{ grist_openbao_secret_path }}" ]][[ .Data.data.GRIST_OIDC_IDP_CLIENT_SECRET ]][[ end ]]' in env_ctemplate
    assert "      - {{ grist_static_env_file }}" in compose_template
    assert "      - {{ grist_persist_dir }}:/persist" in compose_template
    assert '      - "{{ ansible_host }}:{{ grist_internal_port }}:8484"' in compose_template
    assert '      - "127.0.0.1:{{ grist_internal_port }}:8484"' in compose_template
    assert '      - "{{ item.hostname }}:{{ item.address }}"' in compose_template
