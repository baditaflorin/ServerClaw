from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

ROLE_RUNTIME_PATHS = {
    "windmill_runtime": "/run/lv3-secrets/windmill/runtime.env",
    "keycloak_runtime": "/run/lv3-secrets/keycloak/runtime.env",
    "mattermost_runtime": "/run/lv3-secrets/mattermost/runtime.env",
    "matrix_synapse_runtime": "/run/lv3-secrets/matrix-synapse/runtime.env",
    "netbox_runtime": "/run/lv3-secrets/netbox/runtime.env",
    "plane_runtime": "/run/lv3-secrets/plane/runtime.env",
    "rag_context_runtime": "/run/lv3-secrets/platform-context/runtime.env",
}


def test_common_openbao_agent_helper_exists() -> None:
    helper = (REPO_ROOT / "roles" / "common" / "tasks" / "openbao_compose_env.yml").read_text()
    template = (REPO_ROOT / "roles" / "common" / "templates" / "openbao-agent.hcl.j2").read_text()
    assert "kv/data/" in helper
    assert 'static_secret_render_interval = "5m"' in template
    assert "{{ common_openbao_compose_env_agent_template_file | basename }}" in template
    assert 'destination          = "{{ common_openbao_compose_env_env_file }}"' in template
    assert "Render the bootstrap runtime env file from the managed secret payload" in helper
    assert "common_openbao_compose_env_secret_payload | dictsort" in helper
    assert "register: common_openbao_compose_env_approle_upsert" in helper
    assert "until: common_openbao_compose_env_approle_upsert.status == 204" in helper
    assert "register: common_openbao_compose_env_unsealed_status" in helper
    assert "not (common_openbao_compose_env_unsealed_status.json.sealed | bool)" in helper


def test_validate_repo_checks_for_unexpected_env_files() -> None:
    validate_script = (REPO_ROOT / "scripts" / "validate_repo.sh").read_text()
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert "compose-runtime-envs" in validate_script
    assert "validate_compose_runtime_envs" in validate_script
    assert "validate-compose-runtime-envs" in makefile


def test_migrated_role_defaults_use_tmpfs_runtime_env_paths() -> None:
    for role_name, expected_path in ROLE_RUNTIME_PATHS.items():
        defaults_text = (REPO_ROOT / "roles" / role_name / "defaults" / "main.yml").read_text()
        assert expected_path.endswith("/runtime.env")
        assert "runtime.env" in defaults_text
        assert expected_path in defaults_text or "{{ compose_runtime_secret_root }}" in defaults_text


def test_migrated_role_tasks_no_longer_shell_out_with_env_file_flag() -> None:
    for role_name in ROLE_RUNTIME_PATHS:
        tasks_text = (REPO_ROOT / "roles" / role_name / "tasks" / "main.yml").read_text()
        assert "--env-file" not in tasks_text


def test_runtime_secret_payloads_are_built_in_follow_up_tasks() -> None:
    windmill_defaults = (REPO_ROOT / "roles" / "windmill_runtime" / "defaults" / "main.yml").read_text()
    windmill_tasks = (REPO_ROOT / "roles" / "windmill_runtime" / "tasks" / "main.yml").read_text()
    windmill_env_template = (
        REPO_ROOT / "roles" / "windmill_runtime" / "templates" / "windmill-runtime.env.j2"
    ).read_text()
    windmill_template = (
        REPO_ROOT / "roles" / "windmill_runtime" / "templates" / "windmill-runtime.env.ctmpl.j2"
    ).read_text()
    mattermost_tasks = (REPO_ROOT / "roles" / "mattermost_runtime" / "tasks" / "main.yml").read_text()
    assert "windmill_ledger_postgres_user: patroni" in windmill_defaults
    assert "windmill_ledger_dsn" in windmill_defaults
    assert "windmill_ledger_nats_url" in windmill_defaults
    assert "- name: Build the Windmill runtime secret payload" in windmill_tasks
    assert "'LV3_LEDGER_DSN': windmill_ledger_dsn" in windmill_tasks
    assert "'LV3_LEDGER_NATS_URL': windmill_ledger_nats_url" in windmill_tasks
    assert "LV3_LEDGER_DSN={{ windmill_ledger_dsn }}" in windmill_env_template
    assert "LV3_LEDGER_NATS_URL={{ windmill_ledger_nats_url }}" in windmill_env_template
    assert "LV3_LEDGER_DSN" in windmill_template
    assert "LV3_LEDGER_NATS_URL" in windmill_template
    assert "- name: Build Mattermost runtime secret payload" in mattermost_tasks


def test_windmill_runtime_env_file_is_left_to_openbao() -> None:
    windmill_tasks = (REPO_ROOT / "roles" / "windmill_runtime" / "tasks" / "main.yml").read_text()
    assert "src: windmill-runtime.env.j2" not in windmill_tasks
    assert 'dest: "{{ windmill_env_file }}"' not in windmill_tasks


def test_migrated_compose_templates_include_openbao_agent_sidecars() -> None:
    compose_roles = list(ROLE_RUNTIME_PATHS) + ["mail_platform_runtime"]
    for role_name in compose_roles:
        template_text = (REPO_ROOT / "roles" / role_name / "templates" / "docker-compose.yml.j2").read_text()
        assert "openbao-agent:" in template_text
        assert 'user: "0:0"' in template_text
        assert 'BAO_SKIP_DROP_ROOT: "true"' in template_text
        assert "-config=/openbao-agent/agent.hcl" in template_text


