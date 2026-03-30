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
    assert defaults["keycloak_mail_platform_submission_host"] == "{{ smtp_host }}"
    assert defaults["keycloak_mail_platform_submission_port"] == "{{ smtp_port }}"
    assert defaults["keycloak_mail_platform_submission_starttls"] == "{{ smtp_starttls }}"
    assert defaults["keycloak_mail_platform_submission_auth_enabled"] == "{{ smtp_auth_enabled }}"
    assert defaults["keycloak_mail_platform_docker_network_name"] == "{{ smtp_docker_network_name }}"
    assert defaults["keycloak_compose_project_name"] == "keycloak"
    assert defaults["keycloak_compose_network_name"] == "{{ keycloak_compose_project_name }}_default"
    assert defaults["keycloak_langfuse_client_id"] == "langfuse"
    assert defaults["keycloak_langfuse_client_secret_local_file"].endswith("/.local/keycloak/langfuse-client-secret.txt")
    assert defaults["keycloak_jupyterhub_client_id"] == "jupyterhub"
    assert defaults["keycloak_jupyterhub_client_secret_local_file"].endswith("/.local/keycloak/jupyterhub-client-secret.txt")
    assert defaults["keycloak_serverclaw_runtime_client_id"] == "serverclaw-runtime"
    assert defaults["keycloak_serverclaw_runtime_client_secret_local_file"].endswith(
        "/.local/keycloak/serverclaw-runtime-client-secret.txt"
    )
    assert defaults["keycloak_grist_client_id"] == "grist"
    assert defaults["keycloak_grist_client_secret_local_file"].endswith("/.local/keycloak/grist-client-secret.txt")
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
    assert defaults["keycloak_grist_post_logout_redirect_uris"] == [
        "{{ keycloak_grist_root_url }}",
        "{{ keycloak_grist_root_url }}/",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert defaults["keycloak_outline_post_logout_redirect_uris"] == [
        "{{ keycloak_outline_root_url }}",
        "{{ keycloak_outline_root_url }}/",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert defaults["keycloak_jupyterhub_post_logout_redirect_uris"] == [
        "{{ keycloak_jupyterhub_root_url }}",
        "{{ keycloak_jupyterhub_root_url }}/",
        "{{ keycloak_session_authority.shared_proxy_cleanup_url }}",
    ]
    assert smtp_server["auth"] == "{{ keycloak_mail_platform_submission_auth_enabled }}"
    assert smtp_server["host"] == "{{ keycloak_mail_platform_submission_host }}"
    assert smtp_server["port"] == "{{ keycloak_mail_platform_submission_port }}"
    assert smtp_server["user"] == "{{ keycloak_mail_platform_submission_username if keycloak_mail_platform_submission_auth_enabled else '' }}"
    assert smtp_server["starttls"] == "{{ keycloak_mail_platform_submission_starttls }}"
    assert smtp_server["ssl"] is False


def test_role_requires_local_mail_submission_secret() -> None:
    tasks = load_tasks()
    stat_task = next(
        task
        for task in tasks
        if task.get("name") == "Ensure the Keycloak mail submission password exists on the control machine when SMTP auth is enabled"
    )
    fail_task = next(
        task
        for task in tasks
        if task.get("name") == "Fail if the Keycloak mail submission password is missing locally when SMTP auth is enabled"
    )
    assert stat_task["ansible.builtin.stat"]["path"] == "{{ keycloak_mail_platform_submission_password_local_file }}"
    assert stat_task["when"] == "keycloak_mail_platform_submission_auth_enabled"
    assert fail_task["when"] == [
        "keycloak_mail_platform_submission_auth_enabled",
        "not keycloak_mail_platform_submission_password_local.stat.exists",
    ]
    assert "password-reset and required-action mail" in fail_task["ansible.builtin.fail"]["msg"]


def test_realm_task_applies_repo_managed_smtp_settings() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    assert realm_block["module_defaults"]["group/community.general.keycloak"]["connection_timeout"] == (
        "{{ keycloak_admin_connection_timeout }}"
    )
    realm_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the LV3 realm exists")
    assert realm_task["community.general.keycloak_realm"]["smtp_server"] == "{{ keycloak_realm_smtp_server }}"
    assert realm_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert realm_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert realm_task["until"] == "keycloak_realm_reconcile is succeeded"


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
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the Keycloak service after Docker networking recovery"
    )
    force_recreate_fact = next(
        task
        for task in tasks
        if task.get("name") == "Record whether the Keycloak startup needs a force recreate"
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
    assert bridge_chain_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert bridge_chain_helper["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert bridge_chain_helper["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    assert env_render["register"] == "keycloak_env_template"
    assert compose_render["register"] == "keycloak_compose_template"
    assert defaults["keycloak_image_pull_retries"] == 5
    assert defaults["keycloak_image_pull_delay_seconds"] == 5
    assert image_pull["retries"] == "{{ keycloak_image_pull_retries }}"
    assert image_pull["delay"] == "{{ keycloak_image_pull_delay_seconds }}"
    assert image_pull["until"] == "keycloak_pull.rc == 0"
    assert "com.docker.compose.project=keycloak" in replace_cleanup["ansible.builtin.shell"]
    assert "com.docker.compose.replace" in replace_cleanup["ansible.builtin.shell"]
    assert openbao_agent_recreate["ansible.builtin.command"]["argv"][-4:] == ["up", "-d", "--force-recreate", "openbao-agent"]
    assert 'grep -Fqx "KC_DB_URL_HOST={{ keycloak_database_host }}" "{{ keycloak_env_file }}"' in runtime_env_wait["ansible.builtin.shell"]
    assert (
        'grep -Fqx "KC_BOOTSTRAP_ADMIN_USERNAME={{ keycloak_bootstrap_admin_username }}" "{{ keycloak_env_file }}"'
        in runtime_env_wait["ansible.builtin.shell"]
    )
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
    force_recreate_shell = force_recreate["ansible.builtin.shell"]
    assert "docker network inspect" in force_recreate_shell
    assert "{{ keycloak_mail_platform_docker_network_name }}" in force_recreate_shell
    assert "docker compose --file \"{{ keycloak_compose_file }}\" up -d --force-recreate --no-deps keycloak" in force_recreate_shell
    assert "com.docker.compose.project=keycloak" in force_recreate_shell
    assert "com.docker.compose.service=keycloak" in force_recreate_shell
    assert "docker rm -f $stale_ids || true" in force_recreate_shell
    assert force_recreate["args"]["executable"] == "/bin/bash"
    force_recreate_expression = force_recreate_fact["ansible.builtin.set_fact"]["keycloak_force_recreate"]
    assert "keycloak_docker_nat_chain.rc != 0" in force_recreate_expression
    assert "keycloak_local_http_port_probe.failed" in force_recreate_expression
    assert "keycloak_readiness_probe.status" in force_recreate_expression
    assert "keycloak_env_template.changed" not in force_recreate_expression
    assert "keycloak_compose_template.changed" not in force_recreate_expression
    assert "keycloak_pull.changed" not in force_recreate_expression
    nat_assert = next(task for task in tasks if task.get("name") == "Assert Docker nat chain is present before Keycloak startup")
    assert nat_assert["ansible.builtin.assert"]["that"] == [
        "keycloak_docker_nat_chain.rc == 0 or (common_docker_bridge_chains_nat_verify.rc | default(1)) == 0"
    ]


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
    api_gateway_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the API gateway client secret")
    assert api_gateway_client_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert api_gateway_client_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert api_gateway_client_task["until"] == "keycloak_api_gateway_client_reconcile is succeeded"
    assert api_gateway_secret_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert api_gateway_secret_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert api_gateway_secret_task["until"] == "keycloak_api_gateway_client_secret_info is succeeded"


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
    settle_task = next(
        task
        for task in tasks
        if task.get("name") == "Allow the Keycloak admin API to settle after the first authenticated probe"
    )
    token_probe_confirmed_task = next(
        task
        for task in tasks
        if task.get("name") == "Reconfirm the Keycloak bootstrap admin token endpoint after the settle window"
    )
    admin_probe_confirmed_task = next(
        task
        for task in tasks
        if task.get("name") == "Reconfirm an authenticated Keycloak admin realm query after the settle window"
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
    assert settle_task["ansible.builtin.pause"]["seconds"] == "{{ keycloak_startup_probe_delay }}"
    assert token_probe_confirmed_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert token_probe_confirmed_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert admin_probe_confirmed_task["retries"] == "{{ keycloak_startup_probe_retries }}"
    assert admin_probe_confirmed_task["delay"] == "{{ keycloak_startup_probe_delay }}"
    assert token_probe_task["ansible.builtin.uri"]["return_content"] is True
    assert admin_probe_task["ansible.builtin.uri"]["url"] == "{{ keycloak_local_admin_url }}/admin/realms/{{ keycloak_realm_name }}"
    assert admin_probe_task["ansible.builtin.uri"]["headers"]["Authorization"] == (
        "Bearer {{ keycloak_bootstrap_admin_token_probe.json.access_token }}"
    )
    assert token_probe_confirmed_task["ansible.builtin.uri"]["return_content"] is True
    assert admin_probe_confirmed_task["ansible.builtin.uri"]["headers"]["Authorization"] == (
        "Bearer {{ keycloak_bootstrap_admin_token_probe_confirmed.json.access_token }}"
    )


def test_realm_reconciliation_retries_repo_managed_keycloak_modules() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    assert defaults["keycloak_admin_connection_timeout"] == 60
    assert defaults["keycloak_admin_reconciliation_retries"] == 24
    assert defaults["keycloak_admin_reconciliation_delay"] == 5
    assert realm_block["module_defaults"]["group/community.general.keycloak"]["connection_timeout"] == (
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
        "Ensure the Outline OAuth client exists",
        "Ensure the JupyterHub OAuth client exists",
        "Ensure the ServerClaw OAuth client exists",
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
        "Read the Outline client secret",
        "Read the JupyterHub client secret",
        "Read the ServerClaw client secret",
        "Read the API gateway client secret",
        "Read the ServerClaw runtime client secret",
    ]
    retry_tasks = [next(task for task in realm_block["block"] if task.get("name") == name) for name in retry_task_names]
    for task in retry_tasks:
        assert "register" in task
        assert task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
        assert task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
        assert task["until"] == f"{task['register']} is succeeded"


def test_all_keycloak_client_secret_reads_retry_reconciliation_until_success() -> None:
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    read_secret_tasks = [
        task
        for task in realm_block["block"]
        if task.get("name", "").startswith("Read the ") and task.get("name", "").endswith(" client secret")
    ]

    assert len(read_secret_tasks) == 11
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
    langfuse_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Langfuse OAuth client exists")
    read_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the Langfuse client secret")
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the Langfuse client secret to the control machine")
    assert langfuse_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_langfuse_client_id }}"
    assert langfuse_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_langfuse_root_url }}/api/auth/callback/keycloak"
    ]
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == "{{ keycloak_langfuse_client_id }}"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_langfuse_client_secret_local_file }}"


