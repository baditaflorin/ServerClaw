import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "piper_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "piper_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "piper_runtime" / "tasks" / "verify.yml"
ROLE_META = REPO_ROOT / "roles" / "piper_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "piper_runtime" / "templates" / "docker-compose.yml.j2"
DOCKERFILE_TEMPLATE = REPO_ROOT / "roles" / "piper_runtime" / "templates" / "Dockerfile.j2"
SERVICE_SCRIPT = REPO_ROOT / "roles" / "piper_runtime" / "files" / "piper_service.py"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "configure-piper.md"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
HEALTH_CATALOG_PATH = REPO_ROOT / "config" / "health-probe-catalog.json"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_defaults_define_private_piper_runtime_contract() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert (
        defaults["piper_service_topology"]
        == "{{ hostvars['proxmox-host'].platform_service_topology | platform_service('piper') }}"
    )
    assert defaults["piper_runtime_site_dir"] == "/opt/piper"
    assert defaults["piper_runtime_compose_file"] == "{{ piper_runtime_site_dir }}/docker-compose.yml"
    assert defaults["piper_runtime_compose_project_name"] == "{{ piper_runtime_site_dir | basename }}"
    assert defaults["piper_runtime_container_name"] == "piper"
    assert defaults["piper_runtime_image_name"] == "lv3-piper"
    assert defaults["piper_runtime_port"] == "{{ piper_service_topology.ports.internal }}"
    assert defaults["piper_runtime_model_volume_name"] == "piper-models"
    assert defaults["piper_runtime_default_voice"] == "en_US-ryan-medium"
    assert defaults["piper_runtime_voice_models"] == ["en_US-ryan-medium"]
    assert defaults["piper_runtime_base_image"].startswith("docker.io/library/python:3.12-slim-bookworm@sha256:")


def test_argument_spec_requires_private_listener_and_voice_inputs() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["piper_runtime_port"]["type"] == "int"
    assert options["piper_runtime_base_url"]["type"] == "str"
    assert options["piper_runtime_bind_host"]["type"] == "str"
    assert options["piper_runtime_loopback_bind_host"]["type"] == "str"
    assert options["piper_runtime_model_volume_name"]["type"] == "str"
    assert options["piper_runtime_voice_models"]["elements"] == "str"


def test_main_tasks_render_build_wait_and_verify_piper() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Render the Piper compose file" in names
    assert "Render the Piper Dockerfile" in names
    assert "Sync the Piper runtime requirements" in names
    assert "Define the Piper image build shell" in names
    assert "Build the Piper runtime image and recover stale Docker build-network drift" in names
    assert "Check whether Docker nat chain exists before Piper startup" in names
    assert "Build the Piper compose startup command" in names
    assert "Start the Piper runtime and recover Docker nat-chain or stale compose-network failures" in names
    assert "Wait for the Piper listener" in names
    assert "Verify the Piper runtime" in names

    health_probe = next(
        task
        for task in tasks
        if task["name"] == "Check whether the current Piper health endpoint is healthy before startup"
    )
    assert health_probe["ansible.builtin.uri"]["url"] == "{{ piper_runtime_health_url }}"

    build_shell_task = next(task for task in tasks if task["name"] == "Define the Piper image build shell")
    assert (
        'DOCKER_BUILDKIT=0 docker build --pull=false --network host -t "{{ piper_runtime_image_name }}:latest"'
        in build_shell_task["ansible.builtin.set_fact"]["piper_runtime_build_shell"]
    )

    build_task = next(
        task
        for task in next(
            task
            for task in tasks
            if task["name"] == "Build the Piper runtime image and recover stale Docker build-network drift"
        )["block"]
        if task["name"] == "Build the Piper runtime image"
    )
    assert build_task["ansible.builtin.shell"] == "{{ piper_runtime_build_shell }}"
    build_rescue_names = [
        task["name"]
        for task in next(
            task
            for task in tasks
            if task["name"] == "Build the Piper runtime image and recover stale Docker build-network drift"
        )["rescue"]
    ]
    assert "Restart Docker to restore bridge networking before retrying the Piper image build" in build_rescue_names
    assert (
        "Ensure Docker bridge networking chains are present before retrying the Piper image build" in build_rescue_names
    )
    assert "Retry the Piper runtime image build after Docker networking recovery" in build_rescue_names

    compose_up_task = next(task for task in tasks if task["name"] == "Build the Piper compose startup command")
    assert "--no-build" in compose_up_task["ansible.builtin.set_fact"]["piper_runtime_compose_up_argv"]

    startup_block = next(
        task
        for task in tasks
        if task["name"] == "Start the Piper runtime and recover Docker nat-chain or stale compose-network failures"
    )
    rescue_names = [task["name"] for task in startup_block["rescue"]]
    assert "Reset stale Piper compose resources after startup failure" in rescue_names
    assert "Remove the stale Piper compose network before retrying startup" in rescue_names
    assert "Restart Docker to restore bridge networking before retrying Piper startup" in rescue_names
    assert "Ensure Docker bridge networking chains are present before retrying Piper startup" in rescue_names
    assert "Retry Piper startup after Docker nat-chain or compose-network recovery" in rescue_names


