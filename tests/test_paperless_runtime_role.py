import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DEFAULTS = REPO_ROOT / "roles" / "paperless_runtime" / "defaults" / "main.yml"
ROLE_TASKS = REPO_ROOT / "roles" / "paperless_runtime" / "tasks" / "main.yml"
ROLE_VERIFY = REPO_ROOT / "roles" / "paperless_runtime" / "tasks" / "verify.yml"
ROLE_PUBLISH = REPO_ROOT / "roles" / "paperless_runtime" / "tasks" / "publish.yml"
ROLE_META = REPO_ROOT / "roles" / "paperless_runtime" / "meta" / "argument_specs.yml"
COMPOSE_TEMPLATE = REPO_ROOT / "roles" / "paperless_runtime" / "templates" / "docker-compose.yml.j2"
ENV_TEMPLATE = REPO_ROOT / "roles" / "paperless_runtime" / "templates" / "paperless.env.j2"
ENV_CTEMPLATE = REPO_ROOT / "roles" / "paperless_runtime" / "templates" / "paperless.env.ctmpl.j2"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
API_GATEWAY_CATALOG_PATH = REPO_ROOT / "config" / "api-gateway-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_defaults_define_public_oidc_runtime_and_taxonomy_contract() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)

    assert defaults["paperless_public_base_url"] == "https://{{ paperless_service_topology.public_hostname }}"
    assert (
        defaults["paperless_public_hostname_overrides"][0]["hostname"]
        == "{{ paperless_service_topology.public_hostname }}"
    )
    assert (
        defaults["paperless_public_hostname_overrides"][1]["hostname"]
        == "{{ hostvars['proxmox-host'].lv3_service_topology.keycloak.public_hostname }}"
    )
    assert defaults["paperless_internal_port"] == "{{ paperless_service_topology.ports.internal }}"
    assert defaults["paperless_internal_base_url"] == "http://127.0.0.1:{{ paperless_internal_port }}"
    assert defaults["paperless_keycloak_client_id"] == "paperless"
    assert defaults["paperless_keycloak_issuer"] == "https://sso.example.com/realms/lv3"
    assert defaults["paperless_ocr_language"] == "eng"
    assert defaults["paperless_image_pull_retries"] == 5
    assert defaults["paperless_image_pull_delay_seconds"] == 5
    assert defaults["paperless_openbao_runtime_compose_file"] == (
        "{{ openbao_compose_file | default('/opt/openbao/docker-compose.yml') }}"
    )
    assert defaults["paperless_openbao_runtime_service_name"] == "openbao"
    assert defaults["paperless_openbao_runtime_recovery_enabled"] == (
        "{{ paperless_openbao_runtime_compose_file | length > 0 }}"
    )
    assert defaults["paperless_api_token_local_file"].endswith("/.local/paperless/api-token.txt")
    assert defaults["paperless_taxonomy_local_file"].endswith("/.local/paperless/taxonomy.json")
    assert defaults["paperless_smoke_report_local_file"].endswith("/.local/paperless/smoke-upload-report.json")
    assert defaults["paperless_volume_names"]["media"] == "paperless-media"
    assert len(defaults["paperless_taxonomy_manifest"]["correspondents"]) == 3
    assert len(defaults["paperless_taxonomy_manifest"]["document_types"]) == 3
    assert len(defaults["paperless_taxonomy_manifest"]["tags"]) == 3


def test_argument_spec_requires_runtime_and_taxonomy_inputs() -> None:
    specs = load_yaml(ROLE_META)
    options = specs["argument_specs"]["main"]["options"]

    assert options["paperless_internal_port"]["type"] == "int"
    assert options["paperless_public_base_url"]["type"] == "str"
    assert options["paperless_image_pull_retries"]["type"] == "int"
    assert options["paperless_image_pull_delay_seconds"]["type"] == "int"
    assert options["paperless_openbao_runtime_compose_file"]["type"] == "path"
    assert options["paperless_openbao_runtime_service_name"]["type"] == "str"
    assert options["paperless_openbao_runtime_recovery_enabled"]["type"] == "bool"
    assert options["paperless_database_password_local_file"]["type"] == "path"
    assert options["paperless_sync_script"]["type"] == "path"
    assert options["paperless_taxonomy_manifest"]["type"] == "dict"


