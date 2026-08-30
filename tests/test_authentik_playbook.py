import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "authentik.yml"
VARS_PATH = REPO_ROOT / "playbooks" / "vars" / "authentik.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
CONTROLLER_SECRET_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"
SECRET_CATALOG_PATH = REPO_ROOT / "config" / "secret-catalog.json"
SERVICE_CAPABILITY_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
DEPENDENCY_GRAPH_PATH = REPO_ROOT / "config" / "dependency-graph.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
AUTHENTIK_RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "configure-authentik.md"
PLATFORM_SERVICE_REGISTRY_PATH = REPO_ROOT / "inventory" / "group_vars" / "all" / "platform_services.yml"
GENERATED_PLATFORM_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"


def test_authentik_uses_localhost_dns_include_and_serial_runtime_then_edge() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))

    assert plays[0]["import_playbook"] == "_includes/dns_publication.yml"
    assert plays[0]["vars"]["service_dns_fqdn"] == "id.{{ platform_domain }}"
    assert plays[1]["hosts"] == (
        "{{ 'docker-runtime-staging' if (env | default('production')) == 'staging' else 'runtime-control' }}"
    )
    assert plays[1]["roles"][-1]["role"] == "lv3.platform.authentik_runtime"
    assert plays[2]["roles"] == [{"role": "lv3.platform.nginx_edge_publication"}]


def test_authentik_service_vars_pin_host_port_9010_without_shared_postgres() -> None:
    variables = yaml.safe_load(VARS_PATH.read_text(encoding="utf-8"))
    registry = yaml.safe_load(PLATFORM_SERVICE_REGISTRY_PATH.read_text(encoding="utf-8"))
    generated = yaml.safe_load(GENERATED_PLATFORM_PATH.read_text(encoding="utf-8"))

    assert variables["service_dns_fqdn"] == "id.{{ platform_domain }}"
    assert variables["service_needs_dns"] is True
    assert variables["service_needs_postgres"] is False
    assert variables["service_needs_nginx_edge"] is True
    assert "authentik_internal_port" not in variables
    assert variables["authentik_container_port"] == 9000
    assert registry["platform_service_registry"]["authentik"]["internal_port"] == 9010
    assert generated["platform_service_topology"]["authentik"]["ports"]["internal"] == 9010


def test_runtime_control_firewall_allows_the_edge_to_reach_authentik() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    runtime_control_rules = host_vars["network_policy"]["guests"]["runtime-control"]["allowed_inbound"]
    edge_rule = next(rule for rule in runtime_control_rules if rule["source"] == "nginx")

    assert edge_rule["protocol"] == "tcp"
    assert 9010 in edge_rule["ports"]


