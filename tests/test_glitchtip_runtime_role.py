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
ENV_TEMPLATE = REPO_ROOT / "roles" / "glitchtip_runtime" / "templates" / "glitchtip.env.j2"
CTMPL_TEMPLATE = REPO_ROOT / "roles" / "glitchtip_runtime" / "templates" / "glitchtip.env.ctmpl.j2"
BOOTSTRAP_TEMPLATE = REPO_ROOT / "roles" / "glitchtip_runtime" / "templates" / "bootstrap-glitchtip.py.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_glitchtip_runtime_defaults_reference_service_topology_images_and_local_artifacts() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["glitchtip_service_topology"] == (
        "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('glitchtip') }}"
    )
    assert defaults["glitchtip_internal_port"] == "{{ platform_service_topology | platform_service_port('glitchtip', 'internal') }}"
    assert defaults["glitchtip_internal_base_url"] == "{{ platform_service_topology | platform_service_url('glitchtip', 'internal') }}"
    assert defaults["glitchtip_public_base_url"] == "https://{{ glitchtip_service_topology.public_hostname }}"
    assert defaults["glitchtip_compose_network_name"] == "glitchtip_default"
    assert defaults["glitchtip_image"] == "{{ container_image_catalog.images.glitchtip_runtime.ref }}"
    assert defaults["glitchtip_valkey_image"] == "{{ container_image_catalog.images.glitchtip_valkey_runtime.ref }}"
    assert defaults["glitchtip_database_password_local_file"].endswith("/.local/glitchtip/database-password.txt")
    assert defaults["glitchtip_local_artifact_dir"].endswith("/.local/glitchtip")
    assert defaults["glitchtip_api_token_local_file"] == "{{ glitchtip_local_artifact_dir }}/api-token.txt"
    assert defaults["glitchtip_keycloak_client_secret_local_file"].endswith("/.local/keycloak/glitchtip-client-secret.txt")
    assert defaults["glitchtip_mail_submission_password_local_file"] == (
        "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/server-mailbox-password.txt"
    )
    assert [project["slug"] for project in defaults["glitchtip_bootstrap_projects"]] == [
        "mail-gateway",
        "windmill-jobs",
        "platform-findings",
    ]


