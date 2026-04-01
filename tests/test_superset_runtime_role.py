import importlib.util
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "superset_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "superset_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "superset_runtime" / "tasks" / "verify.yml"
ROLE_PUBLISH = REPO_ROOT / "roles" / "superset_runtime" / "tasks" / "publish.yml"
ROLE_META = REPO_ROOT / "roles" / "superset_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "superset_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = REPO_ROOT / "roles" / "superset_runtime" / "templates" / "runtime.env.j2"
ENV_CTEMPLATE = REPO_ROOT / "roles" / "superset_runtime" / "templates" / "superset.env.ctmpl.j2"
CONFIG_TEMPLATE = REPO_ROOT / "roles" / "superset_runtime" / "templates" / "superset_config.py.j2"
BOOTSTRAP_TEMPLATE = REPO_ROOT / "roles" / "superset_runtime" / "templates" / "bootstrap-definition.json.j2"
DOCKERFILE = REPO_ROOT / "roles" / "superset_runtime" / "templates" / "Dockerfile.j2"
REQUIREMENTS = REPO_ROOT / "roles" / "superset_runtime" / "templates" / "requirements.txt.j2"
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "superset_bootstrap.py"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def load_bootstrap_module():
    spec = importlib.util.spec_from_file_location("superset_bootstrap", BOOTSTRAP_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_defaults_define_runtime_paths_keycloak_and_landing_dashboard_contract() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["superset_service_topology"] == "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('superset') }}"
    assert defaults["superset_site_dir"] == "/opt/superset"
    assert defaults["superset_build_dir"] == "{{ superset_site_dir }}/build"
    assert defaults["superset_data_dir"] == "{{ superset_site_dir }}/data"
    assert defaults["superset_pythonpath_dir"] == "{{ superset_site_dir }}/pythonpath"
    assert defaults["superset_asset_dir"] == "{{ superset_site_dir }}/assets"
    assert defaults["superset_static_env_file"] == "{{ superset_site_dir }}/runtime.env"
    assert defaults["superset_public_base_url"] == "https://{{ superset_service_topology.public_hostname }}"
    assert defaults["superset_image_name"] == "lv3/superset"
    assert defaults["superset_internal_port"] == "{{ hostvars['proxmox_florin'].platform_port_assignments.superset_port }}"
    assert defaults["superset_controller_bootstrap_script_local_path"] == "{{ inventory_dir ~ '/../scripts/superset_bootstrap.py' }}"
    assert defaults["superset_keycloak_client_id"] == "superset"
    assert defaults["superset_landing_dataset_name"] == "platform_database_inventory"
    assert defaults["superset_landing_chart_title"] == "PostgreSQL Databases"
    assert defaults["superset_landing_dashboard_title"] == "LV3 Platform Database Inventory"
    assert defaults["superset_register_plausible_clickhouse"] is True
    assert defaults["superset_plausible_clickhouse_name"] == "Plausible ClickHouse"
    assert "authlib==1.6.9" in defaults["superset_python_dependencies"]


def test_argument_spec_requires_runtime_paths_and_bootstrap_inputs() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["superset_site_dir"]["type"] == "path"
    assert options["superset_static_env_file"]["type"] == "path"
    assert options["superset_internal_port"]["type"] == "int"
    assert options["superset_public_base_url"]["type"] == "str"
    assert options["superset_database_password_local_file"]["type"] == "path"
    assert options["superset_reader_password_local_file"]["type"] == "path"
    assert options["superset_postgres_database_catalog_local_file"]["type"] == "path"
    assert options["superset_controller_bootstrap_script_local_path"]["type"] == "path"


def test_main_tasks_render_build_bootstrap_and_verify_runtime() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Render the Superset environment file" in names
    assert "Render the Superset bootstrap definition" in names
    assert "Render the Superset compose file" in names
    assert "Render the Superset Dockerfile" in names
    assert "Render the Superset config module" in names
    assert "Copy the Superset bootstrap helper into the mounted Python path" in names
    assert "Ensure the Superset base image is cached locally" in names
    assert "Build the Superset image" in names
    assert "Force-recreate the Superset runtime stack after Docker networking recovery" in names
    assert "Bootstrap the Superset datasource inventory and landing dashboard" in names
    assert "Verify the Superset runtime" in names

    bootstrap_task = next(task for task in tasks if task["name"] == "Bootstrap the Superset datasource inventory and landing dashboard")
    assert bootstrap_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "exec",
        "-u",
        "0",
        "{{ superset_container_name }}",
        "/app/.venv/bin/python",
        "{{ superset_bootstrap_script_container_file }}",
        "bootstrap-local",
        "--definition-file",
        "{{ superset_bootstrap_definition_container_file }}",
    ]
    assert "(superset_bootstrap.rc | default(1)) == 0" in bootstrap_task["changed_when"]
    assert "(superset_bootstrap.stdout_lines | default([]) | length) > 0" in bootstrap_task["changed_when"]
    assert "(superset_bootstrap.stdout_lines | last)" in bootstrap_task["changed_when"]
    assert "from_json" in bootstrap_task["changed_when"]

    db_upgrade_task = next(task for task in tasks if task["name"] == "Run the Superset metadata database migrations")
    assert db_upgrade_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "exec",
        "{{ superset_container_name }}",
        "/app/.venv/bin/superset",
        "db",
        "upgrade",
    ]

    admin_check_task = next(task for task in tasks if task["name"] == "Check whether the Superset admin user already exists")
    admin_check_script = admin_check_task["ansible.builtin.command"]["argv"][5]
    assert "with app.app_context():" in admin_check_script
    assert "app = create_app()" in admin_check_script
    assert "create_app();" not in admin_check_script

    admin_create_task = next(task for task in tasks if task["name"] == "Create the Superset admin user")
    assert admin_create_task["ansible.builtin.command"]["argv"][3:6] == [
        "/app/.venv/bin/superset",
        "fab",
        "create-admin",
    ]

    force_recreate = next(task for task in tasks if task["name"] == "Force-recreate the Superset runtime stack after Docker networking recovery")
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
    assert force_recreate["until"] == "superset_force_recreate_up.rc == 0"


