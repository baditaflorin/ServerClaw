import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "changedetection_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "changedetection_runtime" / "tasks" / "verify.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "changedetection_runtime" / "defaults" / "main.yml"
ROLE_META = REPO_ROOT / "roles" / "changedetection_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "changedetection_runtime" / "templates" / "docker-compose.yml.j2"
WATCH_CATALOG_TEMPLATE = REPO_ROOT / "roles" / "changedetection_runtime" / "templates" / "watch-catalog.json.j2"
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "changedetection.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "changedetection.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
API_GATEWAY_CATALOG_PATH = REPO_ROOT / "config" / "api-gateway-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_defaults_pin_private_runtime_and_watch_catalogue() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["changedetection_runtime_site_dir"] == "/opt/changedetection"
    assert defaults["changedetection_runtime_secret_dir"] == "/etc/lv3/changedetection"
    assert defaults["changedetection_runtime_container_name"] == "changedetection"
    assert defaults["changedetection_runtime_volume_name"] == "changedetection-datastore"
    assert defaults["changedetection_runtime_port"] == (
        "{{ hostvars['proxmox-host'].platform_service_topology | platform_service_port('changedetection', 'internal') }}"
    )
    assert defaults["changedetection_runtime_recheck_minimum_seconds"] == 3600
    assert len(defaults["changedetection_runtime_watch_groups"]) == 4
    assert len(defaults["changedetection_runtime_watches"]) >= 8
    assert any(watch["group"] == "security-advisories" for watch in defaults["changedetection_runtime_watches"])


def test_argument_spec_requires_watch_catalogue_and_notification_inputs() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["changedetection_runtime_port"]["type"] == "int"
    assert options["changedetection_runtime_base_url"]["type"] == "str"
    assert options["changedetection_runtime_ntfy_password_local_file"]["type"] == "path"
    assert options["changedetection_runtime_watch_groups"]["elements"] == "dict"
    assert options["changedetection_runtime_watches"]["elements"] == "dict"


def test_main_tasks_deploy_sync_and_verify_changedetection() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]
    task_text = ROLE_TASKS.read_text(encoding="utf-8")

    assert "Build the desired Changedetection watch catalogue" in names
    assert "Consolidate the desired Changedetection watch catalogue" in names
    assert "Decode Changedetection notification route inputs" in names
    assert "Build Changedetection notification URLs" in names
    assert "Persist the Changedetection watch catalogue" in names
    assert "Read the Changedetection API token from the datastore" in names
    assert "Mirror the Changedetection API token to the control machine" in names
    assert "Reconcile the Changedetection watch catalogue over the live API" in names
    assert "Verify Changedetection health probes" in names
    assert "watch-catalog.json.j2" in task_text
    assert "changedetection_runtime_desired_tags_json" not in task_text


def test_verify_tasks_assert_watch_count_and_sync_idempotency() -> None:
    tasks = load_yaml(ROLE_VERIFY)
    names = [task["name"] for task in tasks]

    assert "Verify the Changedetection system info endpoint" in names
    assert "Verify the Changedetection tags endpoint" in names
    assert "Assert the Changedetection watch catalogue is loaded" in names
    assert "Verify the Changedetection watch sync is idempotent" in names
    assert "Assert the Changedetection watch sync is drift-free" in names


def test_compose_template_uses_host_network_and_named_volume() -> None:
    template = COMPOSE_TEMPLATE.read_text(encoding="utf-8")

    assert "network_mode: host" in template
    assert "MINIMUM_SECONDS_RECHECK_TIME" in template
    assert "PORT:" in template
    assert "{{ changedetection_runtime_volume_name }}:/datastore" in template
    assert "volumes:" in template


def test_watch_catalog_template_renders_notification_urls_into_json() -> None:
    template = WATCH_CATALOG_TEMPLATE.read_text(encoding="utf-8")

    assert '"schema_version": "1.0.0"' in template
    assert "notification_urls" in template
    assert "notification_muted" in template
    assert "changedetection_runtime_notification_urls[group.notification_channel]" in template


def test_playbook_converges_runtime_and_api_gateway_route() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == "docker-runtime"
    roles = [role["role"] for role in play["roles"]]
    assert roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.changedetection_runtime",
        "lv3.platform.api_gateway_runtime",
    ]


def test_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../changedetection.yml"}]


def test_inventory_exposes_changedetection_to_host_monitoring_and_local_docker_callers() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))

    assert host_vars["platform_port_assignments"]["changedetection_port"] == 5000
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]
    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    assert 5000 in host_rule["ports"]
    docker_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "172.16.0.0/12" and 5000 in rule["ports"]
    )
    assert 5000 in docker_rule["ports"]
    monitoring_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "monitoring" and 5000 in rule["ports"]
    )
    assert 5000 in monitoring_rule["ports"]


def test_workflow_and_command_catalogs_declare_converge_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))

    workflow = workflow_catalog["workflows"]["converge-changedetection"]
    command = command_catalog["commands"]["converge-changedetection"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-changedetection",
        "command": "make converge-changedetection",
    }
    assert "syntax-check-changedetection" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-changedetection.md"
    assert command["workflow_id"] == "converge-changedetection"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_api_gateway_catalog_exposes_the_authenticated_changedetection_route() -> None:
    catalog = json.loads(API_GATEWAY_CATALOG_PATH.read_text(encoding="utf-8"))
    route = next(service for service in catalog["services"] if service["id"] == "changedetection")

    assert route["gateway_prefix"] == "/v1/changedetection"
    assert route["upstream"] == "http://10.10.10.20:5000"
    assert route["auth"] == "keycloak_jwt"
    assert route["healthcheck_path"] == "/"


def test_ansible_execution_scopes_registers_the_direct_changedetection_playbook() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))
    entry = scopes["playbooks"]["playbooks/changedetection.yml"]

    assert entry["playbook_id"] == "changedetection"
    assert entry["mutation_scope"] == "host"
    assert "service:changedetection" in entry["shared_surfaces"]
