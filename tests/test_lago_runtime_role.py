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

    assert defaults["lago_service_topology"] == "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('lago') }}"
    assert defaults["lago_api_image"] == "{{ container_image_catalog.images.lago_api_runtime.ref }}"
    assert defaults["lago_front_image"] == "{{ container_image_catalog.images.lago_front_runtime.ref }}"
    assert defaults["lago_pdf_image"] == "{{ container_image_catalog.images.lago_pdf_runtime.ref }}"
    assert defaults["lago_redis_image"] == "{{ container_image_catalog.images.lago_redis_runtime.ref }}"
    assert defaults["lago_public_base_url"] == "{{ platform_service_topology.lago.urls.public }}"
    assert defaults["lago_public_api_base_url"] == "{{ platform_service_topology.lago.urls.public }}/api"
    assert defaults["lago_api_local_base_url"] == "{{ platform_service_topology.lago.urls.api }}"
    assert defaults["lago_direct_api_local_base_url"] == "http://127.0.0.1:{{ platform_service_topology.lago.ports.api }}"
    assert defaults["lago_direct_front_local_base_url"] == "http://127.0.0.1:{{ platform_service_topology.lago.ports.internal }}"
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
    secret_task = next(task for task in tasks if task["name"] == "Generate the Lago runtime secrets")
    mirror_task = next(task for task in tasks if task["name"] == "Mirror the Lago runtime secrets to the control machine")
    producer_catalog_task = next(task for task in tasks if task["name"] == "Render the controller-local Lago producer catalog")
    startup_task = next(task for task in tasks if task["name"] == "Start the Lago runtime and recover Docker bridge-chain failures")
    metric_task = next(task for task in tasks if task["name"] == "Create the Lago smoke billable metric")
    plan_task = next(task for task in tasks if task["name"] == "Create the Lago smoke plan")
    customer_task = next(task for task in tasks if task["name"] == "Upsert the Lago smoke customer")
    subscription_task = next(task for task in tasks if task["name"] == "Upsert the Lago smoke subscription")
    event_task = next(task for task in tasks if task["name"] == "Submit a direct Lago smoke event")
    verify_task = next(task for task in tasks if task["name"] == "Verify the Lago runtime")

    assert "curl" in packages_task["ansible.builtin.apt"]["name"]
    assert "openssl genrsa 2048" in secret_task["loop"][2]["command"]
    assert mirror_task["delegate_to"] == "localhost"
    assert producer_catalog_task["delegate_to"] == "localhost"
    assert startup_task["block"][0]["name"] == "Start the Lago stack"
    assert startup_task["rescue"][-1]["name"] == "Retry Lago startup after Docker bridge-chain recovery"
    assert metric_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/billable_metrics"
    assert plan_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/plans"
    assert customer_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/customers"
    assert subscription_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/subscriptions"
    assert event_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/api/v1/events"
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_lago_verify_tasks_cover_local_health_front_and_current_usage() -> None:
    tasks = load_tasks(VERIFY_TASKS_PATH)

    health_task = next(task for task in tasks if task["name"] == "Verify the Lago local health endpoint")
    usage_task = next(task for task in tasks if task["name"] == "Verify the Lago direct current usage endpoint returns the smoke metric")
    front_task = next(task for task in tasks if task["name"] == "Verify the Lago front surface listens locally")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ lago_direct_api_local_base_url }}/health"
    assert usage_task["ansible.builtin.uri"]["url"] == (
        "{{ lago_direct_api_local_base_url }}/api/v1/customers/{{ lago_smoke_external_customer_id }}/current_usage"
    )
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
    assert 'LAGO_RSA_PRIVATE_KEY="{{ lago_rsa_private_key_b64 }}"' in env_template
    assert '"token": "{{ lago_smoke_producer_token }}"' in producer_template


def test_lago_postgres_defaults_and_tasks_manage_the_shared_database_password() -> None:
    defaults = yaml.safe_load(POSTGRES_DEFAULTS_PATH.read_text(encoding="utf-8"))
    tasks = load_tasks(POSTGRES_TASKS_PATH)

    assert defaults["lago_database_password_local_file"].endswith("/.local/lago/database-password.txt")
    assert defaults["lago_postgres_password_file"] == "{{ lago_postgres_secret_dir }}/database-password"
    assert next(task for task in tasks if task["name"] == "Generate the Lago database password")
    assert next(task for task in tasks if task["name"] == "Create the Lago database role")
    assert next(task for task in tasks if task["name"] == "Create the Lago PostgreSQL database")
