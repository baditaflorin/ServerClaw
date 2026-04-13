from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "main.yml"
REPO_USER_TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "reconcile_repo_managed_users.yml"
ADMIN_CLIENT_TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "reconcile_admin_client.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "templates" / "docker-compose.yml.j2"
SERVERCLAW_TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "serverclaw_client.yml"
PLANE_CLIENT_TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "plane_client.yml"
COMMON_COMPOSE_MACROS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "common"
    / "templates"
    / "compose_macros.j2"
)
PLAYBOOK_COMPOSE_MACROS_PATH = REPO_ROOT / "playbooks" / "templates" / "compose_macros.j2"


def load_tasks(path: Path = TASKS_PATH) -> list[dict]:
    raw_tasks = yaml.safe_load(path.read_text())
    flattened: list[dict] = []

    def visit(task_list: list[dict]) -> None:
        for task in task_list:
            flattened.append(task)
            for nested_key in ("block", "rescue", "always"):
                nested_tasks = task.get(nested_key)
                if nested_tasks:
                    visit(nested_tasks)

    visit(raw_tasks)
    return flattened


def load_serverclaw_tasks() -> list[dict]:
    return yaml.safe_load(SERVERCLAW_TASKS_PATH.read_text())


def load_admin_client_tasks() -> list[dict]:
    return yaml.safe_load(ADMIN_CLIENT_TASKS_PATH.read_text())


def load_plane_client_tasks() -> list[dict]:
    return yaml.safe_load(PLANE_CLIENT_TASKS_PATH.read_text())


def assert_task_retries(task: dict, register: str) -> None:
    assert task["register"] == register
    assert task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert task["until"] == f"{register} is succeeded"


def test_playbook_template_loader_exports_current_shared_compose_macros() -> None:
    assert PLAYBOOK_COMPOSE_MACROS_PATH.read_text() == COMMON_COMPOSE_MACROS_PATH.read_text()


def test_plane_oidc_client_reconciliation_uses_keycloak_client_module() -> None:
    tasks = load_plane_client_tasks()
    config_task = next(task for task in tasks if task.get("name") == "Set Plane OIDC client configuration facts")
    reconcile_task = next(task for task in tasks if task.get("name") == "Ensure Plane OIDC client exists")

    assert config_task["ansible.builtin.set_fact"]["plane_oidc_public_url"] == (
        "{{ hostvars[platform_topology_host].platform_service_topology.plane.urls.public }}"
    )
    assert config_task["ansible.builtin.set_fact"]["plane_oidc_internal_url"] == (
        "{{ hostvars[platform_topology_host].platform_service_topology.plane.urls.internal }}"
    )

    client = reconcile_task["community.general.keycloak_client"]
    assert client["client_id"] == "{{ plane_oidc_client_id }}"
    assert client["secret"] == "{{ plane_oidc_client_secret }}"
    assert client["redirect_uris"] == [
        "{{ plane_oidc_public_url }}/auth/callback/keycloak",
        "{{ plane_oidc_public_url }}/auth/oidc/callback",
        "{{ plane_oidc_internal_url }}/auth/callback/keycloak",
        "{{ plane_oidc_internal_url }}/auth/oidc/callback",
    ]
    assert client["valid_post_logout_redirect_uris"] == "{{ keycloak_plane_post_logout_redirect_uris }}"
    assert reconcile_task["register"] == "plane_client_reconcile"
    assert reconcile_task["until"] == "plane_client_reconcile is succeeded"


