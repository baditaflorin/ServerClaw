from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "glitchtip_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "glitchtip_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "glitchtip_runtime" / "tasks" / "verify.yml"
ROLE_PUBLISH = REPO_ROOT / "roles" / "glitchtip_runtime" / "tasks" / "publish.yml"
ROLE_PUBLISH_VERIFY = REPO_ROOT / "roles" / "glitchtip_runtime" / "tasks" / "publish_verify.yml"
ROLE_META = REPO_ROOT / "roles" / "glitchtip_runtime" / "meta" / "argument_specs.yml"
POSTGRES_TASKS = REPO_ROOT / "roles" / "glitchtip_postgres" / "tasks" / "main.yml"
POSTGRES_META = REPO_ROOT / "roles" / "glitchtip_postgres" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "glitchtip_runtime" / "templates" / "docker-compose.yml.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "glitchtip_runtime" / "templates" / "glitchtip.env.ctmpl.j2"
BOOTSTRAP_TEMPLATE = REPO_ROOT / "roles" / "glitchtip_runtime" / "templates" / "bootstrap-glitchtip.py.j2"
OIDC_SMOKE_SCRIPT = REPO_ROOT / "scripts" / "glitchtip_oidc_smoke.py"
INTEGRATION_CONTRACT = REPO_ROOT / "config" / "integrations" / "glitchtip--authentik.yaml"
SERVICE_CATALOG = REPO_ROOT / "catalog" / "services" / "glitchtip" / "service.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_glitchtip_runtime_defaults_reference_service_topology_images_and_local_artifacts() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["glitchtip_service_topology"] == (
        "{{ hostvars[platform_topology_host].platform_service_topology | service_topology_get('glitchtip') }}"
    )
    assert "glitchtip_internal_port" not in defaults
    assert "glitchtip_internal_base_url" not in defaults
    assert defaults["glitchtip_public_base_url"] == "https://{{ glitchtip_service_topology.public_hostname }}"
    assert defaults["glitchtip_compose_network_name"] == "glitchtip_default"
    assert defaults["glitchtip_image"] == "{{ container_image_catalog.images.glitchtip_runtime.ref }}"
    assert defaults["glitchtip_valkey_image"] == "{{ container_image_catalog.images.glitchtip_valkey_runtime.ref }}"
    assert defaults["glitchtip_database_password_local_file"] == (
        "{{ repo_shared_local_root }}/glitchtip/database-password.txt"
    )
    assert defaults["glitchtip_local_artifact_dir"] == "{{ repo_shared_local_root }}/glitchtip"
    assert defaults["glitchtip_api_token_local_file"] == "{{ glitchtip_local_artifact_dir }}/api-token.txt"
    assert defaults["glitchtip_oidc_client_secret_local_file"] == (
        "{{ repo_shared_local_root }}/authentik/glitchtip-client-secret.txt"
    )
    assert defaults["glitchtip_keycloak_rollback_client_secret_local_file"] == (
        "{{ repo_shared_local_root }}/keycloak/glitchtip-client-secret.txt"
    )
    assert defaults["glitchtip_oidc_provider"] == "openid_connect"
    assert defaults["glitchtip_oidc_provider_id"] == "authentik"
    assert defaults["glitchtip_oidc_provider_name"] == "Authentik"
    assert defaults["glitchtip_oidc_client_id"] == "glitchtip"
    assert not defaults["glitchtip_oidc_issuer_url"].endswith("/")
    assert defaults["glitchtip_keycloak_rollback_provider"] == "openid_connect"
    assert defaults["glitchtip_keycloak_rollback_provider_id"] == "keycloak"
    assert defaults["glitchtip_keycloak_rollback_client_id"] == "glitchtip"
    assert defaults["glitchtip_keycloak_rollback_issuer_url"] == "{{ keycloak_oidc_issuer_url }}"
    assert defaults["glitchtip_mail_submission_password_local_file"] == (
        "{{ repo_shared_local_root }}/mail-platform/server-mailbox-password.txt"
    )
    assert [project["slug"] for project in defaults["glitchtip_bootstrap_projects"]] == [
        "mail-gateway",
        "windmill-jobs",
        "platform-findings",
    ]


