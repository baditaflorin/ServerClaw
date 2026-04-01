from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "rag_context_runtime" / "tasks" / "main.yml"
VERIFY_TASKS = REPO_ROOT / "roles" / "rag_context_runtime" / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "rag_context_runtime" / "templates" / "docker-compose.yml.j2"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "rag_context_runtime" / "defaults" / "main.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "rag_context_runtime" / "templates" / "platform-context.env.j2"
ENV_CTEMPLATE = REPO_ROOT / "roles" / "rag_context_runtime" / "templates" / "platform-context.env.ctmpl.j2"
REQUIREMENTS = REPO_ROOT / "requirements" / "platform-context-api.txt"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_verify_tasks() -> list[dict]:
    return yaml.safe_load(VERIFY_TASKS.read_text())


def load_defaults() -> dict:
    return yaml.safe_load(ROLE_DEFAULTS.read_text())


def test_pull_task_only_targets_external_qdrant_image() -> None:
    tasks = load_tasks()
    pull_task = next(task for task in tasks if task.get("name") == "Pull the platform context images")
    assert pull_task["ansible.builtin.command"]["argv"][-2:] == ["pull", "qdrant"]


def test_compose_template_build_uses_host_network() -> None:
    assert "network: host" in COMPOSE_TEMPLATE.read_text()