def test_defaults_define_internal_mail_submission_for_realm_mail() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    smtp_server = defaults["keycloak_realm_smtp_server"]
    assert defaults["keycloak_session_authority"] == "{{ platform_session_authority }}"
    assert (
        defaults["keycloak_database_host"]
        == "{{ hostvars[hostvars[platform_topology_host].postgres_ha.initial_primary].ansible_host }}"
    )
    assert defaults["keycloak_mail_platform_submission_host"] == "{{ smtp_host }}"
    assert defaults["keycloak_mail_platform_submission_port"] == "{{ smtp_port }}"
    assert defaults["keycloak_mail_platform_submission_starttls"] == "{{ smtp_starttls }}"
    assert defaults["keycloak_mail_platform_submission_auth_enabled"] == "{{ smtp_auth_enabled }}"
    assert defaults["keycloak_mail_platform_docker_network_name"] == "{{ smtp_docker_network_name }}"
    assert defaults["keycloak_mail_platform_compose_file"] == (
        "{{ mail_platform_compose_file | default('/opt/mail-platform/docker-compose.yml') }}"
    )
    assert defaults["keycloak_mail_platform_submission_service_name"] == "stalwart"
    assert (
        "keycloak_mail_platform_docker_network_name | length > 0"
        in defaults["keycloak_mail_platform_submission_recovery_enabled"]
    )
    assert (
        "keycloak_mail_platform_compose_file | length > 0"
        in defaults["keycloak_mail_platform_submission_recovery_enabled"]
    )
    assert defaults["keycloak_compose_project_name"] == "keycloak"
    assert defaults["keycloak_compose_network_name"] == "{{ keycloak_compose_project_name }}_default"
    assert defaults["keycloak_langfuse_client_id"] == "langfuse"
    assert defaults["keycloak_langfuse_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/langfuse-client-secret.txt"
    )
    assert defaults["keycloak_superset_client_id"] == "superset"
    assert defaults["keycloak_superset_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/superset-client-secret.txt"
    )
    assert defaults["keycloak_glitchtip_client_id"] == "glitchtip"
    assert defaults["keycloak_glitchtip_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/glitchtip-client-secret.txt"
    )
    assert defaults["keycloak_serverclaw_runtime_client_id"] == "serverclaw-runtime"
    assert defaults["keycloak_serverclaw_runtime_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/serverclaw-runtime-client-secret.txt"
    )
    assert defaults["keycloak_admin_client_id"] == "lv3-admin-runtime"
    assert defaults["keycloak_admin_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/admin-client-secret.txt"
    )
    assert defaults["keycloak_recovery_admin_service_client_id"] == "lv3-recovery-admin"
    assert defaults["keycloak_grist_client_id"] == "grist"
    assert defaults["keycloak_grist_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/grist-client-secret.txt"
    )
    assert defaults["keycloak_outline_automation_username"] == "outline.automation"
    assert defaults["keycloak_outline_automation_password_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/outline.automation-password.txt"
    )
    assert defaults["keycloak_ops_portal_post_logout_redirect_uris"] == [
        "{{ keycloak_ops_portal_root_url }}/",
        "{{ keycloak_ops_portal_root_url }}",
        "{{ keycloak_session_authority.shared_logged_out_url }}",
    ]
    assert defaults["keycloak_grafana_post_logout_redirect_uris"] == [
        "{{ keycloak_grafana_root_url }}/login",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert defaults["keycloak_grist_post_logout_redirect_uris"] == [
        "{{ keycloak_grist_root_url }}",
        "{{ keycloak_grist_root_url }}/",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert defaults["keycloak_glitchtip_root_url"] == "https://errors.{{ platform_domain }}"
    assert defaults["keycloak_glitchtip_post_logout_redirect_uris"] == [
        "{{ keycloak_glitchtip_root_url }}",
        "{{ keycloak_glitchtip_root_url }}/",
        "{{ keycloak_glitchtip_root_url }}/login",
    ]
    assert defaults["keycloak_outline_post_logout_redirect_uris"] == [
        "{{ keycloak_outline_root_url }}",
        "{{ keycloak_outline_root_url }}/",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert defaults["keycloak_superset_root_url"] == "https://bi.{{ platform_domain }}"
    assert defaults["keycloak_superset_post_logout_redirect_uris"] == [
        "{{ keycloak_superset_root_url }}",
        "{{ keycloak_superset_root_url }}/",
    ]
    assert defaults["keycloak_paperless_client_id"] == "paperless"
    assert defaults["keycloak_paperless_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/paperless-client-secret.txt"
    )
    assert defaults["keycloak_paperless_root_url"] == "https://paperless.{{ platform_domain }}"
    assert defaults["keycloak_paperless_post_logout_redirect_uris"] == [
        "{{ keycloak_paperless_root_url }}",
        "{{ keycloak_paperless_root_url }}/",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert smtp_server["auth"] == "{{ keycloak_mail_platform_submission_auth_enabled }}"
    assert smtp_server["host"] == "{{ keycloak_mail_platform_submission_host }}"
    assert smtp_server["port"] == "{{ keycloak_mail_platform_submission_port }}"
    assert (
        smtp_server["user"]
        == "{{ keycloak_mail_platform_submission_username if keycloak_mail_platform_submission_auth_enabled else '' }}"
    )
    assert smtp_server["starttls"] == "{{ keycloak_mail_platform_submission_starttls }}"
    assert smtp_server["ssl"] is False


def test_role_requires_local_mail_submission_secret() -> None:
    tasks = load_tasks()
    secret_check_task = next(
        task
        for task in tasks
        if task.get("name") == "Check Keycloak mail submission password when SMTP auth is enabled"
    )
    assert secret_check_task["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert secret_check_task["ansible.builtin.include_role"]["tasks_from"] == "check_local_secrets"
    assert secret_check_task["vars"]["common_check_local_secrets_files"] == [
        {
            "path": "{{ keycloak_mail_platform_submission_password_local_file }}",
            "description": "Keycloak mail submission password",
            "prerequisite": "Converge the mail platform before deploying Keycloak",
        }
    ]
    assert secret_check_task["when"] == "keycloak_mail_platform_submission_auth_enabled"


def test_ops_portal_post_logout_redirects_cover_stale_session_recovery() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())

    assert defaults["keycloak_ops_portal_root_url"] == "https://ops.{{ platform_domain }}"
    assert defaults["keycloak_ops_portal_post_logout_redirect_uris"] == [
        "{{ keycloak_ops_portal_root_url }}/",
        "{{ keycloak_ops_portal_root_url }}",
        "{{ keycloak_session_authority.shared_logged_out_url }}",
    ]


def test_role_reuses_recent_apt_cache_for_runtime_packages() -> None:
    tasks = load_tasks()
    package_task = next(
        task for task in tasks if task.get("name") == "Ensure the Keycloak runtime packages are present"
    )

    assert package_task["ansible.builtin.apt"]["cache_valid_time"] == 3600


def test_realm_task_applies_repo_managed_smtp_settings() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    assert realm_block["module_defaults"]["community.general.keycloak_realm"]["connection_timeout"] == (
        "{{ keycloak_admin_connection_timeout }}"
    )
    realm_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the LV3 realm exists")
    assert realm_task["community.general.keycloak_realm"]["smtp_server"] == "{{ keycloak_realm_smtp_server }}"
    assert_task_retries(realm_task, "keycloak_realm_reconcile")


def test_role_restores_docker_nat_chain_before_startup() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    env_render = next(task for task in tasks if task.get("name") == "Render the Keycloak environment file")
    compose_render = next(task for task in tasks if task.get("name") == "Render the Keycloak compose file")
    image_pull = next(task for task in tasks if task.get("name") == "Pull the Keycloak image")
    nat_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker nat chain exists before recreating Keycloak published ports"
    )
    nat_restore = next(
        task
        for task in tasks
        if task.get("name") == "Restore Docker networking when the nat chain is missing before Keycloak startup"
    )
    bridge_chain_helper = next(
        task
        for task in tasks
        if task.get("name") == "Ensure Docker bridge networking chains are present before Keycloak startup"
    )
    replace_cleanup = next(
        task
        for task in tasks
        if task.get("name") == "Remove stale Keycloak compose replacement containers before recovery"
    )
    project_cleanup = next(
        task for task in tasks if task.get("name") == "Remove stale Keycloak project containers before network cleanup"
    )
    force_recreate_block = next(
        task
        for task in tasks
        if task.get("name")
        == "Force-recreate the Keycloak service and recover Docker bridge-chain loss after networking recovery"
    )
    openbao_agent_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the Keycloak OpenBao agent after Docker networking recovery"
    )
    runtime_env_wait = next(
        task
        for task in tasks
        if task.get("name") == "Wait for the Keycloak runtime env file after OpenBao agent recovery"
    )
    force_recreate_fact = next(
        task for task in tasks if task.get("name") == "Record whether the Keycloak startup needs a force recreate"
    )
    force_recreate_fact = next(
        task for task in tasks if task.get("name") == "Record whether the Keycloak startup needs a force recreate"
    )
    force_recreate_down = next(
        task for task in tasks if task.get("name") == "Reset the Keycloak stack before a force recreate"
    )
    network_cleanup = next(
        task for task in tasks if task.get("name") == "Remove stale Keycloak compose networks after project cleanup"
    )
    readiness_probe = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the current Keycloak readiness endpoint is healthy before startup"
    )
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert nat_restore["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert nat_restore["ansible.builtin.include_role"]["tasks_from"] == "docker_daemon_restart"
    assert nat_restore["vars"]["common_docker_daemon_restart_service_name"] == "docker"
    assert nat_restore["vars"]["common_docker_daemon_restart_reason"] == "Keycloak startup nat-chain recovery"
    assert bridge_chain_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert bridge_chain_helper["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    assert env_render["register"] == "keycloak_env_template"
    assert compose_render["register"] == "keycloak_compose_template"
    assert compose_render["vars"]["ansible_search_path"] == (
        "{{ [role_path + '/../common'] + (ansible_search_path | default([])) }}"
    )
    assert defaults["keycloak_image_pull_retries"] == 5
    assert defaults["keycloak_image_pull_delay_seconds"] == 5
    assert image_pull["retries"] == "{{ keycloak_image_pull_retries }}"
    assert image_pull["delay"] == "{{ keycloak_image_pull_delay_seconds }}"
    assert image_pull["until"] == "keycloak_pull.rc == 0"
    assert "label=com.docker.compose.project=keycloak" in project_cleanup["ansible.builtin.shell"]
    assert "com.docker.compose.project=keycloak" in replace_cleanup["ansible.builtin.shell"]
    assert "com.docker.compose.replace" in replace_cleanup["ansible.builtin.shell"]
    assert openbao_agent_recreate["ansible.builtin.command"]["argv"][-4:] == [
        "up",
        "-d",
        "--force-recreate",
        "openbao-agent",
    ]
    assert (
        'grep -Fqx "KC_DB_URL_HOST={{ keycloak_database_host }}" "{{ keycloak_env_file }}"'
        in runtime_env_wait["ansible.builtin.shell"]
    )
    assert (
        'grep -Fqx "KC_BOOTSTRAP_ADMIN_USERNAME={{ keycloak_bootstrap_admin_username }}" "{{ keycloak_env_file }}"'
        in runtime_env_wait["ansible.builtin.shell"]
    )
    assert (
        readiness_probe["ansible.builtin.uri"]["url"]
        == "http://127.0.0.1:{{ keycloak_local_management_port }}/health/ready"
    )
    assert force_recreate_down["ansible.builtin.command"]["argv"] == [
        "docker",
        "compose",
        "--file",
        "{{ keycloak_compose_file }}",
        "down",
        "--remove-orphans",
    ]
    assert force_recreate_down["when"] == "keycloak_force_recreate"
    assert "{{ keycloak_compose_network_name }}" in network_cleanup["ansible.builtin.shell"]
    assert "for attempt in $(seq 1 5)" in network_cleanup["ansible.builtin.shell"]
    assert "sleep 3" in network_cleanup["ansible.builtin.shell"]
    assert network_cleanup["when"] == "keycloak_force_recreate"
    rescue_names = [task["name"] for task in force_recreate_block["rescue"]]
    assert "Detect Docker bridge-chain loss during the Keycloak force-recreate" in rescue_names
    assert "Restart Docker to restore bridge networking before retrying the Keycloak force-recreate" in rescue_names
    assert (
        "Ensure Docker bridge networking chains are present before retrying the Keycloak force-recreate" in rescue_names
    )
    assert "Retry the Keycloak service force-recreate after Docker networking recovery" in rescue_names
    rescue_restart = next(
        task
        for task in force_recreate_block["rescue"]
        if task.get("name") == "Restart Docker to restore bridge networking before retrying the Keycloak force-recreate"
    )
    assert rescue_restart["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert rescue_restart["ansible.builtin.include_role"]["tasks_from"] == "docker_daemon_restart"
    assert rescue_restart["vars"]["common_docker_daemon_restart_service_name"] == "docker"
    assert rescue_restart["vars"]["common_docker_daemon_restart_reason"] == (
        "Keycloak force-recreate bridge-chain recovery"
    )
    force_recreate = force_recreate_block["block"][0]
    force_recreate_shell = force_recreate["ansible.builtin.shell"]
    assert "docker network inspect" in force_recreate_shell
    assert "{{ keycloak_mail_platform_docker_network_name }}" in force_recreate_shell
    assert (
        'docker compose --file "{{ keycloak_compose_file }}" up -d --force-recreate --no-deps keycloak'
        in force_recreate_shell
    )
    assert "com.docker.compose.project=keycloak" in force_recreate_shell
    assert "com.docker.compose.service=keycloak" in force_recreate_shell
    assert "docker rm -f $stale_ids || true" in force_recreate_shell
    assert force_recreate["args"]["executable"] == "/bin/bash"
    assert force_recreate["failed_when"] == "keycloak_up.rc != 0"
    force_recreate_expression = force_recreate_fact["ansible.builtin.set_fact"]["keycloak_force_recreate"]
    assert "keycloak_docker_nat_chain.rc != 0" in force_recreate_expression
    assert "keycloak_local_http_port_probe.failed" in force_recreate_expression
    assert "keycloak_readiness_probe.status" in force_recreate_expression
    assert "keycloak_env_template.changed" not in force_recreate_expression
    assert "keycloak_compose_template.changed" not in force_recreate_expression
    assert "keycloak_pull.changed" not in force_recreate_expression
    nat_assert = next(
        task for task in tasks if task.get("name") == "Assert Docker nat chain is present before Keycloak startup"
    )
    assert nat_assert["ansible.builtin.assert"]["that"] == [
        "keycloak_docker_nat_chain.rc == 0 or (common_docker_bridge_chains_nat_chain_present | default(false))"
    ]


def test_role_verifies_internal_mail_network_connectivity() -> None:
    tasks = load_tasks()
    initial_resolve_task = next(
        task for task in tasks if task.get("name") == "Verify Keycloak resolves the internal mail-platform relay host"
    )
    recovery_task = next(
        task
        for task in tasks
        if task.get("name") == "Recover the internal mail-platform submission relay before Keycloak SMTP verification"
    )
    recovery_wait_task = next(
        task
        for task in tasks
        if task.get("name") == "Wait for the internal mail-platform submission listener after dependency recovery"
    )
    resolve_task = next(
        task
        for task in tasks[tasks.index(initial_resolve_task) + 1 :]
        if task.get("name") == "Verify Keycloak resolves the internal mail-platform relay host"
    )
    connect_task = next(
        task
        for task in tasks
        if task.get("name") == "Verify Keycloak reaches the internal mail-platform submission listener"
    )
    assert initial_resolve_task["register"] == "keycloak_mail_submission_host_lookup_initial"
    assert initial_resolve_task["failed_when"] is False
    assert initial_resolve_task["when"] == "keycloak_mail_platform_submission_recovery_enabled"
    assert recovery_task["ansible.builtin.command"]["argv"][-5:] == [
        "up",
        "-d",
        "--force-recreate",
        "--no-deps",
        "{{ keycloak_mail_platform_submission_service_name }}",
    ]
    assert recovery_task["ansible.builtin.command"]["argv"][3] == "{{ keycloak_mail_platform_compose_file }}"
    assert recovery_task["when"] == [
        "keycloak_mail_platform_submission_recovery_enabled",
        "keycloak_mail_submission_host_lookup_initial.rc != 0",
    ]
    assert recovery_wait_task["ansible.builtin.wait_for"]["host"] == "{{ ansible_host }}"
    assert recovery_wait_task["ansible.builtin.wait_for"]["port"] == "{{ keycloak_mail_platform_submission_port }}"
    assert recovery_wait_task["when"] == [
        "keycloak_mail_platform_submission_recovery_enabled",
        "keycloak_mail_submission_host_lookup_initial.rc != 0",
    ]
    assert resolve_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "exec",
        "keycloak-keycloak-1",
        "getent",
        "ahostsv4",
        "{{ keycloak_mail_platform_submission_host }}",
    ]
    assert resolve_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert resolve_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert resolve_task["until"] == "keycloak_mail_submission_host_lookup.rc == 0"
    assert "{{ keycloak_mail_platform_submission_host }}" in connect_task["ansible.builtin.shell"]
    assert "{{ keycloak_mail_platform_submission_port }}" in connect_task["ansible.builtin.shell"]
    assert connect_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert connect_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert connect_task["until"] == "keycloak_mail_submission_probe.rc == 0"


def test_role_retries_api_gateway_client_reconcile_and_secret_read() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    api_gateway_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the API gateway client exists"
    )
    api_gateway_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the API gateway client secret"
    )
    assert api_gateway_client_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert api_gateway_client_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert api_gateway_client_task["until"] == "keycloak_api_gateway_client_reconcile is succeeded"
    assert api_gateway_secret_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert api_gateway_secret_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert api_gateway_secret_task["until"] == "keycloak_api_gateway_client_secret_info is succeeded"


def test_role_warms_authenticated_keycloak_admin_queries_before_realm_reconcile() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    startup_block = next(
        task for task in tasks if task.get("name") == "Warm the Keycloak admin APIs before realm reconciliation"
    )
    admin_access_block = next(
        task
        for task in tasks
        if task.get("name")
        == "Ensure the repo-managed Keycloak admin client can authenticate before realm reconciliation"
    )
    readiness_task = next(task for task in tasks if task.get("name") == "Wait for the Keycloak readiness endpoint")
    admin_api_task = next(task for task in tasks if task.get("name") == "Wait for the Keycloak admin API to answer")
    token_probe_task = next(
        task
        for task in admin_access_block["block"]
        if task.get("name") == "Wait for the repo-managed Keycloak admin client token endpoint to succeed"
    )
    preflight_admin_probe_task = next(
        task
        for task in admin_access_block["block"]
        if task.get("name")
        == "Require an authenticated Keycloak admin realm query before accepting the repo-managed admin client"
    )
    admin_probe_task = next(
        task for task in tasks if task.get("name") == "Wait for an authenticated Keycloak admin realm query to answer"
    )
    settle_task = next(
        task
        for task in tasks
        if task.get("name") == "Allow the Keycloak admin API to settle after the first authenticated admin-client probe"
    )
    token_probe_confirmed_task = next(
        task
        for task in tasks
        if task.get("name") == "Reconfirm the repo-managed Keycloak admin client token endpoint after the settle window"
    )
    admin_probe_confirmed_task = next(
        task
        for task in tasks
        if task.get("name") == "Reconfirm an authenticated Keycloak admin realm query after the settle window"
    )
    assert defaults["keycloak_startup_probe_retries"] == 60
    assert defaults["keycloak_startup_probe_delay"] == 5
    recovery_bridge_helper = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Ensure Docker bridge networking chains are present after Keycloak startup probe failure"
    )
    recovery_runtime_env_wait = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Wait for the Keycloak runtime env file after startup probe recovery"
    )
    recovery_jgroups_cleanup = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Clear stale Keycloak JDBC_PING rows before retrying the startup probes"
    )
    recovery_recreate = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Recreate the Keycloak service before retrying the startup probes"
    )
    recovery_readiness_task = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Wait for the Keycloak readiness endpoint after startup probe recovery"
    )
    runtime_recovery_inspect_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name") == "Inspect the Keycloak service state before admin bootstrap recovery"
    )
    runtime_recovery_fact_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name") == "Record whether the Keycloak runtime needs recovery before admin bootstrap fallback"
    )
    runtime_recovery_recreate_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name") == "Recreate the Keycloak service after admin-client runtime drift"
    )
    runtime_recovery_token_probe_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name")
        == "Retry the repo-managed Keycloak admin client token endpoint after admin-client runtime recovery"
    )
    runtime_recovery_admin_probe_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name") == "Retry the authenticated Keycloak admin realm query after admin-client runtime recovery"
    )
    runtime_live_secret_query_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name")
        == "Read the live Keycloak admin client secret directly from PostgreSQL when file-based auth fails"
    )
    runtime_live_secret_token_probe_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name")
        == "Retry the repo-managed Keycloak admin client token endpoint with the live PostgreSQL-backed secret"
    )
    runtime_live_secret_admin_probe_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name")
        == "Retry the authenticated Keycloak admin realm query with the live PostgreSQL-backed secret"
    )
    runtime_live_secret_reconcile_task = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name")
        == "Reconcile the repo-managed Keycloak admin client using the live PostgreSQL-backed secret"
    )
    fallback_block = next(
        task
        for task in admin_access_block["rescue"]
        if task.get("name")
        == "Recover repo-managed Keycloak admin access with bootstrap credentials when runtime recovery is insufficient"
    )
    fallback_bootstrap_task = next(
        task
        for task in tasks
        if task.get("name") == "Try the Keycloak bootstrap admin token endpoint as a fallback admin bootstrap path"
    )
    recovery_stop_task = next(
        task for task in tasks if task.get("name") == "Stop the Keycloak service before offline admin recovery"
    )
    assert readiness_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert readiness_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert readiness_task["ansible.builtin.uri"]["return_content"] is True
    assert readiness_task["ansible.builtin.uri"]["status_code"] == [200, 503]
    assert readiness_task["until"] == "(keycloak_health_ready.status | default(0)) in [200, 503]"
    assert readiness_task["failed_when"] == "(keycloak_health_ready.status | default(0)) != 200"
    assert admin_api_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert admin_api_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert token_probe_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert token_probe_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert preflight_admin_probe_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert preflight_admin_probe_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert admin_probe_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert admin_probe_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert settle_task["ansible.builtin.pause"]["seconds"] == "{{ keycloak_startup_probe_delay }}"
    assert token_probe_confirmed_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert token_probe_confirmed_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert admin_probe_confirmed_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert admin_probe_confirmed_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert token_probe_task["ansible.builtin.uri"]["return_content"] is True
    assert preflight_admin_probe_task["ansible.builtin.uri"]["url"] == (
        "{{ keycloak_local_admin_url }}/admin/realms/{{ keycloak_realm_name }}"
    )
    assert preflight_admin_probe_task["ansible.builtin.uri"]["headers"]["Authorization"] == (
        "Bearer {{ keycloak_admin_client_token_probe.json.access_token }}"
    )
    assert preflight_admin_probe_task["ansible.builtin.uri"]["status_code"] == [200, 403, 404]
    assert preflight_admin_probe_task["until"] == (
        "(keycloak_admin_realm_probe_preflight.status | default(0)) in [200, 403, 404]"
    )
    assert preflight_admin_probe_task["failed_when"] == (
        "(keycloak_admin_realm_probe_preflight.status | default(0)) == 403"
    )
    assert (
        admin_probe_task["ansible.builtin.uri"]["url"]
        == "{{ keycloak_local_admin_url }}/admin/realms/{{ keycloak_realm_name }}"
    )
    assert admin_probe_task["ansible.builtin.uri"]["headers"]["Authorization"] == (
        "Bearer {{ keycloak_admin_client_token_probe_confirmed.json.access_token }}"
    )
    assert admin_probe_task["ansible.builtin.uri"]["status_code"] == [200, 403, 404]
    assert admin_probe_task["until"] == "(keycloak_admin_realm_probe.status | default(0)) in [200, 403, 404]"
    assert admin_probe_task["failed_when"] == "(keycloak_admin_realm_probe.status | default(0)) == 403"
    assert token_probe_confirmed_task["ansible.builtin.uri"]["return_content"] is True
    assert admin_probe_confirmed_task["ansible.builtin.uri"]["headers"]["Authorization"] == (
        "Bearer {{ keycloak_admin_client_token_probe_stable.json.access_token }}"
    )
    assert admin_probe_confirmed_task["ansible.builtin.uri"]["status_code"] == [200, 403, 404]
    assert admin_probe_confirmed_task["until"] == (
        "(keycloak_admin_realm_probe_confirmed.status | default(0)) in [200, 403, 404]"
    )
    assert admin_probe_confirmed_task["failed_when"] == (
        "(keycloak_admin_realm_probe_confirmed.status | default(0)) == 403"
    )
    assert recovery_bridge_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert recovery_bridge_helper["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert recovery_bridge_helper["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    assert (
        'grep -Fqx "KC_DB_URL_HOST={{ keycloak_database_host }}" "{{ keycloak_env_file }}"'
        in recovery_runtime_env_wait["ansible.builtin.shell"]
    )
    assert recovery_jgroups_cleanup["ansible.builtin.command"]["argv"] == [
        "psql",
        "-d",
        "{{ keycloak_database_name }}",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "DELETE FROM jgroups_ping;",
    ]
    assert (
        recovery_jgroups_cleanup["delegate_to"]
        == "{{ playbook_execution_required_hosts.postgres[playbook_execution_env] }}"
    )
    assert recovery_jgroups_cleanup["become"] is True
    assert recovery_jgroups_cleanup["become_user"] == "postgres"
    assert recovery_jgroups_cleanup["changed_when"] == (
        "'DELETE ' in (keycloak_startup_probe_recovery_jgroups_cleanup.stdout | default(''))"
    )
    assert (
        'docker compose --file "{{ keycloak_compose_file }}" up -d --force-recreate --no-deps keycloak'
        in recovery_recreate["ansible.builtin.shell"]
    )
    assert recovery_readiness_task["ansible.builtin.uri"]["return_content"] is True
    assert recovery_readiness_task["ansible.builtin.uri"]["status_code"] == [200, 503]
    assert recovery_readiness_task["until"] == (
        "(keycloak_startup_probe_recovery_health_ready.status | default(0)) in [200, 503]"
    )
    assert recovery_readiness_task["failed_when"] == (
        "(keycloak_startup_probe_recovery_health_ready.status | default(0)) != 200"
    )
    assert "label=com.docker.compose.project=keycloak" in runtime_recovery_inspect_task["ansible.builtin.shell"]
    assert "label=com.docker.compose.service=keycloak" in runtime_recovery_inspect_task["ansible.builtin.shell"]
    assert runtime_recovery_fact_task["ansible.builtin.set_fact"][
        "keycloak_admin_access_runtime_recovery_needed"
    ].startswith("{{")
    assert "{{ keycloak_mail_platform_docker_network_name }}" in runtime_recovery_recreate_task["ansible.builtin.shell"]
    assert "--force-recreate --no-deps keycloak" in runtime_recovery_recreate_task["ansible.builtin.shell"]
    assert runtime_recovery_recreate_task["failed_when"] is False
    assert runtime_recovery_token_probe_task["ansible.builtin.uri"]["status_code"] == [200, 400, 401, 403, 500]
    assert runtime_recovery_token_probe_task["failed_when"] == (
        "(keycloak_admin_access_token_probe_recovery.status | default(0)) != 200"
    )
    assert runtime_recovery_admin_probe_task["ansible.builtin.uri"]["status_code"] == [200, 403, 404]
    assert runtime_recovery_admin_probe_task["failed_when"] == (
        "(keycloak_admin_access_realm_probe_recovery.status | default(0)) == 403"
    )
    assert runtime_live_secret_query_task["ansible.builtin.command"]["argv"] == [
        "psql",
        "-d",
        "{{ keycloak_database_name }}",
        "-At",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "SELECT secret FROM client WHERE client_id = '{{ keycloak_admin_client_id }}';",
    ]
    assert runtime_live_secret_query_task["delegate_to"] == (
        "{{ playbook_execution_required_hosts.postgres[playbook_execution_env] }}"
    )
    assert runtime_live_secret_query_task["become"] is True
    assert runtime_live_secret_query_task["become_user"] == "postgres"
    assert runtime_live_secret_token_probe_task["ansible.builtin.uri"]["body"]["client_secret"] == (
        "{{ keycloak_admin_client_secret_live }}"
    )
    assert runtime_live_secret_token_probe_task["ansible.builtin.uri"]["status_code"] == [200, 400, 401, 403, 500]
    assert runtime_live_secret_token_probe_task["until"] == (
        "(keycloak_admin_client_live_secret_token_probe.status | default(0)) in [200, 400, 401, 403]"
    )
    assert runtime_live_secret_token_probe_task["failed_when"] == (
        "(keycloak_admin_client_live_secret_token_probe.status | default(0)) != 200"
    )
    assert runtime_live_secret_admin_probe_task["ansible.builtin.uri"]["headers"]["Authorization"] == (
        "Bearer {{ keycloak_admin_client_live_secret_token_probe.json.access_token }}"
    )
    assert runtime_live_secret_admin_probe_task["ansible.builtin.uri"]["status_code"] == [200, 403, 404]
    assert runtime_live_secret_admin_probe_task["failed_when"] == (
        "(keycloak_admin_client_live_secret_realm_probe.status | default(0)) == 403"
    )
    assert runtime_live_secret_reconcile_task["ansible.builtin.include_tasks"] == "reconcile_admin_client.yml"
    assert runtime_live_secret_reconcile_task["vars"] == {
        "keycloak_admin_bootstrap_auth_realm": "master",
        "keycloak_admin_bootstrap_auth_client_id": "{{ keycloak_admin_client_id }}",
        "keycloak_admin_bootstrap_auth_client_secret": "{{ keycloak_admin_client_secret_live }}",
    }
    assert fallback_block["when"] == "keycloak_admin_bootstrap_fallback_required | bool"
    assert fallback_bootstrap_task["ansible.builtin.uri"]["body"]["client_id"] == "admin-cli"
    assert recovery_stop_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "compose",
        "--file",
        "{{ keycloak_compose_file }}",
        "stop",
        "keycloak",
    ]


