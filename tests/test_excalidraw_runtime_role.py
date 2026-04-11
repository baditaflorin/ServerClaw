from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "excalidraw_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "excalidraw_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "excalidraw_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "excalidraw_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "excalidraw_runtime" / "templates" / "docker-compose.yml.j2"
BOOTSTRAP_TEMPLATE = REPO_ROOT / "roles" / "excalidraw_runtime" / "templates" / "bootstrap-app.sh.j2"


def test_defaults_define_frontend_and_room_ports() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["excalidraw_runtime_site_dir"] == "/opt/excalidraw"
    assert defaults["excalidraw_runtime_app_container_name"] == "excalidraw-app"
    assert defaults["excalidraw_runtime_room_container_name"] == "excalidraw-room"
    assert defaults["excalidraw_runtime_app_container_port"] == 80
    assert defaults["excalidraw_runtime_bind_host"] == "127.0.0.1"
    assert defaults["excalidraw_runtime_upstream_collab_origin"] == "https://oss-collab.excalidraw.com"


def test_argument_spec_requires_room_and_public_origin_inputs() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["excalidraw_runtime_app_port"]["type"] == "int"
    assert options["excalidraw_runtime_room_port"]["type"] == "int"
    assert options["excalidraw_runtime_app_container_port"]["type"] == "int"
    assert options["excalidraw_runtime_public_url"]["type"] == "str"
    assert options["excalidraw_runtime_collab_origin"]["type"] == "str"


def test_main_tasks_render_compose_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Render the Excalidraw frontend bootstrap script" in names
    assert "Render the Excalidraw compose file" in names
    assert "Wait for the Excalidraw frontend listener" in names
    assert "Wait for the Excalidraw collaboration room listener" in names
    assert "Verify the Excalidraw runtime" in names


def test_verify_tasks_cover_frontend_room_and_asset_patch() -> None:
    verify = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in verify]

    assert "Verify the Excalidraw frontend responds locally" in names
    assert "Verify the Excalidraw collaboration room responds locally" in names
    assert "Verify the Excalidraw frontend asset patch points to the shared collaboration origin" in names
    room_probe_task = next(
        task for task in verify if task["name"] == "Verify the Excalidraw collaboration room responds locally"
    )
    assert room_probe_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ excalidraw_runtime_room_port }}/"


def test_templates_define_bootstrap_patch_and_port_publishing() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()
    bootstrap_template = BOOTSTRAP_TEMPLATE.read_text()

    assert "container_name: {{ excalidraw_runtime_app_container_name }}" in compose_template
    assert "container_name: {{ excalidraw_runtime_room_container_name }}" in compose_template
    assert "ports:" in compose_template
    assert (
        "{{ excalidraw_runtime_bind_host }}:{{ excalidraw_runtime_app_port }}:{{ excalidraw_runtime_app_container_port }}"
        in compose_template
    )
    assert (
        "{{ excalidraw_runtime_bind_host }}:{{ excalidraw_runtime_room_port }}:{{ excalidraw_runtime_room_port }}"
        in compose_template
    )
    assert "PORT:" in compose_template
    assert "grep -R -l -F" in bootstrap_template
    assert "{{ excalidraw_runtime_upstream_collab_origin }}" in bootstrap_template
    assert "{{ excalidraw_runtime_collab_origin }}" in bootstrap_template
