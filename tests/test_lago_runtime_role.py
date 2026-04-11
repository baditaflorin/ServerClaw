from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DEFAULTS_PATH = REPO_ROOT / "roles" / "lago_runtime" / "defaults" / "main.yml"
RUNTIME_TASKS_PATH = REPO_ROOT / "roles" / "lago_runtime" / "tasks" / "main.yml"
VERIFY_TASKS_PATH = REPO_ROOT / "roles" / "lago_runtime" / "tasks" / "verify.yml"
RUNTIME_META_PATH = REPO_ROOT / "roles" / "lago_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "lago_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE_PATH = REPO_ROOT / "roles" / "lago_runtime" / "templates" / "lago.env.j2"
PRODUCER_TEMPLATE_PATH = REPO_ROOT / "roles" / "lago_runtime" / "templates" / "producer-catalog.json.j2"
POSTGRES_DEFAULTS_PATH = REPO_ROOT / "roles" / "lago_postgres" / "defaults" / "main.yml"
POSTGRES_TASKS_PATH = REPO_ROOT / "roles" / "lago_postgres" / "tasks" / "main.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_lago_runtime_defaults_reference_service_topology_images_and_local_secrets() -> None:
    defaults = yaml.safe_load(RUNTIME_DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert (
        defaults["lago_service_topology"]
        == "{{ hostvars['proxmox-host'].lv3_service_topology | service_topology_get('lago') }}"
    )
    assert defaults["lago_api_image"] == "{{ container_image_catalog.images.lago_api_runtime.ref }}"
    assert defaults["lago_front_image"] == "{{ container_image_catalog.images.lago_front_runtime.ref }}"
    assert defaults["lago_pdf_image"] == "{{ container_image_catalog.images.lago_pdf_runtime.ref }}"
    assert defaults["lago_redis_image"] == "{{ container_image_catalog.images.lago_redis_runtime.ref }}"
    assert (
        defaults["lago_redis_url"] == "redis://{{ lago_redis_host }}:{{ lago_redis_port }}/{{ lago_redis_sidekiq_db }}"
    )
    assert (
        defaults["lago_redis_cache_url"]
        == "redis://{{ lago_redis_host }}:{{ lago_redis_port }}/{{ lago_redis_cache_db }}"
    )
    assert defaults["lago_redis_cable_url"] == (
        "redis://:{{ lago_redis_password | urlencode }}@{{ lago_redis_host }}:{{ lago_redis_port }}/{{ lago_redis_cable_db }}"
    )
    assert defaults["lago_redis_data_owner"] == "999"
    assert defaults["lago_redis_data_group"] == "1000"
    assert defaults["lago_redis_data_mode"] == "0770"
    assert defaults["lago_runtime_apt_lock_timeout"] == 1200
    assert defaults["lago_public_base_url"] == "{{ platform_service_topology.lago.urls.public }}"
    assert defaults["lago_public_api_base_url"] == "{{ platform_service_topology.lago.urls.public }}/api"
    assert defaults["lago_api_local_base_url"] == "{{ platform_service_topology.lago.urls.api }}"
    assert (
        defaults["lago_direct_api_local_base_url"] == "http://127.0.0.1:{{ platform_service_topology.lago.ports.api }}"
    )
    assert (
        defaults["lago_direct_front_local_base_url"]
        == "http://127.0.0.1:{{ platform_service_topology.lago.ports.internal }}"
    )
    assert defaults["lago_rails_env"] == "production"
    assert defaults["lago_rack_env"] == "{{ lago_rails_env }}"
    assert defaults["lago_annotaterb_skip_on_db_tasks"] == "1"
    assert defaults["lago_database_password_local_file"].endswith("/.local/lago/database-password.txt")
    assert defaults["lago_org_api_key_local_file"].endswith("/.local/lago/org-api-key.txt")
    assert defaults["lago_producer_catalog_local_file"].endswith("/.local/lago/producer-catalog.json")
    assert defaults["lago_public_ingest_url"] == "{{ lago_public_base_url }}/api/v1/events"


def test_lago_runtime_argument_spec_requires_runtime_and_seed_inputs() -> None:
    specs = yaml.safe_load(RUNTIME_META_PATH.read_text(encoding="utf-8"))
    options = specs["argument_specs"]["main"]["options"]

    assert options["lago_site_dir"]["type"] == "path"
    assert options["lago_env_file"]["type"] == "path"
    assert options["lago_local_artifact_dir"]["type"] == "path"
    assert options["lago_public_base_url"]["type"] == "str"
    assert options["lago_public_api_base_url"]["type"] == "str"
    assert options["lago_direct_api_local_base_url"]["type"] == "str"
    assert options["lago_smoke_metric_code"]["type"] == "str"
    assert options["lago_smoke_external_subscription_id"]["type"] == "str"


def test_lago_runtime_tasks_manage_secret_generation_seed_and_smoke_verification() -> None:
    tasks = load_tasks(RUNTIME_TASKS_PATH)

    packages_task = next(task for task in tasks if task["name"] == "Ensure the Lago runtime packages are present")
    directories_task = next(task for task in tasks if task["name"] == "Ensure the Lago runtime directories exist")
    secret_task = next(task for task in tasks if task["name"] == "Generate the Lago runtime secrets")
    mirror_task = next(
        task for task in tasks if task["name"] == "Mirror the Lago runtime secrets to the control machine"
    )
    producer_catalog_task = next(
        task for task in tasks if task["name"] == "Render the controller-local Lago producer catalog"
    )
    postgres_wait_task = next(
        task for task in tasks if task["name"] == "Wait for the Lago PostgreSQL endpoint to accept TCP connections"
    )
    startup_task = next(
        task for task in tasks if task["name"] == "Start the Lago runtime and recover Docker bridge-chain failures"
    )
    redis_bgsave_task = next(task for task in tasks if task["name"] == "Trigger a Lago Redis background save")
    redis_persistence_task = next(
        task for task in tasks if task["name"] == "Wait for Lago Redis background save to succeed"
    )
    metric_task = next(task for task in tasks if task["name"] == "Create the Lago smoke billable metric")
    plan_task = next(task for task in tasks if task["name"] == "Create the Lago smoke plan")
    customer_task = next(task for task in tasks if task["name"] == "Upsert the Lago smoke customer")
    subscription_task = next(task for task in tasks if task["name"] == "Upsert the Lago smoke subscription")
    event_task = next(task for task in tasks if task["name"] == "Submit a direct Lago smoke event")
    verify_task = next(task for task in tasks if task["name"] == "Verify the Lago runtime")

    assert "curl" in packages_task["ansible.builtin.apt"]["name"]
    assert packages_task["ansible.builtin.apt"]["lock_timeout"] == "{{ lago_runtime_apt_lock_timeout }}"
    redis_dir_entry = next(item for item in directories_task["loop"] if item["path"] == "{{ lago_redis_data_dir }}")
    assert redis_dir_entry["owner"] == "{{ lago_redis_data_owner }}"
    assert redis_dir_entry["group"] == "{{ lago_redis_data_group }}"
    assert redis_dir_entry["mode"] == "{{ lago_redis_data_mode }}"
    assert "openssl genrsa 2048" in secret_task["loop"][2]["command"]
    assert mirror_task["delegate_to"] == "localhost"
    assert producer_catalog_task["delegate_to"] == "localhost"
    assert postgres_wait_task["ansible.builtin.wait_for"]["host"] == "{{ lago_database_host }}"
    assert postgres_wait_task["ansible.builtin.wait_for"]["port"] == "{{ lago_database_port }}"
    assert postgres_wait_task["ansible.builtin.wait_for"]["timeout"] == 300
    assert startup_task["block"][0]["name"] == "Start the Lago stack"
    recovery_fact_task = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Flag Docker bridge-chain, Lago compose dependency, and migrate failures during startup"
    )
    migrate_logs_task = next(
        task for task in startup_task["rescue"] if task["name"] == "Capture Lago migrate logs after startup failure"
    )
    migrate_race_fact_task = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Flag Lago migrate database-race failures during startup"
    )
    unexpected_failure_task = next(
        task for task in startup_task["rescue"] if task["name"] == "Surface unexpected Lago startup failures"
    )
    bridge_retry_task = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Retry Lago startup after Docker bridge-chain recovery"
    )
    dependency_retry_task = next(
        task for task in startup_task["rescue"] if task["name"] == "Retry Lago startup after compose dependency failure"
    )
    migrate_wait_retry_task = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Wait for the Lago PostgreSQL endpoint before retrying startup after migrate failure"
    )
    migrate_remove_task = next(
        task
        for task in startup_task["rescue"]
        if task["name"] == "Remove the failed Lago migrate container before retrying startup"
    )
    migrate_retry_task = next(
        task for task in startup_task["rescue"] if task["name"] == "Retry Lago startup after migrate database race"
    )
    assert (
        "No chain/target/match by that name"
        in recovery_fact_task["ansible.builtin.set_fact"]["lago_docker_bridge_chain_missing"]
    )
    assert (
        "dependency failed to start" in recovery_fact_task["ansible.builtin.set_fact"]["lago_compose_dependency_race"]
    )
    assert "No such container:" in recovery_fact_task["ansible.builtin.set_fact"]["lago_compose_dependency_race"]
    assert (
        "dependency failed to start"
        in recovery_fact_task["ansible.builtin.set_fact"]["lago_compose_dependency_api_restart"]
    )
    assert (
        "'container ' ~ lago_api_container_name ~ ' exited (1)'"
        in recovery_fact_task["ansible.builtin.set_fact"]["lago_compose_dependency_api_restart"]
    )
    assert 'service "migrate"' in recovery_fact_task["ansible.builtin.set_fact"]["lago_compose_migrate_failed"]
    assert "complete successfully" in recovery_fact_task["ansible.builtin.set_fact"]["lago_compose_migrate_failed"]
    assert migrate_logs_task["when"] == "lago_compose_migrate_failed"
    assert "exit 137" in migrate_race_fact_task["ansible.builtin.set_fact"]["lago_migrate_database_race"]
    assert "connection to server at" in migrate_race_fact_task["ansible.builtin.set_fact"]["lago_migrate_database_race"]
    assert (
        "failed: Connection timed out"
        in migrate_race_fact_task["ansible.builtin.set_fact"]["lago_migrate_database_race"]
    )
    assert (
        "failed: Connection refused" in migrate_race_fact_task["ansible.builtin.set_fact"]["lago_migrate_database_race"]
    )
    assert "not lago_docker_bridge_chain_missing" in unexpected_failure_task["when"]
    assert "not lago_compose_dependency_race" in unexpected_failure_task["when"]
    assert "not lago_compose_dependency_api_restart" in unexpected_failure_task["when"]
    assert "not (lago_migrate_database_race | default(false))" in unexpected_failure_task["when"]
    assert bridge_retry_task["when"] == "lago_docker_bridge_chain_missing"
    assert dependency_retry_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "--remove-orphans"]
    assert dependency_retry_task["retries"] == 12
    assert dependency_retry_task["delay"] == 5
    assert dependency_retry_task["until"] == "lago_up_dependency_retry.rc == 0"
    assert dependency_retry_task["when"] == "lago_compose_dependency_race or lago_compose_dependency_api_restart"
    assert migrate_wait_retry_task["ansible.builtin.wait_for"]["host"] == "{{ lago_database_host }}"
    assert migrate_wait_retry_task["ansible.builtin.wait_for"]["port"] == "{{ lago_database_port }}"
    assert migrate_wait_retry_task["when"] == "lago_migrate_database_race | default(false)"
    assert migrate_remove_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "rm",
        "-f",
        "{{ lago_migrate_container_name }}",
    ]
    assert migrate_remove_task["when"] == "lago_migrate_database_race | default(false)"
    assert (
        "'No such container:' not in (lago_migrate_remove.stderr | default(''))" in migrate_remove_task["failed_when"]
    )
    assert migrate_retry_task["ansible.builtin.command"]["argv"][-3:] == ["up", "-d", "--remove-orphans"]
    assert migrate_retry_task["retries"] == 3
    assert migrate_retry_task["delay"] == 5
    assert migrate_retry_task["until"] == "lago_up_migrate_retry.rc == 0"
    assert migrate_retry_task["when"] == "lago_migrate_database_race | default(false)"
    assert redis_bgsave_task["ansible.builtin.command"]["argv"][-1] == "BGSAVE"
    assert redis_persistence_task["retries"] == 60
    assert redis_persistence_task["ansible.builtin.command"]["argv"][-2:] == ["INFO", "persistence"]
    assert redis_persistence_task["until"] == (
        "'rdb_last_bgsave_status:ok' in (lago_redis_persistence_info.stdout | default(''))"
    )
    metric_get_task = next(
        task for task in tasks if task["name"] == "Check whether the Lago smoke billable metric already exists"
    )
    assert metric_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/billable_metrics"
    assert metric_get_task["retries"] == 12
    assert metric_get_task["delay"] == 5
    assert metric_get_task["until"] == "lago_billable_metric_get.status | default(0) in [200, 404]"
    assert metric_task["retries"] == 12
    assert metric_task["delay"] == 5
    assert metric_task["until"] == "lago_billable_metric_create.status | default(0) == 200"
    plan_get_task = next(task for task in tasks if task["name"] == "Check whether the Lago smoke plan already exists")
    assert plan_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/plans"
    assert plan_get_task["retries"] == 12
    assert plan_get_task["delay"] == 5
    assert plan_get_task["until"] == "lago_plan_get.status | default(0) in [200, 404]"
    assert plan_task["retries"] == 12
    assert plan_task["delay"] == 5
    assert plan_task["until"] == "lago_plan_create.status | default(0) == 200"
    assert customer_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/customers"
    assert customer_task["retries"] == 12
    assert customer_task["delay"] == 5
    assert customer_task["until"] == "lago_customer_upsert.status | default(0) == 200"
    assert (
        subscription_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/subscriptions"
    )
    assert subscription_task["retries"] == 12
    assert subscription_task["delay"] == 5
    assert subscription_task["until"] == "lago_subscription_upsert.status | default(0) == 200"
    assert event_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/events"
    assert event_task["retries"] == 12
    assert event_task["delay"] == 5
    assert event_task["until"] == "lago_direct_smoke_event.status == 200"
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_lago_verify_tasks_cover_local_health_front_and_current_usage() -> None:
    tasks = load_tasks(VERIFY_TASKS_PATH)

    health_task = next(task for task in tasks if task["name"] == "Verify the Lago local health endpoint")
    usage_task = next(
        task
        for task in tasks
        if task["name"] == "Verify the Lago direct current usage endpoint returns the smoke metric"
    )
    front_task = next(task for task in tasks if task["name"] == "Verify the Lago front surface listens locally")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/health"
    assert (
        "{{ lago_direct_api_local_base_url }}/api/v1/customers/{{ lago_smoke_external_customer_id }}/current_usage"
        in (usage_task["ansible.builtin.shell"])
    )
    assert "external_subscription_id={{ lago_smoke_external_subscription_id }}" in usage_task["ansible.builtin.shell"]
    assert 'grep -q "{{ lago_smoke_metric_code | lower }}"' in usage_task["ansible.builtin.shell"]
    assert front_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_front_local_base_url }}/"


