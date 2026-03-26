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


def test_api_gateway_role_uses_internal_keycloak_jwks_url() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "api_gateway_keycloak_internal_base_url" in defaults
    assert "http://keycloak:8080" in defaults
    assert "api_gateway_keycloak_verify_base_url: http://127.0.0.1:18080" in defaults
    assert "api_gateway_keycloak_docker_network: keycloak_default" in defaults
    assert "/realms/lv3/protocol/openid-connect/certs" in defaults
    assert "api_gateway_ledger_event_types_src" in defaults
    assert "dest: ledger-event-types.yaml" in defaults
    assert "api_gateway_event_taxonomy_src" in defaults
    assert "dest: event-taxonomy.yaml" in defaults


def test_api_gateway_compose_mounts_config_into_app_root() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "{{ api_gateway_config_dir }}:/config:ro" in compose_template
    assert "{{ api_gateway_config_dir }}:/app/config:ro" in compose_template


def test_api_gateway_role_packages_shared_platform_helpers() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = TASKS_PATH.read_text(encoding="utf-8")

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
