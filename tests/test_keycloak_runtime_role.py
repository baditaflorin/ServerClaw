from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "main.yml"
REPO_USER_TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "reconcile_repo_managed_users.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "templates" / "docker-compose.yml.j2"
SERVERCLAW_TASKS_PATH = REPO_ROOT / "roles" / "keycloak_runtime" / "tasks" / "serverclaw_client.yml"


def load_tasks(path: Path = TASKS_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())


def load_serverclaw_tasks() -> list[dict]:
    return yaml.safe_load(SERVERCLAW_TASKS_PATH.read_text())


def test_defaults_define_internal_mail_submission_for_realm_mail() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    smtp_server = defaults["keycloak_realm_smtp_server"]
    assert defaults["keycloak_session_authority"] == "{{ platform_session_authority }}"
    assert defaults["keycloak_database_host"] == "{{ hostvars[hostvars['proxmox_florin'].postgres_ha.initial_primary].ansible_host }}"
    assert defaults["keycloak_mail_platform_submission_host"] == "lv3-mail-stalwart"
    assert defaults["keycloak_mail_platform_submission_port"] == 1587
    assert defaults["keycloak_mail_platform_submission_starttls"] is False
    assert defaults["keycloak_compose_project_name"] == "keycloak"
    assert defaults["keycloak_compose_network_name"] == "{{ keycloak_compose_project_name }}_default"
    assert defaults["keycloak_mail_platform_docker_network_name"] == "mail-platform_default"
    assert defaults["keycloak_langfuse_client_id"] == "langfuse"
    assert defaults["keycloak_langfuse_client_secret_local_file"].endswith("/.local/keycloak/langfuse-client-secret.txt")
    assert defaults["keycloak_outline_automation_username"] == "outline.automation"
    assert defaults["keycloak_outline_automation_password_local_file"].endswith("/.local/keycloak/outline.automation-password.txt")
    assert defaults["keycloak_ops_portal_post_logout_redirect_uris"] == [
        "{{ keycloak_ops_portal_root_url }}/",
        "{{ keycloak_ops_portal_root_url }}",
        "{{ keycloak_session_authority.shared_logged_out_url }}",
    ]
    assert defaults["keycloak_grafana_post_logout_redirect_uris"] == [
        "{{ keycloak_grafana_root_url }}/login",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert defaults["keycloak_outline_post_logout_redirect_uris"] == [
        "{{ keycloak_outline_root_url }}",
        "{{ keycloak_outline_root_url }}/",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert smtp_server["host"] == "{{ keycloak_mail_platform_submission_host }}"
    assert smtp_server["port"] == "{{ keycloak_mail_platform_submission_port }}"
    assert smtp_server["user"] == "{{ keycloak_mail_platform_submission_username }}"
    assert smtp_server["starttls"] == "{{ keycloak_mail_platform_submission_starttls }}"
    assert smtp_server["ssl"] is False


def test_role_requires_local_mail_submission_secret() -> None:
    tasks = load_tasks()
    stat_task = next(task for task in tasks if task.get("name") == "Ensure the Keycloak mail submission password exists on the control machine")
    fail_task = next(task for task in tasks if task.get("name") == "Fail if the Keycloak mail submission password is missing locally")
    assert stat_task["ansible.builtin.stat"]["path"] == "{{ keycloak_mail_platform_submission_password_local_file }}"
    assert "password-reset and required-action mail" in fail_task["ansible.builtin.fail"]["msg"]


def test_realm_task_applies_repo_managed_smtp_settings() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    assert realm_block["module_defaults"]["group/community.general.keycloak"]["connection_timeout"] == (
        "{{ keycloak_admin_connection_timeout }}"
    )
    realm_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the LV3 realm exists")
    assert realm_task["community.general.keycloak_realm"]["smtp_server"] == "{{ keycloak_realm_smtp_server }}"


def test_role_restores_docker_nat_chain_before_startup() -> None:
    tasks = load_tasks()
    env_render = next(task for task in tasks if task.get("name") == "Render the Keycloak environment file")
    compose_render = next(task for task in tasks if task.get("name") == "Render the Keycloak compose file")
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
    nat_recheck = next(
        task
        for task in tasks
        if task.get("name") == "Recheck the Docker nat chain before Keycloak startup"
    )
    docker_info = next(
        task
        for task in tasks
        if task.get("name") == "Wait for the Docker daemon to answer after networking recovery"
    )
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the Keycloak stack after Docker networking recovery"
    )
    force_recreate_fact = next(
        task for task in tasks if task.get("name") == "Record whether the Keycloak startup needs a force recreate"
    )
    force_recreate_down = next(
        task for task in tasks if task.get("name") == "Reset the Keycloak stack before a force recreate"
    )
    network_cleanup = next(
        task for task in tasks if task.get("name") == "Remove stale Keycloak compose networks after the reset"
    )
    readiness_probe = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the current Keycloak readiness endpoint is healthy before startup"
    )
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert nat_recheck["until"] == "keycloak_docker_nat_chain_recheck.rc == 0"
    assert docker_info["ansible.builtin.command"]["argv"] == ["docker", "info", "--format", '{{ "{{.ServerVersion}}" }}']
    assert env_render["register"] == "keycloak_env_template"
    assert compose_render["register"] == "keycloak_compose_template"
    assert readiness_probe["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ keycloak_local_management_port }}/health/ready"
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
    assert network_cleanup["when"] == "keycloak_force_recreate"
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
    assert force_recreate["until"] == "keycloak_up.rc == 0"
    force_recreate_expression = force_recreate_fact["ansible.builtin.set_fact"]["keycloak_force_recreate"]
    assert "keycloak_docker_nat_chain.rc != 0" in force_recreate_expression
    assert "keycloak_local_http_port_probe.failed" in force_recreate_expression
    assert "keycloak_readiness_probe.status" in force_recreate_expression
    assert "keycloak_env_template.changed" not in force_recreate_expression
    assert "keycloak_compose_template.changed" not in force_recreate_expression
    assert "keycloak_pull.changed" not in force_recreate_expression


def test_role_verifies_internal_mail_network_connectivity() -> None:
    tasks = load_tasks()
    resolve_task = next(
        task for task in tasks if task.get("name") == "Verify Keycloak resolves the internal mail-platform relay host"
    )
    connect_task = next(
        task for task in tasks if task.get("name") == "Verify Keycloak reaches the internal mail-platform submission listener"
    )
    assert resolve_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "exec",
        "keycloak-keycloak-1",
        "getent",
        "ahostsv4",
        "{{ keycloak_mail_platform_submission_host }}",
    ]
    assert "{{ keycloak_mail_platform_submission_host }}" in connect_task["ansible.builtin.shell"]
    assert "{{ keycloak_mail_platform_submission_port }}" in connect_task["ansible.builtin.shell"]


