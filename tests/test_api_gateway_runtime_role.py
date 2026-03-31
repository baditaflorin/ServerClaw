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
VERIFY_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "api_gateway_runtime"
    / "tasks"
    / "verify.yml"
)
SYNC_TREE_TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "api_gateway_runtime"
    / "tasks"
    / "sync_tree.yml"
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
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_api_gateway_role_uses_internal_keycloak_jwks_url() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")

    assert "api_gateway_keycloak_internal_base_url" in defaults
    assert "http://127.0.0.1:18080" in defaults
    assert "api_gateway_keycloak_verify_base_url: http://127.0.0.1:18080" in defaults
    assert "api_gateway_keycloak_verify_ready_retries: 60" in defaults
    assert "api_gateway_keycloak_verify_ready_delay: 5" in defaults
    assert "api_gateway_keycloak_verify_token_retries: 18" in defaults
    assert "api_gateway_keycloak_verify_token_delay: 5" in defaults
    assert "api_gateway_structured_search_verify_retries: 12" in defaults
    assert "api_gateway_structured_search_verify_delay: 5" in defaults
    assert "api_gateway_network_mode: host" in defaults
    assert "api_gateway_keycloak_docker_network: keycloak_default" in defaults
    assert "/realms/lv3/protocol/openid-connect/certs" in defaults
    assert "api_gateway_nats_url: nats://127.0.0.1:4222" in defaults
    assert "/.local/nats/jetstream-admin-password.txt" in defaults
    assert "api_gateway_ledger_event_types_src" in defaults
    assert "dest: ledger-event-types.yaml" in defaults
    assert "api_gateway_event_taxonomy_src" in defaults
    assert "dest: event-taxonomy.yaml" in defaults
    assert "dest: agent-tool-registry.json" in defaults
    assert "dest: api-publication.json" in defaults
    assert "dest: command-catalog.json" in defaults
    assert "dest: workflow-defaults.yaml" in defaults
    assert "dest: execution-lanes.yaml" in defaults
    assert "api_gateway_runtime_assurance_matrix_src" in defaults
    assert "dest: runtime-assurance-matrix.json" in defaults
    assert "api_gateway_environment_topology_src" in defaults
    assert "dest: environment-topology.json" in defaults
    assert "api_gateway_runtime_packaged_probe_paths" in defaults
    assert "/app/.gitea/workflows/release-bundle.yml" in defaults
    assert "/app/.github/workflows/validate.yml" in defaults
    assert "api_gateway_database_name: windmill" in defaults
    assert "api_gateway_database_user: windmill_admin" in defaults
    assert "api_gateway_windmill_service_topology" in defaults
    assert "api_gateway_windmill_base_url" in defaults
    assert "api_gateway_windmill_service_topology.private_ip" in defaults
    assert "windmill_server_port" in defaults
    assert "rev-parse --path-format=absolute --git-common-dir" in defaults
    assert 'api_gateway_database_password_local_file: "{{ api_gateway_shared_local_root }}/windmill/database-password.txt"' in defaults
    assert "api_gateway_graph_dsn" in defaults
    assert 'api_gateway_world_state_dsn: "{{ api_gateway_graph_dsn }}"' in defaults
    assert "/.local/dify/tools-api-key.txt" in defaults
    assert "api_gateway_dify_tools_api_key_header: X-LV3-Dify-Api-Key" in defaults


