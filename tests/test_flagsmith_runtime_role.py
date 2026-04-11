from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DEFAULTS_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "defaults" / "main.yml"
RUNTIME_TASKS_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "tasks" / "main.yml"
VERIFY_TASKS_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "tasks" / "verify.yml"
VERIFY_PUBLIC_TASKS_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "tasks" / "verify_public.yml"
RUNTIME_META_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "templates" / "flagsmith.env.j2"
OPENBAO_ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "flagsmith_runtime" / "templates" / "flagsmith.env.ctmpl.j2"
POSTGRES_DEFAULTS_PATH = REPO_ROOT / "roles" / "flagsmith_postgres" / "defaults" / "main.yml"
POSTGRES_TASKS_PATH = REPO_ROOT / "roles" / "flagsmith_postgres" / "tasks" / "main.yml"
POSTGRES_META_PATH = REPO_ROOT / "roles" / "flagsmith_postgres" / "meta" / "argument_specs.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_flagsmith_runtime_defaults_reference_service_topology_images_and_local_secrets() -> None:
    defaults = yaml.safe_load(RUNTIME_DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert (
        defaults["flagsmith_service_topology"]
        == "{{ hostvars['proxmox-host'].lv3_service_topology | service_topology_get('flagsmith') }}"
    )
    assert (
        defaults["flagsmith_internal_port"]
        == "{{ platform_service_topology | platform_service_port('flagsmith', 'internal') }}"
    )
    assert (
        defaults["flagsmith_internal_base_url"]
        == "{{ platform_service_topology | platform_service_url('flagsmith', 'internal') }}"
    )
    assert defaults["flagsmith_public_base_url"] == "https://{{ flagsmith_service_topology.public_hostname }}"
    assert defaults["flagsmith_runtime_image"] == "{{ container_image_catalog.images.flagsmith_runtime.ref }}"
    assert defaults["flagsmith_api_workers"] == 1
    assert defaults["flagsmith_api_threads"] == 1
    assert defaults["flagsmith_task_processor_threads"] == 2
    assert defaults["flagsmith_database_password_local_file"].endswith("/.local/flagsmith/database-password.txt")
    assert defaults["flagsmith_django_secret_key_local_file"].endswith("/.local/flagsmith/django-secret-key.txt")
    assert defaults["flagsmith_admin_password_local_file"].endswith("/.local/flagsmith/admin-password.txt")
    assert defaults["flagsmith_environment_keys_local_file"].endswith("/.local/flagsmith/environment-keys.json")
    assert [entry["name"] for entry in defaults["flagsmith_environment_definitions"]] == [
        "production",
        "staging",
        "development",
    ]


def test_flagsmith_runtime_argument_spec_requires_runtime_and_secret_inputs() -> None:
    specs = yaml.safe_load(RUNTIME_META_PATH.read_text(encoding="utf-8"))
    options = specs["argument_specs"]["main"]["options"]

    assert options["flagsmith_site_dir"]["type"] == "path"
    assert options["flagsmith_internal_port"]["type"] == "int"
    assert options["flagsmith_internal_base_url"]["type"] == "str"
    assert options["flagsmith_public_base_url"]["type"] == "str"
    assert options["flagsmith_database_password_local_file"]["type"] == "path"
    assert options["flagsmith_environment_keys_local_file"]["type"] == "path"


def test_flagsmith_runtime_tasks_manage_openbao_seed_and_environment_key_flow() -> None:
    tasks = load_tasks(RUNTIME_TASKS_PATH)

    openbao_template_before = next(
        task
        for task in tasks
        if task["name"] == "Check whether the Flagsmith OpenBao agent runtime env template already exists"
    )
    openbao_helper = next(
        task for task in tasks if task["name"] == "Prepare OpenBao agent runtime secret injection for Flagsmith"
    )
    openbao_template_after = next(
        task
        for task in tasks
        if task["name"] == "Check the rendered Flagsmith OpenBao agent runtime env template after helper convergence"
    )
    openbao_template_changed = next(
        task
        for task in tasks
        if task["name"] == "Record whether the Flagsmith OpenBao agent runtime env template changed"
    )
    pull_task = next(task for task in tasks if task["name"] == "Pull the Flagsmith images")
    force_recreate_decision = next(
        task
        for task in tasks
        if task["name"] == "Decide whether the Flagsmith compose services require forced recreation"
    )
    build_startup_command = next(
        task for task in tasks if task["name"] == "Build the Flagsmith compose startup command"
    )
    startup = next(
        task for task in tasks if task["name"] == "Start the Flagsmith stack and recover Docker bridge-chain failures"
    )
    up_task = next(task for task in startup["block"] if task["name"] == "Start the Flagsmith stack")
    port_check_task = next(
        task for task in tasks if task["name"] == "Check whether Flagsmith publishes the expected host port"
    )
    seed_task = next(
        task
        for task in tasks
        if task["name"] == "Reconcile the Flagsmith org, project, environments, features, and environment keys"
    )
    openbao_write_task = next(
        task for task in tasks if task["name"] == "Store the managed Flagsmith environment keys in OpenBao"
    )
    verify_task = next(task for task in tasks if task["name"] == "Verify the Flagsmith runtime")
    admin_password_task = next(
        task
        for task in tasks
        if task["name"] == "Ensure the Flagsmith bootstrap admin password matches the managed secret"
    )
    admin_password_assert = next(
        task for task in tasks if task["name"] == "Assert the Flagsmith bootstrap identity remained a superuser"
    )

    assert (
        openbao_template_before["ansible.builtin.stat"]["path"] == "{{ flagsmith_openbao_agent_dir }}/runtime.env.ctmpl"
    )
    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert (
        openbao_template_after["ansible.builtin.stat"]["path"] == "{{ flagsmith_openbao_agent_dir }}/runtime.env.ctmpl"
    )
    assert (
        "flagsmith_openbao_agent_template_before"
        in openbao_template_changed["ansible.builtin.set_fact"]["flagsmith_openbao_agent_template_changed"]
    )
    assert pull_task["ansible.builtin.command"]["argv"][-1] == "pull"
    assert (
        "flagsmith_openbao_agent_template_changed"
        in force_recreate_decision["ansible.builtin.set_fact"]["flagsmith_force_recreate_required"]
    )
    assert (
        "flagsmith_env_template.changed"
        in force_recreate_decision["ansible.builtin.set_fact"]["flagsmith_force_recreate_required"]
    )
    assert build_startup_command["ansible.builtin.set_fact"]["flagsmith_compose_up_argv"].startswith("{{")
    assert up_task["ansible.builtin.command"]["argv"] == "{{ flagsmith_compose_up_argv }}"
    assert port_check_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "port",
        "{{ flagsmith_container_name }}",
        "8000/tcp",
    ]
    assert seed_task["ansible.builtin.command"]["argv"][:3] == [
        "python3",
        "{{ flagsmith_seed_script_remote_file }}",
        "reconcile",
    ]
    assert "changed and user.set_password(password)" in admin_password_task["ansible.builtin.command"]["argv"][-1]
    assert (
        'changed and user.save(update_fields=["password"])'
        in admin_password_task["ansible.builtin.command"]["argv"][-1]
    )
    assert "stdout_lines" in admin_password_task["changed_when"]
    assert "reject('equalto', '')" in admin_password_task["changed_when"]
    assert "| last" in admin_password_task["changed_when"]
    assert "stdout_lines" in admin_password_assert["ansible.builtin.assert"]["that"][0]
    assert "reject('equalto', '')" in admin_password_assert["ansible.builtin.assert"]["that"][0]
    assert "| last" in admin_password_assert["ansible.builtin.assert"]["that"][0]
    assert (
        openbao_write_task["ansible.builtin.uri"]["url"]
        == "http://127.0.0.1:{{ openbao_http_port }}/v1/kv/data/{{ flagsmith_openbao_environment_keys_path }}"
    )
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_flagsmith_runtime_recovers_bridge_chain_and_stale_compose_network_failures() -> None:
    tasks = load_tasks(RUNTIME_TASKS_PATH)
    startup = next(
        task for task in tasks if task["name"] == "Start the Flagsmith stack and recover Docker bridge-chain failures"
    )

    start_task = next(task for task in startup["block"] if task["name"] == "Start the Flagsmith stack")
    recovery_fact = next(
        task
        for task in startup["rescue"]
        if task["name"] == "Flag Docker bridge-chain and stale Flagsmith compose network failures after startup failure"
    )
    unexpected_failure = next(
        task for task in startup["rescue"] if task["name"] == "Surface unexpected Flagsmith startup failures"
    )
    reset_task = next(
        task
        for task in startup["rescue"]
        if task["name"] == "Reset stale Flagsmith compose resources after startup failure"
    )
    restart_task = next(
        task
        for task in startup["rescue"]
        if task["name"] == "Restart Docker to restore bridge chains before retrying Flagsmith startup"
    )
    reassert_task = next(
        task
        for task in startup["rescue"]
        if task["name"] == "Ensure Docker bridge networking chains are present before retrying Flagsmith startup"
    )
    retry_task = next(
        task
        for task in startup["rescue"]
        if task["name"] == "Retry Flagsmith startup after resetting stale compose resources"
    )

    assert start_task["ansible.builtin.command"]["argv"] == "{{ flagsmith_compose_up_argv }}"
    assert (
        "No chain/target/match by that name"
        in recovery_fact["ansible.builtin.set_fact"]["flagsmith_docker_bridge_chain_missing"]
    )
    assert (
        "Unable to enable ACCEPT OUTGOING rule"
        in recovery_fact["ansible.builtin.set_fact"]["flagsmith_docker_bridge_chain_missing"]
    )
    assert (
        "Unable to enable DNAT rule"
        in recovery_fact["ansible.builtin.set_fact"]["flagsmith_docker_bridge_chain_missing"]
    )
    assert "failed to create endpoint" in recovery_fact["ansible.builtin.set_fact"]["flagsmith_compose_network_missing"]
    assert "does not exist" in recovery_fact["ansible.builtin.set_fact"]["flagsmith_compose_network_missing"]
    assert "not flagsmith_docker_bridge_chain_missing" in unexpected_failure["when"]
    assert "not flagsmith_compose_network_missing" in unexpected_failure["when"]
    assert reset_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert restart_task["when"] == "flagsmith_docker_bridge_chain_missing or flagsmith_compose_network_missing"
    assert reassert_task["ansible.builtin.include_role"]["tasks_from"] == "docker_bridge_chains"
    assert reassert_task["vars"]["common_docker_bridge_chains_service_name"] == "docker"
    assert reassert_task["vars"]["common_docker_bridge_chains_require_nat_chain"] is True
    assert retry_task["ansible.builtin.command"]["argv"][-4:] == ["up", "-d", "--remove-orphans", "--force-recreate"]
    assert retry_task["when"] == "flagsmith_docker_bridge_chain_missing or flagsmith_compose_network_missing"


