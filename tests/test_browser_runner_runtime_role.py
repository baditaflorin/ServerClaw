from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "browser_runner_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "browser_runner_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "browser_runner_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "browser_runner_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "browser_runner_runtime" / "templates" / "docker-compose.yml.j2"
DOCKERFILE_TEMPLATE = REPO_ROOT / "roles" / "browser_runner_runtime" / "templates" / "Dockerfile.j2"


def test_defaults_define_private_runtime_paths_and_timeouts() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["browser_runner_runtime_site_dir"] == "/opt/browser-runner"
    assert defaults["browser_runner_runtime_container_name"] == "browser-runner"
    assert defaults["browser_runner_runtime_image_name"] == "lv3/browser-runner"
    assert defaults["browser_runner_runtime_base_image"] == "python:3.12-slim-bookworm"
    assert defaults["browser_runner_runtime_internal_port"] == "{{ browser_runner_port }}"
    assert defaults["browser_runner_runtime_bind_host"] == "0.0.0.0"
    assert defaults["browser_runner_runtime_network_mode"] == "host"
    assert defaults["browser_runner_runtime_default_timeout_seconds"] == 45
    assert defaults["browser_runner_runtime_max_timeout_seconds"] == 180


def test_argument_spec_requires_runtime_paths_and_port_inputs() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["browser_runner_runtime_compose_file"]["type"] == "path"
    assert options["browser_runner_runtime_internal_port"]["type"] == "int"
    assert options["browser_runner_runtime_bind_host"]["type"] == "str"
    assert options["browser_runner_runtime_service_sources"]["elements"] == "dict"


def test_main_tasks_render_build_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Render the browser runner compose file" in names
    assert "Render the browser runner Dockerfile" in names
    assert "Sync the browser runner service sources" in names
    assert "Build the browser runner image" in names
    assert "Start the browser runner stack" in names
    assert "Verify the browser runner runtime" in names
    build_task = next(task for task in tasks if task["name"] == "Build the browser runner image")
    assert build_task["ansible.builtin.shell"].startswith("set -euo pipefail")
    assert (
        'docker build --pull=false -t "{{ browser_runner_runtime_image_name }}:latest" "$build_dir"'
        in build_task["ansible.builtin.shell"]
    )
    assert build_task["retries"] == 2
    assert build_task["delay"] == 5
    assert build_task["until"] == "browser_runner_runtime_build.rc == 0"


def test_verify_tasks_cover_health_and_smoke_session() -> None:
    verify = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in verify]

    assert "Verify the browser runner health endpoint responds locally" in names
    assert "Build the browser runner smoke payload" in names
    assert "Verify the browser runner smoke session succeeds locally" in names
    assert "Assert the browser runner smoke session returned the expected DOM results" in names
    smoke_task = next(
        task for task in verify if task["name"] == "Verify the browser runner smoke session succeeds locally"
    )
    assert (
        smoke_task["ansible.builtin.uri"]["url"]
        == "http://127.0.0.1:{{ browser_runner_runtime_internal_port }}/sessions"
    )


def test_templates_define_host_network_build_and_healthcheck() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()
    dockerfile_template = DOCKERFILE_TEMPLATE.read_text()

    assert "image: {{ browser_runner_runtime_image_name }}:latest" in compose_template
    assert "network_mode: {{ browser_runner_runtime_network_mode }}" in compose_template
    assert "BROWSER_RUNNER_ARTIFACT_ROOT: /data/artifacts" in compose_template
    assert "http://127.0.0.1:{{ browser_runner_runtime_internal_port }}/healthz" in compose_template
    assert "FROM {{ browser_runner_runtime_base_image }}" in dockerfile_template
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in dockerfile_template
    assert "python -m playwright install --with-deps chromium" in dockerfile_template
    assert "COPY browser_runner_service.py ./browser_runner_service.py" in dockerfile_template