def test_glitchtip_runtime_tasks_manage_openbao_bootstrap_and_port_recovery() -> None:
    tasks = load_yaml(ROLE_TASKS)

    openbao_helper = next(
        task for task in tasks if task.get("name") == "Prepare OpenBao agent runtime secret injection for GlitchTip"
    )
    nat_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker nat chain exists before GlitchTip startup"
    )
    forward_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker forward chain exists before GlitchTip startup"
    )
    nat_restore = next(
        task
        for task in tasks
        if task.get("name") == "Restore Docker networking when bridge chains are missing before GlitchTip startup"
    )
    attach_probe = next(
        task
        for task in tasks
        if task.get("name") == "Probe whether GlitchTip can attach a fresh container to its compose bridge network"
    )
    force_recreate_down = next(
        task for task in tasks if task.get("name") == "Reset the GlitchTip stack before a force recreate"
    )
    network_cleanup = next(
        task for task in tasks if task.get("name") == "Remove stale GlitchTip compose networks after the reset"
    )
    project_cleanup = next(
        task for task in tasks if task.get("name") == "Remove stale GlitchTip project containers before recovery"
    )
    replace_cleanup = next(
        task
        for task in tasks
        if task.get("name") == "Remove stale GlitchTip compose replacement containers before recovery"
    )
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the GlitchTip runtime stack after Docker networking recovery"
    )
    force_recreate_fact = next(
        task for task in tasks if task.get("name") == "Record whether the GlitchTip startup needs a force recreate"
    )
    bootstrap_task = next(
        task
        for task in tasks
        if task.get("name") == "Bootstrap the GlitchTip repo-managed org, team, and project artifacts"
    )
    token_task = next(
        task for task in tasks if task.get("name") == "Generate the local GlitchTip API token when missing"
    )
    runtime_secret_stat_task = next(
        task for task in tasks if task.get("name") == "Inspect the GlitchTip runtime secret files"
    )
    runtime_secret_generate_task = next(
        task for task in tasks if task.get("name") == "Generate missing GlitchTip runtime secrets"
    )
    admin_password_stat_task = next(
        task for task in tasks if task.get("name") == "Inspect the local GlitchTip break-glass admin password"
    )
    admin_password_generate_task = next(
        task
        for task in tasks
        if task.get("name") == "Generate the local GlitchTip break-glass admin password when missing"
    )
    mirror_task = next(
        task for task in tasks if task.get("name") == "Mirror the GlitchTip bootstrap artifacts to the control machine"
    )
    verify_task = next(task for task in tasks if task.get("name") == "Verify the GlitchTip runtime")

    prerequisite_task = next(
        task for task in tasks if task.get("name") == "Check GlitchTip prerequisites on the control machine"
    )
    prerequisite_paths = [item["path"] for item in prerequisite_task["vars"]["common_check_local_secrets_files"]]
    assert "{{ glitchtip_oidc_client_secret_local_file }}" in prerequisite_paths
    assert "{{ glitchtip_keycloak_rollback_client_secret_local_file }}" in prerequisite_paths
    assert openbao_helper["ansible.builtin.include_role"] == {
        "name": "lv3.platform.common",
        "tasks_from": "openbao_compose_env",
    }
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert forward_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "filter", "-S", "DOCKER-FORWARD"]
    assert nat_restore["ansible.builtin.service"]["name"] == "docker"
    assert attach_probe["ansible.builtin.command"]["argv"] == [
        "docker",
        "compose",
        "--file",
        "{{ glitchtip_compose_file }}",
        "run",
        "--rm",
        "--no-deps",
        "valkey",
        "true",
    ]
    assert "--remove-orphans" in force_recreate_down["ansible.builtin.command"]["argv"]
    assert "glitchtip_compose_network_name" in network_cleanup["ansible.builtin.shell"]
    assert "label=com.docker.compose.project=glitchtip" in project_cleanup["ansible.builtin.shell"]
    assert "label=com.docker.compose.replace" in replace_cleanup["ansible.builtin.shell"]
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
    expression = force_recreate_fact["ansible.builtin.set_fact"]["glitchtip_force_recreate"]
    assert "glitchtip_docker_forward_chain.rc" in expression
    assert "common_openbao_compose_env_secret_upsert.changed" in expression
    assert "glitchtip_bootstrap_template.changed" not in expression
    assert "glitchtip_compose_template.changed" in expression
    assert "glitchtip_pull.changed" in expression
    assert "glitchtip_local_port_probe.failed" in expression
    assert "glitchtip_health_probe.status" in expression
    assert "glitchtip_network_attach_probe.rc" in expression
    assert runtime_secret_stat_task["ansible.builtin.stat"]["path"] == "{{ item }}"
    assert runtime_secret_generate_task["ansible.builtin.copy"]["dest"] == "{{ item.item }}"
    assert runtime_secret_generate_task["ansible.builtin.copy"]["content"] == (
        "{{ 'glitchtip' | secret(length=32) }}\n"
    )
    assert runtime_secret_generate_task["ansible.builtin.copy"]["mode"] == "0600"
    assert runtime_secret_generate_task["no_log"] is True
    assert "item.stat.size" in runtime_secret_generate_task["when"]
    assert admin_password_stat_task["delegate_to"] == "localhost"
    assert admin_password_generate_task["ansible.builtin.copy"]["content"] == (
        "{{ 'glitchtip' | secret(length=32) }}\n"
    )
    assert admin_password_generate_task["ansible.builtin.copy"]["mode"] == "0600"
    assert admin_password_generate_task["delegate_to"] == "localhost"
    assert admin_password_generate_task["no_log"] is True
    assert "glitchtip_admin_password_local_state.stat.size" in admin_password_generate_task["when"]
    assert "python3 -c 'import secrets; print(secrets.token_hex(32))'" in token_task["ansible.builtin.shell"]
    render_bootstrap_task = next(
        task
        for task in bootstrap_task["block"]
        if task.get("name") == "Render the temporary GlitchTip bootstrap script"
    )
    execute_bootstrap_task = next(
        task
        for task in bootstrap_task["block"]
        if task.get("name") == "Execute the temporary GlitchTip bootstrap script"
    )
    payload_task = next(
        task for task in bootstrap_task["block"] if task.get("name") == "Record the GlitchTip bootstrap payload"
    )
    cleanup_task = next(
        task
        for task in bootstrap_task["always"]
        if task.get("name") == "Remove the plaintext GlitchTip bootstrap script"
    )
    assert render_bootstrap_task["ansible.builtin.template"]["mode"] == "0600"
    assert (
        "docker exec -i {{ glitchtip_container_name }} python manage.py shell < {{ glitchtip_bootstrap_script_file }}"
        in execute_bootstrap_task["ansible.builtin.shell"]
    )
    assert (
        "glitchtip_bootstrap_run.stdout_lines"
        in payload_task["ansible.builtin.set_fact"]["glitchtip_bootstrap_payload"]
    )
    assert "| last" in payload_task["ansible.builtin.set_fact"]["glitchtip_bootstrap_payload"]
    assert cleanup_task["ansible.builtin.file"] == {
        "path": "{{ glitchtip_bootstrap_script_file }}",
        "state": "absent",
    }
    assert bootstrap_task["no_log"] is True
    destinations = [item["dest"] for item in mirror_task["loop"]]
    assert "{{ glitchtip_projects_local_file }}" in destinations
    assert "{{ glitchtip_mail_gateway_dsn_local_file }}" in destinations
    assert "{{ glitchtip_windmill_jobs_dsn_local_file }}" in destinations
    assert "{{ glitchtip_platform_findings_event_url_local_file }}" in destinations
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_glitchtip_publish_tasks_verify_public_settings_and_smoke_script() -> None:
    publish_tasks = load_yaml(ROLE_PUBLISH)
    verify_tasks = load_yaml(ROLE_PUBLISH_VERIFY)

    orchestration_task = next(
        task
        for task in publish_tasks
        if task.get("name") == "Verify the GlitchTip public surface with a controller-local quiet-window retry"
    )
    quiet_hosts_task = next(
        task
        for task in publish_tasks
        if task.get("name") == "Select controller-local quiet-window hosts for GlitchTip publication"
    )
    quiet_task = orchestration_task["block"][0]
    retry_quiet_task = orchestration_task["rescue"][0]
    verify_include_task = orchestration_task["block"][1]
    retry_verify_task = orchestration_task["rescue"][1]

    health_task = next(
        task for task in verify_tasks if task.get("name") == "Wait for the GlitchTip public health endpoint"
    )
    auth_config_task = next(
        task for task in verify_tasks if task.get("name") == "Read the GlitchTip public auth config document"
    )
    frontend_settings_task = next(
        task for task in verify_tasks if task.get("name") == "Read the GlitchTip frontend settings document"
    )
    provider_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Record the GlitchTip public selected OIDC provider metadata"
    )
    assert_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Assert the GlitchTip public auth config advertises the selected OIDC issuer"
    )
    frontend_assert_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Assert the GlitchTip frontend advertises selected and rollback login providers"
    )
    oidc_smoke_task = next(
        task
        for task in verify_tasks
        if task.get("name") == "Run the GlitchTip headless OIDC redirect smoke verification"
    )
    event_smoke_task = next(
        task for task in verify_tasks if task.get("name") == "Run the GlitchTip event smoke verification"
    )

    quiet_command = quiet_task["ansible.builtin.command"]
    retry_quiet_command = retry_quiet_task["ansible.builtin.command"]
    quiet_hosts_expression = quiet_hosts_task["ansible.builtin.set_fact"]["glitchtip_publication_quiet_hosts"]
    assert "docker-runtime" in quiet_hosts_expression
    assert "docker-runtime" in quiet_hosts_expression
    assert "nginx-staging" in quiet_hosts_expression
    assert "nginx" in quiet_hosts_expression
    assert "python3 {{ inventory_dir }}/../scripts/await_ansible_quiet.py" in quiet_command
    assert "python3 {{ inventory_dir }}/../scripts/await_ansible_quiet.py" in retry_quiet_command
    assert "--quiet-seconds 30" in quiet_command
    assert "--poll-seconds 5" in quiet_command
    assert "--host {{ host }}" in quiet_command
    assert "--host {{ host }}" in retry_quiet_command
    assert "--label glitchtip-publication-retry" in retry_quiet_command
    assert verify_include_task["ansible.builtin.include_tasks"] == "publish_verify.yml"
    assert retry_verify_task["ansible.builtin.include_tasks"] == "publish_verify.yml"
    assert health_task["ansible.builtin.uri"]["url"] == "{{ glitchtip_public_base_url }}/api/0/internal/health/"
    assert (
        auth_config_task["ansible.builtin.uri"]["url"] == "{{ glitchtip_public_base_url }}/_allauth/browser/v1/config"
    )
    assert frontend_settings_task["ansible.builtin.uri"]["url"] == "{{ glitchtip_public_base_url }}/api/settings/"
    provider_expression = provider_task["ansible.builtin.set_fact"]["glitchtip_publish_oidc_provider"]
    assert "glitchtip_publish_auth_config.json.data.socialaccount.providers" in provider_expression
    assert "glitchtip_oidc_provider_id" in provider_expression
    frontend_selected_expression = provider_task["ansible.builtin.set_fact"][
        "glitchtip_publish_frontend_selected_provider"
    ]
    frontend_rollback_expression = provider_task["ansible.builtin.set_fact"][
        "glitchtip_publish_frontend_rollback_provider"
    ]
    assert "glitchtip_publish_frontend_settings.json.socialApps" in frontend_selected_expression
    assert "glitchtip_keycloak_rollback_provider_id" in frontend_rollback_expression
    assert assert_task["ansible.builtin.assert"]["that"][1] == (
        "glitchtip_publish_oidc_provider.client_id == glitchtip_oidc_client_id"
    )
    assert "glitchtip_oidc_discovery_url" in assert_task["ansible.builtin.assert"]["that"][2]
    frontend_assertions = frontend_assert_task["ansible.builtin.assert"]["that"]
    assert "glitchtip_publish_frontend_selected_provider != {}" in frontend_assertions
    assert "glitchtip_publish_frontend_rollback_provider != {}" in frontend_assertions
    assert "glitchtip_publish_frontend_selected_provider.client_id == glitchtip_oidc_client_id" in frontend_assertions
    assert "glitchtip_publish_frontend_selected_provider.authorize_url | length > 0" in frontend_assertions
    assert (
        "glitchtip_publish_frontend_rollback_provider.client_id == glitchtip_keycloak_rollback_client_id"
        in frontend_assertions
    )
    assert "glitchtip_publish_frontend_rollback_provider.authorize_url | length > 0" in frontend_assertions
    assert oidc_smoke_task["ansible.builtin.command"]["argv"][:2] == [
        "python3",
        "{{ inventory_dir }}/../scripts/glitchtip_oidc_smoke.py",
    ]
    assert "--provider-id" in oidc_smoke_task["ansible.builtin.command"]["argv"]
    assert "--issuer-url" in oidc_smoke_task["ansible.builtin.command"]["argv"]
    assert "--client-secret-file" in oidc_smoke_task["ansible.builtin.command"]["argv"]
    secret_argument_index = oidc_smoke_task["ansible.builtin.command"]["argv"].index("--client-secret-file")
    assert oidc_smoke_task["ansible.builtin.command"]["argv"][secret_argument_index + 1] == (
        "{{ glitchtip_oidc_client_secret_local_file }}"
    )
    assert "--expected-client-id" in oidc_smoke_task["ansible.builtin.command"]["argv"]
    assert event_smoke_task["ansible.builtin.command"]["argv"][:2] == [
        "python3",
        "{{ inventory_dir }}/../scripts/glitchtip_event_smoke.py",
    ]
    assert event_smoke_task["ansible.builtin.command"]["argv"][8:12] == [
        "--dsn-file",
        "{{ glitchtip_platform_findings_event_url_local_file }}",
        "--timeout-seconds",
        "300",
    ]
    assert event_smoke_task["ansible.builtin.command"]["argv"][-2:] == [
        "--request-timeout-seconds",
        "60",
    ]