def test_flagsmith_verify_tasks_cover_local_health_task_processor_and_seed_state() -> None:
    tasks = load_tasks(VERIFY_TASKS_PATH)

    health_task = next(task for task in tasks if task["name"] == "Verify the Flagsmith local health endpoint")
    processor_task = next(
        task for task in tasks if task["name"] == "Verify the Flagsmith task processor readiness endpoint"
    )
    seed_task = next(
        task
        for task in tasks
        if task["name"] == "Verify the Flagsmith seeded state and environment-key evaluation path"
    )
    assert_task = next(
        task for task in tasks if task["name"] == "Assert the local Flagsmith verification results are healthy"
    )

    assert health_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_internal_base_url }}/health"
    assert processor_task["ansible.builtin.command"]["argv"][:4] == [
        "docker",
        "exec",
        "{{ flagsmith_task_processor_container_name }}",
        "python",
    ]
    assert processor_task["until"] == "flagsmith_task_processor_health.rc == 0"
    assert seed_task["ansible.builtin.command"]["argv"][:3] == [
        "python3",
        "{{ flagsmith_seed_script_remote_file }}",
        "verify",
    ]
    assert "flagsmith_task_processor_health.rc == 0" in assert_task["ansible.builtin.assert"]["that"]


def test_flagsmith_public_verify_tasks_expect_health_and_oauth_redirects() -> None:
    tasks = load_tasks(VERIFY_PUBLIC_TASKS_PATH)

    health_task = next(task for task in tasks if task["name"] == "Verify the public Flagsmith health endpoint")
    root_task = next(
        task
        for task in tasks
        if task["name"] == "Verify the public Flagsmith UI is protected by the shared edge auth boundary"
    )
    api_task = next(
        task
        for task in tasks
        if task["name"] == "Verify the public Flagsmith management API is protected by the shared edge auth boundary"
    )

    assert health_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_public_base_url }}/health"
    assert root_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_public_base_url }}/"
    assert api_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_public_base_url }}/api/v1/projects/"