def test_host_network_policy_allows_platform_context_proxy_port() -> None:
    host_vars = yaml.safe_load(
        (REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text()
    )
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    assert 8010 in host_rule["ports"]


def test_role_restores_docker_nat_chain_before_recreate() -> None:
    tasks = load_tasks()
    check_task = next(
        task for task in tasks if task.get("name") == "Check whether the Docker nat chain exists before recreating published ports"
    )
    restore_task = next(
        task for task in tasks if task.get("name") == "Restore Docker networking when the nat chain is missing"
    )
    recheck_task = next(
        task for task in tasks if task.get("name") == "Recheck the Docker nat chain before platform-context startup"
    )
    wait_task = next(
        task for task in tasks if task.get("name") == "Wait for the Docker daemon to answer after networking recovery"
    )
    assert check_task["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert restore_task["ansible.builtin.service"]["name"] == "docker"
    assert recheck_task["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert wait_task["ansible.builtin.command"]["argv"] == ["docker", "info", "--format", '{{ "{{.ServerVersion}}" }}']


def test_role_defaults_include_minio_staging_contract() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert "platform_context_minio_secret_key_local_file" in defaults
    assert "platform_context_minio_bucket_name: rag-staging" in defaults
    assert "platform_service_url('minio', 'internal')" in defaults
    assert "platform_context_memory_dsn" in defaults
    assert "platform_context_memory_collection" in defaults


def test_role_syncs_script_bootstrap_into_platform_context_build_context() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())
    service_sources = defaults["platform_context_service_sources"]
    script_bootstrap = next(source for source in service_sources if source["dest"] == "script_bootstrap.py")
    assert script_bootstrap["src"] == "{{ platform_context_repo_root }}/scripts/script_bootstrap.py"


def test_env_template_exposes_serverclaw_memory_settings() -> None:
    template = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "PLATFORM_CONTEXT_MEMORY_DSN" in template
    assert "PLATFORM_CONTEXT_MEMORY_COLLECTION" in template
    assert "PLATFORM_CONTEXT_MEMORY_INDEX_PATH" in template
    assert "PLATFORM_CONTEXT_STAGING_S3_ENDPOINT" in template
    assert "PLATFORM_CONTEXT_STAGING_S3_BUCKET" in template
    assert "PLATFORM_CONTEXT_STAGING_S3_SECRET_ACCESS_KEY" in template
    assert template.count("PLATFORM_CONTEXT_OLLAMA_URL") == 1


def test_env_ctemplate_exposes_openbao_backed_minio_staging_settings() -> None:
    template = ENV_CTEMPLATE.read_text(encoding="utf-8")
    assert "PLATFORM_CONTEXT_STAGING_S3_ENDPOINT" in template
    assert "PLATFORM_CONTEXT_STAGING_S3_BUCKET" in template
    assert "PLATFORM_CONTEXT_STAGING_S3_SECRET_ACCESS_KEY=[[ with secret " in template
    assert template.count("PLATFORM_CONTEXT_OLLAMA_URL") == 1


def test_platform_context_requirements_keep_sentence_transformers_optional() -> None:
    requirements = REQUIREMENTS.read_text(encoding="utf-8")
    assert "sentence-transformers" not in requirements


def test_role_only_installs_sentence_transformers_when_backend_requests_it() -> None:
    dockerfile_task = next(
        task for task in load_tasks() if task.get("name") == "Render the platform context API Dockerfile"
    )
    dockerfile = dockerfile_task["ansible.builtin.copy"]["content"]
    assert '{% if platform_context_embedding_backend == "sentence-transformers" %}' in dockerfile
    assert "sentence-transformers==5.1.0" in dockerfile


def test_role_dockerfile_copies_script_bootstrap_into_runtime_image() -> None:
    dockerfile_task = next(
        task for task in load_tasks() if task.get("name") == "Render the platform context API Dockerfile"
    )
    dockerfile = dockerfile_task["ansible.builtin.copy"]["content"]
    assert "COPY script_bootstrap.py ./script_bootstrap.py" in dockerfile


def test_role_uses_classic_builder_for_platform_context_stack_bring_up() -> None:
    env_contract_task = next(
        task
        for task in load_tasks()
        if task.get("name") == "Verify the rendered platform context runtime env contract before startup"
    )
    startup_block = next(
        task
        for task in load_tasks()
        if task.get("name") == "Build and start the platform context stack and recover stale compose networks"
    )
    build_task = next(
        task for task in startup_block["block"] if task.get("name") == "Build the platform context API image with host networking"
    )
    start_task = next(task for task in startup_block["block"] if task.get("name") == "Start the platform context stack")
    assert build_task["ansible.builtin.command"]["argv"][:4] == ["docker", "build", "--network", "host"]
    assert build_task["ansible.builtin.command"]["argv"][-2:] == ["{{ platform_context_api_image_name }}:latest", "{{ platform_context_service_dir }}"]
    assert build_task["environment"]["DOCKER_BUILDKIT"] == "0"
    assert build_task["environment"]["COMPOSE_DOCKER_CLI_BUILD"] == "0"
    assert "--no-build" in start_task["ansible.builtin.command"]["argv"]
    assert 'PLATFORM_CONTEXT_CORPUS_ROOT={{ platform_context_corpus_dir }}' in env_contract_task["ansible.builtin.shell"]
    assert 'PLATFORM_CONTEXT_MEMORY_COLLECTION={{ platform_context_memory_collection }}' in env_contract_task["ansible.builtin.shell"]
    assert 'PLATFORM_CONTEXT_API_TOKEN=' in env_contract_task["ansible.builtin.shell"]


def test_compose_template_starts_platform_context_without_openbao_health_gate() -> None:
    template = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    platform_context_api_section = template.split("  platform-context-api:", 1)[1]
    assert "qdrant:" in platform_context_api_section
    assert "openbao-agent:\n        condition: service_healthy" not in platform_context_api_section


def test_role_resets_stale_compose_networks_before_retrying_platform_context_startup() -> None:
    startup_block = next(
        task
        for task in load_tasks()
        if task.get("name") == "Build and start the platform context stack and recover stale compose networks"
    )
    flag_task = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Flag stale platform context compose-network failures during startup"
    )
    reset_task = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Reset stale platform context compose resources before retrying startup"
    )
    retry_task = next(
        task
        for task in startup_block["rescue"]
        if task.get("name") == "Retry platform context stack startup after compose-network recovery"
    )
    assert "failed to create endpoint" in flag_task["ansible.builtin.set_fact"]["platform_context_docker_network_missing"]
    assert reset_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert "--force-recreate" in retry_task["ansible.builtin.command"]["argv"]
    assert retry_task["when"] == "platform_context_docker_network_missing"


def test_role_applies_serverclaw_memory_migration() -> None:
    tasks = load_tasks()
    apply_task = next(
        task
        for task in tasks
        if task.get("name") == "Apply the ADR 0263 ServerClaw memory migration in the shared platform database"
    )
    assert apply_task["delegate_to"] == "{{ platform_context_database_inventory_host }}"
    assert apply_task["become_user"] == "postgres"
    assert apply_task["ansible.builtin.command"]["argv"][:4] == ["psql", "-d", "{{ platform_context_database_name }}", "-v"]


def test_role_uses_archive_bundle_for_platform_context_corpus_sync() -> None:
    tasks = load_tasks()
    archive_task = next(
        task
        for task in tasks
        if task.get("name") == "Archive the platform context corpus bundle from the repository workspace"
    )
    unpack_task = next(
        task
        for task in tasks
        if task.get("name") == "Unpack the platform context corpus bundle on the runtime host"
    )
    assert archive_task["delegate_to"] == "localhost"
    assert archive_task["become"] is False
    assert unpack_task["ansible.builtin.unarchive"]["dest"] == "{{ platform_context_corpus_dir }}"


