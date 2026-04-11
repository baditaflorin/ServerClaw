from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "mailpit_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "mailpit_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "mailpit_runtime" / "tasks" / "verify.yml"
ROLE_META = REPO_ROOT / "roles" / "mailpit_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "mailpit_runtime" / "templates" / "docker-compose.yml.j2"


def test_defaults_define_private_mailpit_runtime_contract() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert (
        defaults["mailpit_service_topology"]
        == "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service('mailpit') }}"
    )
    assert defaults["mailpit_site_dir"] == "/opt/dev-tools/mailpit"
    assert defaults["mailpit_compose_file"] == "{{ mailpit_site_dir }}/docker-compose.yml"
    assert defaults["mailpit_container_name"] == "mailpit"
    assert defaults["mailpit_image"] == "{{ container_image_catalog.images.mailpit_runtime.ref }}"
    assert defaults["mailpit_http_port"] == "{{ mailpit_service_topology.ports.internal }}"
    assert defaults["mailpit_smtp_port"] == "{{ mailpit_service_topology.ports.smtp }}"
    assert defaults["mailpit_api_url"] == "{{ mailpit_service_topology.urls.internal }}/api/v1"
    assert defaults["mailpit_docker_network_name"] == "dev-tools_default"
    assert defaults["mailpit_test_from_address"] == "mailpit-probe@lv3.org"
    assert defaults["mailpit_test_to_address"] == "dev-mail@lv3.org"


def test_argument_spec_requires_private_listener_and_probe_inputs() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["mailpit_http_port"]["type"] == "int"
    assert options["mailpit_smtp_port"]["type"] == "int"
    assert options["mailpit_bind_host"]["type"] == "str"
    assert options["mailpit_loopback_bind_host"]["type"] == "str"
    assert options["mailpit_docker_network_name"]["type"] == "str"
    assert options["mailpit_test_subject_prefix"]["type"] == "str"


def test_main_tasks_render_pull_wait_and_verify_mailpit() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Render the Mailpit compose file" in names
    assert "Pull the Mailpit image" in names
    assert "Check whether the Docker nat chain exists before recreating Mailpit published ports" in names
    assert "Build the Mailpit compose startup command" in names
    assert "Start the Mailpit stack with stale-network recovery" in names
    assert "Wait for the Mailpit HTTP listener" in names
    assert "Wait for the Mailpit SMTP listener" in names
    assert "Verify the Mailpit runtime" in names

    info_probe = next(
        task
        for task in tasks
        if task["name"] == "Check whether the current Mailpit info endpoint is healthy before startup"
    )
    assert info_probe["ansible.builtin.uri"]["url"] == "{{ mailpit_api_url }}/info"

    startup_block = next(
        task for task in tasks if task["name"] == "Start the Mailpit stack with stale-network recovery"
    )
    rescue_names = [task["name"] for task in startup_block["rescue"]]
    assert "Detect stale Mailpit compose-network startup failures" in rescue_names
    assert "Reset the stale Mailpit compose network before retrying startup" in rescue_names

    reset_task = next(
        task
        for task in startup_block["rescue"]
        if task["name"] == "Reset the stale Mailpit compose network before retrying startup"
    )
    assert 'docker network rm "{{ mailpit_docker_network_name }}"' in reset_task["ansible.builtin.shell"]


def test_verify_tasks_clear_probe_and_assert_mail_capture() -> None:
    tasks = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in tasks]

    assert "Verify the Mailpit info endpoint responds locally" in names
    assert "Clear any previous Mailpit messages" in names
    assert "Send a repo-managed Mailpit SMTP probe" in names
    assert "Read the captured Mailpit messages" in names
    assert "Assert Mailpit captured the expected probe message" in names

    clear_task = next(task for task in tasks if task["name"] == "Clear any previous Mailpit messages")
    assert clear_task["ansible.builtin.uri"]["url"] == "{{ mailpit_api_url }}/messages"
    smtp_probe = next(task for task in tasks if task["name"] == "Send a repo-managed Mailpit SMTP probe")
    assert "with smtplib.SMTP('127.0.0.1', {{ mailpit_smtp_port }}" in smtp_probe["ansible.builtin.shell"]


def test_compose_template_binds_private_http_and_smtp_ports() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert "MP_UI_BIND_ADDR: 0.0.0.0:8025" in template
    assert "MP_SMTP_BIND_ADDR: 0.0.0.0:1025" in template
    assert '"{{ mailpit_bind_host }}:{{ mailpit_http_port }}:8025"' in template
    assert '"{{ mailpit_loopback_bind_host }}:{{ mailpit_http_port }}:8025"' in template
    assert '"{{ mailpit_bind_host }}:{{ mailpit_smtp_port }}:1025"' in template
    assert '"{{ mailpit_loopback_bind_host }}:{{ mailpit_smtp_port }}:1025"' in template
    assert "name: {{ mailpit_docker_network_name }}" in template
