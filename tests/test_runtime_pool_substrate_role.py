from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "runtime_pool_substrate"
ROLE_DEFAULTS = ROLE_ROOT / "defaults" / "main.yml"
ROLE_META = ROLE_ROOT / "meta" / "argument_specs.yml"
ROLE_TASKS = ROLE_ROOT / "tasks" / "main.yml"
ROLE_VERIFY = ROLE_ROOT / "tasks" / "verify.yml"
COMPOSE_TEMPLATE = ROLE_ROOT / "templates" / "docker-compose.yml.j2"
ROUTER_TEMPLATE = ROLE_ROOT / "templates" / "runtime-ai-router.yml.j2"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_pin_the_runtime_ai_substrate_contract() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["runtime_pool_substrate_root_dir"] == "/opt/runtime-pool-substrate"
    assert defaults["runtime_pool_substrate_traefik_image"] == "traefik:v3.6"
    assert defaults["runtime_pool_substrate_traefik_port"] == 9080
    assert defaults["runtime_pool_substrate_dapr_image"] == "daprio/daprd:1.16.0"
    assert defaults["runtime_pool_substrate_dapr_app_id"] == "runtime-ai-router"
    assert defaults["runtime_pool_substrate_dapr_http_port"] == 3500
    assert defaults["runtime_pool_substrate_tika_prefix"] == "/tika"
    assert defaults["runtime_pool_substrate_gotenberg_prefix"] == "/gotenberg"
    assert defaults["runtime_pool_substrate_tesseract_prefix"] == "/tesseract-ocr"


def test_argument_specs_cover_traefik_dapr_and_upstream_inputs() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["runtime_pool_substrate_traefik_port"]["type"] == "int"
    assert options["runtime_pool_substrate_dapr_http_port"]["type"] == "int"
    assert options["runtime_pool_substrate_dapr_grpc_port"]["type"] == "int"
    assert options["runtime_pool_substrate_tika_upstream"]["type"] == "str"
    assert options["runtime_pool_substrate_gotenberg_upstream"]["type"] == "str"
    assert options["runtime_pool_substrate_tesseract_upstream"]["type"] == "str"


def test_main_tasks_render_pull_start_and_verify_the_substrate() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Validate runtime-pool substrate inputs" in names
    assert "Ensure runtime-pool substrate directories exist" in names
    assert "Render the runtime-pool router config" in names
    assert "Render the runtime-pool substrate compose file" in names
    assert "Pull the runtime-pool substrate images" in names
    assert "Ensure the runtime-pool substrate is running" in names
    assert "Verify the runtime-pool substrate" in names


def test_verify_tasks_cover_traefik_ping_dapr_metadata_and_dapr_invoke() -> None:
    tasks = load_yaml(ROLE_VERIFY)
    names = [task["name"] for task in tasks]

    assert "Verify the runtime-pool Traefik ping endpoint responds locally" in names
    assert "Assert the Traefik ping payload is healthy" in names
    assert "Verify the runtime-pool Dapr metadata endpoint responds locally" in names
    assert "Assert the Dapr router metadata carries the expected app id" in names
    assert "Verify the Dapr sidecar can invoke the Traefik ping route" in names
    assert "Assert the Dapr invocation bridge returns the Traefik ping payload" in names

    dapr_invoke_task = next(task for task in tasks if task["name"] == "Verify the Dapr sidecar can invoke the Traefik ping route")
    assert dapr_invoke_task["ansible.builtin.command"]["argv"][:5] == [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--path-as-is",
    ]
    assert "http://127.0.0.1:{{ runtime_pool_substrate_dapr_http_port }}/v1.0/invoke/http://127.0.0.1:{{ runtime_pool_substrate_traefik_port }}/method{{ runtime_pool_substrate_traefik_ping_path }}" in dapr_invoke_task["ansible.builtin.command"]["argv"][-1]


def test_templates_define_host_networked_traefik_and_dapr_router() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text()
    router_template = ROUTER_TEMPLATE.read_text()

    assert "runtime-ai-traefik:" in compose_template
    assert "runtime-ai-dapr-router:" in compose_template
    assert "network_mode: host" in compose_template
    assert "./daprd" in compose_template
    assert "--app-id" in compose_template
    assert "runtime-ai-tika:" in router_template
    assert "runtime-ai-gotenberg:" in router_template
    assert "runtime-ai-tesseract:" in router_template
    assert "stripPrefix:" in router_template