def test_api_gateway_compose_mounts_config_into_app_root() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "image: {{ api_gateway_image_name }}:latest" in compose_template
    assert "network_mode: {{ api_gateway_network_mode }}" in compose_template
    assert '- "{{ api_gateway_internal_port }}"' in compose_template
    assert "http://127.0.0.1:{{ api_gateway_internal_port }}/healthz" in compose_template
    assert "{{ api_gateway_config_dir }}:/config:ro" in compose_template
    assert "{{ api_gateway_config_dir }}:/app/config:ro" in compose_template
    assert "build:" not in compose_template
    assert "{{ api_gateway_service_dir }}/receipts:/app/receipts:ro" in compose_template
    assert "LV3_GATEWAY_GRAPH_DSN={{ api_gateway_graph_dsn }}" in env_template
    assert "LV3_GATEWAY_WORLD_STATE_DSN={{ api_gateway_world_state_dsn }}" in env_template
    assert "LV3_DIFY_TOOLS_API_KEY={{ api_gateway_dify_tools_api_key }}" in env_template
    assert "LV3_DIFY_TOOLS_API_KEY_HEADER={{ api_gateway_dify_tools_api_key_header }}" in env_template


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
        / "windmill-runtime.env.j2"
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
        / "windmill-runtime.env.ctmpl.j2"
    ).read_text(encoding="utf-8")

    for text in (runtime_tasks, legacy_template, runtime_template):
        assert "LV3_GRAPH_DSN" in text
        assert "WORLD_STATE_DSN" in text
        assert "LV3_LEDGER_DSN" in text
    assert "Create a controller-local staging path for the Windmill OpenBao agent runtime env template" in runtime_tasks
    assert "Render the Windmill OpenBao agent runtime env template to a controller-local file" in runtime_tasks
    assert "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill-runtime.env.ctmpl.j2" in runtime_tasks
    assert 'common_openbao_compose_env_agent_template_local_file: "{{ windmill_openbao_agent_template_local.path }}"' in runtime_tasks
    assert "Remove the controller-local Windmill OpenBao agent runtime env template staging file" in runtime_tasks