def test_admin_client_repair_paths_use_refreshable_credentials() -> None:
    tasks = load_tasks()
    bootstrap_include = next(
        task
        for task in tasks
        if task.get("name")
        == "Reconcile the repo-managed Keycloak admin client using the bootstrap admin fallback credentials"
    )
    admin_live_secret_include = next(
        task
        for task in tasks
        if task.get("name")
        == "Reconcile the repo-managed Keycloak admin client using the live PostgreSQL-backed secret"
    )
    recovery_include = next(
        task
        for task in tasks
        if task.get("name")
        == "Reconcile the repo-managed Keycloak admin client using the temporary recovery admin service credentials"
    )
    recovery_live_secret_query = next(
        task
        for task in tasks
        if task.get("name")
        == "Read the live temporary Keycloak recovery admin secret directly from PostgreSQL when file-based recovery auth fails"
    )
    recovery_live_secret_token_probe = next(
        task
        for task in tasks
        if task.get("name")
        == "Retry the temporary Keycloak recovery admin service token endpoint with the live PostgreSQL-backed secret"
    )
    assert bootstrap_include["ansible.builtin.include_tasks"] == "reconcile_admin_client.yml"
    assert bootstrap_include["vars"] == {
        "keycloak_admin_bootstrap_auth_realm": "master",
        "keycloak_admin_bootstrap_auth_client_id": "admin-cli",
        "keycloak_admin_bootstrap_auth_username": "{{ keycloak_bootstrap_admin_username }}",
        "keycloak_admin_bootstrap_auth_password": "{{ keycloak_bootstrap_admin_password }}",
    }
    assert admin_live_secret_include["ansible.builtin.include_tasks"] == "reconcile_admin_client.yml"
    assert admin_live_secret_include["vars"] == {
        "keycloak_admin_bootstrap_auth_realm": "master",
        "keycloak_admin_bootstrap_auth_client_id": "{{ keycloak_admin_client_id }}",
        "keycloak_admin_bootstrap_auth_client_secret": "{{ keycloak_admin_client_secret_live }}",
    }
    assert recovery_include["ansible.builtin.include_tasks"] == "reconcile_admin_client.yml"
    assert recovery_include["vars"] == {
        "keycloak_admin_bootstrap_auth_realm": "master",
        "keycloak_admin_bootstrap_auth_client_id": "{{ keycloak_recovery_admin_service_client_id }}",
        "keycloak_admin_bootstrap_auth_client_secret": "{{ keycloak_recovery_admin_service_auth_client_secret }}",
    }
    assert recovery_live_secret_query["ansible.builtin.command"]["argv"] == [
        "psql",
        "-d",
        "{{ keycloak_database_name }}",
        "-At",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "SELECT secret FROM client WHERE client_id = '{{ keycloak_recovery_admin_service_client_id }}';",
    ]
    assert recovery_live_secret_query["delegate_to"] == (
        "{{ playbook_execution_required_hosts.postgres[playbook_execution_env] }}"
    )
    assert recovery_live_secret_query["become"] is True
    assert recovery_live_secret_query["become_user"] == "postgres"
    assert recovery_live_secret_token_probe["ansible.builtin.uri"]["body"]["client_secret"] == (
        "{{ keycloak_recovery_admin_service_secret_live }}"
    )
    assert recovery_live_secret_token_probe["ansible.builtin.uri"]["status_code"] == [200, 400, 401, 403, 500]
    assert recovery_live_secret_token_probe["until"] == (
        "(keycloak_recovery_admin_service_live_secret_token_probe.status | default(0)) in [200, 400, 401, 403]"
    )


