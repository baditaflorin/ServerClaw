from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "dozzle_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "dozzle_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "dozzle_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "dozzle_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "dozzle_runtime" / "templates" / "docker-compose.yml.j2"


def test_defaults_define_hub_and_agent_ports() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["dozzle_runtime_site_dir"] == "/opt/dozzle"
    assert defaults["dozzle_runtime_hub_container_name"] == "dozzle"
    assert defaults["dozzle_runtime_agent_container_name"] == "dozzle-agent"
    assert defaults["dozzle_runtime_agent_port"] == 7007
    assert defaults["dozzle_runtime_hub_inventory_host"] == "docker-runtime-lv3"
    assert defaults["dozzle_runtime_agent_inventory_hosts"] == [
        "docker-runtime-lv3",
        "docker-build-lv3",
        "monitoring-lv3",
    ]


def test_argument_spec_requires_hub_and_agent_inputs() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["dozzle_runtime_hub_port"]["type"] == "int"
    assert options["dozzle_runtime_agent_port"]["type"] == "int"
    assert options["dozzle_runtime_agent_inventory_hosts"]["elements"] == "str"
    assert options["dozzle_runtime_is_hub"]["type"] == "bool"


def test_main_tasks_render_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Render the Dozzle compose file" in names
    assert "Wait for the Dozzle agent listener" in names
    assert "Wait for the Dozzle hub listener on the hub node" in names
    assert "Verify the Dozzle runtime" in names


def test_verify_tasks_cover_remote_agent_tests() -> None:
    verify = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in verify]

    assert "Verify the Dozzle agent healthcheck succeeds" in names
    assert "Verify the Dozzle hub healthcheck succeeds" in names
    assert "Verify the local Dozzle agent is reachable from the hub container" in names
    assert "Verify the remote Dozzle agents are reachable from the hub container" in names
    hub_health_task = next(
        task for task in verify if task["name"] == "Verify the Dozzle hub healthcheck succeeds"
    )
    assert "ansible.builtin.uri" in hub_health_task
    assert hub_health_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ dozzle_runtime_hub_port }}/healthcheck"
    local_agent_task = next(
        task for task in verify if task["name"] == "Verify the local Dozzle agent is reachable from the hub container"
    )
    assert "127.0.0.1:{{ dozzle_runtime_agent_port }}" in local_agent_task["ansible.builtin.command"]["argv"]


def test_compose_template_defines_hub_remote_agents_and_healthchecks() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert "dozzle_runtime_remote_agents" in template
    assert "--remote-agent" in template
    assert 'container_name: {{ dozzle_runtime_hub_container_name }}' in template
    assert 'container_name: {{ dozzle_runtime_agent_container_name }}' in template
    assert "network_mode: host" in template
    assert '/dozzle' in template
    assert '":{{ dozzle_runtime_hub_port }}"' in template
    assert '":{{ dozzle_runtime_agent_port }}"' in template
    assert "condition: service_healthy" in template
    assert "ports:" not in template