def test_glitchtip_runtime_tasks_manage_openbao_bootstrap_and_port_recovery() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    openbao_helper = next(
        task for task in tasks if task.get("name") == "Prepare OpenBao agent runtime secret injection for GlitchTip"
    )
    nat_check = next(task for task in tasks if task.get("name") == "Check whether the Docker nat chain exists before GlitchTip startup")
    forward_check = next(
        task for task in tasks if task.get("name") == "Check whether the Docker forward chain exists before GlitchTip startup"
    )
    nat_restore = next(
        task for task in tasks if task.get("name") == "Restore Docker networking when bridge chains are missing before GlitchTip startup"
    )
    attach_probe = next(
        task for task in tasks if task.get("name") == "Probe whether GlitchTip can attach a fresh container to its compose bridge network"
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
        task for task in tasks if task.get("name") == "Remove stale GlitchTip compose replacement containers before recovery"
    )
    force_recreate = next(
        task for task in tasks if task.get("name") == "Force-recreate the GlitchTip runtime stack after Docker networking recovery"
    )
    force_recreate_fact = next(
        task for task in tasks if task.get("name") == "Record whether the GlitchTip startup needs a force recreate"
    )
    bootstrap_task = next(
        task for task in tasks if task.get("name") == "Bootstrap the GlitchTip repo-managed org, team, and project artifacts"
    )
    payload_task = next(
        task for task in tasks if task.get("name") == "Record the GlitchTip bootstrap payload"
    )
    token_task = next(
        task for task in tasks if task.get("name") == "Generate the local GlitchTip API token when missing"
    )
    mirror_task = next(
        task for task in tasks if task.get("name") == "Mirror the GlitchTip bootstrap artifacts to the control machine"
    )
    verify_task = next(task for task in tasks if task.get("name") == "Verify the GlitchTip runtime")

    assert "Fail if the GlitchTip Keycloak client secret is missing locally" in names
    assert openbao_helper["ansible.builtin.include_role"] == {"name": "lv3.platform.common", "tasks_from": "openbao_compose_env"}
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
    assert "glitchtip_env_template.changed" in expression
    assert "glitchtip_bootstrap_template.changed" in expression
    assert "glitchtip_compose_template.changed" in expression
    assert "glitchtip_pull.changed" in expression
    assert "glitchtip_local_port_probe.failed" in expression
    assert "glitchtip_health_probe.status" in expression
    assert "glitchtip_network_attach_probe.rc" in expression
    assert "python3 -c 'import secrets; print(secrets.token_hex(32))'" in token_task["ansible.builtin.shell"]
    assert "docker exec -i {{ glitchtip_container_name }} python manage.py shell < {{ glitchtip_bootstrap_script_file }}" in bootstrap_task["ansible.builtin.shell"]
    assert "glitchtip_bootstrap_run.stdout_lines" in payload_task["ansible.builtin.set_fact"]["glitchtip_bootstrap_payload"]
    assert "| last" in payload_task["ansible.builtin.set_fact"]["glitchtip_bootstrap_payload"]
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
        task for task in publish_tasks if task.get("name") == "Verify the GlitchTip public surface with a controller-local quiet-window retry"
    )
    quiet_hosts_task = next(
        task for task in publish_tasks if task.get("name") == "Select controller-local quiet-window hosts for GlitchTip publication"
    )
    quiet_task = orchestration_task["block"][0]
    retry_quiet_task = orchestration_task["rescue"][0]
    verify_include_task = orchestration_task["block"][1]
    retry_verify_task = orchestration_task["rescue"][1]

    health_task = next(task for task in verify_tasks if task.get("name") == "Wait for the GlitchTip public health endpoint")
    auth_config_task = next(task for task in verify_tasks if task.get("name") == "Read the GlitchTip public auth config document")
    provider_task = next(task for task in verify_tasks if task.get("name") == "Record the GlitchTip public Keycloak OIDC provider metadata")
    assert_task = next(
        task for task in verify_tasks if task.get("name") == "Assert the GlitchTip public auth config advertises the Keycloak OIDC issuer"
    )
    smoke_task = next(task for task in verify_tasks if task.get("name") == "Run the GlitchTip event smoke verification")

    quiet_command = quiet_task["ansible.builtin.command"]
    retry_quiet_command = retry_quiet_task["ansible.builtin.command"]
    quiet_hosts_expression = quiet_hosts_task["ansible.builtin.set_fact"]["glitchtip_publication_quiet_hosts"]
    assert "docker-runtime-staging-lv3" in quiet_hosts_expression
    assert "docker-runtime-lv3" in quiet_hosts_expression
    assert "nginx-staging-lv3" in quiet_hosts_expression
    assert "nginx-lv3" in quiet_hosts_expression
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
    assert auth_config_task["ansible.builtin.uri"]["url"] == "{{ glitchtip_public_base_url }}/_allauth/browser/v1/config"
    provider_expression = provider_task["ansible.builtin.set_fact"]["glitchtip_publish_keycloak_provider"]
    assert "glitchtip_publish_auth_config.json.data.socialaccount.providers" in provider_expression
    assert "glitchtip_keycloak_provider_id" in provider_expression
    assert assert_task["ansible.builtin.assert"]["that"][1] == (
        "glitchtip_publish_keycloak_provider.client_id == glitchtip_keycloak_client_id"
    )
    assert "glitchtip_keycloak_server_url" in assert_task["ansible.builtin.assert"]["that"][2]
    assert ".well-known/openid-configuration" in assert_task["ansible.builtin.assert"]["that"][2]
    assert smoke_task["ansible.builtin.command"]["argv"][:2] == ["python3", "{{ inventory_dir }}/../scripts/glitchtip_event_smoke.py"]
    assert smoke_task["ansible.builtin.command"]["argv"][8:12] == [
        "--dsn-file",
        "{{ glitchtip_platform_findings_event_url_local_file }}",
        "--timeout-seconds",
        "300",
    ]
    assert smoke_task["ansible.builtin.command"]["argv"][-2:] == [
        "--request-timeout-seconds",
        "60",
    ]


def test_glitchtip_runtime_templates_render_public_oidc_and_mail_settings() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE.read_text(encoding="utf-8")
    ctmpl_template = CTMPL_TEMPLATE.read_text(encoding="utf-8")
    bootstrap_template = BOOTSTRAP_TEMPLATE.read_text(encoding="utf-8")

    assert "container_name: {{ glitchtip_container_name }}" in compose_template
    assert '- "{{ ansible_host }}:{{ glitchtip_internal_port }}:8000"' in compose_template
    assert '- "127.0.0.1:{{ glitchtip_internal_port }}:8000"' in compose_template
    assert "./bin/run-all-in-one.sh" in compose_template
    assert "/api/0/internal/health/" in compose_template
    assert "GLITCHTIP_DOMAIN={{ glitchtip_public_base_url }}" in env_template
    assert "EMAIL_URL={{ glitchtip_mail_url_scheme }}://{{ glitchtip_mail_username | urlencode }}:" in env_template
    assert '[[ with secret "kv/data/{{ glitchtip_openbao_secret_path }}" ]]' in ctmpl_template
    assert 'EMAIL_URL=[[ with secret "kv/data/{{ glitchtip_openbao_secret_path }}" ]]' in ctmpl_template
    assert "OrganizationUser" in bootstrap_template
    assert "OrganizationUser.objects.filter(organization=org, user=user).first()" in bootstrap_template
    assert "OrganizationSocialApp.objects.get_or_create" in bootstrap_template
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
    assert options["glitchtip_keycloak_client_secret_local_file"]["type"] == "path"
    assert options["glitchtip_api_token_local_file"]["type"] == "path"
    assert postgres_options["glitchtip_postgres_secret_dir"]["type"] == "path"
    assert postgres_options["glitchtip_postgres_password_file"]["type"] == "path"
    assert "Generate the GlitchTip database password" in names
    assert "Create the GlitchTip role" in names
    assert "Create the GlitchTip database" in names
    assert "Ensure the GlitchTip database owner is correct" in names
