import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "gotenberg_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "gotenberg_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "gotenberg_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "gotenberg_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "gotenberg_runtime" / "templates" / "docker-compose.yml.j2"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "gotenberg.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "gotenberg.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
API_GATEWAY_CATALOG_PATH = REPO_ROOT / "config" / "api-gateway-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
RUNTIME_AI_HOSTS = "{{ 'docker-runtime' if (env | default('production')) == 'staging' else 'runtime-ai' }}"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_private_runtime_port_and_limits() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["gotenberg_runtime_site_dir"] == "/opt/gotenberg"
    assert defaults["gotenberg_runtime_container_name"] == "gotenberg"
    assert defaults["gotenberg_runtime_container_port"] == 3000
    assert defaults["gotenberg_runtime_healthcheck_path"] == "/health"
    assert defaults["gotenberg_runtime_memory_limit"] == "4g"
    assert defaults["gotenberg_runtime_cpu_limit"] == "2.0"
    assert defaults["gotenberg_runtime_chromium_auto_start"] is True
    assert defaults["gotenberg_runtime_libreoffice_auto_start"] is True


def test_argument_spec_requires_runtime_urls_and_resource_limits() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["gotenberg_runtime_port"]["type"] == "int"
    assert options["gotenberg_runtime_internal_base_url"]["type"] == "str"
    assert options["gotenberg_runtime_local_base_url"]["type"] == "str"
    assert options["gotenberg_runtime_memory_limit"]["type"] == "str"
    assert options["gotenberg_runtime_cpu_limit"]["type"] == "str"


def test_main_tasks_render_compose_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Render the Gotenberg compose file" in names
    assert "Pull the Gotenberg image" in names
    assert "Wait for the Gotenberg health endpoint" in names
    assert "Verify the Gotenberg runtime" in names
    port_check = next(
        task for task in tasks if task["name"] == "Check whether Gotenberg publishes the expected host port"
    )
    assert port_check["ansible.builtin.command"]["argv"] == [
        "docker",
        "port",
        "{{ gotenberg_runtime_container_name }}",
        "{{ gotenberg_runtime_container_port }}/tcp",
    ]


def test_verify_tasks_cover_health_chromium_and_libreoffice_paths() -> None:
    verify = yaml.safe_load(ROLE_VERIFY.read_text())
    names = [task["name"] for task in verify]

    assert "Verify the Gotenberg health endpoint responds locally" in names
    assert "Verify the Gotenberg Chromium HTML conversion route renders a PDF" in names
    assert "Verify the Gotenberg LibreOffice conversion route renders a PDF" in names
    chromium_task = next(
        task for task in verify if task["name"] == "Verify the Gotenberg Chromium HTML conversion route renders a PDF"
    )
    assert "/forms/chromium/convert/html" in chromium_task["ansible.builtin.shell"]
    assert "filename=index.html" in chromium_task["ansible.builtin.shell"]
    libreoffice_task = next(
        task for task in verify if task["name"] == "Verify the Gotenberg LibreOffice conversion route renders a PDF"
    )
    assert "/forms/libreoffice/convert" in libreoffice_task["ansible.builtin.shell"]


def test_compose_template_publishes_private_port_and_prestarts_renderers() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert "network_mode: bridge" in template
    assert '"{{ gotenberg_runtime_port }}:{{ gotenberg_runtime_container_port }}"' in template
    assert "CHROMIUM_AUTO_START" in template
    assert "LIBREOFFICE_AUTO_START" in template
    assert "mem_limit: {{ gotenberg_runtime_memory_limit }}" in template
    assert 'cpus: "{{ gotenberg_runtime_cpu_limit }}"' in template


def test_playbook_converges_runtime_and_api_gateway_route() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == RUNTIME_AI_HOSTS
    roles = [role["role"] for role in play["roles"]]
    assert roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.gotenberg_runtime",
    ]


def test_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../gotenberg.yml"}]


def test_inventory_opens_the_private_rendering_port_to_guest_and_docker_callers() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())

    assert host_vars["platform_port_assignments"]["gotenberg_port"] == 3007
    runtime_ai_rules = host_vars["network_policy"]["guests"]["runtime-ai"]["allowed_inbound"]
    guest_rule = next(rule for rule in runtime_ai_rules if rule["source"] == "all_guests" and 3007 in rule["ports"])
    assert 3007 in guest_rule["ports"]
    docker_rule = next(rule for rule in runtime_ai_rules if rule["source"] == "172.16.0.0/12" and 3007 in rule["ports"])
    assert 3007 in docker_rule["ports"]
    host_rule = next(rule for rule in runtime_ai_rules if rule["source"] == "host" and 3007 in rule["ports"])
    assert 3007 in host_rule["ports"]


def test_workflow_and_command_catalogs_declare_converge_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())

    workflow = workflow_catalog["workflows"]["converge-gotenberg"]
    command = command_catalog["commands"]["converge-gotenberg"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-gotenberg",
        "command": "make converge-gotenberg",
    }
    assert "syntax-check-gotenberg" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-gotenberg.md"
    assert command["workflow_id"] == "converge-gotenberg"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_api_gateway_catalog_exposes_the_authenticated_gotenberg_route() -> None:
    catalog = json.loads(API_GATEWAY_CATALOG_PATH.read_text())
    route = next(service for service in catalog["services"] if service["id"] == "gotenberg")

    assert route["gateway_prefix"] == "/v1/gotenberg"
    assert route["upstream"] == "http://10.10.10.90:3007"
    assert route["auth"] == "keycloak_jwt"
    assert route["healthcheck_path"] == "/health"


def test_ansible_execution_scopes_registers_the_direct_gotenberg_playbook() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text())
    entry = scopes["playbooks"]["playbooks/gotenberg.yml"]
    service_entry = scopes["playbooks"]["playbooks/services/gotenberg.yml"]

    assert entry["playbook_id"] == "gotenberg"
    assert entry["mutation_scope"] == "lane"
    assert entry["target_lane"] == "lane:runtime-ai"
    assert "service:gotenberg" in entry["shared_surfaces"]
    assert service_entry["playbook_id"] == "gotenberg"
    assert service_entry["mutation_scope"] == "lane"
    assert service_entry["target_lane"] == "lane:runtime-ai"
