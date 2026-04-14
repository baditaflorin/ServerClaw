import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "repo_intake_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "repo_intake_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "repo_intake_runtime" / "tasks" / "verify.yml"
ROLE_META = REPO_ROOT / "roles" / "repo_intake_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "repo_intake_runtime" / "templates" / "docker-compose.yml.j2"
DOCKERFILE_TEMPLATE = REPO_ROOT / "roles" / "repo_intake_runtime" / "templates" / "Dockerfile.j2"
APP_PATH = REPO_ROOT / "scripts" / "repo_intake" / "app.py"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
HEALTH_CATALOG_PATH = REPO_ROOT / "config" / "health-probe-catalog.json"
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
PARTITION_CATALOG_PATH = REPO_ROOT / "config" / "contracts" / "service-partitions" / "catalog.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "repo-intake.md"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "repo-intake.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_defaults_keep_only_repo_specific_runtime_inputs() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert "repo_intake_port" not in defaults
    assert "repo_intake_container_name" not in defaults
    assert "repo_intake_build_context_dir" not in defaults
    assert defaults["repo_intake_image"] == "repo-intake:latest"
    assert defaults["repo_intake_repo_root"] == "{{ playbook_dir | dirname }}"


def test_argument_specs_drop_the_legacy_port_override() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert "repo_intake_port" not in options
    assert options["repo_intake_build_context_dir"]["type"] == "str"
    assert "default" not in options["repo_intake_build_context_dir"]
    assert options["repo_intake_coolify_admin_auth_local_file"]["type"] == "str"
    assert options["repo_intake_bootstrap_private_key_local_file"]["type"] == "str"


def test_tasks_wait_and_verify_using_the_derived_internal_port() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]
    build_context_task = next(
        task for task in tasks if task["name"] == "Resolve the repo-intake build context directory"
    )
    wait_task = next(task for task in tasks if task["name"] == "Wait for repo-intake to be ready")

    assert "Derive Repo Intake conventional defaults from the service registry" in names
    assert (
        build_context_task["ansible.builtin.set_fact"]["repo_intake_build_context_dir"]
        == "{{ repo_intake_build_context_dir | default(repo_intake_site_dir ~ '/build-context', true) }}"
    )
    assert "Verify the repo-intake runtime" in names
    assert wait_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ repo_intake_internal_port }}/health"
    assert wait_task["failed_when"] is False
    assert wait_task["until"] == "result.status | default(0) == 200"


def test_verify_tasks_assert_health_and_dashboard_shell() -> None:
    tasks = load_yaml(ROLE_VERIFY)
    names = [task["name"] for task in tasks]
    root_task = next(task for task in tasks if task["name"] == "Verify the repo-intake root page renders locally")

    assert "Verify the repo-intake health endpoint responds locally" in names
    assert "Assert the repo-intake root page renders with the expected deployment surface" in names
    assert root_task["ansible.builtin.uri"]["url"] == "http://127.0.0.1:{{ repo_intake_internal_port }}/"


def test_templates_and_app_use_the_single_internal_port_contract() -> None:
    compose = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE_TEMPLATE.read_text(encoding="utf-8")
    app_text = APP_PATH.read_text(encoding="utf-8")

    assert "{{ repo_intake_internal_port }}:{{ repo_intake_internal_port }}" in compose
    assert "http://127.0.0.1:{{ repo_intake_internal_port }}/health" in compose
    assert "PORT={{ repo_intake_internal_port }}" in (
        REPO_ROOT / "roles" / "repo_intake_runtime" / "templates" / "repo-intake.env.j2"
    ).read_text(encoding="utf-8")
    assert "EXPOSE {{ repo_intake_internal_port }}" in dockerfile
    assert '__import__("os").environ.get("PORT", "8101")' in app_text


def test_inventory_and_health_catalog_capture_repo_intake_runtime_contract() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    health_catalog = json.loads(HEALTH_CATALOG_PATH.read_text(encoding="utf-8"))
    service_catalog = json.loads(SERVICE_CATALOG_PATH.read_text(encoding="utf-8"))
    partition_catalog = json.loads(PARTITION_CATALOG_PATH.read_text(encoding="utf-8"))

    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]
    nginx_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "nginx" and 8101 in rule["ports"])
    repo_intake_service = next(item for item in service_catalog["services"] if item["id"] == "repo_intake")

    assert nginx_rule["description"] == "Reverse proxy access to the repo-intake deployment surface"
    assert host_vars["lv3_service_topology"]["repo_intake"]["public_hostname"] == "repo-intake.{{ platform_domain }}"
    assert host_vars["lv3_service_topology"]["repo_intake"]["edge"]["upstream"].endswith(":8101")
    assert health_catalog["services"]["repo_intake"]["verify_file"] == "roles/repo_intake_runtime/tasks/verify.yml"
    assert health_catalog["services"]["repo_intake"]["liveness"]["url"] == "http://127.0.0.1:8101/health"
    assert health_catalog["services"]["repo_intake"]["uptime_kuma"]["enabled"] is False
    assert repo_intake_service["public_url"] == "https://repo-intake.example.com"
    assert repo_intake_service["subdomain"] == "repo-intake.example.com"
    assert repo_intake_service["runbook"] == "docs/runbooks/repo-intake.md"
    assert repo_intake_service["runtime_pool"] == "runtime-general"
    assert repo_intake_service["deployment_surface"] == "playbooks/services/repo-intake.yml"
    assert "repo_intake" in partition_catalog["partitions"]["runtime-general"]["services"]
    assert "make converge-repo-intake" in RUNBOOK_PATH.read_text(encoding="utf-8")


def test_repo_intake_playbook_allows_first_published_runtime_chain_creation() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    roles = playbook[0]["roles"]
    docker_runtime_role = next(role for role in roles if role["role"] == "lv3.platform.docker_runtime")

    assert docker_runtime_role["vars"]["docker_runtime_require_nat_chain"] is False