def test_converge_authentik_target_and_controller_catalogs_cover_safe_adoption() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    converge_block = makefile.split("converge-authentik:\n", 1)[1].split("\n\n", 1)[0]
    workflow = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))["workflows"]["converge-authentik"]
    command = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))["commands"]["converge-authentik"]

    assert "$(MAKE) preflight-authentik-deployment-selection" in converge_block
    assert "$(MAKE) preflight WORKFLOW=converge-authentik" in converge_block
    assert converge_block.index("preflight-authentik-deployment-selection") < converge_block.index(
        "preflight WORKFLOW=converge-authentik"
    )
    assert "converge-openbao" not in converge_block
    assert "$(REPO_ROOT)/playbooks/authentik.yml" in converge_block
    assert "-e @$(REPO_ROOT)/playbooks/vars/authentik.yml" in converge_block
    assert "$(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)" in converge_block
    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-authentik",
        "command": (
            "PLATFORM_IDENTITY_OVERLAY=/absolute/path/to/identity.yml "
            "PLATFORM_TOPOLOGY_OVERLAY=/absolute/path/to/topology.yml "
            "HETZNER_DNS_API_TOKEN=... make converge-authentik env=production"
        ),
    }
    assert workflow["preflight"]["generated_secret_ids"] == [
        "authentik_admin_token",
        "authentik_glitchtip_client_secret",
        "authentik_outline_client_secret",
    ]
    assert "syntax-check-authentik" in workflow["validation_targets"]
    assert "preflight-authentik-deployment-selection" in workflow["validation_targets"]
    assert "scripts/reconcile_authentik_oauth.py" in workflow["implementation_refs"]
    required_secrets = set(workflow["preflight"]["required_secret_ids"])
    assert "openbao_runtime_secret_provisioner_approle" in required_secrets
    assert "openbao_runtime_secret_provisioner_bootstrap_receipt" in required_secrets
    health_checks = {entry["id"]: entry for entry in workflow["preflight"]["health_checks"]}
    assert health_checks["authentik_deployment_selection"]["command"] == (
        "make --no-print-directory preflight-authentik-deployment-selection env=production"
    )
    assert (
        "https://sso.${platform_domain}/realms/${keycloak_realm}/"
        in health_checks["keycloak_public_discovery"]["command"]
    )
    oauth_verification = next(
        entry for entry in workflow["verification_commands"] if "reconcile_authentik_oauth.py" in entry
    )
    assert "--check --expect-no-change" in oauth_verification
    assert "--apply --expect-no-change" not in oauth_verification
    assert "scripts/resolve_local_overlay_root.sh" in oauth_verification
    assert all("id.example.com" not in entry for entry in workflow["verification_commands"])
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True
    assert "stable Authentik provider/application identifiers" in command["evidence"]["notes"]
    assert "Keycloak" in command["failure_guidance"]["rollback_guidance"][1]
    command_inputs = {entry["name"]: entry for entry in command["inputs"]}
    assert command_inputs["PLATFORM_IDENTITY_OVERLAY"]["required"] is True
    assert command_inputs["PLATFORM_TOPOLOGY_OVERLAY"]["required"] is True
    assert command_inputs["PLATFORM_INVENTORY_OVERLAY"]["required"] is False
    assert command_inputs["openbao_runtime_secret_provisioner_approle"]["required"] is True
    assert command_inputs["openbao_runtime_secret_provisioner_bootstrap_receipt"]["required"] is True

    scope = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))["playbooks"][
        "playbooks/authentik.yml"
    ]
    assert scope["mutation_scope"] == "platform"
    assert "service:authentik" in scope["shared_surfaces"]
    assert "service:glitchtip" in scope["shared_surfaces"]
    assert "service:outline" in scope["shared_surfaces"]
    assert "config/authentik/oauth-clients.yaml" in scope["shared_surfaces"]
    assert "config/integrations/glitchtip--authentik.yaml" in scope["shared_surfaces"]
    assert "config/integrations/outline--authentik.yaml" in scope["shared_surfaces"]


def test_openbao_provisioner_bootstrap_is_bounded_governed_and_selector_first() -> None:
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    target_block = makefile.split("bootstrap-openbao-runtime-secret-provisioner:\n", 1)[1].split("\n\n", 1)[0]
    recipe_lines = [line.strip() for line in target_block.splitlines() if line.startswith("\t")]
    workflow = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))["workflows"][
        "bootstrap-openbao-runtime-secret-provisioner"
    ]
    command = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))["commands"][
        "bootstrap-openbao-runtime-secret-provisioner"
    ]

    assert recipe_lines[0] == "$(MAKE) preflight-openbao-deployment-selection"
    assert recipe_lines[1] == "$(MAKE) preflight WORKFLOW=bootstrap-openbao-runtime-secret-provisioner"
    assert "scripts/bootstrap_openbao_runtime_secret_provisioner.py --apply" in recipe_lines[2]
    assert '--topology-file "$(PLATFORM_TOPOLOGY_OVERLAY)"' in recipe_lines[2]
    assert '--breakglass-password-file "$(LOCAL_OVERLAY_ROOT)/openbao/breakglass-password.txt"' in recipe_lines[2]
    assert '--output-root "$(LOCAL_OVERLAY_ROOT)/openbao"' in recipe_lines[2]
    assert '--ssh-private-key-file "$(BOOTSTRAP_KEY)"' in recipe_lines[2]
    assert "converge-openbao" not in target_block
    assert "ansible-playbook" not in target_block

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "bootstrap-openbao-runtime-secret-provisioner",
        "command": (
            "PLATFORM_IDENTITY_OVERLAY=/absolute/path/to/identity.yml "
            "PLATFORM_TOPOLOGY_OVERLAY=/absolute/path/to/topology.yml "
            "make bootstrap-openbao-runtime-secret-provisioner env=production"
        ),
    }
    assert workflow["preflight"]["required_secret_ids"] == [
        "bootstrap_ssh_private_key",
        "openbao_breakglass_password",
    ]
    assert workflow["preflight"]["generated_secret_ids"] == [
        "openbao_runtime_secret_provisioner_approle",
        "openbao_runtime_secret_provisioner_bootstrap_receipt",
    ]
    assert workflow["preflight"]["health_checks"][0]["command"] == (
        "make --no-print-directory preflight-openbao-deployment-selection env=production"
    )
    assert workflow["budget"]["max_restarts"] == 0
    verification = next(
        entry
        for entry in workflow["verification_commands"]
        if "bootstrap_openbao_runtime_secret_provisioner.py" in entry
    )
    assert "--check" in verification
    assert "--apply" not in verification
    assert "--topology-file" in verification
    assert "--ssh-private-key-file" in verification
    assert "scripts/resolve_local_overlay_root.sh" in verification

    command_inputs = {entry["name"]: entry for entry in command["inputs"]}
    assert command["approval_policy"] == "sensitive_live_change"
    assert command_inputs["PLATFORM_IDENTITY_OVERLAY"]["required"] is True
    assert command_inputs["PLATFORM_TOPOLOGY_OVERLAY"]["required"] is True
    assert command_inputs["PLATFORM_INVENTORY_OVERLAY"]["required"] is False
    assert command_inputs["bootstrap_ssh_private_key"]["required"] is True
    assert command_inputs["openbao_breakglass_password"]["required"] is True
    assert "Never record the password, role_id, secret_id, token" in command["evidence"]["notes"]


