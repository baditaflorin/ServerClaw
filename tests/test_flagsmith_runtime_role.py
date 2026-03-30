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
POSTGRES_DEFAULTS_PATH = REPO_ROOT / "roles" / "flagsmith_postgres" / "defaults" / "main.yml"
POSTGRES_TASKS_PATH = REPO_ROOT / "roles" / "flagsmith_postgres" / "tasks" / "main.yml"
POSTGRES_META_PATH = REPO_ROOT / "roles" / "flagsmith_postgres" / "meta" / "argument_specs.yml"


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_flagsmith_runtime_defaults_reference_service_topology_images_and_local_secrets() -> None:
    defaults = yaml.safe_load(RUNTIME_DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["flagsmith_service_topology"] == "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('flagsmith') }}"
    assert defaults["flagsmith_internal_port"] == "{{ platform_service_topology | platform_service_port('flagsmith', 'internal') }}"
    assert defaults["flagsmith_internal_base_url"] == "{{ platform_service_topology | platform_service_url('flagsmith', 'internal') }}"
    assert defaults["flagsmith_public_base_url"] == "https://{{ flagsmith_service_topology.public_hostname }}"
    assert defaults["flagsmith_runtime_image"] == "{{ container_image_catalog.images.flagsmith_runtime.ref }}"
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

    openbao_helper = next(
        task for task in tasks if task["name"] == "Prepare OpenBao agent runtime secret injection for Flagsmith"
    )
    pull_task = next(task for task in tasks if task["name"] == "Pull the Flagsmith images")
    up_task = next(task for task in tasks if task["name"] == "Start the Flagsmith stack")
    port_check_task = next(
        task for task in tasks if task["name"] == "Check whether Flagsmith publishes the expected host port"
    )
    seed_task = next(
        task for task in tasks if task["name"] == "Reconcile the Flagsmith org, project, environments, features, and environment keys"
    )
    openbao_write_task = next(
        task for task in tasks if task["name"] == "Store the managed Flagsmith environment keys in OpenBao"
    )
    verify_task = next(task for task in tasks if task["name"] == "Verify the Flagsmith runtime")

    assert openbao_helper["ansible.builtin.include_role"]["name"] == "lv3.platform.common"
    assert openbao_helper["ansible.builtin.include_role"]["tasks_from"] == "openbao_compose_env"
    assert pull_task["ansible.builtin.command"]["argv"][-1] == "pull"
    assert up_task["ansible.builtin.command"]["argv"][-2:] == ["-d", "--remove-orphans"]
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
    assert openbao_write_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ openbao_http_port }}/v1/kv/data/{{ flagsmith_openbao_environment_keys_path }}"
    assert verify_task["ansible.builtin.import_tasks"] == "verify.yml"


def test_flagsmith_verify_tasks_cover_local_health_task_processor_and_seed_state() -> None:
    tasks = load_tasks(VERIFY_TASKS_PATH)

    health_task = next(task for task in tasks if task["name"] == "Verify the Flagsmith local health endpoint")
    processor_task = next(task for task in tasks if task["name"] == "Verify the Flagsmith task processor readiness endpoint")
    seed_task = next(task for task in tasks if task["name"] == "Verify the Flagsmith seeded state and environment-key evaluation path")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_internal_base_url }}/health"
    assert processor_task["ansible.builtin.command"]["argv"][:4] == [
        "docker",
        "exec",
        "{{ flagsmith_task_processor_container_name }}",
        "python",
    ]
    assert seed_task["ansible.builtin.command"]["argv"][:3] == [
        "python3",
        "{{ flagsmith_seed_script_remote_file }}",
        "verify",
    ]


def test_flagsmith_public_verify_tasks_expect_health_and_oauth_redirects() -> None:
    tasks = load_tasks(VERIFY_PUBLIC_TASKS_PATH)

    health_task = next(task for task in tasks if task["name"] == "Verify the public Flagsmith health endpoint")
    root_task = next(task for task in tasks if task["name"] == "Verify the public Flagsmith UI is protected by the shared edge auth boundary")
    api_task = next(task for task in tasks if task["name"] == "Verify the public Flagsmith management API is protected by the shared edge auth boundary")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_public_base_url }}/health"
    assert root_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_public_base_url }}/"
    assert api_task["ansible.builtin.uri"]["url"] == "{{ flagsmith_public_base_url }}/api/v1/projects/"


def test_flagsmith_templates_bind_private_port_and_render_public_domain() -> None:
    compose_template = COMPOSE_TEMPLATE_PATH.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'container_name: {{ flagsmith_container_name }}' in compose_template
    assert '"{{ ansible_host }}:{{ flagsmith_internal_port }}:8000"' in compose_template
    assert '"127.0.0.1:{{ flagsmith_internal_port }}:8000"' in compose_template
    assert "container_name: {{ flagsmith_task_processor_container_name }}" in compose_template
    assert "FLAGSMITH_DOMAIN={{ flagsmith_service_topology.public_hostname }}" in env_template
    assert "ALLOW_ADMIN_INITIATION_VIA_CLI=true" in env_template
    assert "ENABLE_TASK_PROCESSOR_HEALTH_CHECK=True" in env_template


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