def test_langfuse_runtime_pins_redis_volume_permissions_to_redis_uid() -> None:
    defaults_text = (REPO_ROOT / "roles" / "langfuse_runtime" / "defaults" / "main.yml").read_text()
    tasks_text = (REPO_ROOT / "roles" / "langfuse_runtime" / "tasks" / "main.yml").read_text()
    template_text = (REPO_ROOT / "roles" / "langfuse_runtime" / "templates" / "docker-compose.yml.j2").read_text()

    assert 'langfuse_redis_uid: "999"' in defaults_text
    assert 'langfuse_redis_gid: "999"' in defaults_text
    assert 'path: "{{ langfuse_redis_data_dir }}"' in tasks_text
    assert 'owner: "{{ langfuse_redis_uid }}"' in tasks_text
    assert 'group: "{{ langfuse_redis_gid }}"' in tasks_text
    assert 'user: "{{ langfuse_redis_uid }}:{{ langfuse_redis_gid }}"' in template_text


def test_control_plane_recovery_no_longer_requires_windmill_env_file() -> None:
    defaults_text = (REPO_ROOT / "roles" / "control_plane_recovery_store" / "defaults" / "main.yml").read_text()
    assert "opt/windmill/windmill.env" not in defaults_text


def test_control_plane_recovery_uses_dedicated_windmill_backup_dsn() -> None:
    defaults_text = (REPO_ROOT / "roles" / "control_plane_recovery" / "defaults" / "main.yml").read_text()
    script_text = (
        REPO_ROOT / "roles" / "control_plane_recovery" / "templates" / "lv3-control-plane-backup.sh.j2"
    ).read_text()
    service_text = (
        REPO_ROOT / "roles" / "control_plane_recovery" / "templates" / "lv3-control-plane-backup.service.j2"
    ).read_text()
    tasks_text = (REPO_ROOT / "roles" / "control_plane_recovery" / "tasks" / "main.yml").read_text()
    helper_text = (REPO_ROOT / "roles" / "common" / "tasks" / "openbao_systemd_credentials.yml").read_text()
    helper_config_text = (
        REPO_ROOT / "roles" / "common" / "templates" / "openbao-agent-systemd-credentials.hcl.j2"
    ).read_text()
    helper_service_text = (
        REPO_ROOT / "roles" / "common" / "templates" / "openbao-agent-systemd-credentials.service.j2"
    ).read_text()

    assert "patroni-superuser-password.txt" in defaults_text
    assert "control_plane_recovery_windmill_backup_database_dsn" in defaults_text
    assert "openbao-backup-token.json" not in defaults_text
    assert '. "{{ windmill_env_file }}"' not in script_text
    assert "CREDENTIALS_DIRECTORY" in script_text
    assert "postgresql://" not in script_text
    assert "openbao-backup-token.json" not in script_text
    assert "LoadCredential=openbao-token:" in service_text
    assert "LoadCredential=windmill-db-dsn:" in service_text
    assert "openbao_systemd_credentials" in tasks_text
    assert "systemctl\n      - start" in tasks_text
    assert 'command: "{{ control_plane_recovery_runtime_backup_script }}"' not in tasks_text
    assert 'sink "file"' in helper_config_text
    assert "docker run --rm --name" in helper_service_text
    assert "--entrypoint {{ common_openbao_systemd_credentials_container_entrypoint }}" in helper_service_text
    assert "common_openbao_systemd_credentials_secret_path" in helper_text
    assert "register: common_openbao_systemd_credentials_approle_upsert" in helper_text
    assert 'retries: "{{ common_openbao_api_operation_retries }}"' in helper_text
    assert 'delay: "{{ common_openbao_api_operation_delay }}"' in helper_text
    assert "until: common_openbao_systemd_credentials_approle_upsert.status == 204" in helper_text
    assert "register: common_openbao_systemd_credentials_unsealed_status" in helper_text
    assert "not (common_openbao_systemd_credentials_unsealed_status.json.sealed | bool)" in helper_text


def test_mail_gateway_image_includes_telemetry_module() -> None:
    dockerfile_text = (
        REPO_ROOT / "roles" / "mail_platform_runtime" / "templates" / "mail-gateway.Dockerfile.j2"
    ).read_text()
    app_text = (REPO_ROOT / "roles" / "mail_platform_runtime" / "files" / "mail-gateway" / "app.py").read_text()
    assert "from telemetry import configure_telemetry" in app_text
    assert "COPY telemetry.py ./" in dockerfile_text
    assert "uvicorn app:app --host 0.0.0.0 --port 8081" in dockerfile_text


def test_ops_portal_image_includes_publication_contract_helper() -> None:
    dockerfile_text = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "ops_portal_runtime"
        / "templates"
        / "Dockerfile.j2"
    ).read_text()
    app_text = (REPO_ROOT / "scripts" / "ops_portal" / "app.py").read_text()
    assert "from publication_contract import registry_entries" in app_text
    assert "COPY publication_contract.py ./publication_contract.py" in dockerfile_text
    assert "COPY stage_smoke.py ./stage_smoke.py" in dockerfile_text