def test_reconcile_admin_client_accepts_refreshable_auth_inputs() -> None:
    tasks = load_admin_client_tasks()
    client_task = next(
        task
        for task in tasks
        if task.get("name") == "Ensure the repo-managed Keycloak admin client exists in the master realm"
    )
    post_reconcile_secret_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Record the auth client secret that should work after the admin client secret is reconciled"
    )
    role_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Ensure the repo-managed Keycloak admin client service account has the master admin composite realm role"
    )
    assert client_task["community.general.keycloak_client"]["full_scope_allowed"] is True
    assert "client_id" not in role_task["community.general.keycloak_user_rolemapping"]
    assert role_task["community.general.keycloak_user_rolemapping"]["roles"] == [{"name": "admin"}]
    client_module_args = client_task["community.general.keycloak_client"]
    assert client_module_args["auth_keycloak_url"] == "{{ keycloak_local_admin_url }}"
    assert client_module_args["auth_realm"] == "{{ keycloak_admin_bootstrap_auth_realm | default(omit) }}"
    assert client_module_args["auth_client_id"] == "{{ keycloak_admin_bootstrap_auth_client_id | default(omit) }}"
    assert (
        client_module_args["auth_client_secret"] == "{{ keycloak_admin_bootstrap_auth_client_secret | default(omit) }}"
    )
    assert client_module_args["auth_username"] == "{{ keycloak_admin_bootstrap_auth_username | default(omit) }}"
    assert client_module_args["auth_password"] == "{{ keycloak_admin_bootstrap_auth_password | default(omit) }}"
    assert client_module_args["token"] == "{{ keycloak_admin_bootstrap_token | default(omit) }}"
    assert post_reconcile_secret_task["ansible.builtin.set_fact"][
        "keycloak_admin_bootstrap_auth_client_secret_after_reconcile"
    ].startswith("{{")
    role_module_args = role_task["community.general.keycloak_user_rolemapping"]
    assert role_module_args["auth_keycloak_url"] == "{{ keycloak_local_admin_url }}"
    assert role_module_args["auth_realm"] == "{{ keycloak_admin_bootstrap_auth_realm | default(omit) }}"
    assert role_module_args["auth_client_id"] == "{{ keycloak_admin_bootstrap_auth_client_id | default(omit) }}"
    assert "keycloak_admin_bootstrap_auth_client_secret_after_reconcile" in role_module_args["auth_client_secret"]
    assert role_module_args["auth_username"] == "{{ keycloak_admin_bootstrap_auth_username | default(omit) }}"
    assert role_module_args["auth_password"] == "{{ keycloak_admin_bootstrap_auth_password | default(omit) }}"
    assert role_module_args["token"] == "{{ keycloak_admin_bootstrap_token | default(omit) }}"