def test_authentik_glitchtip_secret_is_complete_across_secret_and_service_catalogs() -> None:
    controller_secrets = json.loads(CONTROLLER_SECRET_PATH.read_text(encoding="utf-8"))["secrets"]
    secret_catalog = json.loads(SECRET_CATALOG_PATH.read_text(encoding="utf-8"))["secrets"]
    services = {
        service["id"]: service
        for service in json.loads(SERVICE_CAPABILITY_PATH.read_text(encoding="utf-8"))["services"]
    }

    selected_secret = controller_secrets["authentik_glitchtip_client_secret"]
    assert selected_secret["path"] == ".local/authentik/glitchtip-client-secret.txt"
    assert selected_secret["status"] == "active"
    assert selected_secret["origin"] == "generated_by_repo"
    secret_entry = next(entry for entry in secret_catalog if entry["id"] == "authentik_glitchtip_client_secret")
    assert secret_entry["owner_service"] == "glitchtip"
    assert secret_entry["storage_ref"] == "authentik_glitchtip_client_secret"
    assert "authentik_glitchtip_client_secret" in services["authentik"]["secret_catalog_ids"]
    assert "authentik_glitchtip_client_secret" in services["glitchtip"]["secret_catalog_ids"]
    assert "keycloak_glitchtip_client_secret" in services["glitchtip"]["secret_catalog_ids"]
    provisioner = controller_secrets["openbao_runtime_secret_provisioner_approle"]
    assert provisioner["path"] == ".local/openbao/runtime-secret-provisioner-approle.json"
    receipt = controller_secrets["openbao_runtime_secret_provisioner_bootstrap_receipt"]
    assert receipt["path"] == ".local/openbao/runtime-secret-provisioner-bootstrap-receipt.json"
    assert "openbao_runtime_secret_provisioner_approle" in services["openbao"]["secret_catalog_ids"]


def test_generated_dependency_evidence_models_authentik_selection_and_keycloak_rollback() -> None:
    graph = json.loads(DEPENDENCY_GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = {entry["id"]: entry for entry in graph["nodes"]}
    edges = {(entry["from"], entry["to"]): entry for entry in graph["edges"]}

    assert nodes["authentik"]["tier"] == 1
    assert ("authentik", "postgres") not in edges
    assert edges[("authentik", "openbao")]["type"] == "startup_only"
    assert edges[("glitchtip", "authentik")]["type"] == "soft"
    assert "headless allauth redirect" in edges[("glitchtip", "authentik")]["description"]
    assert edges[("glitchtip", "keycloak")]["type"] == "soft"
    assert "rollback" in edges[("glitchtip", "keycloak")]["description"]


def test_authentik_runbook_documents_safe_bootstrap_adoption_and_read_only_idempotence() -> None:
    runbook = AUTHENTIK_RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "bootstrap-openbao-runtime-secret-provisioner" in runbook
    assert "make converge-openbao" not in runbook
    assert "authentik_secret_bootstrap_mode=adopt_legacy" in runbook
    assert "authentik_secret_bootstrap_mode` has three explicit modes" in runbook
    assert "--check" in runbook
    assert "--expect-no-change" in runbook
    assert "--apply" not in runbook
    assert "scripts/resolve_local_overlay_root.sh" in runbook
    assert "PLATFORM_INVENTORY_OVERLAY" in runbook
    assert "bootstrap-openbao-runtime-secret-provisioner env=production" in runbook
    assert "Authorization: Bearer $(" not in runbook
    assert "id.example.org" not in runbook
    assert "/Users/" not in runbook