def test_verify_tasks_cover_local_health_and_managed_contract() -> None:
    verify = load_yaml(ROLE_VERIFY)
    health_task = next(task for task in verify if task["name"] == "Verify the Superset health endpoint locally")
    contract_task = next(task for task in verify if task["name"] == "Verify the managed Superset datasources and landing dashboard locally")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ superset_internal_base_url }}/health"
    assert contract_task["ansible.builtin.command"]["argv"] == [
        "docker",
        "exec",
        "-u",
        "0",
        "{{ superset_container_name }}",
        "/app/.venv/bin/python",
        "{{ superset_bootstrap_script_container_file }}",
        "verify-local",
        "--base-url",
        "http://127.0.0.1:{{ superset_container_port }}",
        "--definition-file",
        "{{ superset_bootstrap_definition_container_file }}",
        "--report-file",
        "{{ superset_verify_report_container_file }}",
    ]


def test_publish_tasks_verify_public_health_redirect_and_api_contract() -> None:
    publish = load_yaml(ROLE_PUBLISH)
    health_task = next(task for task in publish if task["name"] == "Wait for the Superset public health endpoint")
    verify_task = next(task for task in publish if task["name"] == "Verify the public Superset publication and Keycloak redirect contract")

    assert health_task["ansible.builtin.uri"]["url"] == "{{ superset_public_base_url }}/health"
    assert verify_task["ansible.builtin.command"]["argv"][0:5] == [
        "python3",
        "{{ superset_controller_bootstrap_script_local_path }}",
        "verify-public",
        "--base-url",
        "{{ superset_public_base_url }}",
    ]
    assert "--expected-extra-database" in verify_task["ansible.builtin.command"]["argv"]