def test_main_tasks_render_bootstrap_sync_and_verify_paperless() -> None:
    tasks = load_yaml(ROLE_TASKS)
    names = [task["name"] for task in tasks]

    assert "Persist the Paperless taxonomy manifest on the guest" in names
    assert "Prepare OpenBao agent runtime secret injection for Paperless" in names
    assert "Render the Paperless environment file" in names
    assert "Render the Paperless compose file" in names
    assert "Pull the Paperless images" in names
    assert "Bootstrap the Paperless API token locally" in names
    assert "Check whether OpenBao answers before persisting the Paperless API token" in names
    assert "Recover the OpenBao runtime before persisting the Paperless API token" in names
    assert "Wait for OpenBao to answer after runtime recovery" in names
    assert "Load the OpenBao init payload before persisting the Paperless API token" in names
    assert "Ensure OpenBao is unsealed before persisting the Paperless API token" in names
    assert "Persist the Paperless API token in OpenBao" in names
    assert "Wait for the Paperless authenticated taxonomy endpoint" in names
    assert "Reconcile the Paperless taxonomy over the live API" in names
    assert "Verify the Paperless runtime" in names

    force_recreate_block = next(
        task
        for task in tasks
        if task.get("name")
        == "Force-recreate the Paperless runtime stack and recover Docker bridge-chain loss after networking recovery"
    )
    pull_task = next(task for task in tasks if task.get("name") == "Pull the Paperless images")
    bootstrap_task = next(task for task in tasks if task.get("name") == "Bootstrap the Paperless API token locally")
    openbao_probe_task = next(
        task
        for task in tasks
        if task.get("name") == "Check whether OpenBao answers before persisting the Paperless API token"
    )
    openbao_recovery_task = next(
        task
        for task in tasks
        if task.get("name") == "Recover the OpenBao runtime before persisting the Paperless API token"
    )
    openbao_recovery_wait_task = next(
        task for task in tasks if task.get("name") == "Wait for OpenBao to answer after runtime recovery"
    )
    openbao_unseal_task = next(
        task
        for task in tasks
        if task.get("name") == "Ensure OpenBao is unsealed before persisting the Paperless API token"
    )
    taxonomy_ready_task = next(
        task for task in tasks if task.get("name") == "Wait for the Paperless authenticated taxonomy endpoint"
    )
    sync_task = next(task for task in tasks if task.get("name") == "Reconcile the Paperless taxonomy over the live API")

    rescue_names = [task["name"] for task in force_recreate_block["rescue"]]
    assert "Detect Docker bridge-chain loss during the Paperless force-recreate" in rescue_names
    assert "Restart Docker to restore bridge networking before retrying the Paperless force-recreate" in rescue_names
    assert (
        "Ensure Docker bridge networking chains are present before retrying the Paperless force-recreate"
        in rescue_names
    )
    assert "Retry the Paperless runtime force-recreate after Docker networking recovery" in rescue_names
    force_recreate = force_recreate_block["block"][0]
    assert "--force-recreate" in force_recreate["ansible.builtin.command"]["argv"]
    assert force_recreate["failed_when"] == "paperless_force_recreate_up.rc != 0"
    assert pull_task["register"] == "paperless_pull"
    assert pull_task["retries"] == "{{ paperless_image_pull_retries }}"
    assert pull_task["delay"] == "{{ paperless_image_pull_delay_seconds }}"
    assert pull_task["until"] == "paperless_pull.rc == 0"
    assert "'Pull complete' in paperless_pull.stdout" in pull_task["changed_when"]
    assert "bootstrap-token" in bootstrap_task["ansible.builtin.script"]
    assert "--token-file {{ paperless_api_token_file | quote }}" in bootstrap_task["ansible.builtin.script"]
    assert (
        openbao_probe_task["ansible.builtin.uri"]["url"]
        == "http://127.0.0.1:{{ openbao_http_port }}/v1/sys/seal-status"
    )
    assert openbao_probe_task["register"] == "paperless_openbao_seal_status_initial"
    assert openbao_probe_task["failed_when"] is False
    assert openbao_recovery_task["ansible.builtin.command"]["argv"][-5:] == [
        "up",
        "-d",
        "--force-recreate",
        "--no-deps",
        "{{ paperless_openbao_runtime_service_name }}",
    ]
    assert openbao_recovery_task["ansible.builtin.command"]["argv"][3] == "{{ paperless_openbao_runtime_compose_file }}"
    assert openbao_recovery_task["when"] == [
        "paperless_openbao_runtime_recovery_enabled",
        "paperless_openbao_seal_status_initial.status | default(0) != 200",
    ]
    assert openbao_recovery_wait_task["until"] == "paperless_openbao_seal_status_recovered.status == 200"
    assert openbao_recovery_wait_task["when"] == [
        "paperless_openbao_runtime_recovery_enabled",
        "paperless_openbao_seal_status_initial.status | default(0) != 200",
    ]
    assert openbao_unseal_task["ansible.builtin.include_role"]["name"] == "lv3.platform.openbao_runtime"
    assert openbao_unseal_task["ansible.builtin.include_role"]["tasks_from"] == "ensure_unsealed"
    assert openbao_unseal_task["vars"]["openbao_unseal_context"] == "persisting the Paperless API token in OpenBao"
    assert (
        taxonomy_ready_task["ansible.builtin.uri"]["url"] == "{{ paperless_internal_base_url }}/api/tags/?page_size=1"
    )
    assert taxonomy_ready_task["ansible.builtin.uri"]["headers"]["Authorization"] == "Token {{ paperless_api_token }}"
    assert taxonomy_ready_task["retries"] == 24
    assert taxonomy_ready_task["delay"] == 5
    assert taxonomy_ready_task["until"] == "paperless_taxonomy_endpoint_ready.status == 200"
    assert "sync" in sync_task["ansible.builtin.script"]
    assert "--desired-state-file {{ paperless_taxonomy_manifest_file | quote }}" in sync_task["ansible.builtin.script"]
    assert "paperless_taxonomy_sync.rc == 0" in sync_task["changed_when"]
    assert sync_task["failed_when"] == "paperless_taxonomy_sync.rc != 0"