def test_role_warms_authenticated_keycloak_admin_queries_before_realm_reconcile() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    readiness_task = next(task for task in tasks if task.get("name") == "Wait for the Keycloak readiness endpoint")
    admin_api_task = next(task for task in tasks if task.get("name") == "Wait for the Keycloak admin API to answer")
    token_probe_task = next(
        task for task in tasks if task.get("name") == "Wait for the Keycloak bootstrap admin token endpoint to succeed"
    )
    admin_probe_task = next(
        task for task in tasks if task.get("name") == "Wait for an authenticated Keycloak admin realm query to answer"
    )
    assert defaults["keycloak_startup_probe_retries"] == 60
    assert defaults["keycloak_startup_probe_delay"] == 5
    assert readiness_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert readiness_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert admin_api_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert admin_api_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert token_probe_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert token_probe_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert admin_probe_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert admin_probe_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert token_probe_task["ansible.builtin.uri"]["return_content"] is True
    assert admin_probe_task["ansible.builtin.uri"]["url"] == "{{ keycloak_local_admin_url }}/admin/realms/{{ keycloak_realm_name }}"
    assert admin_probe_task["ansible.builtin.uri"]["headers"]["Authorization"] == (
        "Bearer {{ keycloak_bootstrap_admin_token_probe.json.access_token }}"
    )


def test_compose_template_joins_the_mail_platform_network() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text()
    assert "      - mail-platform" in template
    assert "  mail-platform:" in template
    assert "    external: true" in template
    assert "    name: {{ keycloak_mail_platform_docker_network_name }}" in template


def test_role_manages_langfuse_client_secret() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    langfuse_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Langfuse OAuth client exists")
    read_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the Langfuse client secret")
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the Langfuse client secret to the control machine")
    assert langfuse_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_langfuse_client_id }}"
    assert langfuse_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_langfuse_root_url }}/api/auth/callback/keycloak"
    ]
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == "{{ keycloak_langfuse_client_id }}"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_langfuse_client_secret_local_file }}"


def test_role_manages_outline_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    grafana_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Grafana OAuth client exists")
    ops_portal_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the operations portal OAuth client exists"
    )
    outline_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Outline OAuth client exists")
    read_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the Outline client secret")
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the Outline client secret to the control machine")
    assert defaults["keycloak_outline_client_id"] == "outline"
    assert defaults["keycloak_outline_client_secret_local_file"].endswith("/.local/keycloak/outline-client-secret.txt")
    assert defaults["keycloak_outline_root_url"] == "https://wiki.lv3.org"
    assert grafana_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_grafana_post_logout_redirect_uris }}"
    )
    assert ops_portal_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_ops_portal_post_logout_redirect_uris }}"
    )
    assert outline_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_outline_client_id }}"
    assert outline_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_outline_root_url }}/auth/oidc.callback"
    ]
    assert outline_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_outline_post_logout_redirect_uris }}"
    )
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == "{{ keycloak_outline_client_id }}"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_outline_client_secret_local_file }}"


