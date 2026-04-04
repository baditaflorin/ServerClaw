import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "typesense_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "typesense_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "typesense_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "typesense_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "typesense_runtime" / "templates" / "docker-compose.yml.j2"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "typesense.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "typesense.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
API_GATEWAY_CATALOG_PATH = REPO_ROOT / "config" / "api-gateway-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_define_private_runtime_paths_and_urls() -> None:
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text())

    assert defaults["typesense_site_dir"] == "/opt/typesense"
    assert defaults["typesense_container_name"] == "typesense"
    assert defaults["typesense_collection_name"] == "platform-services"
    assert defaults["typesense_openbao_secret_path"] == "services/typesense/runtime-env"
    assert defaults["typesense_api_key_local_file"] == "{{ typesense_local_artifact_dir }}/api-key.txt"


def test_argument_spec_requires_port_and_controller_contracts() -> None:
    specs = yaml.safe_load(ROLE_META.read_text())
    options = specs["argument_specs"]["main"]["options"]

    assert options["typesense_port"]["type"] == "int"
    assert options["typesense_host_proxy_port"]["type"] == "int"
    assert options["typesense_internal_base_url"]["type"] == "str"
    assert options["typesense_controller_url"]["type"] == "str"
    assert options["typesense_api_key_local_file"]["type"] == "path"


def test_main_tasks_generate_api_key_sync_openbao_and_verify_runtime() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    names = [task["name"] for task in tasks]

    assert "Generate the controller-local Typesense API key" in names
    assert "Prepare OpenBao agent runtime secret injection for Typesense" in names
    assert "Render the Typesense compose file" in names
    assert "Pull the Typesense image" in names
    assert "Start or refresh the Typesense runtime" in names
    assert "Wait for Typesense to listen locally" in names
    assert "Verify the Typesense runtime" in names
    task_text = ROLE_TASKS.read_text()
    assert "Record whether the Typesense runtime failed because the compose network is missing" in task_text
    assert "Tear down the stale Typesense compose stack after missing-network startup failure" in task_text
    assert "Remove the stale Typesense bridge network after missing-network startup failure" in task_text
    assert "Recover the Typesense compose stack when a stale network reference blocks startup" in task_text
    assert "- network" in task_text
    assert "typesense_site_dir | basename" in task_text


def test_verify_tasks_cover_the_health_contract() -> None:
    verify = yaml.safe_load(ROLE_VERIFY.read_text())

    assert verify[0]["name"] == "Verify the Typesense health endpoint responds"
    assert verify[0]["ansible.builtin.uri"]["url"] == "{{ typesense_internal_base_url }}/health"
    assert verify[0]["until"] == "typesense_verify_health.status == 200"


def test_compose_template_publishes_private_port_and_openbao_sidecar() -> None:
    template = COMPOSE_TEMPLATE.read_text()

    assert '"{{ typesense_port }}:8108"' in template
    assert "container_name: {{ typesense_openbao_agent_container_name }}" in template
    assert "openbao-agent:" in template
    assert "env_file:" in template
    assert "- {{ typesense_env_file }}" in template
    assert "typesense-data:/data" in template


def test_playbook_converges_proxy_runtime_and_catalog_sync() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert len(playbook) == 2
    host_play = playbook[0]
    guest_play = playbook[1]
    assert host_play["hosts"] == "proxmox_hosts"
    assert [role["role"] for role in host_play["roles"]] == [
        "lv3.platform.proxmox_tailscale_proxy",
        "lv3.platform.proxmox_security",
    ]
    assert guest_play["hosts"] == "docker-runtime-lv3"
    assert guest_play["roles"][0]["vars"] == {
        "linux_guest_firewall_recover_missing_docker_bridge_chains": True
    }
    assert [role["role"] for role in guest_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.typesense_runtime",
        "lv3.platform.api_gateway_runtime",
    ]


def test_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../typesense.yml"}]


def test_inventory_declares_private_port_and_controller_proxy() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())

    assert host_vars["platform_port_assignments"]["typesense_port"] == 8108
    assert host_vars["platform_port_assignments"]["typesense_host_proxy_port"] == 8016
    proxy = next(item for item in host_vars["proxmox_tailscale_tcp_proxies"] if item["name"] == "typesense")
    assert proxy["listen_port"] == "{{ platform_port_assignments.typesense_host_proxy_port }}"
    assert proxy["upstream_port"] == "{{ platform_port_assignments.typesense_port }}"


def test_workflow_and_command_catalogs_declare_converge_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())

    workflow = workflow_catalog["workflows"]["converge-typesense"]
    command = command_catalog["commands"]["converge-typesense"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-typesense",
        "command": "make converge-typesense",
    }
    assert "syntax-check-typesense" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-typesense.md"
    assert command["workflow_id"] == "converge-typesense"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_api_gateway_catalog_exposes_the_authenticated_typesense_route() -> None:
    catalog = json.loads(API_GATEWAY_CATALOG_PATH.read_text())
    route = next(service for service in catalog["services"] if service["id"] == "typesense")

    assert route["gateway_prefix"] == "/v1/typesense"
    assert route["upstream"] == "http://10.10.10.20:8108"
    assert route["auth"] == "keycloak_jwt"
    assert route["upstream_auth_env_var"] == "LV3_GATEWAY_TYPESENSE_API_KEY"
    assert route["upstream_auth_header"] == "X-TYPESENSE-API-KEY"
    assert route["upstream_auth_scheme"] == "raw"


def test_ansible_execution_scopes_registers_the_direct_typesense_playbook() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text())
    entry = scopes["playbooks"]["playbooks/typesense.yml"]

    assert entry["playbook_id"] == "typesense"
    assert entry["mutation_scope"] == "platform"
    assert "service:typesense" in entry["shared_surfaces"]
    assert "service:api-gateway" in entry["shared_surfaces"]