def test_role_manages_directus_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    directus_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Directus OAuth client exists")
    read_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the Directus client secret")
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the Directus client secret to the control machine")

    assert defaults["keycloak_directus_client_id"] == "directus"
    assert defaults["keycloak_directus_client_secret_local_file"].endswith("/.local/keycloak/directus-client-secret.txt")
    assert defaults["keycloak_directus_root_url"] == "https://data.lv3.org"
    assert directus_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_directus_client_id }}"
    assert directus_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_directus_root_url }}/auth/login/keycloak/callback"
    ]
    assert directus_client_task["community.general.keycloak_client"]["web_origins"] == ["{{ keycloak_directus_root_url }}"]
    directus_mapper = directus_client_task["community.general.keycloak_client"]["protocol_mappers"][0]
    assert directus_mapper["name"] == "groups"
    assert directus_mapper["config"]["claim.name"] == "groups"
    assert directus_mapper["config"]["full.path"] == "true"
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == "{{ keycloak_directus_client_id }}"
    assert read_secret_task["retries"] == "{{ keycloak_admin_reconciliation_retries }}"
    assert read_secret_task["delay"] == "{{ keycloak_admin_reconciliation_delay }}"
    assert read_secret_task["until"] == "keycloak_directus_client_secret_info is succeeded"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_directus_client_secret_local_file }}"