def test_role_manages_serverclaw_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    serverclaw_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the ServerClaw OAuth client exists"
    )
    read_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the ServerClaw client secret")
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the ServerClaw client secret to the control machine")
    assert defaults["keycloak_serverclaw_client_id"] == "serverclaw"
    assert defaults["keycloak_serverclaw_client_secret_local_file"].endswith("/.local/keycloak/serverclaw-client-secret.txt")
    assert defaults["keycloak_serverclaw_root_url"] == "https://chat.lv3.org"
    assert defaults["keycloak_serverclaw_post_logout_redirect_uris"] == [
        "{{ keycloak_serverclaw_root_url }}",
        "{{ keycloak_serverclaw_root_url }}/",
    ]
    assert serverclaw_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_serverclaw_client_id }}"
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
        task for task in tasks if task.get("name") == "Wait for the Keycloak bootstrap admin token endpoint to succeed"
    )
    realm_block = next(task for task in tasks if task.get("name") == "Converge the dedicated ServerClaw Keycloak client")
    serverclaw_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the ServerClaw OAuth client exists"
    )
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the ServerClaw client secret to the control machine")
    assert readiness_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ keycloak_local_management_port }}/health/ready"
    assert admin_api_task["ansible.builtin.uri"]["url"] == "{{ keycloak_local_admin_url }}/realms/master/.well-known/openid-configuration"
    assert token_probe_task["ansible.builtin.uri"]["body"]["client_id"] == "admin-cli"
    assert serverclaw_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_serverclaw_client_id }}"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_serverclaw_client_secret_local_file }}"


def test_role_manages_the_outline_automation_identity() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    repo_user_tasks = load_tasks(REPO_USER_TASKS_PATH)
    password_generation_task = next(task for task in tasks if task.get("name") == "Generate the Outline automation password")
    password_mirror_task = next(task for task in tasks if task.get("name") == "Mirror the Outline automation password to the control machine")
    repo_user_reconciliation = next(task for task in tasks if task.get("name") == "Reconcile repo-managed Keycloak users")
    include_task = next(
        task for task in repo_user_reconciliation["block"] if task.get("name") == "Run the repo-managed Keycloak user reconciliation tasks"
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
        == "Wait for the Keycloak bootstrap admin token endpoint after repo-managed user reconciliation recovery"
    )
    recovery_retry_task = next(
        task
        for task in repo_user_reconciliation["rescue"]
        if task.get("name") == "Retry the repo-managed Keycloak user reconciliation tasks after recovery"
    )
    admin_token_task = next(
        task for task in repo_user_tasks if task.get("name") == "Request a Keycloak admin token for repo-managed user reconciliation"
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
        task for task in repo_user_tasks if task.get("name") == "Create the Outline automation user in Keycloak when missing"
    )
    automation_user_task = next(
        task for task in repo_user_tasks if task.get("name") == "Update the Outline automation user profile in Keycloak"
    )
    automation_password_task = next(
        task for task in repo_user_tasks if task.get("name") == "Reset the Outline automation user password in Keycloak"
    )
    assert password_generation_task["ansible.builtin.shell"].count("openssl rand -base64 24") == 1
    assert password_mirror_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_outline_automation_password_local_file }}"
    assert defaults["keycloak_repo_user_reconciliation_retries"] == 24
    assert defaults["keycloak_repo_user_reconciliation_delay"] == 5
    assert defaults["keycloak_admin_connection_timeout"] == 30
    assert defaults["keycloak_local_admin_url"] == "http://{{ ansible_host }}:{{ keycloak_internal_http_port }}"
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
    assert recovery_retry_task["ansible.builtin.include_tasks"] == "reconcile_repo_managed_users.yml"
    assert admin_token_task["ansible.builtin.uri"]["url"] == (
        "{{ keycloak_repo_user_admin_url }}/realms/master/protocol/openid-connect/token"
    )
    assert admin_token_task["ansible.builtin.uri"]["body"]["client_id"] == "admin-cli"
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
    assert automation_user_task["ansible.builtin.uri"]["body"]["username"] == "{{ keycloak_outline_automation_username }}"
    assert automation_user_task["ansible.builtin.uri"]["body"]["requiredActions"] == []
    assert automation_password_task["ansible.builtin.uri"]["body"]["temporary"] is False