def test_flagsmith_templates_bind_private_port_and_render_public_domain() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    openbao_env_template = OPENBAO_ENV_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "container_name: {{ flagsmith_container_name }}" in compose_template
    assert 'user: "0:0"' in compose_template
    assert 'BAO_SKIP_DROP_ROOT: "true"' in compose_template
    assert "- test -s {{ flagsmith_env_file }}" in compose_template
    assert "{{ flagsmith_env_file | dirname }}:{{ flagsmith_env_file | dirname }}" in compose_template
    assert '"{{ ansible_host }}:{{ flagsmith_internal_port }}:8000"' in compose_template
    assert '"127.0.0.1:{{ flagsmith_internal_port }}:8000"' in compose_template
    assert "openbao-agent:\n        condition: service_healthy" in compose_template
    assert "ACCESS_LOG_LOCATION: {{ flagsmith_access_log_file | to_json }}" in compose_template
    assert "ACCESS_LOG_FORMAT: {{ flagsmith_access_log_format | to_json }}" in compose_template
    assert 'GUNICORN_TIMEOUT: "{{ flagsmith_api_timeout_seconds }}"' in compose_template
    assert 'GUNICORN_WORKERS: "{{ flagsmith_api_workers }}"' in compose_template
    assert 'GUNICORN_THREADS: "{{ flagsmith_api_threads }}"' in compose_template
    assert 'GUNICORN_KEEP_ALIVE: "{{ flagsmith_api_keepalive_seconds }}"' in compose_template
    assert "container_name: {{ flagsmith_task_processor_container_name }}" in compose_template
    assert 'TASK_PROCESSOR_SLEEP_INTERVAL_MS: "{{ flagsmith_task_processor_sleep_interval_ms }}"' in compose_template
    assert 'TASK_PROCESSOR_GRACE_PERIOD_MS: "{{ flagsmith_task_processor_grace_period_ms }}"' in compose_template
    assert 'TASK_PROCESSOR_NUM_THREADS: "{{ flagsmith_task_processor_threads }}"' in compose_template
    assert 'TASK_PROCESSOR_QUEUE_POP_SIZE: "{{ flagsmith_task_processor_queue_pop_size }}"' in compose_template
    assert "- run-task-processor" in compose_template
    assert "FLAGSMITH_DOMAIN={{ flagsmith_service_topology.public_hostname }}" in env_template
    assert "ALLOW_ADMIN_INITIATION_VIA_CLI=true" in env_template
    assert "ENABLE_TASK_PROCESSOR_HEALTH_CHECK=True" in env_template
    assert (
        'DATABASE_URL=[[ with secret "kv/data/{{ flagsmith_openbao_secret_path }}" ]][[ .Data.data.DATABASE_URL ]][[ end ]]'
        in openbao_env_template
    )
    assert (
        'DJANGO_SECRET_KEY=[[ with secret "kv/data/{{ flagsmith_openbao_secret_path }}" ]][[ .Data.data.DJANGO_SECRET_KEY ]][[ end ]]'
        in openbao_env_template
    )
    assert "FLAGSMITH_DOMAIN={{ flagsmith_service_topology.public_hostname }}" in openbao_env_template
    assert "ADMIN_EMAIL={{ flagsmith_admin_email }}" in openbao_env_template
    assert "ALLOW_ADMIN_INITIATION_VIA_CLI=true" in openbao_env_template
    assert "ENABLE_TASK_PROCESSOR_HEALTH_CHECK=True" in openbao_env_template


def test_flagsmith_postgres_role_defaults_specs_and_tasks_cover_database_setup() -> None:
    defaults = yaml.safe_load(POSTGRES_DEFAULTS_PATH.read_text(encoding="utf-8"))
    specs = yaml.safe_load(POSTGRES_META_PATH.read_text(encoding="utf-8"))
    tasks = load_tasks(POSTGRES_TASKS_PATH)
    options = specs["argument_specs"]["main"]["options"]
    names = [task["name"] for task in tasks]

    assert defaults["flagsmith_database_name"] == "flagsmith"
    assert defaults["flagsmith_database_user"] == "flagsmith"
    assert defaults["flagsmith_database_password_local_file"].endswith("/.local/flagsmith/database-password.txt")
    assert options["flagsmith_database_name"]["type"] == "str"
    assert options["flagsmith_postgres_password_file"]["type"] == "path"
    assert "Generate the Flagsmith database password" in names
    assert "Create the Flagsmith role" in names
    assert "Create the Flagsmith PostgreSQL database" in names