def test_realm_reconciliation_retries_repo_managed_keycloak_modules() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    assert defaults["keycloak_admin_connection_timeout"] == 60
    assert defaults["keycloak_admin_reconciliation_retries"] == 24
    assert defaults["keycloak_admin_reconciliation_delay"] == 5
    assert realm_block["module_defaults"]["community.general.keycloak_realm"]["connection_timeout"] == (
        "{{ keycloak_admin_connection_timeout }}"
    )
    retry_task_names = [
        "Ensure the LV3 realm exists",
        "Ensure the Keycloak realm groups exist",
        "Ensure the Keycloak realm roles exist",
        "Ensure realm roles are mapped to Keycloak groups",
        "Ensure the Grafana OAuth client exists",
        "Ensure the operations portal OAuth client exists",
        "Ensure the Gitea OAuth client exists",
        "Ensure the agent service client exists",
        "Ensure the Langfuse OAuth client exists",
        "Ensure the Dify OAuth client exists",
        "Ensure the Nomad OIDC client exists",
        "Ensure the Directus OAuth client exists",
        "Ensure the Outline OAuth client exists",
        "Ensure the Paperless OAuth client exists",
        "Ensure the Superset OAuth client exists",
        "Ensure the ServerClaw OAuth client exists",
        "Ensure the Grist OAuth client exists",
        "Ensure the API gateway client exists",
        "Ensure the obsolete ServerClaw operator CLI direct-grant client is absent",
        "Ensure the ServerClaw runtime client exists",
        "Ensure realm roles are mapped to service account users",
        "Read the Grafana client secret",
        "Read the operations portal client secret",
        "Read the Gitea client secret",
        "Read the agent client secret",
        "Read the Langfuse client secret",
        "Read the Directus client secret",
        "Read the Grist client secret",
        "Read the GlitchTip client secret",
        "Read the Outline client secret",
        "Read the Paperless client secret",
        "Read the Superset client secret",
        "Read the ServerClaw client secret",
        "Read the API gateway client secret",
        "Read the ServerClaw runtime client secret",
        "Read the Dify client secret",
        "Read the Nomad client secret",
    ]
    for task_name in retry_task_names:
        task = next(task for task in realm_block["block"] if task.get("name") == task_name)
        assert_task_retries(task, task["register"])