def test_api_gateway_role_packages_shared_platform_helpers() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = TASKS_PATH.read_text(encoding="utf-8")
    verify_tasks = VERIFY_TASKS_PATH.read_text(encoding="utf-8")
    sync_tree_tasks = SYNC_TREE_TASKS_PATH.read_text(encoding="utf-8")
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")

    assert "scripts/maintenance_window_tool.py" in defaults
    assert "scripts/slo_tracking.py" in defaults
    assert "scripts/runtime_assurance.py" in defaults
    assert "api_gateway_tree_sync_specs" in defaults
    assert ".githooks/pre-push" in defaults
    assert ".github/workflows/validate.yml" in defaults
    assert ".pre-commit-config.yaml" in defaults
    assert "README.md" in defaults
    assert "ansible.cfg" in defaults
    assert "workstreams.yaml" in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/gitea-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/collections-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/inventory-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/migrations-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/molecule-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/packer-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/playbooks-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/scripts-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/config-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/docs-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/receipts-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/requirements-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/roles-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/tests-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/tofu-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/windmill-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/gitea-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/serverclaw-config-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/serverclaw-skill-packs-script-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/serverclaw-use-case-sync.tar.gz"' in defaults
    assert 'remote_archive: "{{ api_gateway_site_dir }}/serverclaw-runbook-sync.tar.gz"' in defaults
    assert "source: .gitea" in defaults
    assert "source: serverclaw" in defaults
    assert "source: serverclaw_skill_packs.py" in defaults
    assert "source: serverclaw_skills.py" in defaults
    assert "source: serverclaw-skills.md" in defaults
    assert "preserve_destination_root: true" in defaults
    assert "api_gateway_runtime_config_probe_path: /app/config/ledger-event-types.yaml" in defaults
    assert "Sync the staged repo trees required by the API gateway runtime" in tasks
    assert "Ensure nested parent directories for managed API gateway source files exist" in tasks
    assert "ansible.builtin.include_tasks: sync_tree.yml" in tasks
    assert "Inspect the built API gateway image id" in tasks
    assert "Inspect the running API gateway container image id" in tasks
    assert "api_gateway_container_image_drifted" in tasks
    assert "Derive a per-run guest archive path for {{ api_gateway_tree_sync_spec.name }}" in sync_tree_tasks
    assert "api_gateway_tree_remote_archive_path" in sync_tree_tasks
    assert "(api_gateway_tree_archive_local.path | basename)" in sync_tree_tasks
    assert 'dest: "{{ api_gateway_tree_remote_archive_path }}"' in sync_tree_tasks
    assert "COPYFILE_DISABLE=1" in sync_tree_tasks
    assert "COPY_EXTENDED_ATTRIBUTES_DISABLE=1" in sync_tree_tasks
    assert 'apple_double="{{ api_gateway_tree_sync_spec.dest_parent }}/._{{ api_gateway_tree_sync_spec.source | basename }}"' in sync_tree_tasks
    assert "api_gateway_tree_remove_destination" in sync_tree_tasks
    assert 'tar --no-same-owner --no-same-permissions \\' in sync_tree_tasks
    assert "--no-same-owner" in sync_tree_tasks
    assert 'export COPYFILE_DISABLE=1' in sync_tree_tasks
    assert 'export COPY_EXTENDED_ATTRIBUTES_DISABLE=1' in sync_tree_tasks
    assert "Render the API gateway build-context ignore file" in tasks
    assert "Remove stale API gateway nested build-context ignore files" in tasks
    assert "{{ api_gateway_service_dir }}/.dockerignore" in tasks
    assert "**/._*" in tasks
    assert "Ensure the API gateway receipts build-context tree exists" not in tasks
    assert "Sync the API gateway receipts build-context tree explicitly" not in tasks
    assert 'src: "{{ api_gateway_repo_root }}/receipts/"' not in tasks
    assert 'dest: "{{ api_gateway_service_dir }}/receipts/"' not in tasks
    assert "Remove stale managed API gateway config bundle entries" in tasks
    assert "ansible.builtin.meta: reset_connection" in tasks
    assert "Build the API gateway image" in tasks
    assert "mktemp -d /tmp/api-gateway-build." in tasks
    assert 'DOCKER_BUILDKIT=0 docker build --pull=false -t "{{ api_gateway_image_name }}:latest"' in tasks
    assert "Check whether the API gateway container sees the runtime config bundle" in tasks
    assert "Check whether the API gateway container sees the packaged runtime probes" in tasks
    assert "Re-check whether the API gateway container sees the packaged runtime probes after startup recovery" in tasks
    assert "Fail when the API gateway runtime still misses required packaged content after recovery" in tasks
    assert "until: api_gateway_runtime_config_probe_after_recovery.rc == 0" in tasks
    assert "until: api_gateway_runtime_packaged_probes_after_recovery.rc == 0" in tasks
    assert "database not open" in tasks
    assert "api_gateway_docker_builder_database_missing" in tasks
    assert "api_gateway_docker_recoverable_start_failure" in tasks
    assert "Restart Docker to restore the container engine before retrying the API gateway start" in tasks
    assert "Retry the API gateway stack start after Docker engine recovery" in tasks
    assert "/v1/platform/runtime-assurance" in verify_tasks
    assert "runtime assurance endpoint returns a report envelope" in verify_tasks
    assert "Check whether the controller-local legacy platform context token exists" in verify_tasks
    assert "Read the controller-local legacy platform context token" in verify_tasks
    assert "Default the Keycloak API gateway verification token request status" in verify_tasks
    assert "Record whether the Keycloak verification token request returned an access token" in verify_tasks
    assert "Mark the Keycloak verification token request as unavailable" in verify_tasks
    assert "Record the API gateway verification bearer token from the legacy platform context" in verify_tasks
    assert "API gateway verification requires either the Keycloak client secret or the" in verify_tasks
    assert "tar --no-same-owner --no-same-permissions" in sync_tree_tasks
    assert "api_gateway_keycloak_retry_after_seconds: 30" in defaults
    assert "Request a Keycloak bearer token for API gateway verification" in verify_tasks
    assert "Wait for the local Keycloak realm discovery endpoint used by API gateway verification" in verify_tasks
    assert "/realms/lv3/.well-known/openid-configuration" in verify_tasks
    assert "api_gateway_keycloak_verify_discovery.json.issuer == api_gateway_keycloak_issuer_url" in verify_tasks
    assert 'retries: "{{ api_gateway_keycloak_verify_ready_retries }}"' in verify_tasks
    assert 'delay: "{{ api_gateway_keycloak_verify_ready_delay }}"' in verify_tasks
    assert 'retries: "{{ api_gateway_keycloak_verify_token_retries }}"' in verify_tasks
    assert 'delay: "{{ api_gateway_keycloak_verify_token_delay }}"' in verify_tasks
    assert "until: api_gateway_verify_token_response.status == 200" in verify_tasks
    assert 'retries: "{{ api_gateway_structured_search_verify_retries }}"' in verify_tasks
    assert 'delay: "{{ api_gateway_structured_search_verify_delay }}"' in verify_tasks
    assert "until: api_gateway_structured_search_check.status == 200" in verify_tasks
    assert "{{ api_gateway_service_dir }}/.githooks" in tasks
    assert "COPY Makefile ./Makefile" in tasks
    assert "COPY .githooks ./.githooks" in tasks
    assert "COPY .gitea ./.gitea" in tasks
    assert "COPY .github ./.github" in tasks
    assert "COPY .pre-commit-config.yaml ./.pre-commit-config.yaml" in tasks
    assert "COPY README.md ./README.md" in tasks
    assert "COPY ansible.cfg ./ansible.cfg" in tasks
    assert "COPY maintenance_window_tool.py ./maintenance_window_tool.py" in tasks
    assert "COPY slo_tracking.py ./slo_tracking.py" in tasks
    assert "COPY runtime_assurance.py ./runtime_assurance.py" in tasks
    assert "COPY collections ./collections" in tasks
    assert "COPY docs ./docs" in tasks
    assert "COPY inventory ./inventory" in tasks
    assert "COPY migrations ./migrations" in tasks
    assert "COPY molecule ./molecule" in tasks
    assert "COPY packer ./packer" in tasks
    assert "COPY playbooks ./playbooks" in tasks
    assert "COPY receipts ./receipts" in tasks
    assert "COPY requirements ./requirements" in tasks
    assert "COPY roles ./roles" in tasks
    assert "COPY scripts ./scripts" in tasks
    assert "COPY tests ./tests" in tasks
    assert "COPY tofu ./tofu" in tasks
    assert "COPY versions ./versions" in tasks
    assert "COPY windmill ./windmill" in tasks
    assert "COPY workstreams.yaml ./workstreams.yaml" in tasks
    assert "--build" not in tasks
    assert 'DOCKER_BUILDKIT: "0"' in tasks
    assert 'COMPOSE_DOCKER_CLI_BUILD: "0"' in tasks
    assert "psycopg[binary]==" in requirements