def test_templates_define_openbao_envs_compose_and_bootstrap_contract() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()
    env_template = ENV_TEMPLATE.read_text()
    env_ctemplate = ENV_CTEMPLATE.read_text()
    config_template = CONFIG_TEMPLATE.read_text()
    bootstrap_template = BOOTSTRAP_TEMPLATE.read_text()
    dockerfile = DOCKERFILE.read_text()
    requirements = REQUIREMENTS.read_text()

    assert "image: {{ superset_image_name }}:latest" in compose_template
    assert "{{ superset_data_dir }}:/app/superset_home" in compose_template
    assert "{{ superset_pythonpath_dir }}:/app/pythonpath:ro" in compose_template
    assert "{{ superset_asset_dir }}:/app/assets:ro" in compose_template
    assert "http://127.0.0.1:{{ superset_container_port }}/health" in compose_template
    assert "- {{ superset_static_env_file }}" in compose_template
    assert "- {{ superset_env_file }}" in compose_template

    assert "SUPERSET_CONFIG_PATH=/app/pythonpath/superset_config.py" in env_template
    assert "SUPERSET_KEYCLOAK_CLIENT_ID={{ superset_keycloak_client_id }}" in env_template
    assert "SUPERSET_AUTH_ROLES_MAPPING_JSON={{ superset_auth_roles_mapping | to_json }}" in env_template

    assert 'kv/data/{{ superset_openbao_secret_path }}' in env_ctemplate
    assert "SUPERSET_DATABASE_URI" in env_ctemplate
    assert "SUPERSET_KEYCLOAK_CLIENT_SECRET" in env_ctemplate

    assert "AUTH_API_LOGIN_ALLOW_MULTIPLE_PROVIDERS = True" in config_template
    assert 'AUTH_TYPE = AUTH_OAUTH' in config_template
    assert '"name": "keycloak"' in config_template
    assert "AUTH_ROLES_MAPPING = json.loads" in config_template

    assert '"name": "{{ superset_plausible_clickhouse_name }}"' in bootstrap_template
    assert '"dataset_name": "{{ superset_landing_dataset_name }}"' in bootstrap_template
    assert '"dashboard_title": "{{ superset_landing_dashboard_title }}"' in bootstrap_template

    assert "FROM {{ superset_base_image }}" in dockerfile
    assert "/app/.venv/bin/python -m ensurepip --default-pip" in dockerfile
    assert "/app/.venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt" in dockerfile
    assert "{% for dependency in superset_python_dependencies %}" in requirements
    assert "{{ dependency }}" in requirements


def test_bootstrap_script_sets_chart_fields_before_flush() -> None:
    script = BOOTSTRAP_SCRIPT.read_text()

    assert "with db.session.no_autoflush:" in script
    assert script.index('chart.datasource_type = "table"') < script.index("chart.datasource_id = dataset.id")
    assert "dashboard.slices = [chart]" in script


def test_bootstrap_script_reconciles_named_children_in_place() -> None:
    module = load_bootstrap_module()

    class DummyItem:
        def __init__(self, name: str, **attrs) -> None:
            self.column_name = name
            for key, value in attrs.items():
                setattr(self, key, value)

    items = [
        DummyItem("database_name", type="OLD", verbose_name="Old"),
        DummyItem("database_name", type="DUPLICATE"),
        DummyItem("legacy_column", type="TEXT"),
    ]
    removed: list[str] = []

    def remove_item(item) -> None:
        removed.append(item.column_name)
        items.remove(item)

    result = module.reconcile_named_collection(
        items,
        [
            {
                "name": "database_name",
                "type": "TEXT",
                "verbose_name": "Database Name",
                "groupby": True,
                "filterable": True,
                "is_dttm": False,
            },
            {
                "name": "workspace_name",
                "type": "TEXT",
                "verbose_name": "Workspace Name",
                "groupby": True,
                "filterable": True,
                "is_dttm": False,
            },
        ],
        key_attr="column_name",
        make_item=lambda: DummyItem(""),
        apply_spec=module.apply_table_column_spec,
        remove_item=remove_item,
    )

    assert [item.column_name for item in items] == ["database_name", "workspace_name"]
    assert items[0].type == "TEXT"
    assert items[0].verbose_name == "Database Name"
    assert removed == ["database_name", "legacy_column"]
    assert result == {
        "created": ["workspace_name"],
        "removed": ["legacy_column"],
        "deduped": ["database_name"],
    }


def test_bootstrap_script_reconciles_metrics_without_clear_and_rebuild() -> None:
    script = BOOTSTRAP_SCRIPT.read_text()

    assert "reconcile_named_collection(" in script
    assert "dataset.columns.clear()" not in script
    assert "dataset.metrics.clear()" not in script