def test_role_manages_outline_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    grafana_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Grafana OAuth client exists")
    ops_portal_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the operations portal OAuth client exists"
    )
    grist_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Grist OAuth client exists")
    outline_client_task = next(task for task in realm_block["block"] if task.get("name") == "Ensure the Outline OAuth client exists")
    read_grist_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the Grist client secret")
    read_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the Outline client secret")
    mirror_grist_secret_task = next(task for task in tasks if task.get("name") == "Mirror the Grist client secret to the control machine")
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the Outline client secret to the control machine")
    assert defaults["keycloak_grist_client_id"] == "grist"
    assert defaults["keycloak_grist_client_secret_local_file"].endswith("/.local/keycloak/grist-client-secret.txt")
    assert defaults["keycloak_grist_root_url"] == "https://grist.lv3.org"
    assert defaults["keycloak_outline_client_id"] == "outline"
    assert defaults["keycloak_outline_client_secret_local_file"].endswith("/.local/keycloak/outline-client-secret.txt")
    assert defaults["keycloak_outline_root_url"] == "https://wiki.lv3.org"
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
    assert read_grist_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == "{{ keycloak_grist_client_id }}"
    assert mirror_grist_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_grist_client_secret_local_file }}"
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == "{{ keycloak_outline_client_id }}"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_outline_client_secret_local_file }}"


