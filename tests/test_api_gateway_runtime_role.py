from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "api_gateway_runtime"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "api_gateway_runtime"
    / "tasks"
    / "main.yml"
)
COMPOSE_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "api_gateway_runtime"
    / "templates"
    / "docker-compose.yml.j2"
)
ENV_TEMPLATE_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "api_gateway_runtime"
    / "templates"
    / "api-gateway.env.j2"
)
REQUIREMENTS_PATH = REPO_ROOT / "requirements" / "api-gateway.txt"


def test_api_gateway_role_uses_internal_keycloak_jwks_url() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "api_gateway_keycloak_internal_base_url" in defaults
    assert "http://127.0.0.1:18080" in defaults
    assert "api_gateway_keycloak_verify_base_url: http://127.0.0.1:18080" in defaults
    assert "api_gateway_network_mode: host" in defaults
    assert "api_gateway_keycloak_docker_network: keycloak_default" in defaults
    assert "/realms/lv3/protocol/openid-connect/certs" in defaults
    assert "api_gateway_nats_url: nats://127.0.0.1:4222" in defaults
    assert "/.local/nats/jetstream-admin-password.txt" in defaults
    assert "api_gateway_ledger_event_types_src" in defaults
    assert "dest: ledger-event-types.yaml" in defaults
    assert "api_gateway_event_taxonomy_src" in defaults
    assert "dest: event-taxonomy.yaml" in defaults
    assert "api_gateway_database_name: windmill" in defaults
    assert "api_gateway_database_user: windmill_admin" in defaults
    assert "rev-parse --path-format=absolute --git-common-dir" in defaults
    assert 'api_gateway_database_password_local_file: "{{ api_gateway_shared_local_root }}/windmill/database-password.txt"' in defaults
    assert "api_gateway_graph_dsn" in defaults
    assert 'api_gateway_world_state_dsn: "{{ api_gateway_graph_dsn }}"' in defaults


def test_api_gateway_compose_mounts_config_into_app_root() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "network_mode: {{ api_gateway_network_mode }}" in compose_template
    assert '- "{{ api_gateway_internal_port }}"' in compose_template
    assert "http://127.0.0.1:{{ api_gateway_internal_port }}/healthz" in compose_template
    assert "{{ api_gateway_config_dir }}:/config:ro" in compose_template
    assert "{{ api_gateway_config_dir }}:/app/config:ro" in compose_template
    assert "LV3_GATEWAY_GRAPH_DSN={{ api_gateway_graph_dsn }}" in env_template
    assert "LV3_GATEWAY_WORLD_STATE_DSN={{ api_gateway_world_state_dsn }}" in env_template


def test_windmill_runtime_templates_export_graph_world_state_and_ledger_dsns() -> None:
    runtime_tasks = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "windmill_runtime"
        / "tasks"
        / "main.yml"
    ).read_text(encoding="utf-8")
    legacy_template = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "windmill_runtime"
        / "templates"
        / "windmill.env.j2"
    ).read_text(encoding="utf-8")
    runtime_template = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "windmill_runtime"
        / "templates"
        / "windmill.env.ctmpl.j2"
    ).read_text(encoding="utf-8")

    for text in (runtime_tasks, legacy_template, runtime_template):
        assert "LV3_GRAPH_DSN" in text
        assert "WORLD_STATE_DSN" in text
        assert "LV3_LEDGER_DSN" in text
    assert "Create a controller-local staging path for the Windmill OpenBao agent runtime env template" in runtime_tasks
    assert "Render the Windmill OpenBao agent runtime env template to a controller-local file" in runtime_tasks
    assert "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill.env.ctmpl.j2" in runtime_tasks
    assert 'common_openbao_compose_env_agent_template_local_file: "{{ windmill_openbao_agent_template_local.path }}"' in runtime_tasks
    assert "Remove the controller-local Windmill OpenBao agent runtime env template staging file" in runtime_tasks


def test_api_gateway_role_packages_shared_platform_helpers() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = TASKS_PATH.read_text(encoding="utf-8")
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")

    assert "scripts/maintenance_window_tool.py" in defaults
    assert "scripts/slo_tracking.py" in defaults
    assert "api_gateway_tree_sync_specs" in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/scripts-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/config-sync.tar.gz"' in defaults
    assert "preserve_destination_root: true" in defaults
    assert "api_gateway_runtime_config_probe_path: /app/config/ledger-event-types.yaml" in defaults
    assert "Sync the staged repo trees required by the API gateway runtime" in tasks
    assert "ansible.builtin.include_tasks: sync_tree.yml" in tasks
    assert "ansible.builtin.meta: reset_connection" in tasks
    assert "Check whether the API gateway container sees the runtime config bundle" in tasks
    assert "COPY maintenance_window_tool.py ./maintenance_window_tool.py" in tasks
    assert "COPY slo_tracking.py ./slo_tracking.py" in tasks
    assert "COPY scripts ./scripts" in tasks
    assert "psycopg[binary]==" in requirements
