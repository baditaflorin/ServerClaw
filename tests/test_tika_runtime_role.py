from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "tika_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "tika_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "tika_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "tika_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "tika_runtime" / "templates" / "docker-compose.yml.j2"


def test_defaults_define_private_tika_listener_and_fixture() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["tika_runtime_site_dir"] == "/opt/tika"
    assert defaults["tika_runtime_container_name"] == "tika"
    assert defaults["tika_runtime_java_opts"] == "-Xms256m -Xmx1024m"
    assert "Hello Tika" in defaults["tika_runtime_verify_html_fixture"]


def test_argument_spec_requires_core_runtime_inputs() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["tika_runtime_port"]["type"] == "int"
    assert options["tika_runtime_base_url"]["type"] == "str"
    assert options["tika_runtime_verify_html_fixture"]["type"] == "str"


def test_main_tasks_render_pull_start_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Render the Apache Tika compose file" in names
    assert "Pull the Apache Tika image" in names
    assert "Start the Apache Tika runtime" in names
    assert "Wait for Apache Tika to listen locally" in names
    assert "Verify the Apache Tika runtime" in names


def test_verify_tasks_cover_version_text_and_metadata_contracts() -> None:
    verify = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in verify]

    assert "Verify the Apache Tika version endpoint responds" in names
    assert "Verify Apache Tika extracts plaintext from the HTML fixture" in names
    assert "Verify Apache Tika returns JSON metadata for the HTML fixture" in names

    text_task = next(
        task for task in verify if task["name"] == "Verify Apache Tika extracts plaintext from the HTML fixture"
    )
    assert text_task["ansible.builtin.uri"]["headers"]["Accept"] == "text/plain"
    assert text_task["ansible.builtin.uri"]["url"] == "{{ tika_runtime_base_url }}/tika"

    meta_task = next(
        task for task in verify if task["name"] == "Verify Apache Tika returns JSON metadata for the HTML fixture"
    )
    assert meta_task["ansible.builtin.uri"]["headers"]["Accept"] == "application/json"
    assert meta_task["ansible.builtin.uri"]["url"] == "{{ tika_runtime_base_url }}/meta"


def test_compose_template_publishes_private_port_with_bounded_jvm() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert 'container_name: {{ tika_runtime_container_name }}' in template
    assert '"{{ tika_runtime_port }}:9998"' in template
    assert "JDK_JAVA_OPTIONS" in template


def test_host_network_policy_allows_private_tika_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text())
    assert host_vars["platform_port_assignments"]["tika_port"] == 9998
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    guest_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 9998 in rule["ports"]
    )
    assert 9998 in guest_rule["ports"]