def test_glitchtip_runtime_templates_render_public_oidc_and_mail_settings() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    ctmpl_template = CTMPL_TEMPLATE.read_text(encoding="utf-8")
    bootstrap_template = BOOTSTRAP_TEMPLATE.read_text(encoding="utf-8")
    tasks = load_yaml(ROLE_TASKS)

    assert "container_name: {{ glitchtip_container_name }}" in compose_template
    assert "{% from 'compose_macros.j2' import hairpin_hosts" in compose_template
    assert "{{ hairpin_hosts() }}" in compose_template
    assert '- "{{ ansible_host }}:{{ glitchtip_internal_port }}:8000"' in compose_template
    assert '- "127.0.0.1:{{ glitchtip_internal_port }}:8000"' in compose_template
    assert "./bin/run-all-in-one.sh" in compose_template
    assert "/api/0/internal/health/" in compose_template
    assert not any(task.get("name") == "Render the GlitchTip environment file" for task in tasks)
    assert not (CTMPL_TEMPLATE.parent / "glitchtip.env.j2").exists()
    assert '[[ with secret "kv/data/{{ glitchtip_openbao_secret_path }}" ]]' in ctmpl_template
    assert 'EMAIL_URL=[[ with secret "kv/data/{{ glitchtip_openbao_secret_path }}" ]]' in ctmpl_template
    assert "OrganizationUser" in bootstrap_template
    assert "OrganizationUser.objects.filter(organization=org, user=user).first()" in bootstrap_template
    assert "OrganizationSocialApp.objects.get_or_create" in bootstrap_template
    assert "OIDC_PROVIDER_ID = {{ glitchtip_oidc_provider_id | to_json }}" in bootstrap_template
    assert (
        "KEYCLOAK_ROLLBACK_PROVIDER_ID = {{ glitchtip_keycloak_rollback_provider_id | to_json }}" in bootstrap_template
    )
    assert "client_secret=KEYCLOAK_ROLLBACK_CLIENT_SECRET" in bootstrap_template
    assert '"rollback_social_app": {' in bootstrap_template
    assert "SocialApp.objects.select_for_update()" in bootstrap_template
    assert "duplicate.delete()" in bootstrap_template
    assert (
        "OIDC_SERVER_URL = {{ glitchtip_oidc_issuer_url | regex_replace('/+$', '') | to_json }}" in bootstrap_template
    )
    assert "django.contrib.sites.models" not in bootstrap_template
    assert "app.sites.add" not in bootstrap_template
    assert "RecipientType.GENERAL_WEBHOOK" in bootstrap_template
    assert "RecipientType.NTFY" in bootstrap_template