def test_realm_reconciliation_retries_client_secret_reads() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    read_secret_tasks = [
        task
        for task in realm_block["block"]
        if task.get("name", "").startswith("Read the ") and task.get("name", "").endswith(" client secret")
    ]

    assert len(read_secret_tasks) == 16
    for task in read_secret_tasks:
        assert task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
        assert task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
        assert task["until"] == f"{task['register']} is succeeded"


def test_runtime_token_verification_retries_confidential_clients() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    agent_token_task = next(task for task in tasks if task.get("name") == "Request an agent client-credentials token")
    serverclaw_runtime_token_task = next(
        task for task in tasks if task.get("name") == "Request the ServerClaw runtime client-credentials token"
    )
    assert defaults["keycloak_admin_connection_timeout"] == 60
    for task in (agent_token_task, serverclaw_runtime_token_task):
        assert task["ansible.builtin.uri"]["timeout"] == "{{ keycloak_admin_connection_timeout }}"
        assert task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
        assert task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
        assert task["until"] == f"{task['register']}.status == 200"


def test_compose_template_joins_the_mail_platform_network() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text()
    assert "      - mail-platform" in template
    assert "  mail-platform:" in template
    assert "    external: true" in template
    assert "    name: {{ keycloak_mail_platform_docker_network_name }}" in template


def test_role_manages_langfuse_client_secret() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    langfuse_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the Langfuse OAuth client exists"
    )
    read_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the Langfuse client secret"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the Langfuse client secret to the control machine"
    )
    assert langfuse_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_langfuse_client_id }}"
    assert langfuse_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_langfuse_root_url }}/api/auth/callback/keycloak"
    ]
    assert (
        read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"]
        == "{{ keycloak_langfuse_client_id }}"
    )
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_langfuse_client_secret_local_file }}"


def test_role_manages_directus_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    directus_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the Directus OAuth client exists"
    )
    read_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the Directus client secret"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the Directus client secret to the control machine"
    )

    assert defaults["keycloak_directus_client_id"] == "directus"
    assert defaults["keycloak_directus_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/directus-client-secret.txt"
    )
    assert defaults["keycloak_directus_root_url"] == "https://data.{{ platform_domain }}"
    assert directus_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_directus_client_id }}"
    assert directus_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_directus_root_url }}/auth/login/keycloak/callback"
    ]
    assert directus_client_task["community.general.keycloak_client"]["web_origins"] == [
        "{{ keycloak_directus_root_url }}"
    ]
    directus_mapper = directus_client_task["community.general.keycloak_client"]["protocol_mappers"][0]
    assert directus_mapper["name"] == "groups"
    assert directus_mapper["config"]["claim.name"] == "groups"
    assert directus_mapper["config"]["full.path"] == "true"
    assert (
        read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"]
        == "{{ keycloak_directus_client_id }}"
    )
    assert read_secret_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert read_secret_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert read_secret_task["until"] == "keycloak_directus_client_secret_info is succeeded"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_directus_client_secret_local_file }}"


def test_role_manages_outline_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    grafana_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the Grafana OAuth client exists"
    )
    ops_portal_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the operations portal OAuth client exists"
    )
    grist_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the Grist OAuth client exists"
    )
    outline_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the Outline OAuth client exists"
    )
    read_grist_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the Grist client secret"
    )
    read_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the Outline client secret"
    )
    mirror_grist_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the Grist client secret to the control machine"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the Outline client secret to the control machine"
    )
    assert defaults["keycloak_grist_client_id"] == "grist"
    assert defaults["keycloak_grist_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/grist-client-secret.txt"
    )
    assert defaults["keycloak_grist_root_url"] == "https://grist.{{ platform_domain }}"
    assert defaults["keycloak_outline_client_id"] == "outline"
    assert defaults["keycloak_outline_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/outline-client-secret.txt"
    )
    assert defaults["keycloak_outline_root_url"] == "https://wiki.{{ platform_domain }}"
    assert grafana_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_grafana_post_logout_redirect_uris }}"
    )
    assert ops_portal_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_ops_portal_post_logout_redirect_uris }}"
    )
    assert grist_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_grist_client_id }}"
    assert grist_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_grist_root_url }}/oauth2/callback"
    ]
    assert grist_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_grist_post_logout_redirect_uris }}"
    )
    assert outline_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_outline_client_id }}"
    assert outline_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_outline_root_url }}/auth/oidc.callback"
    ]
    assert outline_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_outline_post_logout_redirect_uris }}"
    )
    assert (
        read_grist_secret_task["community.general.keycloak_clientsecret_info"]["client_id"]
        == "{{ keycloak_grist_client_id }}"
    )
    assert mirror_grist_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_grist_client_secret_local_file }}"
    assert (
        read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"]
        == "{{ keycloak_outline_client_id }}"
    )
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_outline_client_secret_local_file }}"


