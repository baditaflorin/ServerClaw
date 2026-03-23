from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

ROLE_RUNTIME_PATHS = {
    "windmill_runtime": "/run/lv3-secrets/windmill/runtime.env",
    "keycloak_runtime": "/run/lv3-secrets/keycloak/runtime.env",
    "mattermost_runtime": "/run/lv3-secrets/mattermost/runtime.env",
    "open_webui_runtime": "/run/lv3-secrets/open-webui/runtime.env",
    "netbox_runtime": "/run/lv3-secrets/netbox/runtime.env",
    "rag_context_runtime": "/run/lv3-secrets/platform-context/runtime.env",
}


def test_common_openbao_agent_helper_exists() -> None:
    helper = (REPO_ROOT / "roles" / "common" / "tasks" / "openbao_compose_env.yml").read_text()
    template = (REPO_ROOT / "roles" / "common" / "templates" / "openbao-agent.hcl.j2").read_text()
    assert "kv/data/" in helper
    assert 'static_secret_render_interval = "5m"' in template
    assert 'destination          = "{{ common_openbao_compose_env_env_file }}"' in template


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
        assert (
            expected_path in defaults_text
            or "{{ compose_runtime_secret_root }}" in defaults_text
        )


def test_migrated_role_tasks_no_longer_shell_out_with_env_file_flag() -> None:
    for role_name in ROLE_RUNTIME_PATHS:
        tasks_text = (REPO_ROOT / "roles" / role_name / "tasks" / "main.yml").read_text()
        assert "--env-file" not in tasks_text


def test_runtime_secret_payloads_are_built_in_follow_up_tasks() -> None:
    windmill_tasks = (REPO_ROOT / "roles" / "windmill_runtime" / "tasks" / "main.yml").read_text()
    mattermost_tasks = (REPO_ROOT / "roles" / "mattermost_runtime" / "tasks" / "main.yml").read_text()
    assert "- name: Build the Windmill runtime secret payload" in windmill_tasks
    assert "- name: Build Mattermost runtime secret payload" in mattermost_tasks


def test_migrated_compose_templates_include_openbao_agent_sidecars() -> None:
    compose_roles = list(ROLE_RUNTIME_PATHS) + ["mail_platform_runtime"]
    for role_name in compose_roles:
        template_text = (REPO_ROOT / "roles" / role_name / "templates" / "docker-compose.yml.j2").read_text()
        assert "openbao-agent:" in template_text
        assert 'user: "0:0"' in template_text
        assert 'BAO_SKIP_DROP_ROOT: "true"' in template_text
        assert "-config=/openbao-agent/agent.hcl" in template_text


def test_control_plane_recovery_no_longer_requires_windmill_env_file() -> None:
    defaults_text = (REPO_ROOT / "roles" / "control_plane_recovery_store" / "defaults" / "main.yml").read_text()
    assert "opt/windmill/windmill.env" not in defaults_text


def test_mail_gateway_image_includes_telemetry_module() -> None:
    dockerfile_text = (REPO_ROOT / "roles" / "mail_platform_runtime" / "templates" / "mail-gateway.Dockerfile.j2").read_text()
    app_text = (REPO_ROOT / "roles" / "mail_platform_runtime" / "files" / "mail-gateway" / "app.py").read_text()
    assert "from telemetry import configure_telemetry" in app_text
    assert "COPY telemetry.py ./" in dockerfile_text
    assert "uvicorn app:app --host 0.0.0.0 --port 8081" in dockerfile_text