def test_role_manages_jupyterhub_client_secret() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    tasks = load_tasks()
    realm_block = next(task for task in tasks if task.get("name") == "Converge Keycloak realm objects")
    jupyterhub_client_task = next(
        task for task in realm_block["block"] if task.get("name") == "Ensure the JupyterHub OAuth client exists"
    )
    read_secret_task = next(task for task in realm_block["block"] if task.get("name") == "Read the JupyterHub client secret")
    mirror_secret_task = next(task for task in tasks if task.get("name") == "Mirror the JupyterHub client secret to the control machine")

    assert defaults["keycloak_jupyterhub_client_id"] == "jupyterhub"
    assert defaults["keycloak_jupyterhub_client_secret_local_file"].endswith("/.local/keycloak/jupyterhub-client-secret.txt")
    assert defaults["keycloak_jupyterhub_root_url"] == "https://notebooks.lv3.org"
    assert jupyterhub_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_jupyterhub_client_id }}"
    assert jupyterhub_client_task["community.general.keycloak_client"]["redirect_uris"] == [
        "{{ keycloak_jupyterhub_root_url }}/hub/oauth_callback"
    ]
    assert jupyterhub_client_task["community.general.keycloak_client"]["valid_post_logout_redirect_uris"] == (
        "{{ keycloak_jupyterhub_post_logout_redirect_uris }}"
    )
    assert read_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == "{{ keycloak_jupyterhub_client_id }}"
    assert mirror_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_jupyterhub_client_secret_local_file }}"


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


def test_repo_managed_user_reconciliation_is_delegated_to_the_include_file() -> None:
    tasks = load_tasks()
    repo_user_tasks = load_tasks(REPO_USER_TASKS_PATH)
    repo_user_reconciliation = next(task for task in tasks if task.get("name") == "Reconcile repo-managed Keycloak users")
    include_task = next(
        task for task in repo_user_reconciliation["block"] if task.get("name") == "Run the repo-managed Keycloak user reconciliation tasks"
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
    operator_lookup_task = next(task for task in repo_user_tasks if task.get("name") == "Look up the named operator in Keycloak")
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
        task for task in tasks if task.get("name") == "Mirror the ServerClaw runtime client secret to the control machine"
    )
    runtime_token_task = next(
        task for task in tasks if task.get("name") == "Request the ServerClaw runtime client-credentials token"
    )
    assert_task = next(task for task in tasks if task.get("name") == "Assert Keycloak endpoints and automation credentials are working")

    assert remove_operator_client_task["community.general.keycloak_client"]["client_id"] == "serverclaw-operator-cli"
    assert remove_operator_client_task["community.general.keycloak_client"]["state"] == "absent"
    assert runtime_client_task["community.general.keycloak_client"]["client_id"] == "{{ keycloak_serverclaw_runtime_client_id }}"
    assert runtime_client_task["community.general.keycloak_client"]["service_accounts_enabled"] is True
    assert read_runtime_secret_task["community.general.keycloak_clientsecret_info"]["client_id"] == (
        "{{ keycloak_serverclaw_runtime_client_id }}"
    )
    assert remove_operator_secret_task["ansible.builtin.file"]["state"] == "absent"
    assert mirror_runtime_secret_task["ansible.builtin.copy"]["dest"] == "{{ keycloak_serverclaw_runtime_client_secret_local_file }}"
    assert runtime_token_task["ansible.builtin.uri"]["body"]["grant_type"] == "client_credentials"
    assert runtime_token_task["ansible.builtin.uri"]["body"]["client_id"] == "{{ keycloak_serverclaw_runtime_client_id }}"
    assert "keycloak_serverclaw_runtime_token.json.access_token" in str(assert_task["ansible.builtin.assert"]["that"])