def test_role_manages_paperless_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    paperless_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the Paperless OAuth client exists"
    )
    read_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the Paperless client secret"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the Paperless client secret to the control machine"
    )

    assert defaults["keycloak_paperless_client_id"] == "paperless"
    assert defaults["keycloak_paperless_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/paperless-client-secret.txt"
    )
    assert defaults["keycloak_paperless_root_url"] == "https://paperless.{{ platform_domain }}"
    assert (
        paperless_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_paperless_client_id }}"
    )
    assert paperless_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_paperless_root_url }}/accounts/oidc/keycloak/login/callback/"
    ]
    assert paperless_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_paperless_post_logout_redirect_uris }}"
    )
    assert (
        read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"]
        == "{{ keycloak_paperless_client_id }}"
    )
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_paperless_client_secret_local_file }}"


def test_role_manages_superset_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    superset_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the Superset OAuth client exists"
    )
    read_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the Superset client secret"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the Superset client secret to the control machine"
    )

    assert defaults["keycloak_superset_client_id"] == "superset"
    assert defaults["keycloak_superset_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/superset-client-secret.txt"
    )
    assert defaults["keycloak_superset_root_url"] == "https://bi.{{ platform_domain }}"
    assert superset_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_superset_client_id }}"
    assert superset_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_superset_root_url }}/oauth-authorized/keycloak"
    ]
    assert superset_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_superset_post_logout_redirect_uris }}"
    )
    assert superset_client_task["community.general.keycloak_client"]["web_origins"] == [
        "{{ keycloak_superset_root_url }}"
    ]
    superset_mapper = superset_client_task["community.general.keycloak_client"]["protocol_mappers"][0]
    assert superset_mapper["name"] == "groups"
    assert superset_mapper["config"]["claim.name"] == "groups"
    assert superset_mapper["config"]["full.path"] == "true"
    assert (
        read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"]
        == "{{ keycloak_superset_client_id }}"
    )
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_superset_client_secret_local_file }}"


def test_role_manages_serverclaw_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    serverclaw_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the ServerClaw OAuth client exists"
    )
    read_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the ServerClaw client secret"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the ServerClaw client secret to the control machine"
    )
    assert defaults["keycloak_serverclaw_client_id"] == "serverclaw"
    assert defaults["keycloak_serverclaw_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/serverclaw-client-secret.txt"
    )
    assert defaults["keycloak_serverclaw_root_url"] == "https://chat.{{ platform_domain }}"
    assert defaults["keycloak_serverclaw_post_logout_redirect_uris"] == [
        "{{ keycloak_serverclaw_root_url }}",
        "{{ keycloak_serverclaw_root_url }}/",
    ]
    assert (
        serverclaw_client_task["community.general.keycloak_client"]["client_id"]
        == "{{ keycloak_serverclaw_client_id }}"
    )
    assert serverclaw_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_serverclaw_root_url }}/oauth/oidc/callback"
    ]
    assert serverclaw_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_serverclaw_post_logout_redirect_uris }}"
    )
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == (
        "{{ keycloak_serverclaw_client_id }}"
    )
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_serverclaw_client_secret_local_file }}"


def test_serverclaw_client_tasks_wait_for_keycloak_then_mirror_secret() -> None:
    tasks = load_serverclaw_tasks()
    readiness_task = next(task for task in tasks if task.get("name") == "Wait for the Keycloak readiness endpoint")
    admin_api_task = next(task for task in tasks if task.get("name") == "Wait for the Keycloak admin API to answer")
    token_probe_task = next(
        task
        for task in tasks
        if task.get("name") == "Wait for the repo-managed Keycloak admin client token endpoint to succeed"
    )
    realm_block = next(
        task for task in tasks if task.get("name") == "Converge the dedicated ServerClaw Keycloak client"
    )
    serverclaw_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the ServerClaw OAuth client exists"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the ServerClaw client secret to the control machine"
    )
    assert (
        readiness_task["ansible.builtin.uri"]["url"]
        == "http://127.0.0.1:{{ keycloak_local_management_port }}/health/ready"
    )
    assert (
        admin_api_task["ansible.builtin.uri"]["url"]
        == "{{ keycloak_local_admin_url }}/realms/master/.well-known/openid-configuration"
    )
    assert token_probe_task["ansible.builtin.uri"]["body"]["client_id"] == "{{ keycloak_admin_client_id }}"
    assert (
        serverclaw_client_task["community.general.keycloak_client"]["client_id"]
        == "{{ keycloak_serverclaw_client_id }}"
    )
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_serverclaw_client_secret_local_file }}"


def test_role_manages_the_outline_automation_identity() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    repo_user_tasks = load_tasks(REPO_USER_TASKS_PATH)
    runtime_secrets_task = next(task for task in tasks if task.get("name") == "Manage Keycloak runtime secrets")
    repo_user_reconciliation = next(
        task for task in tasks if task.get("name") == "Reconcile repo-managed Keycloak users"
    )
    include_task = next(
        task
        for task in repo_user_reconciliation["block"]
        if task.get("name") == "Run the repo-managed Keycloak user reconciliation tasks"
    )
    recovery_restart_task = next(
        task
        for task in repo_user_reconciliation["rescue"]
        if task.get("name") == "Recreate the Keycloak service before retrying repo-managed user reconciliation"
    )
    recovery_token_probe_task = next(
        task
        for task in repo_user_reconciliation["rescue"]
        if task.get("name")
        == "Wait for the repo-managed Keycloak admin client token endpoint after repo-managed user reconciliation recovery"
    )
    recovery_admin_probe_task = next(
        task
        for task in repo_user_reconciliation["rescue"]
        if task.get("name")
        == "Wait for an authenticated Keycloak admin realm query after repo-managed user reconciliation recovery"
    )
    recovery_retry_task = next(
        task
        for task in repo_user_reconciliation["rescue"]
        if task.get("name") == "Retry the repo-managed Keycloak user reconciliation tasks after recovery"
    )
    admin_token_task = next(
        task
        for task in repo_user_tasks
        if task.get("name") == "Request a Keycloak admin token for repo-managed user reconciliation"
    )
    platform_group_lookup_task = next(
        task for task in repo_user_tasks if task.get("name") == "Look up the lv3-platform-admins group in Keycloak"
    )
    operator_update_task = next(
        task for task in repo_user_tasks if task.get("name") == "Update the named operator profile in Keycloak"
    )
    operator_password_task = next(
        task for task in repo_user_tasks if task.get("name") == "Reset the named operator password in Keycloak"
    )
    automation_create_task = next(
        task
        for task in repo_user_tasks
        if task.get("name") == "Create the Outline automation user in Keycloak when missing"
    )
    automation_user_task = next(
        task for task in repo_user_tasks if task.get("name") == "Update the Outline automation user profile in Keycloak"
    )
    automation_password_task = next(
        task for task in repo_user_tasks if task.get("name") == "Reset the Outline automation user password in Keycloak"
    )
    assert {
        "path": "{{ keycloak_outline_automation_password_remote_file }}",
        "command": "openssl rand -base64 24 | tr -d '\\n'",
        "label": "keycloak-outline-automation-password",
    } in runtime_secrets_task["vars"]["common_manage_service_secrets_generate"]
    assert {
        "dest": "{{ keycloak_outline_automation_password_local_file }}",
        "content_index": 4,
    } in runtime_secrets_task["vars"]["common_manage_service_secrets_mirror"]
    assert defaults["keycloak_repo_user_reconciliation_retries"] == 24
    assert defaults["keycloak_repo_user_reconciliation_delay"] == 5
    assert defaults["keycloak_admin_connection_timeout"] == 60
    assert defaults["keycloak_local_admin_url"] == "http://127.0.0.1:{{ keycloak_local_http_port }}"
    assert defaults["keycloak_repo_user_admin_url"] == "{{ keycloak_local_admin_url }}"
    assert include_task["ansible.builtin.include_tasks"] == "reconcile_repo_managed_users.yml"
    assert recovery_restart_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "compose",
        "--file",
        "{{ keycloak_compose_file }}",
        "up",
        "-d",
        "--force-recreate",
        "--no-deps",
        "keycloak",
    ]
    assert recovery_token_probe_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert recovery_token_probe_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert recovery_token_probe_task["until"] == (
        "(keycloak_repo_user_reconciliation_admin_client_token_probe.status | default(0)) in [200, 400, 401, 403]"
    )
    assert recovery_token_probe_task["failed_when"] == (
        "(keycloak_repo_user_reconciliation_admin_client_token_probe.status | default(0)) != 200"
    )
    assert recovery_admin_probe_task["ansible.builtin.uri"]["status_code"] == [200, 403, 404]
    assert recovery_admin_probe_task["until"] == (
        "(keycloak_repo_user_reconciliation_admin_realm_probe.status | default(0)) in [200, 403, 404]"
    )
    assert recovery_admin_probe_task["failed_when"] == (
        "(keycloak_repo_user_reconciliation_admin_realm_probe.status | default(0)) == 403"
    )
    assert recovery_retry_task["ansible.builtin.include_tasks"] == "reconcile_repo_managed_users.yml"
    assert admin_token_task["ansible.builtin.uri"]["url"] == (
        "{{ keycloak_repo_user_admin_url }}/realms/master/protocol/openid-connect/token"
    )
    assert admin_token_task["ansible.builtin.uri"]["body"]["grant_type"] == "client_credentials"
    assert admin_token_task["ansible.builtin.uri"]["body"]["client_id"] == "{{ keycloak_admin_client_id }}"
    assert admin_token_task["retries"] == "{{ keycloak_repo_user_reconciliation_retries }}"
    assert admin_token_task["delay"] == "{{ keycloak_repo_user_reconciliation_delay }}"
    assert "json.access_token" in admin_token_task["until"]
    assert platform_group_lookup_task["retries"] == "{{ keycloak_repo_user_reconciliation_retries }}"
    assert platform_group_lookup_task["delay"] == "{{ keycloak_repo_user_reconciliation_delay }}"
    assert platform_group_lookup_task["until"] == "keycloak_platform_admin_group_lookup.status == 200"
    assert operator_update_task["ansible.builtin.uri"]["body"]["requiredActions"] == ["CONFIGURE_TOTP"]
    assert operator_password_task["ansible.builtin.uri"]["body"]["temporary"] is False
    assert automation_create_task["retries"] == "{{ keycloak_repo_user_reconciliation_retries }}"
    assert automation_create_task["delay"] == "{{ keycloak_repo_user_reconciliation_delay }}"
    assert automation_create_task["ansible.builtin.uri"]["status_code"] == [201, 204, 409]
    assert (
        automation_user_task["ansible.builtin.uri"]["body"]["username"] == "{{ keycloak_outline_automation_username }}"
    )
    assert automation_user_task["ansible.builtin.uri"]["body"]["requiredActions"] == []
    assert automation_password_task["ansible.builtin.uri"]["body"]["temporary"] is False


