from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "uptime_kuma_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "uptime_kuma_runtime" / "tasks" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "uptime_kuma_runtime" / "meta" / "main.yml"
ROLE_ARGUMENT_SPECS = REPO_ROOT / "roles" / "uptime_kuma_runtime" / "meta" / "argument_specs.yml"


def test_defaults_define_private_uptime_kuma_runtime_contract() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["uptime_kuma_site_dir"] == "/opt/uptime-kuma"
    assert defaults["uptime_kuma_compose_file"] == "/opt/uptime-kuma/docker-compose.yml"
    assert defaults["uptime_kuma_data_dir"] == "/opt/uptime-kuma/data"
    assert defaults["uptime_kuma_container_name"] == "uptime-kuma"
    assert defaults["uptime_kuma_image"] == "{{ container_image_catalog.images.uptime_kuma_runtime.ref }}"
    assert defaults["uptime_kuma_port"] == "{{ uptime_kuma_service_topology.ports.internal }}"


def test_preflight_dependency_only_requires_defined_runtime_inputs() -> None:
    meta = yaml.safe_load(ROLE_META.read_text())
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())
    argument_specs = yaml.safe_load(ROLE_ARGUMENT_SPECS.read_text())

    required = meta["dependencies"][0]["vars"]["preflight_required_vars"]
    defined_inputs = set(defaults) | set(argument_specs["argument_specs"]["main"]["options"])

    assert required == ["uptime_kuma_site_dir", "uptime_kuma_port"]
    assert set(required) <= defined_inputs


def test_tasks_render_pull_start_wait_and_verify_uptime_kuma() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    package_task = next(task for task in tasks if task["name"] == "Ensure Uptime Kuma runtime packages are present")
    assert package_task["ansible.builtin.apt"]["name"] == ["docker-compose-plugin"]

    assert "Render the Uptime Kuma compose file" in names
    assert "Pull the Uptime Kuma image" in names
    assert "Start the Uptime Kuma stack" in names
    assert "Wait for Uptime Kuma to listen locally" in names
    assert "Verify Uptime Kuma health probes" in names

    pull_task = next(task for task in tasks if task["name"] == "Pull the Uptime Kuma image")
    assert pull_task["ansible.builtin.command"]["argv"][:3] == ["docker", "compose", "--file"]

    up_task = next(task for task in tasks if task["name"] == "Start the Uptime Kuma stack")
    assert up_task["ansible.builtin.command"]["argv"][:3] == ["docker", "compose", "--file"]
