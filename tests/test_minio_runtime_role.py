from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "roles" / "minio_runtime"
DEFAULTS_PATH = ROLE_ROOT / "defaults" / "main.yml"
TASKS_PATH = ROLE_ROOT / "tasks" / "main.yml"
MIGRATE_SECRET_PATH = ROLE_ROOT / "tasks" / "migrate_secret.yml"
MIGRATE_DATA_OWNER_PATH = ROLE_ROOT / "tasks" / "migrate_data_owner.yml"
VERIFY_PATH = ROLE_ROOT / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = ROLE_ROOT / "templates" / "runtime.env.j2"
ENV_CTEMPLATE = ROLE_ROOT / "templates" / "runtime.env.ctmpl.j2"
MINIO_VARS_PATH = REPO_ROOT / "playbooks" / "vars" / "minio.yml"
MINIO_SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "minio.yml"
PATCHED_MINIO_DOCKERFILE = REPO_ROOT / "build" / "patched-images" / "minio" / "Dockerfile"


def load_yaml(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def test_defaults_define_shared_bucket_contracts() -> None:
    defaults = DEFAULTS_PATH.read_text()
    assert "container_image_catalog.images.minio_runtime.ref" in defaults
    assert "minio_langfuse_bucket_name: langfuse-exports" in defaults
    assert "minio_langfuse_cors_smoke_object_name: __lv3-langfuse-cors-smoke.txt" in defaults
    assert "minio_gitea_bucket_name: gitea-lfs" in defaults
    assert "minio_loki_bucket_name: loki-chunks" in defaults
    assert "minio_platform_context_bucket_name: rag-staging" in defaults
    assert "minio_platform_context_retention_days: 14" in defaults


def test_tasks_install_mc_and_manage_buckets_policies_and_lifecycle() -> None:
    tasks = load_yaml(TASKS_PATH)
    names = {task["name"] for task in tasks}
    tasks_text = TASKS_PATH.read_text()

    assert "Install the pinned MinIO client" in names
    assert "Resolve the managed MinIO consumer contracts" in names
    assert "Resolve the managed MinIO secret migration contracts" in names
    assert "Preserve MinIO secrets across the POSIX-safe directory migration" in names
    assert "Wait for the MinIO admin API to respond via the local client alias" in names
    assert "Reconcile the managed MinIO users with their desired secrets" in names
    assert "Render the MinIO bucket policy documents" in names
    assert "Ensure the RAG staging bucket lifecycle rule exists" in names
    assert "Verify the MinIO runtime" in names
    assert "minio_managed_consumers_resolved" in tasks_text
    assert "admin\n      - info\n      - local" in tasks_text
    assert 'loop: "{{ minio_managed_consumers_resolved }}"' in tasks_text
    assert "admin\n      - user\n      - add\n      - local" in tasks_text
    assert "when: item.rc != 0" not in tasks_text


def test_secret_migration_prefers_existing_remote_authority_without_rotation() -> None:
    defaults = DEFAULTS_PATH.read_text()
    tasks = load_yaml(MIGRATE_SECRET_PATH)
    names = {task["name"] for task in tasks}
    tasks_text = MIGRATE_SECRET_PATH.read_text()

    assert '"/etc/{{ platform_identity.config_prefix }}/minio"' in defaults
    assert "Migrate the legacy MinIO secret for {{ minio_secret_contract.name }}" in names
    assert "Restore the controller-local MinIO secret for {{ minio_secret_contract.name }}" in names
    assert "Generate a new MinIO secret for {{ minio_secret_contract.name }}" in names
    assert "remote_src: true" in tasks_text
    assert "not minio_canonical_secret_stat.stat.exists" in tasks_text
    assert "minio_selected_legacy_secret_file | length > 0" in tasks_text
    assert "minio_controller_secret_stat.stat.isreg | default(false)" in tasks_text
    assert "| secret(length=20)" in tasks_text
    assert "force: false" in tasks_text
    assert "no_log: true" in tasks_text


def test_nonroot_minio_migration_is_single_shot_and_recovers_on_failure() -> None:
    defaults = DEFAULTS_PATH.read_text()
    tasks = load_yaml(MIGRATE_DATA_OWNER_PATH)
    task_names = [task["name"] for task in tasks]
    migration_block = next(
        task
        for task in tasks
        if task.get("name") == "Convert the MinIO data ownership before switching to the non-root user"
    )
    migration_names = [task["name"] for task in migration_block["block"]]
    rollback_names = [task["name"] for task in migration_block["rescue"]]
    dockerfile = PATCHED_MINIO_DOCKERFILE.read_text()
    compose = COMPOSE_TEMPLATE.read_text()

    assert "minio_runtime_uid: 10001" in defaults
    assert "minio_runtime_gid: 10001" in defaults
    assert "minio_data_owner_migration_marker_file" in defaults
    assert task_names[0] == "Check the MinIO data-owner migration marker"
    assert (
        migration_names.index("Stop MinIO for the one-time object ownership conversion")
        < migration_names.index("Transfer existing MinIO objects to the unprivileged UID and GID")
        < migration_names.index("Mark MinIO data-owner migration complete")
    )
    assert "--recursive" in str(migration_block["block"][1]["ansible.builtin.command"]["argv"])
    assert "Restore MinIO availability after migration failure" in rollback_names
    assert "Report the failed MinIO ownership conversion" in rollback_names
    assert "ansible_search_path | default([])" not in MIGRATE_DATA_OWNER_PATH.read_text()
    assert 'user: "{{ minio_runtime_user }}"' in compose
    assert "USER 10001:10001" in dockerfile
    assert "MINIO_ROOT_PASSWORD_FILE" not in dockerfile


def test_playbooks_use_the_registered_minio_openbao_contract() -> None:
    for path in (MINIO_VARS_PATH, MINIO_SERVICE_PLAYBOOK_PATH):
        text = path.read_text()
        assert "minio_openbao_secret_path: services/minio/runtime-env" in text
        assert 'minio_openbao_policy_name: "{{ platform_identity.config_prefix }}-service-minio-runtime"' in text
        assert "minio_openbao_approle_name: minio-runtime" in text
        assert "minio/data/root" not in text


def test_tasks_recover_stale_compose_network_during_startup() -> None:
    tasks = load_yaml(TASKS_PATH)
    start_block = next(
        task
        for task in tasks
        if task.get("name") == "Start the MinIO runtime and recover stale compose-network or task-state failures"
    )
    rescue_fact = next(
        task
        for task in start_block["rescue"]
        if task["name"] == "Flag stale MinIO compose-network failures during startup"
    )
    unexpected_failure = next(
        task for task in start_block["rescue"] if task["name"] == "Surface unexpected MinIO startup failures"
    )
    cleanup_task = next(
        task
        for task in start_block["rescue"]
        if task["name"] == "Force-remove stale MinIO containers after task-state startup failure"
    )
    reset_task = next(
        task
        for task in start_block["rescue"]
        if task["name"] == "Reset stale MinIO compose resources after startup failure"
    )
    retry_task = next(
        task for task in start_block["rescue"] if task["name"] == "Retry MinIO startup after compose-network recovery"
    )
    rescue_names = [task["name"] for task in start_block["rescue"]]

    assert "Flag stale MinIO compose-network failures during startup" in rescue_names
    assert "Reset stale MinIO compose resources after startup failure" in rescue_names
    assert "Force-remove stale MinIO containers after task-state startup failure" in rescue_names
    assert "Retry MinIO startup after compose-network recovery" in rescue_names
    assert "AlreadyExists: task" in rescue_fact["ansible.builtin.set_fact"]["minio_container_task_already_exists"]
    assert "already exists" in rescue_fact["ansible.builtin.set_fact"]["minio_container_task_already_exists"]
    assert unexpected_failure["when"] == [
        "not minio_compose_network_missing",
        "not minio_container_task_already_exists",
    ]
    assert 'docker rm -f "$container_name"' in cleanup_task["ansible.builtin.shell"]
    assert cleanup_task["when"] == "minio_container_task_already_exists"
    assert reset_task["when"] == "minio_compose_network_missing or minio_container_task_already_exists"
    assert retry_task["when"] == "minio_compose_network_missing or minio_container_task_already_exists"


def test_templates_publish_public_server_and_console_urls() -> None:
    compose = COMPOSE_TEMPLATE.read_text()
    env_template = ENV_TEMPLATE.read_text()
    env_ctemplate = ENV_CTEMPLATE.read_text()

    assert "{% from 'compose_macros.j2' import openbao_sidecar %}" in compose
    assert "openbao_sidecar(" in compose
    assert '"BAO_ADDR": "http://host.docker.internal:" ~ openbao_http_port' in compose
    assert 'extra_hosts=["host.docker.internal:host-gateway"]' in compose
    assert '"{{ minio_api_port }}:9000"' in compose
    assert '"{{ minio_console_port }}:9001"' in compose
    assert "--console-address" in compose
    assert "condition: service_healthy" in compose
    assert "MINIO_SERVER_URL={{ minio_public_base_url }}" in env_template
    assert "MINIO_BROWSER_REDIRECT_URL={{ minio_console_public_url }}" in env_template
    assert "MINIO_ROOT_PASSWORD=[[ with secret " in env_ctemplate


def test_verify_tasks_probe_health_buckets_cors_and_lifecycle() -> None:
    tasks = load_yaml(VERIFY_PATH)
    names = {task["name"] for task in tasks}
    verify_text = VERIFY_PATH.read_text()

    assert "Verify the MinIO runtime health" in names
    assert "Verify the managed MinIO buckets are reachable" in names
    assert "Verify the Langfuse bucket default CORS behavior" in names
    assert "Verify the RAG staging bucket lifecycle rule" in names
    assert "minio_managed_consumers_resolved" in verify_text
    assert "/minio/health/live" in verify_text
    assert "/minio/health/ready" in verify_text
    assert "share download --json --expire 5m" in verify_text
    assert "--retry-connrefused" in verify_text
    assert "--connect-timeout 5 --max-time 30" in verify_text
    assert "access-control-allow-origin" in verify_text