def test_repo_managed_user_reconciliation_is_delegated_to_the_include_file() -> None:
    tasks = load_tasks()
    repo_user_tasks = load_tasks(REPO_USER_TASKS_PATH)
    repo_user_reconciliation = next(
        task for task in tasks if task.get("name") == "Reconcile repo-managed Keycloak users"
    )
    include_task = next(
        task
        for task in repo_user_reconciliation["block"]
        if task.get("name") == "Run the repo-managed Keycloak user reconciliation tasks"
    )
    retry_task = next(
        task
        for task in repo_user_reconciliation["rescue"]
        if task.get("name") == "Retry the repo-managed Keycloak user reconciliation tasks after recovery"
    )
    group_token_task = next(
        task
        for task in repo_user_tasks
        if task.get("name") == "Request a Keycloak admin token for repo-managed user reconciliation"
    )
    platform_group_lookup_task = next(
        task for task in repo_user_tasks if task.get("name") == "Look up the lv3-platform-admins group in Keycloak"
    )
    operator_lookup_task = next(
        task for task in repo_user_tasks if task.get("name") == "Look up the named operator in Keycloak"
    )
    outline_lookup_task = next(
        task for task in repo_user_tasks if task.get("name") == "Look up the Outline automation user in Keycloak"
    )

    assert include_task["ansible.builtin.include_tasks"] == "reconcile_repo_managed_users.yml"
    assert retry_task["ansible.builtin.include_tasks"] == "reconcile_repo_managed_users.yml"
    assert group_token_task["ansible.builtin.uri"]["timeout"] == "{{ keycloak_admin_connection_timeout }}"
    assert group_token_task["retries"] == "{{ keycloak_repo_user_reconciliation_retries }}"
    assert group_token_task["delay"] == "{{ keycloak_repo_user_reconciliation_delay }}"
    assert "json.access_token" in group_token_task["until"]
    assert repo_user_tasks.index(group_token_task) < repo_user_tasks.index(platform_group_lookup_task)
    assert repo_user_tasks.index(platform_group_lookup_task) < repo_user_tasks.index(operator_lookup_task)
    assert repo_user_tasks.index(operator_lookup_task) < repo_user_tasks.index(outline_lookup_task)


def test_role_manages_serverclaw_runtime_client_and_removes_the_stale_operator_direct_grant() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    remove_operator_client_task = next(
        task
        for task in realm_block["block"]
        if task.get("name") == "Ensure the obsolete ServerClaw operator CLI direct-grant client is absent"
    )
    runtime_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the ServerClaw runtime client exists"
    )
    read_runtime_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the ServerClaw runtime client secret"
    )
    remove_operator_secret_task = next(
        task
        for task in tasks
        if task.get("name") == "Remove the stale ServerClaw operator CLI client secret from the control machine"
    )
    mirror_runtime_secret_task = next(
        task
        for task in tasks
        if task.get("name") == "Mirror the ServerClaw runtime client secret to the control machine"
    )
    runtime_token_task = next(
        task for task in tasks if task.get("name") == "Request the ServerClaw runtime client-credentials token"
    )
    assert_task = next(
        task for task in tasks if task.get("name") == "Assert Keycloak endpoints and automation credentials are working"
    )

    assert remove_operator_client_task["community.general.keycloak_client"]["client_id"] == "serverclaw-operator-cli"
    assert remove_operator_client_task["community.general.keycloak_client"]["state"] == "absent"
    assert (
        runtime_client_task["community.general.keycloak_client"]["client_id"]
        == "{{ keycloak_serverclaw_runtime_client_id }}"
    )
    assert runtime_client_task["community.general.keycloak_client"]["service_accounts_enabled"] is True
    assert read_runtime_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == (
        "{{ keycloak_serverclaw_runtime_client_id }}"
    )
    assert remove_operator_secret_task["ansible.builtin.file"]["state"] == "absent"
    assert (
        mirror_runtime_secret_task["ansible.builtin.copy"]["dest"]
        == "{{ keycloak_serverclaw_runtime_client_secret_local_file }}"
    )
    assert runtime_token_task["ansible.builtin.uri"]["body"]["grant_type"] == "client_credentials"
    assert (
        runtime_token_task["ansible.builtin.uri"]["body"]["client_id"] == "{{ keycloak_serverclaw_runtime_client_id }}"
    )
    assert "keycloak_serverclaw_runtime_token.json.access_token" in str(assert_task["ansible.builtin.assert"]["that"])


def test_role_manages_glitchtip_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    read_secret_task = next(
        task for task in realm_block["block"] if task.get("name") == "Read the GlitchTip client secret"
    )
    mirror_secret_task = next(
        task for task in tasks if task.get("name") == "Mirror the GlitchTip client secret to the control machine"
    )

    assert defaults["keycloak_glitchtip_client_id"] == "glitchtip"
    assert defaults["keycloak_glitchtip_client_secret_local_file"] == (
        "{{ keycloak_local_artifact_dir }}/glitchtip-client-secret.txt"
    )
    assert defaults["keycloak_glitchtip_root_url"] == "https://errors.{{ platform_domain }}"
    assert defaults["keycloak_glitchtip_post_logout_redirect_uris"] == [
        "{{ keycloak_glitchtip_root_url }}",
        "{{ keycloak_glitchtip_root_url }}/",
        "{{ keycloak_glitchtip_root_url }}/login",
    ]
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == (
        "{{ keycloak_glitchtip_client_id }}"
    )
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_glitchtip_client_secret_local_file }}"
