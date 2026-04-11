from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "tasks" / "main.yml"
VERIFY_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "tasks" / "verify.yml"
PUBLISH_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "tasks" / "publish.yml"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "templates" / "sftpgo.env.j2"
ENV_CTEMPLATE_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "templates" / "sftpgo.env.ctmpl.j2"
CONFIG_TEMPLATE_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "templates" / "sftpgo.json.j2"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "sftpgo_runtime" / "templates" / "docker-compose.yml.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_controller_publication_and_local_artifacts() -> None:
    defaults = load_yaml(DEFAULTS_PATH)
    assert (
        defaults["sftpgo_service_topology"]
        == "{{ hostvars['proxmox-host'].platform_service_topology | service_topology_get('sftpgo') }}"
    )
    assert defaults["sftpgo_public_base_url"] == "https://{{ sftpgo_service_topology.public_hostname }}"
    assert defaults["sftpgo_controller_url"] == "{{ hostvars['proxmox-host'].sftpgo_controller_url }}"
    assert (
        defaults["sftpgo_database_host"]
        == "{{ hostvars[hostvars['proxmox-host'].postgres_ha.initial_primary].ansible_host }}"
    )
    assert defaults["sftpgo_keycloak_client_id"] == "sftpgo"
    assert defaults["sftpgo_api_key_name"] == "lv3-sftpgo-rest-provisioner"
    assert defaults["sftpgo_bootstrap_admin_password_local_file"].endswith(
        "/.local/sftpgo/bootstrap-admin-password.txt"
    )
    assert defaults["sftpgo_smoke_user_private_key_local_file"].endswith("/.local/sftpgo/smoke-user.id_ed25519")
    assert defaults["sftpgo_nats_password_local_file"].endswith("/.local/nats/jetstream-admin-password.txt")
    assert defaults["sftpgo_event_subject"] == "platform.sftpgo.events"


def test_runtime_role_records_openbao_secret_payload_and_force_recreate_inputs() -> None:
    tasks = load_yaml(TASKS_PATH)
    secret_fact = next(task for task in tasks if task.get("name") == "Record the SFTPGo runtime secrets")
    force_recreate_fact = next(
        task for task in tasks if task.get("name") == "Record whether the SFTPGo startup needs a force recreate"
    )
    force_recreate = next(
        task
        for task in tasks
        if task.get("name") == "Force-recreate the SFTPGo runtime stack after Docker networking recovery"
    )

    payload = secret_fact["ansible.builtin.set_fact"]["sftpgo_runtime_secret_payload"]
    assert "SFTPGO_DATA_PROVIDER__PASSWORD" in payload
    assert "SFTPGO_HTTPD__BINDINGS__0__OIDC__CLIENT_SECRET" in payload
    assert "SFTPGO_DEFAULT_ADMIN_PASSWORD" in payload
    assert "NATS_SERVER_URL" in payload
    expression = force_recreate_fact["ansible.builtin.set_fact"]["sftpgo_force_recreate"]
    assert "sftpgo_env_template.changed" in expression
    assert "sftpgo_config_template.changed" in expression
    assert "sftpgo_compose_template.changed" in expression
    assert "sftpgo_pull.changed" in expression
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]


def test_verify_tasks_check_admin_webdav_and_sftp_listeners() -> None:
    verify = load_yaml(VERIFY_PATH)
    admin = next(task for task in verify if task.get("name") == "Verify the SFTPGo local admin health endpoint")
    webdav = next(
        task for task in verify if task.get("name") == "Verify the SFTPGo local WebDAV listener requires authentication"
    )
    sftp = next(task for task in verify if task.get("name") == "Verify the SFTPGo local SFTP port is listening")

    assert admin["ansible.builtin.uri"]["url"] == "{{ sftpgo_local_admin_url }}/healthz"
    assert webdav["ansible.builtin.uri"]["url"] == "{{ sftpgo_local_webdav_url }}/healthz"
    assert webdav["ansible.builtin.uri"]["status_code"] == 401
    assert sftp["ansible.builtin.wait_for"]["port"] == "{{ sftpgo_sftp_port }}"


