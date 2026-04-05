from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "roles" / "uptime_kuma_runtime"
ROLE_DEFAULTS = ROLE_ROOT / "defaults" / "main.yml"
ROLE_META = ROLE_ROOT / "meta" / "argument_specs.yml"
ROLE_DEPENDENCY_META = ROLE_ROOT / "meta" / "main.yml"
ROLE_TASKS = ROLE_ROOT / "tasks" / "main.yml"
ROLE_VERIFY = ROLE_ROOT / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "templates" / "docker-compose.yml.j2"


def test_defaults_define_the_private_uptime_kuma_runtime_contract() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["uptime_kuma_site_dir"] == "/opt/uptime-kuma"
    assert defaults["uptime_kuma_compose_file"] == "/opt/uptime-kuma/docker-compose.yml"
    assert defaults["uptime_kuma_data_dir"] == "/opt/uptime-kuma/data"
    assert defaults["uptime_kuma_container_name"] == "uptime-kuma"
    assert defaults["uptime_kuma_image"] == "{{ container_image_catalog.images.uptime_kuma_runtime.ref }}"
    assert defaults["uptime_kuma_port"] == "{{ uptime_kuma_service_topology.ports.internal }}"


def test_preflight_dependency_requires_the_runtime_inputs_the_role_actually_uses() -> None:
    dependency_meta = yaml.safe_load(ROLE_DEPENDENCY_META.read_text())
    required_vars = dependency_meta["dependencies"][0]["vars"]["preflight_required_vars"]

    assert required_vars == [
        "uptime_kuma_site_dir",
        "uptime_kuma_compose_file",
        "uptime_kuma_port",
    ]


def test_argument_spec_covers_the_runtime_paths_and_listener_port() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["uptime_kuma_site_dir"]["type"] == "path"
    assert options["uptime_kuma_data_dir"]["type"] == "path"
    assert options["uptime_kuma_compose_file"]["type"] == "path"
    assert options["uptime_kuma_container_name"]["type"] == "str"
    assert options["uptime_kuma_port"]["type"] == "int"


def test_main_tasks_render_pull_start_and_verify_uptime_kuma() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    package_task = next(task for task in tasks if task["name"] == "Ensure Uptime Kuma runtime packages are present")
    assert package_task["ansible.builtin.apt"]["name"] == ["docker-compose-plugin"]

    assert "Render the Uptime Kuma compose file" in names
    assert "Pull the Uptime Kuma image" in names
    assert "Start the Uptime Kuma stack" in names
    assert "Wait for Uptime Kuma to listen locally" in names
    assert "Verify Uptime Kuma health probes" in names

    assert_vars_task = next(task for task in tasks if task["name"] == "Validate Uptime Kuma runtime inputs")
    assert assert_vars_task["vars"]["common_assert_vars_required"] == [
        "uptime_kuma_site_dir",
        "uptime_kuma_data_dir",
        "uptime_kuma_compose_file",
        "uptime_kuma_container_name",
        "uptime_kuma_image",
        "uptime_kuma_port",
    ]

    pull_task = next(task for task in tasks if task["name"] == "Pull the Uptime Kuma image")
    assert pull_task["ansible.builtin.command"]["argv"][:3] == ["docker", "compose", "--file"]

    start_task = next(task for task in tasks if task["name"] == "Start the Uptime Kuma stack")
    assert start_task["ansible.builtin.command"]["argv"][:3] == ["docker", "compose", "--file"]


def test_verify_tasks_probe_the_local_http_surface() -> None:
    tasks = yaml.safe_load(ROLE_VERIFY.read_text())
    probe_task = next(task for task in tasks if task["name"] == "Verify the Uptime Kuma web UI responds locally")

    assert probe_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ uptime_kuma_port }}"


def test_compose_template_publishes_the_expected_listener_and_data_mount() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert "{{ uptime_kuma_data_dir }}:/app/data" in template
    assert '"{{ uptime_kuma_port }}:3001"' in template