def test_glitchtip_role_argument_specs_and_postgres_tasks_cover_runtime_contracts() -> None:
    specs = load_yaml(ROLE_META)
    postgres_specs = load_yaml(POSTGRES_META)
    postgres_tasks = load_yaml(POSTGRES_TASKS)
    options = specs["argument_specs"]["main"]["options"]
    postgres_options = postgres_specs["argument_specs"]["main"]["options"]
    names = [task["name"] for task in postgres_tasks]

    assert options["glitchtip_internal_port"]["type"] == "int"
    assert options["glitchtip_public_base_url"]["type"] == "str"
    assert options["glitchtip_compose_network_name"]["type"] == "str"
    assert options["glitchtip_database_password_local_file"]["type"] == "path"
    assert options["glitchtip_oidc_client_secret_local_file"]["type"] == "path"
    assert options["glitchtip_keycloak_rollback_client_secret_local_file"]["type"] == "path"
    assert options["glitchtip_oidc_provider_id"]["type"] == "str"
    assert options["glitchtip_oidc_client_id"]["type"] == "str"
    assert options["glitchtip_oidc_issuer_url"]["type"] == "str"
    assert options["glitchtip_oidc_discovery_url"]["type"] == "str"
    assert options["glitchtip_oidc_frontend_callback_url"]["type"] == "str"
    assert options["glitchtip_keycloak_rollback_provider"]["type"] == "str"
    assert options["glitchtip_keycloak_rollback_provider_id"]["type"] == "str"
    assert options["glitchtip_keycloak_rollback_provider_name"]["type"] == "str"
    assert options["glitchtip_keycloak_rollback_client_id"]["type"] == "str"
    assert options["glitchtip_keycloak_rollback_issuer_url"]["type"] == "str"
    assert options["glitchtip_keycloak_rollback_discovery_url"]["type"] == "str"
    assert options["glitchtip_api_token_local_file"]["type"] == "path"
    assert postgres_options["glitchtip_postgres_secret_dir"]["type"] == "path"
    assert postgres_options["glitchtip_postgres_password_file"]["type"] == "path"
    assert names == ["Provision the glitchtip database via the shared postgres_client role"]
    postgres_task = postgres_tasks[0]
    assert postgres_task["ansible.builtin.include_role"]["name"] == "lv3.platform.postgres_client"
    assert postgres_task["vars"]["postgres_client_service"] == "{{ glitchtip_database_name }}"