def test_publish_tasks_bootstrap_api_verify_oidc_and_smoke_transfers() -> None:
    tasks = load_yaml(PUBLISH_PATH)
    bootstrap = next(
        task for task in tasks if task.get("name") == "Bootstrap the SFTPGo admin, API key, and smoke-user contract"
    )
    verify = next(
        task for task in tasks if task.get("name") == "Verify the durable SFTPGo API key and seeded identities"
    )
    oidc = next(task for task in tasks if task.get("name") == "Verify the SFTPGo admin OIDC redirect path")
    webdav_smoke = next(task for task in tasks if task.get("name") == "Verify the public SFTPGo WebDAV smoke transfer")
    sftp_smoke = next(task for task in tasks if task.get("name") == "Verify the public SFTPGo SFTP smoke transfer")

    assert bootstrap["ansible.builtin.command"]["argv"][2:] == [
        "bootstrap",
        "--base-url",
        "{{ sftpgo_controller_url }}",
        "--bootstrap-admin-username",
        "{{ sftpgo_bootstrap_admin_username }}",
        "--bootstrap-admin-password-file",
        "{{ sftpgo_bootstrap_admin_password_local_file }}",
        "--api-key-name",
        "{{ sftpgo_api_key_name }}",
        "--api-key-file",
        "{{ sftpgo_api_key_local_file }}",
        "--oidc-admin-username",
        "{{ sftpgo_oidc_admin_username }}",
        "--oidc-admin-email",
        "{{ sftpgo_oidc_admin_email }}",
        "--oidc-admin-password-file",
        "{{ sftpgo_oidc_admin_password_local_file }}",
        "--smoke-user-username",
        "{{ sftpgo_smoke_user_username }}",
        "--smoke-user-password-file",
        "{{ sftpgo_smoke_user_password_local_file }}",
        "--smoke-user-public-key-file",
        "{{ sftpgo_smoke_user_public_key_local_file }}",
        "--smoke-user-home-dir",
        "{{ sftpgo_smoke_user_home_dir }}",
        "--smoke-user-quota-bytes",
        "{{ sftpgo_smoke_user_quota_bytes | string }}",
        "--smoke-user-quota-files",
        "{{ sftpgo_smoke_user_quota_files | string }}",
        "--report-file",
        "{{ sftpgo_bootstrap_report_local_file }}",
    ]
    assert verify["ansible.builtin.command"]["argv"][2:] == [
        "verify",
        "--base-url",
        "{{ sftpgo_controller_url }}",
        "--api-key-file",
        "{{ sftpgo_api_key_local_file }}",
        "--expected-admin",
        "{{ sftpgo_oidc_admin_username }}",
        "--expected-user",
        "{{ sftpgo_smoke_user_username }}",
    ]
    assert oidc["ansible.builtin.uri"]["url"] == "{{ sftpgo_controller_url }}/web/admin/oidclogin"
    assert oidc["ansible.builtin.uri"]["status_code"] == 302
    assert webdav_smoke["ansible.builtin.command"]["argv"][2:8] == [
        "smoke-webdav",
        "--base-url",
        "{{ sftpgo_public_base_url }}",
        "--username",
        "{{ sftpgo_smoke_user_username }}",
        "--password-file",
    ]
    assert sftp_smoke["ansible.builtin.command"]["argv"][2:10] == [
        "smoke-sftp",
        "--host",
        "{{ sftpgo_service_topology.public_hostname }}",
        "--port",
        "{{ sftpgo_sftp_port | string }}",
        "--username",
        "{{ sftpgo_smoke_user_username }}",
        "--identity-file",
    ]


def test_templates_publish_ports_oidc_and_notifier_plugin() -> None:
    env_template = ENV_TEMPLATE_PATH.read_text()
    env_ctemplate = ENV_CTEMPLATE_PATH.read_text()
    config_template = CONFIG_TEMPLATE_PATH.read_text()
    compose_template = COMPOSE_TEMPLATE_PATH.read_text()

    assert "SFTPGO_DATA_PROVIDER__PASSWORD={{ sftpgo_database_password }}" in env_template
    assert "SFTPGO_HTTPD__BINDINGS__0__OIDC__CLIENT_SECRET={{ sftpgo_keycloak_client_secret }}" in env_template
    assert "[[ .Data.data.SFTPGO_DEFAULT_ADMIN_PASSWORD ]]" in env_ctemplate
    assert '"client_id": "{{ sftpgo_keycloak_client_id }}"' in config_template
    assert '"redirect_base_url": "{{ sftpgo_controller_url }}"' in config_template
    assert '"args": [' in config_template
    assert '"nats://{{ sftpgo_event_subject }}"' in config_template
    assert '"{{ ansible_host }}:{{ sftpgo_sftp_port }}:{{ sftpgo_sftp_port }}"' in compose_template
    assert '"{{ ansible_host }}:{{ sftpgo_webdav_port }}:{{ sftpgo_webdav_port }}"' in compose_template
    assert '"{{ ansible_host }}:{{ sftpgo_admin_port }}:{{ sftpgo_admin_port }}"' in compose_template
    assert "{{ sftpgo_plugin_dir }}:/plugins:ro" in compose_template
