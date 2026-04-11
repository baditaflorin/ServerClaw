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

    assert (
        defaults["redpanda_service_topology"]
        == "{{ hostvars['proxmox-host'].platform_service_topology | platform_service('redpanda') }}"
    )
    assert defaults["redpanda_site_dir"] == "/opt/redpanda"
    assert defaults["redpanda_compose_file"] == "{{ redpanda_site_dir }}/docker-compose.yml"
    assert defaults["redpanda_image"] == "{{ container_image_catalog.images.redpanda_runtime.ref }}"
    assert defaults["redpanda_admin_user"] == "redpanda-admin"
    assert defaults["redpanda_platform_user"] == "redpanda-platform"
    assert defaults["redpanda_smoke_topic"] == "platform.redpanda.smoke"
    assert defaults["redpanda_schema_subject"] == "platform.redpanda.smoke-value"
    assert defaults["redpanda_storage_min_free_bytes"] == 1073741824
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
    assert options["redpanda_storage_min_free_bytes"]["type"] == "int"
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
    assert "Inspect the existing Redpanda container state" in names
    assert "Inspect the Redpanda data volume mountpoint" in names
    assert "Check for the Redpanda crash-tracker startup log" in names
    assert "Flag whether Redpanda needs recovery cleanup" in names
    assert "Flag whether Redpanda requires a forced recreate" in names
    assert "Build the Redpanda compose startup command" in names
    assert "Reset the Redpanda compose stack before recovery cleanup" in names
    assert "Clear the Redpanda crash-tracker startup log before restart" in names
    assert "Read the active Redpanda minimum free storage cluster setting" in names
    assert "Reconcile the Redpanda minimum free storage cluster setting" in names
    assert "Confirm the Redpanda minimum free storage cluster setting" in names
    assert "Create the Redpanda platform principal" in names
    assert "Create the declared Redpanda topics when missing" in names
    assert "Grant the Redpanda platform principal access to the smoke topic family" in names
    assert "Register the Redpanda smoke schema when missing or outdated" in names
    assert "Verify the Redpanda runtime" in names

    create_user = next(task for task in tasks if task["name"] == "Create the Redpanda platform principal")
    assert create_user["when"] == "redpanda_platform_user not in redpanda_user_list.stdout_lines"

    topic_acl = next(
        task
        for task in tasks
        if task["name"] == "Grant the Redpanda platform principal access to the smoke topic family"
    )
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
    assert bootstrap_task["register"] == "redpanda_bootstrap_template"

    start_task = next(task for task in tasks if task["name"] == "Render the Redpanda start script")
    assert start_task["ansible.builtin.template"]["owner"] == "101"
    assert start_task["ansible.builtin.template"]["group"] == "101"
    assert start_task["register"] == "redpanda_start_script_template"

    compose_task = next(task for task in tasks if task["name"] == "Render the Redpanda compose file")
    assert compose_task["register"] == "redpanda_compose_template"

    container_inspect = next(task for task in tasks if task["name"] == "Inspect the existing Redpanda container state")
    assert container_inspect["ansible.builtin.command"]["argv"][:3] == ["docker", "inspect", "--format"]
    assert container_inspect["changed_when"] is False
    assert container_inspect["failed_when"] is False

    volume_inspect = next(task for task in tasks if task["name"] == "Inspect the Redpanda data volume mountpoint")
    assert volume_inspect["ansible.builtin.command"]["argv"][:4] == ["docker", "volume", "inspect", "--format"]
    assert volume_inspect["failed_when"] is False

    startup_log = next(task for task in tasks if task["name"] == "Check for the Redpanda crash-tracker startup log")
    assert startup_log["when"] == "redpanda_volume_inspect.rc == 0"

    recovery_fact = next(task for task in tasks if task["name"] == "Flag whether Redpanda needs recovery cleanup")
    assert (
        "redpanda_container_inspect.rc == 0" in recovery_fact["ansible.builtin.set_fact"]["redpanda_recovery_required"]
    )
    assert (
        "redpanda_container_inspect.stdout != 'healthy'"
        in recovery_fact["ansible.builtin.set_fact"]["redpanda_recovery_required"]
    )

    recreate_fact = next(task for task in tasks if task["name"] == "Flag whether Redpanda requires a forced recreate")
    recreate_expr = recreate_fact["ansible.builtin.set_fact"]["redpanda_force_recreate_required"]
    assert "redpanda_bootstrap_template.changed" in recreate_expr
    assert "redpanda_start_script_template.changed" in recreate_expr
    assert "redpanda_compose_template.changed" in recreate_expr
    assert "redpanda_recovery_required" in recreate_expr
    assert "redpanda_startup_log.stat.exists" in recreate_expr

    compose_up = next(task for task in tasks if task["name"] == "Build the Redpanda compose startup command")
    assert "redpanda_compose_up_argv" in compose_up["ansible.builtin.set_fact"]
    assert "--force-recreate" in compose_up["ansible.builtin.set_fact"]["redpanda_compose_up_argv"]

    reset_task = next(
        task for task in tasks if task["name"] == "Reset the Redpanda compose stack before recovery cleanup"
    )
    assert reset_task["ansible.builtin.command"]["argv"][-2:] == ["down", "--remove-orphans"]
    assert reset_task["failed_when"] is False
    assert reset_task["when"] == "redpanda_recovery_required or (redpanda_startup_log.stat.exists | default(false))"

    clear_task = next(
        task for task in tasks if task["name"] == "Clear the Redpanda crash-tracker startup log before restart"
    )
    assert clear_task["ansible.builtin.file"]["state"] == "absent"
    assert clear_task["when"] == "redpanda_startup_log.stat.exists | default(false)"

    startup_task = next(task for task in tasks if task["name"] == "Start the Redpanda stack")
    assert startup_task["ansible.builtin.command"]["argv"] == "{{ redpanda_compose_up_argv }}"

    storage_get = next(
        task for task in tasks if task["name"] == "Read the active Redpanda minimum free storage cluster setting"
    )
    assert storage_get["ansible.builtin.command"]["argv"][:7] == [
        "docker",
        "exec",
        "{{ redpanda_container_name }}",
        "rpk",
        "cluster",
        "config",
        "get",
    ]
    assert storage_get["changed_when"] is False

    storage_set = next(
        task for task in tasks if task["name"] == "Reconcile the Redpanda minimum free storage cluster setting"
    )
    assert storage_set["ansible.builtin.command"]["argv"][:7] == [
        "docker",
        "exec",
        "{{ redpanda_container_name }}",
        "rpk",
        "cluster",
        "config",
        "set",
    ]
    assert "storage_min_free_bytes" in storage_set["ansible.builtin.command"]["argv"]
    assert "redpanda_storage_min_free_bytes_current.stdout | trim" in storage_set["when"]

    storage_confirm = next(
        task for task in tasks if task["name"] == "Confirm the Redpanda minimum free storage cluster setting"
    )
    assert storage_confirm["retries"] == 12
    assert storage_confirm["delay"] == 2
    assert "redpanda_storage_min_free_bytes_effective.stdout | trim" in storage_confirm["until"]
    assert storage_confirm["changed_when"] is False


