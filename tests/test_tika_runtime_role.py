from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "tika_runtime" / "tasks" / "main.yml"
VERIFY_TASKS = REPO_ROOT / "roles" / "tika_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "tika_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "tika_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "tika_runtime" / "templates" / "docker-compose.yml.j2"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_verify_tasks() -> list[dict]:
    return yaml.safe_load(VERIFY_TASKS.read_text())


def test_role_defaults_pin_the_standard_tika_listener() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())
    assert defaults["tika_runtime_site_dir"] == "/opt/tika"
    assert defaults["tika_runtime_container_name"] == "tika"
    assert defaults["tika_runtime_port"] == "{{ platform_port_assignments.tika_port }}"
    assert defaults["tika_runtime_base_url"] == "http://127.0.0.1:{{ tika_runtime_port }}"
    assert defaults["tika_runtime_container_port"] == 9998
    assert defaults["tika_runtime_sample_text"] == "Hello from Apache Tika.\n"
    assert defaults["tika_runtime_java_opts"] == "-Xms256m -Xmx1024m"
    assert "Hello Tika" in defaults["tika_runtime_verify_html_fixture"]


def test_argument_spec_requires_core_runtime_inputs() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["tika_runtime_port"]["type"] == "int"
    assert options["tika_runtime_base_url"]["type"] == "str"
    assert options["tika_runtime_container_port"]["type"] == "int"
    assert options["tika_runtime_sample_text"]["type"] == "str"
    assert options["tika_runtime_verify_html_fixture"]["type"] == "str"


def test_role_recovers_missing_docker_nat_chain_before_startup() -> None:
    tasks = load_tasks()
    precheck_task = next(
        task for task in tasks if task.get("name") == "Check whether Docker nat chain exists before Tika startup"
    )
    assert precheck_task["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]

    reset_task = next(
        task for task in tasks if task.get("name") == "Reset Docker failed state before nat-chain recovery restart"
    )
    assert reset_task["ansible.builtin.command"] == "systemctl reset-failed docker.service"
    assert reset_task["changed_when"] is False

    start_block = next(
        task
        for task in tasks
        if task.get("name") == "Start the Apache Tika runtime and recover Docker nat-chain and compose-network failures"
    )
    rescue_names = [task["name"] for task in start_block["rescue"]]
    recovery_fact = next(
        task
        for task in start_block["rescue"]
        if task.get("name") == "Flag Docker nat-chain and stale compose-network failures during Tika startup"
    )
    assert "Reset Docker failed state before nat-chain recovery restart" in [task["name"] for task in tasks]
    assert "Reset Docker failed state before nat-chain recovery retry" in rescue_names
    assert "Restart Docker to restore nat chain before retrying Tika startup" in rescue_names
    assert "Reset stale Tika compose resources after startup failure" in rescue_names
    assert "Retry Tika startup after Docker nat-chain or compose-network recovery" in rescue_names
    assert (
        "failed to create endpoint" in recovery_fact["ansible.builtin.set_fact"]["tika_runtime_compose_network_missing"]
    )


def test_role_force_recreates_tika_when_port_binding_is_missing() -> None:
    tasks = load_tasks()
    port_check = next(
        task for task in tasks if task.get("name") == "Check whether Tika publishes the expected host port"
    )
    assert port_check["ansible.builtin.command"]["argv"] == [
        "docker",
        "port",
        "{{ tika_runtime_container_name }}",
        "{{ tika_runtime_container_port }}",
    ]

    recreate_block = next(
        task
        for task in tasks
        if task.get("name")
        == "Force-recreate Tika when the host port binding is missing and recover stale compose-network drift"
    )
    recreate_task = next(
        task
        for task in recreate_block["block"]
        if task.get("name") == "Force-recreate Tika when the host port binding is missing"
    )
    rescue_names = [task["name"] for task in recreate_block["rescue"]]
    assert "--force-recreate" in recreate_task["ansible.builtin.command"]["argv"]
    assert "Reset stale Tika compose resources after force-recreate failure" in rescue_names
    assert "Retry Tika force-recreate after compose-network recovery" in rescue_names


def test_verify_tasks_cover_plaintext_and_metadata_extraction() -> None:
    tasks = load_verify_tasks()
    names = [task["name"] for task in tasks]

    assert "Verify the Apache Tika version endpoint responds" in names
    assert "Verify Apache Tika extracts plaintext from the HTML fixture" in names
    assert "Verify Apache Tika returns JSON metadata for the HTML fixture" in names

    text_task = next(
        task for task in tasks if task.get("name") == "Verify Apache Tika extracts plaintext from the HTML fixture"
    )
    meta_task = next(
        task for task in tasks if task.get("name") == "Verify Apache Tika returns JSON metadata for the HTML fixture"
    )
    meta_assert_task = next(
        task for task in tasks if task.get("name") == "Assert Apache Tika returned metadata for the fixture"
    )

    assert text_task["ansible.builtin.uri"]["url"] == "{{ tika_runtime_base_url }}/tika"
    assert text_task["ansible.builtin.uri"]["headers"]["Accept"] == "text/plain"
    assert meta_task["ansible.builtin.uri"]["url"] == "{{ tika_runtime_base_url }}/meta"
    assert meta_task["ansible.builtin.uri"]["headers"]["Accept"] == "application/json"
    assert (
        "tika_runtime_verify_meta_payload['Content-Type'] is defined"
        in meta_assert_task["ansible.builtin.assert"]["that"]
    )
    assert (
        "tika_runtime_verify_meta_payload['Content-Type'] is match('^text/html(;.*)?$')"
        in meta_assert_task["ansible.builtin.assert"]["that"]
    )


def test_compose_template_exposes_the_private_tika_port() -> None:
    template = COMPOSE_TEMPLATE.read_text()
    assert '"{{ tika_runtime_port }}:{{ tika_runtime_container_port }}"' in template
    assert "JDK_JAVA_OPTIONS" in template


def test_host_network_policy_allows_private_tika_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text())
    runtime_ai_rules = host_vars["network_policy"]["guests"]["runtime-ai"]["allowed_inbound"]
    guest_rule = next(rule for rule in runtime_ai_rules if rule["source"] == "all_guests" and 9998 in rule["ports"])
    assert 9998 in guest_rule["ports"]
    host_rule = next(rule for rule in runtime_ai_rules if rule["source"] == "host" and 9998 in rule["ports"])
    assert 9998 in host_rule["ports"]
