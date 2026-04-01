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
    pre_restart_ids = next(
        task for task in tasks if task.get("name") == "Record container ids that are running before the Grist-triggered Docker restart"
    )
    pre_restart_inspect = next(
        task for task in tasks if task.get("name") == "Inspect running containers before the Grist-triggered Docker restart"
    )
    pre_restart_record = next(
        task for task in tasks if task.get("name") == "Record containers that were running before the Grist-triggered Docker restart"
    )
    nat_restore = next(task for task in tasks if task.get("name") == "Restore Docker networking when the nat chain is missing before Grist startup")
    nat_recheck = next(task for task in tasks if task.get("name") == "Recheck the Docker nat chain before Grist startup")
    docker_info = next(task for task in tasks if task.get("name") == "Wait for the Docker daemon to answer after networking recovery")
    post_restart_inspect = next(
        task for task in tasks if task.get("name") == "Re-inspect pre-restart containers after the Grist-triggered Docker restart"
    )
    stopped_record = next(
        task for task in tasks if task.get("name") == "Record pre-restart containers that remained stopped after the Grist-triggered Docker restart"
    )
    recover_containers = next(
        task for task in tasks if task.get("name") == "Recover pre-restart containers that remained stopped after the Grist-triggered Docker restart"
    )
    confirm_recovery = next(
        task for task in tasks if task.get("name") == "Confirm pre-restart containers recovered after the Grist-triggered Docker restart"
    )
    persist_dir = next(task for task in tasks if task.get("name") == "Ensure the Grist persist directory is writable by the runtime user")
    persist_recurse = next(task for task in tasks if task.get("name") == "Ensure existing Grist persist content is owned by the runtime user")
    env_render = next(task for task in tasks if task.get("name") == "Render the Grist environment file")
    compose_render = next(task for task in tasks if task.get("name") == "Render the Grist compose file")
    keycloak_discovery = next(
        task for task in tasks
        if task.get("name") == "Wait for the Keycloak issuer discovery document through the shared edge route before Grist startup"
    )
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
    auth_surface_probe = next(task for task in tasks if task.get("name") == "Probe the Grist local auth surface before final verification")
    auth_recovery_fact = next(task for task in tasks if task.get("name") == "Record whether the Grist login middleware needs recovery")
    auth_recovery_discovery = next(
        task for task in tasks
        if task.get("name") == "Wait for the Keycloak issuer discovery document through the shared edge route before Grist login middleware recovery"
    )
    auth_recovery_up = next(task for task in tasks if task.get("name") == "Force-recreate the Grist runtime after OIDC bootstrap recovery")
    auth_recovery_wait = next(task for task in tasks if task.get("name") == "Wait for Grist to listen locally after login middleware recovery")
    task_names = [task.get("name") for task in tasks]

    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert task_names.index("Record container ids that are running before the Grist-triggered Docker restart") < task_names.index(
        "Restore Docker networking when the nat chain is missing before Grist startup"
    )
    assert pre_restart_ids["ansible.builtin.command"]["argv"] == ["docker", "ps", "-q", "--no-trunc"]
    assert pre_restart_inspect["ansible.builtin.command"]["stdin"] == "{{ grist_pre_restart_container_ids.stdout_lines | to_json }}"
    assert '["docker", "inspect", container_id]' in pre_restart_inspect["ansible.builtin.command"]["argv"][2]
    assert "grist_pre_restart_container_details" in pre_restart_record["ansible.builtin.set_fact"]
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert nat_recheck["until"] == "grist_docker_nat_chain_recheck.rc == 0"
    assert docker_info["ansible.builtin.command"]["argv"] == ["docker", "info", "--format", '{{ "{{.ServerVersion}}" }}']
    assert post_restart_inspect["ansible.builtin.command"]["stdin"] == "{{ grist_pre_restart_container_names | default([]) | to_json }}"
    assert "grist_stopped_pre_restart_container_details" in stopped_record["ansible.builtin.set_fact"]
    assert recover_containers["ansible.builtin.command"]["stdin"] == (
        "{{ (grist_stopped_pre_restart_container_details | default([])) | to_json }}"
    )
    assert "TRANSIENT_DOCKER_NETWORK_ERRORS" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "STALE_COMPOSE_ENDPOINT_ERRORS" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "retry_on_any_error=False" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def combined_output(stdout, stderr):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def exception_output(exc):" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "OPENBAO_HEALTH_URL" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "wait_for_local_openbao" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '"http://127.0.0.1:8201/v1/sys/health"' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "No chain/target/match by that name" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "failed to create endpoint" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "retry_on_any_error=True" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'attempts=5,' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'delay_seconds=5,' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "run_with_retry(" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "cwd=working_dir or None," in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "def is_local_openbao_group(" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'normalized_working_dir == "/opt/openbao"' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert '"lv3-openbao" in container_names' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'if "openbao-agent" in services and not local_openbao_group:' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'remove_command = ["docker", "rm", "-f", *container_names]' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'recovery_command.extend(["up", "-d", "--force-recreate", *services])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'down_command.extend(["down", "--remove-orphans"])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'final_up_command.extend(["up", "-d", *services])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "docker_compose_down_remove_orphans" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "docker_compose_up_after_down" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "com.docker.compose.project.working_dir" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "docker_compose_up" in recover_containers["ansible.builtin.command"]["argv"][2]
    assert 'command.extend(["up", "-d", "--force-recreate", *services])' in recover_containers["ansible.builtin.command"]["argv"][2]
    assert "NONPERSISTENT_RESTART_POLICIES = {\"\", \"no\"}" in confirm_recovery["ansible.builtin.command"]["argv"][2]
    assert confirm_recovery["until"] == "grist_recovered_container_inspect.rc == 0"
    assert confirm_recovery["retries"] == 12
    assert confirm_recovery["delay"] == 5
    assert persist_dir["ansible.builtin.file"]["path"] == "{{ grist_persist_dir }}"
    assert persist_dir["ansible.builtin.file"]["owner"] == "{{ grist_runtime_uid }}"
    assert persist_recurse["ansible.builtin.file"]["recurse"] is True
    assert env_render["register"] == "grist_env_template"
    assert env_render["ansible.builtin.template"]["dest"] == "{{ grist_static_env_file }}"
    assert compose_render["register"] == "grist_compose_template"
    assert "--resolve" in keycloak_discovery["ansible.builtin.shell"]
    assert "--connect-timeout 5" in keycloak_discovery["ansible.builtin.shell"]
    assert "--max-time 10" in keycloak_discovery["ansible.builtin.shell"]
    assert "{{ grist_public_edge_private_ip }}" in keycloak_discovery["ansible.builtin.shell"]
    assert "{{ grist_keycloak_issuer }}/.well-known/openid-configuration" in keycloak_discovery["ansible.builtin.shell"]
    assert "{{ hostvars[\"proxmox_florin\"].lv3_service_topology.keycloak.public_hostname }}" in keycloak_discovery["ansible.builtin.shell"]
    assert 'DISCOVERY_JSON="$discovery_json" python3 - "{{ grist_keycloak_issuer }}" <<\'PY\'' in keycloak_discovery["ansible.builtin.shell"]
    assert 'payload = json.loads(os.environ["DISCOVERY_JSON"])' in keycloak_discovery["ansible.builtin.shell"]
    assert keycloak_discovery["until"] == "grist_keycloak_discovery.rc == 0"
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
    assert auth_surface_probe["ansible.builtin.uri"]["url"] == "{{ grist_internal_base_url }}/o/docs/"
    assert auth_surface_probe["ansible.builtin.uri"]["headers"]["Host"] == "{{ grist_service_topology.public_hostname }}"
    auth_recovery_expression = auth_recovery_fact["ansible.builtin.set_fact"]["grist_oidc_login_recovery_needed"]
    assert "(grist_pre_verify_auth_surface.status | int) in [200, 400]" in auth_recovery_expression
    assert '"errMessage":"No login system is configured"' in auth_recovery_expression
    assert "--resolve" in auth_recovery_discovery["ansible.builtin.shell"]
    assert "--connect-timeout 5" in auth_recovery_discovery["ansible.builtin.shell"]
    assert "--max-time 10" in auth_recovery_discovery["ansible.builtin.shell"]
    assert "{{ grist_public_edge_private_ip }}" in auth_recovery_discovery["ansible.builtin.shell"]
    assert 'payload = json.loads(os.environ["DISCOVERY_JSON"])' in auth_recovery_discovery["ansible.builtin.shell"]
    assert auth_recovery_discovery["until"] == "grist_keycloak_discovery_recovery.rc == 0"
    assert auth_recovery_up["ansible.builtin.command"]["argv"][-3:] == ["--force-recreate", "--no-deps", "grist"]
    assert auth_recovery_up["register"] == "grist_oidc_recovery_up"
    assert auth_recovery_up["until"] == "grist_oidc_recovery_up.rc == 0"
    assert auth_recovery_wait["ansible.builtin.wait_for"]["port"] == "{{ grist_internal_port }}"
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
    assert '"errMessage":"No login system is configured"' in login_gate_expression


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
    assert '"errMessage":"No login system is configured"' in local_gate_expression


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
    assert "node -e" in compose_template
    assert "http://127.0.0.1:8484/status" in compose_template
    assert "wget --no-verbose" not in compose_template