def test_verify_tasks_exercise_http_proxy_and_schema_registry() -> None:
    tasks = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in tasks]

    assert "Verify the Redpanda admin ready endpoint responds" in names
    assert "Produce a Redpanda HTTP Proxy smoke record" in names
    assert "Assert the Redpanda HTTP Proxy smoke produce request succeeded" in names
    assert "Read Redpanda smoke records through the HTTP Proxy" in names
    assert "Read the Redpanda smoke schema subject" in names
    assert "Assert the Redpanda runtime contract" in names

    produce_task = next(task for task in tasks if task["name"] == "Produce a Redpanda HTTP Proxy smoke record")
    assert (
        produce_task["ansible.builtin.uri"]["url"] == "{{ redpanda_http_proxy_url }}/topics/{{ redpanda_smoke_topic }}"
    )
    assert produce_task["ansible.builtin.uri"]["return_content"] is True

    produce_assert = next(
        task for task in tasks if task["name"] == "Assert the Redpanda HTTP Proxy smoke produce request succeeded"
    )
    produce_conditions = produce_assert["ansible.builtin.assert"]["that"]
    assert "redpanda_produce_result.content | from_json" in produce_conditions[0]
    assert "error_code" in produce_conditions[1]
    assert "offset" in produce_conditions[2]

    read_task = next(task for task in tasks if task["name"] == "Read Redpanda smoke records through the HTTP Proxy")
    assert (
        read_task["ansible.builtin.uri"]["url"]
        == "{{ redpanda_http_proxy_url }}/topics/{{ redpanda_smoke_topic }}/partitions/0/records?offset=0&timeout=3000&max_bytes=1048576"
    )
    assert read_task["ansible.builtin.uri"]["return_content"] is True
    until_expr = read_task["until"]
    assert "redpanda_verify_marker in" in until_expr
    assert "redpanda_records_result.content | default('[]', true) | from_json" in until_expr
    assert "map(attribute='marker')" in until_expr
    assert "no_log" not in read_task

    payload_task = next(task for task in tasks if task["name"] == "Parse the Redpanda smoke record payload")
    assert (
        payload_task["ansible.builtin.set_fact"]["redpanda_records_payload"]
        == "{{ redpanda_records_result.content | default('[]', true) | from_json }}"
    )

    schema_task = next(task for task in tasks if task["name"] == "Read the Redpanda smoke schema subject")
    assert (
        "{{ redpanda_schema_registry_url }}/subjects/{{ redpanda_schema_subject | urlencode }}/versions/latest"
        in schema_task["ansible.builtin.uri"]["url"]
    )
    assert schema_task["ansible.builtin.uri"]["return_content"] is True

    assert_task = next(task for task in tasks if task["name"] == "Assert the Redpanda runtime contract")
    conditions = assert_task["ansible.builtin.assert"]["that"]
    assert "redpanda_schema_result.content | from_json" in conditions[3]


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
    assert "storage_min_free_bytes: {{ redpanda_storage_min_free_bytes }}" in start_template
    assert "schema_registry_client:" in start_template
    assert "export RP_BOOTSTRAP_USER=" in start_template
    assert "runtime_config_file=/tmp/redpanda.yaml" in start_template
    assert "exec redpanda \\" in start_template
    assert '--redpanda-cfg "${runtime_config_file}"' in start_template
    assert "sasl_mechanism: ${REDPANDA_SASL_MECHANISM}" in start_template
    assert "scram_password: ${REDPANDA_ADMIN_PASSWORD}" in start_template
    assert "\\${REDPANDA_" not in start_template
    assert "redpanda start" not in start_template
    assert "--check=false" not in start_template
