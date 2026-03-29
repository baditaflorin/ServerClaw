from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "rag_context_runtime" / "tasks" / "main.yml"
VERIFY_TASKS = REPO_ROOT / "roles" / "rag_context_runtime" / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "rag_context_runtime" / "templates" / "docker-compose.yml.j2"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "rag_context_runtime" / "defaults" / "main.yml"
ENV_TEMPLATE = REPO_ROOT / "roles" / "rag_context_runtime" / "templates" / "platform-context.env.j2"
REQUIREMENTS = REPO_ROOT / "requirements" / "platform-context-api.txt"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_verify_tasks() -> list[dict]:
    return yaml.safe_load(VERIFY_TASKS.read_text())


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


def test_role_defaults_do_not_depend_on_platform_service_topology() -> None:
    defaults = ROLE_DEFAULTS.read_text()
    assert "platform_service_topology" not in defaults
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


def test_verify_tasks_smoke_serverclaw_memory_query() -> None:
    tasks = load_verify_tasks()
    smoke_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Verify the ServerClaw memory query endpoint returns the smoke entry through both recall paths"
    )
    assert smoke_task["ansible.builtin.uri"]["url"] == "{{ platform_context_private_url }}/v1/memory/query"