def test_glitchtip_catalog_and_integration_select_authentik_with_keycloak_rollback() -> None:
    contract = load_yaml(INTEGRATION_CONTRACT)
    catalog_bundle = load_yaml(SERVICE_CATALOG)
    catalog = catalog_bundle["service"]

    assert contract["consumer"] == "glitchtip_runtime"
    assert contract["provider"] == "authentik_runtime"
    assert contract["integration_type"] == "oidc"
    assert contract["connection"]["provider_id"] == "authentik"
    assert contract["connection"]["client_id"] == "glitchtip"
    assert contract["connection"]["issuer_url_var"] == "glitchtip_oidc_issuer_url"
    assert contract["connection"]["headless_redirect_path"] == ("/_allauth/browser/v1/auth/provider/redirect")
    secret_purposes = {entry["purpose"] for entry in contract["secrets"]}
    assert secret_purposes == {"selected_oidc_client_secret", "keycloak_per_client_rollback"}
    assert "authentik_glitchtip_client_secret" in catalog["secret_catalog_ids"]
    dependencies = {edge["to"]: edge for edge in catalog_bundle["dependency"]["outbound_edges"]}
    assert "Authentik OIDC" in dependencies["authentik"]["description"]
    assert "rollback" in dependencies["keycloak"]["description"]


def test_glitchtip_oidc_smoke_uses_headless_redirect_without_logging_oauth_state() -> None:
    smoke_script = OIDC_SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert "/_allauth/browser/v1/auth/provider/redirect" in smoke_script
    assert '"process": "login"' in smoke_script
    assert 'find_cookie_value(cookie_jar, "csrftoken")' in smoke_script
    assert "NoRedirectHandler" in smoke_script
    assert 'parsed._replace(query="", fragment="")' in smoke_script
    assert '"state":' not in smoke_script
