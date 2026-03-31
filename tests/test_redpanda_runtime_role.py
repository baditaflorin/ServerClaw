from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "redpanda_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "redpanda_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "redpanda_runtime" / "tasks" / "verify.yml"
ROLE_META = REPO_ROOT / "roles" / "redpanda_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "redpanda_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = REPO_ROOT / "roles" / "redpanda_runtime" / "templates" / "runtime.env.ctmpl.j2"
BOOTSTRAP_TEMPLATE = REPO_ROOT / "roles" / "redpanda_runtime" / "templates" / "bootstrap.yml.j2"
START_TEMPLATE = REPO_ROOT / "roles" / "redpanda_runtime" / "templates" / "start-redpanda.sh.j2"


def test_defaults_define_private_redpanda_runtime_contract() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["redpanda_service_topology"] == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service('redpanda') }}"
    assert defaults["redpanda_site_dir"] == "/opt/redpanda"
    assert defaults["redpanda_compose_file"] == "{{ redpanda_site_dir }}/docker-compose.yml"
    assert defaults["redpanda_image"] == "{{ container_image_catalog.images.redpanda_runtime.ref }}"
    assert defaults["redpanda_admin_user"] == "redpanda-admin"
    assert defaults["redpanda_platform_user"] == "redpanda-platform"
    assert defaults["redpanda_smoke_topic"] == "platform.redpanda.smoke"
    assert defaults["redpanda_schema_subject"] == "platform.redpanda.smoke-value"
    assert defaults["redpanda_admin_api_url"] == "{{ redpanda_service_topology.urls.admin }}"
    assert defaults["redpanda_http_proxy_url"] == "{{ redpanda_service_topology.urls.http_proxy }}"
    assert defaults["redpanda_schema_registry_url"] == "{{ redpanda_service_topology.urls.schema_registry }}"


def test_argument_spec_requires_ports_passwords_and_topic_contract() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["redpanda_admin_password_local_file"]["type"] == "path"
    assert options["redpanda_platform_password_local_file"]["type"] == "path"
    assert options["redpanda_kafka_port"]["type"] == "int"
    assert options["redpanda_admin_port"]["type"] == "int"
    assert options["redpanda_pandaproxy_port"]["type"] == "int"
    assert options["redpanda_schema_registry_port"]["type"] == "int"
    assert options["redpanda_topics"]["type"] == "list"
    assert options["redpanda_schema_definition"]["type"] == "dict"


def test_main_tasks_prepare_users_topics_and_schema() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Prepare OpenBao agent runtime secret injection for Redpanda" in names
    assert "Ensure the Redpanda runtime env file exists before compose evaluation" in names
    assert "Render the Redpanda bootstrap cluster properties" in names
    assert "Render the Redpanda start script" in names
    assert "Render the Redpanda compose file" in names
    assert "Create the Redpanda platform principal" in names
    assert "Create the declared Redpanda topics when missing" in names
    assert "Grant the Redpanda platform principal access to the smoke topic family" in names
    assert "Register the Redpanda smoke schema when missing or outdated" in names
    assert "Verify the Redpanda runtime" in names

    create_user = next(task for task in tasks if task["name"] == "Create the Redpanda platform principal")
    assert create_user["when"] == "redpanda_platform_user not in redpanda_user_list.stdout_lines"

    topic_acl = next(task for task in tasks if task["name"] == "Grant the Redpanda platform principal access to the smoke topic family")
    acl_argv = topic_acl["ansible.builtin.command"]["argv"]
    assert "--resource-pattern-type" in acl_argv
    assert "prefixed" in acl_argv

    directory_task = next(task for task in tasks if task["name"] == "Ensure the Redpanda runtime directories exist")
    config_dir = next(item for item in directory_task["loop"] if item["path"] == "{{ redpanda_config_dir }}")
    assert config_dir["owner"] == "101"
    assert config_dir["group"] == "101"
    assert config_dir["mode"] == "0750"

    bootstrap_task = next(task for task in tasks if task["name"] == "Render the Redpanda bootstrap cluster properties")
    assert bootstrap_task["ansible.builtin.template"]["owner"] == "101"
    assert bootstrap_task["ansible.builtin.template"]["group"] == "101"
    assert bootstrap_task["ansible.builtin.template"]["mode"] == "0640"

    start_task = next(task for task in tasks if task["name"] == "Render the Redpanda start script")
    assert start_task["ansible.builtin.template"]["owner"] == "101"
    assert start_task["ansible.builtin.template"]["group"] == "101"


def test_verify_tasks_exercise_http_proxy_and_schema_registry() -> None:
    tasks = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in tasks]

    assert "Verify the Redpanda admin ready endpoint responds" in names
    assert "Produce a Redpanda HTTP Proxy smoke record" in names
    assert "Read Redpanda smoke records through the HTTP Proxy" in names
    assert "Read the Redpanda smoke schema subject" in names
    assert "Assert the Redpanda runtime contract" in names

    produce_task = next(task for task in tasks if task["name"] == "Produce a Redpanda HTTP Proxy smoke record")
    assert produce_task["ansible.builtin.uri"]["url"] == "{{ redpanda_http_proxy_url }}/topics/{{ redpanda_smoke_topic }}"

    schema_task = next(task for task in tasks if task["name"] == "Read the Redpanda smoke schema subject")
    assert "{{ redpanda_schema_registry_url }}/subjects/{{ redpanda_schema_subject | urlencode }}/versions/latest" in schema_task["ansible.builtin.uri"]["url"]


def test_templates_define_bootstrap_env_and_host_network_runtime() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()
    env_template = ENV_TEMPLATE.read_text()
    bootstrap_template = BOOTSTRAP_TEMPLATE.read_text()
    start_template = START_TEMPLATE.read_text()

    assert "network_mode: host" in compose_template
    assert "name: {{ redpanda_volume_name }}" in compose_template
    assert "entrypoint:" in compose_template
    assert "      - /bin/bash" in compose_template
    assert "      - /etc/redpanda/start-redpanda.sh" in compose_template
    assert "REDPANDA_ADMIN_PASSWORD" in env_template
    assert "REDPANDA_PLATFORM_PASSWORD" in env_template
    assert "http_authentication:" in bootstrap_template
    assert "auto_create_topics_enabled: false" in bootstrap_template
    assert "kafka_enable_authorization: true" in start_template
    assert "schema_registry_client:" in start_template
    assert "export RP_BOOTSTRAP_USER=" in start_template
    assert "exec redpanda \\" in start_template
    assert "--redpanda-cfg /etc/redpanda/redpanda.yaml" in start_template
    assert "redpanda start" not in start_template
    assert "--check=false" not in start_template