def test_lago_templates_bind_private_ports_and_render_public_urls() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")
    producer_template = PRODUCER_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "container_name: {{ lago_api_container_name }}" in compose_template
    assert "container_name: {{ lago_front_container_name }}" in compose_template
    assert "container_name: {{ lago_worker_container_name }}" in compose_template
    assert "container_name: {{ lago_pdf_container_name }}" in compose_template
    assert "container_name: {{ lago_redis_container_name }}" in compose_template
    assert '"{{ ansible_host }}:{{ platform_service_topology.lago.ports.api }}:3000"' in compose_template
    assert '"127.0.0.1:{{ platform_service_topology.lago.ports.api }}:3000"' in compose_template
    assert '"{{ ansible_host }}:{{ platform_service_topology.lago.ports.internal }}:80"' in compose_template
    assert "LAGO_FRONT_URL={{ lago_public_base_url }}" in env_template
    assert "LAGO_API_URL={{ lago_public_api_base_url }}" in env_template
    assert "API_URL={{ lago_public_api_base_url }}" in env_template
    assert "REDIS_URL={{ lago_redis_url }}" in env_template
    assert "LAGO_REDIS_CACHE_URL={{ lago_redis_cache_url }}" in env_template
    assert "LAGO_REDIS_CABLE_URL={{ lago_redis_cable_url }}" in env_template
    assert "RAILS_ENV={{ lago_rails_env }}" in env_template
    assert "RACK_ENV={{ lago_rack_env }}" in env_template
    assert "ANNOTATERB_SKIP_ON_DB_TASKS={{ lago_annotaterb_skip_on_db_tasks }}" in env_template
    assert 'LAGO_RSA_PRIVATE_KEY="{{ lago_rsa_private_key_b64 }}"' in env_template
    assert '"token": "{{ lago_smoke_producer_token }}"' in producer_template