def test_converge_api_gateway_passes_worktree_repo_root() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")

    assert "converge-api-gateway:" in makefile
    assert "-e api_gateway_repo_root=$(REPO_ROOT)" in makefile


def test_api_gateway_role_syncs_the_typesense_platform_catalog() -> None:
    defaults = DEFAULTS_PATH.read_text(encoding="utf-8")
    tasks = TASKS_PATH.read_text(encoding="utf-8")
    verify_tasks = VERIFY_TASKS_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "api_gateway_typesense_service_topology" in defaults
    assert "api_gateway_typesense_controller_url" in defaults
    assert "platform_service_topology | service_topology_get('typesense')" in defaults
    assert "hostvars['proxmox_florin'].typesense_host_proxy_port" in defaults
    assert "api_gateway_typesense_base_url: http://127.0.0.1:8108" in defaults
    assert "api_gateway_typesense_collection: platform-services" in defaults
    assert "api_gateway_typesense_api_key_local_file" in defaults
    assert "api_gateway_typesense_sync_script" in defaults
    assert "Resolve the API gateway structured-search Typesense connection settings" in tasks
    assert "api_gateway_resolved_typesense_base_url" in tasks
    assert "api_gateway_resolved_typesense_api_key" in tasks
    assert "Assert the API gateway structured-search Typesense connection settings resolved" in tasks
    assert "Check whether the controller-local Typesense API key exists" in tasks
    assert "Wait for the controller-visible Typesense health endpoint" in tasks
    assert "Sync the Typesense platform-services collection from the service catalog" in tasks
    assert "register: api_gateway_env_template" in tasks
    assert "or api_gateway_env_template.changed" in tasks
    assert "--typesense-url" in tasks
    assert "LV3_GATEWAY_TYPESENSE_BASE_URL={{ api_gateway_resolved_typesense_base_url }}" in env_template
    assert "LV3_GATEWAY_TYPESENSE_API_KEY={{ api_gateway_resolved_typesense_api_key }}" in env_template
    assert "/v1/platform/search/structured?q=api&collection={{ api_gateway_typesense_collection | urlencode }}" in verify_tasks
    assert "Assert the structured search endpoint returns Typesense-backed platform catalog results" in verify_tasks