def test_verify_tasks_repair_degraded_vector_index_from_controller_seed() -> None:
    tasks = load_verify_tasks()
    repair_task = next(
        task
        for task in tasks
        if task.get("name") == "Repair a degraded platform context vector index with a bounded controller-side seed rebuild"
    )
    assert repair_task["delegate_to"] == "localhost"
    assert repair_task["become"] is False
    assert "--include-path" in repair_task["ansible.builtin.command"]["cmd"]


def test_verify_tasks_wait_for_runtime_dependencies_before_query_smoke_tests() -> None:
    tasks = load_verify_tasks()
    defaults = load_defaults()
    qdrant_wait = next(
        task for task in tasks if task.get("name") == "Wait for the Qdrant API before live query verification"
    )
    ollama_wait = next(
        task
        for task in tasks
        if task.get("name")
        == "Wait for Ollama again before live query verification when semantic embeddings use the local Ollama backend"
    )
    health_wait = next(
        task
        for task in tasks
        if task.get("name") == "Wait for the platform context health endpoint again before live query verification"
    )
    assert defaults["platform_context_verify_request_retries"] == 12
    assert defaults["platform_context_verify_request_delay_seconds"] == 5
    assert qdrant_wait["ansible.builtin.command"]["argv"][:5] == [
        "docker",
        "exec",
        "platform-context-api",
        "python",
        "-c",
    ]
    assert (
        qdrant_wait["ansible.builtin.command"]["argv"][5]
        == 'import urllib.request\n\nurllib.request.urlopen("http://qdrant:6333/collections", timeout=10)\n'
    )
    assert qdrant_wait["retries"] == "{{ platform_context_verify_request_retries }}"
    assert qdrant_wait["delay"] == "{{ platform_context_verify_request_delay_seconds }}"
    assert qdrant_wait["until"] == "platform_context_qdrant_verify_ready.rc == 0"
    assert ollama_wait["ansible.builtin.uri"]["url"] == "{{ platform_context_ollama_url }}/api/version"
    assert ollama_wait["retries"] == "{{ platform_context_verify_request_retries }}"
    assert ollama_wait["delay"] == "{{ platform_context_verify_request_delay_seconds }}"
    assert ollama_wait["until"] == "platform_context_ollama_verify_ready.status == 200"
    assert ollama_wait["when"] == 'platform_context_embedding_backend == "ollama"'
    assert health_wait["ansible.builtin.uri"]["url"] == "{{ platform_context_private_url }}/healthz"
    assert health_wait["retries"] == "{{ platform_context_verify_request_retries }}"
    assert health_wait["delay"] == "{{ platform_context_verify_request_delay_seconds }}"
    assert health_wait["until"] == "platform_context_query_health.status == 200"


def test_verify_tasks_retry_live_query_smoke_checks() -> None:
    tasks = load_verify_tasks()
    query_task = next(task for task in tasks if task.get("name") == "Verify the platform context query endpoint")
    repaired_query_task = next(
        task for task in tasks if task.get("name") == "Re-verify the platform context query endpoint after seed repair"
    )
    smoke_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Verify the ServerClaw memory query endpoint returns the smoke entry through both recall paths"
    )
    assert query_task["retries"] == "{{ platform_context_verify_request_retries }}"
    assert query_task["delay"] == "{{ platform_context_verify_request_delay_seconds }}"
    assert query_task["until"] == "platform_context_query.status == 200"
    assert repaired_query_task["retries"] == "{{ platform_context_verify_request_retries }}"
    assert repaired_query_task["delay"] == "{{ platform_context_verify_request_delay_seconds }}"
    assert repaired_query_task["until"] == "platform_context_query_repaired.status == 200"
    assert smoke_task["retries"] == "{{ platform_context_verify_request_retries }}"
    assert smoke_task["delay"] == "{{ platform_context_verify_request_delay_seconds }}"
    assert smoke_task["until"] == "platform_context_memory_query.status == 200"


def test_verify_tasks_smoke_serverclaw_memory_query() -> None:
    tasks = load_verify_tasks()
    smoke_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Verify the ServerClaw memory query endpoint returns the smoke entry through both recall paths"
    )
    assert smoke_task["ansible.builtin.uri"]["url"] == "{{ platform_context_private_url }}/v1/memory/query"


def test_role_requires_platform_context_minio_secret_before_runtime_render() -> None:
    tasks = load_tasks()
    names = {task["name"] for task in tasks}
    assert "Ensure the platform context MinIO secret key exists on the control machine" in names
    assert "Fail if the platform context MinIO secret key is missing locally" in names