def test_lago_postgres_defaults_and_tasks_manage_the_shared_database_password() -> None:
    defaults = yaml.safe_load(POSTGRES_DEFAULTS_PATH.read_text(encoding="utf-8"))
    tasks = load_tasks(POSTGRES_TASKS_PATH)

    assert defaults["lago_database_password_local_file"].endswith("/.local/lago/database-password.txt")
    assert defaults["lago_database_user_createdb"] is True
    assert defaults["lago_postgres_required_extensions"] == ["pg_partman"]
    assert defaults["lago_postgres_extension_packages"] == [
        "postgresql-{{ lago_postgres_server_major_version }}-partman"
    ]
    assert defaults["lago_postgres_password_file"] == "{{ lago_postgres_secret_dir }}/database-password"
    assert next(task for task in tasks if task["name"] == "Generate the Lago database password")
    version_task = next(task for task in tasks if task["name"] == "Record PostgreSQL server version number")
    extension_package_task = next(
        task for task in tasks if task["name"] == "Install the Lago PostgreSQL extension packages"
    )
    extension_check_task = next(
        task for task in tasks if task["name"] == "Check whether required Lago PostgreSQL extensions are available"
    )
    create_role_task = next(task for task in tasks if task["name"] == "Create the Lago database role")
    ensure_createdb_task = next(
        task
        for task in tasks
        if task["name"] == "Ensure the Lago database role can create databases for upstream migrations"
    )
    assert next(task for task in tasks if task["name"] == "Create the Lago PostgreSQL database")
    assert version_task["ansible.builtin.command"]["argv"][-1] == "SHOW server_version_num"
    assert extension_package_task["ansible.builtin.apt"]["name"] == "{{ lago_postgres_extension_packages }}"
    assert extension_check_task["loop"] == "{{ lago_postgres_required_extensions }}"
    assert "CREATEDB" in create_role_task["ansible.builtin.command"]["argv"][-1]
    assert ensure_createdb_task["ansible.builtin.command"]["argv"][-1] == "ALTER ROLE {{ lago_database_user }} CREATEDB"