def test_verify_tasks_assert_health_voice_catalog_and_wav_contract() -> None:
    tasks = load_yaml(ROLE_VERIFY)
    names = [task["name"] for task in tasks]

    assert "Verify the Piper health endpoint responds locally" in names
    assert "Verify the Piper voices endpoint reports the declared voices" in names
    assert "Verify Piper synthesizes WAV audio from the ADR contract" in names
    tts_verify = next(
        task for task in tasks if task["name"] == "Verify Piper synthesizes WAV audio from the ADR contract"
    )
    assert "/api/tts?voice={{ piper_runtime_default_voice | urlencode }}" in tts_verify["ansible.builtin.shell"]
    assert 'payload[:4] == b"RIFF"' in tts_verify["ansible.builtin.shell"]


def test_compose_and_dockerfile_templates_pin_the_private_runtime() -> None:
    compose = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE_TEMPLATE.read_text(encoding="utf-8")

    assert "context: {{ piper_runtime_service_dir }}" in compose
    assert '"{{ piper_runtime_bind_host }}:{{ piper_runtime_port }}:{{ piper_runtime_container_port }}"' in compose
    assert (
        '"{{ piper_runtime_loopback_bind_host }}:{{ piper_runtime_port }}:{{ piper_runtime_container_port }}"'
        in compose
    )
    assert "{{ piper_runtime_model_volume_name }}:{{ piper_runtime_model_dir }}" in compose
    assert "FROM {{ piper_runtime_base_image }}" in dockerfile
    assert 'CMD ["python3", "/app/piper_service.py"]' in dockerfile


def test_service_script_and_catalogs_capture_the_private_tts_contract() -> None:
    script_text = SERVICE_SCRIPT.read_text(encoding="utf-8")
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    service_catalog = json.loads(SERVICE_CATALOG_PATH.read_text(encoding="utf-8"))
    health_catalog = json.loads(HEALTH_CATALOG_PATH.read_text(encoding="utf-8"))

    service = next(item for item in service_catalog["services"] if item["id"] == "piper")
    probe = health_catalog["services"]["piper"]

    assert '@app.post("/api/tts")' in script_text
    assert '@app.get("/api/voices")' in script_text
    assert '@app.get("/healthz")' in script_text
    assert "There is no public hostname" in runbook
    assert service["internal_url"] == "http://10.10.10.20:8100"
    assert service["exposure"] == "private-only"
    assert service["health_probe_id"] == "piper"
    assert probe["verify_file"] == "roles/piper_runtime/tasks/verify.yml"
    assert probe["uptime_kuma"]["enabled"] is False