def test_verify_tasks_check_api_auth_and_taxonomy_drift() -> None:
    tasks = load_yaml(ROLE_VERIFY)
    names = [task["name"] for task in tasks]

    assert "Verify the Paperless local root endpoint" in names
    assert "Verify the Paperless authenticated documents endpoint" in names
    assert "Verify the Paperless taxonomy matches the declared manifest" in names


def test_publish_tasks_check_public_api_then_smoke_upload() -> None:
    tasks = load_yaml(ROLE_PUBLISH)
    names = [task["name"] for task in tasks]

    assert "Wait for the Paperless public root endpoint" in names
    assert "Verify the Paperless public API with the durable token" in names
    assert "Verify the Paperless taxonomy through the public publication" in names
    assert "Perform the Paperless public smoke upload verification" in names


def test_templates_enable_public_proxy_headers_and_named_state_volumes() -> None:
    compose_template = COMPOSE_TEMPLATE.read_text(encoding="utf-8")
    env_template = ENV_TEMPLATE.read_text(encoding="utf-8")
    env_ctemplate = ENV_CTEMPLATE.read_text(encoding="utf-8")

    assert "broker:" in compose_template
    assert "{{ paperless_volume_names.media }}:/usr/src/paperless/media" in compose_template
    assert '"{{ ansible_host }}:{{ paperless_internal_port }}:8000"' in compose_template
    assert '"127.0.0.1:{{ paperless_internal_port }}:8000"' in compose_template
    assert '      - "{{ item.hostname }}:{{ item.address }}"' in compose_template
    assert "PAPERLESS_REDIRECT_LOGIN_TO_SSO=true" in env_template
    assert "PAPERLESS_APPS=allauth.socialaccount.providers.openid_connect" in env_template
    assert "PAPERLESS_SOCIALACCOUNT_PROVIDERS={{ paperless_oidc_provider_json }}" in env_template
    assert (
        'PAPERLESS_DBPASS=[[ with secret "kv/data/{{ paperless_openbao_secret_path }}" ]][[ .Data.data.PAPERLESS_DBPASS ]][[ end ]]'
        in env_ctemplate
    )
    assert (
        'PAPERLESS_ADMIN_PASSWORD=[[ with secret "kv/data/{{ paperless_openbao_secret_path }}" ]][[ .Data.data.PAPERLESS_ADMIN_PASSWORD ]][[ end ]]'
        in env_ctemplate
    )


def test_inventory_exposes_paperless_to_edge_monitoring_and_private_callers() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))

    assert host_vars["platform_port_assignments"]["paperless_port"] == 8018
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]
    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    assert 8018 in host_rule["ports"]
    nginx_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "nginx-edge" and 8018 in rule["ports"])
    assert 8018 in nginx_rule["ports"]
    guest_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 8018 in rule["ports"])
    assert 8018 in guest_rule["ports"]
    monitoring_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "monitoring" and 8018 in rule["ports"]
    )
    assert 8018 in monitoring_rule["ports"]


def test_workflow_and_command_catalogs_declare_converge_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))

    workflow = workflow_catalog["workflows"]["converge-paperless"]
    command = command_catalog["commands"]["converge-paperless"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-paperless",
        "command": "make converge-paperless",
    }
    assert "syntax-check-paperless" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-paperless.md"
    assert command["workflow_id"] == "converge-paperless"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_api_gateway_catalog_exposes_the_authenticated_paperless_route() -> None:
    catalog = json.loads(API_GATEWAY_CATALOG_PATH.read_text(encoding="utf-8"))
    route = next(service for service in catalog["services"] if service["id"] == "paperless")

    assert route["gateway_prefix"] == "/v1/paperless"
    assert route["upstream"] == "http://10.10.10.20:8018"
    assert route["auth"] == "keycloak_jwt"
    assert route["healthcheck_path"] == "/"


def test_ansible_execution_scopes_register_the_direct_and_service_paperless_playbooks() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))
    direct = scopes["playbooks"]["playbooks/paperless.yml"]
    service = scopes["playbooks"]["playbooks/services/paperless.yml"]

    assert direct["playbook_id"] == "paperless"
    assert direct["mutation_scope"] == "platform"
    assert "service:paperless" in direct["shared_surfaces"]
    assert service["playbook_id"] == "paperless"
    assert "service:paperless" in service["shared_surfaces"]
