import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "glitchtip.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "glitchtip.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
SERVICE_CAPABILITY_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
SERVICE_COMPLETENESS_PATH = REPO_ROOT / "config" / "service-completeness.json"
HEALTH_PROBE_PATH = REPO_ROOT / "config" / "health-probe-catalog.json"
SUBDOMAIN_CATALOG_PATH = REPO_ROOT / "config" / "subdomain-catalog.json"
GLITCHTIP_RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "configure-glitchtip.md"


def test_glitchtip_playbook_imports_standard_includes_and_publication_play() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/postgres_preparation.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    runtime_play = next(play for play in plays if play.get("name") == "Converge GlitchTip on the Docker runtime VM")
    assert runtime_play["vars"]["linux_guest_firewall_recover_missing_docker_bridge_chains"] is True
    runtime_roles = [entry["role"] for entry in runtime_play["roles"]]
    assert "lv3.platform.glitchtip_runtime" in runtime_roles
    assert "lv3.platform.keycloak_runtime" not in runtime_roles

    publish_play = next(play for play in plays if play.get("name") == "Bootstrap and verify GlitchTip publication")
    publish_task = publish_play["tasks"][0]
    assert publish_task["ansible.builtin.include_role"] == {
        "name": "lv3.platform.glitchtip_runtime",
        "tasks_from": "publish.yml",
    }


def test_glitchtip_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper_text = SERVICE_WRAPPER_PATH.read_text()
    wrapper = yaml.safe_load(wrapper_text)

    assert "# Purpose: Provide the service-scoped live-apply entry point for GlitchTip." in wrapper_text
    assert wrapper == [{"import_playbook": "../glitchtip.yml"}]


def test_converge_glitchtip_target_uses_the_canonical_playbook_and_publication_prechecks() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-glitchtip:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight-glitchtip-deployment-selection" in converge_block
    assert "$(MAKE) preflight WORKFLOW=converge-glitchtip" in converge_block
    assert converge_block.index("preflight-glitchtip-deployment-selection") < converge_block.index(
        "preflight WORKFLOW=converge-glitchtip"
    )
    assert "converge-openbao" not in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/glitchtip.yml" in converge_block
    assert "$(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)" in converge_block


def test_glitchtip_workflow_and_command_catalogs_declare_the_live_apply_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))

    workflow = workflow_catalog["workflows"]["converge-glitchtip"]
    command = command_catalog["commands"]["converge-glitchtip"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-glitchtip",
        "command": (
            "PLATFORM_IDENTITY_OVERLAY=/absolute/path/to/identity.yml "
            "PLATFORM_TOPOLOGY_OVERLAY=/absolute/path/to/topology.yml "
            "HETZNER_DNS_API_TOKEN=... make converge-glitchtip env=production"
        ),
    }
    assert workflow["owner_runbook"] == "docs/runbooks/configure-glitchtip.md"
    assert "syntax-check-glitchtip" in workflow["validation_targets"]
    assert "preflight-glitchtip-deployment-selection" in workflow["validation_targets"]
    assert "openbao_runtime_secret_provisioner_approle" in workflow["preflight"]["required_secret_ids"]
    assert "openbao_runtime_secret_provisioner_bootstrap_receipt" in workflow["preflight"]["required_secret_ids"]
    assert "authentik_glitchtip_client_secret" in workflow["preflight"]["required_secret_ids"]
    assert "authentik_glitchtip_client_secret" not in workflow["preflight"]["generated_secret_ids"]
    assert "glitchtip_platform_findings_event_url" in workflow["preflight"]["generated_secret_ids"]
    assert command["workflow_id"] == "converge-glitchtip"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True
    command_inputs = {entry["name"]: entry for entry in command["inputs"]}
    assert command_inputs["authentik_glitchtip_client_secret"]["required"] is True
    assert command_inputs["PLATFORM_IDENTITY_OVERLAY"]["required"] is True
    assert command_inputs["PLATFORM_TOPOLOGY_OVERLAY"]["required"] is True
    assert command_inputs["PLATFORM_INVENTORY_OVERLAY"]["required"] is False
    assert command_inputs["openbao_runtime_secret_provisioner_approle"]["required"] is True
    assert command_inputs["openbao_runtime_secret_provisioner_bootstrap_receipt"]["required"] is True
    assert "headless authorization redirect" in command["evidence"]["notes"]
    health_checks = {entry["id"]: entry for entry in workflow["preflight"]["health_checks"]}
    assert health_checks["glitchtip_deployment_selection"]["command"] == (
        "make --no-print-directory preflight-glitchtip-deployment-selection env=production"
    )
    authentik_check = health_checks["authentik_public_discovery"]["command"]
    assert "https://id.${platform_domain}/application/o/glitchtip/" in authentik_check
    assert "id.example.com" not in authentik_check
    event_smoke = next(entry for entry in workflow["verification_commands"] if "glitchtip_event_smoke.py" in entry)
    assert "scripts/resolve_local_overlay_root.sh" in event_smoke
    assert ".local/glitchtip" not in event_smoke
    oidc_smoke = next(entry for entry in workflow["verification_commands"] if "glitchtip_oidc_smoke.py" in entry)
    assert '--client-secret-file "${local_root}/authentik/glitchtip-client-secret.txt"' in oidc_smoke
    assert "https://errors.${platform_domain}" in oidc_smoke
    assert all("errors.example.com" not in entry for entry in workflow["verification_commands"])
    assert any("interactive Authentik browser login" in output for output in workflow["outputs"])


def test_inventory_and_execution_scope_expose_glitchtip_publication_surface() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))

    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime"]["allowed_inbound"]
    host_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "host")
    monitoring_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "monitoring" and 3005 in rule["ports"]
    )
    scope_entry = scopes["playbooks"]["playbooks/glitchtip.yml"]

    assert host_vars["platform_port_assignments"]["glitchtip_port"] == 3005
    assert 3005 in host_rule["ports"]
    assert monitoring_rule["description"] == "Private monitoring probes for the GlitchTip runtime"
    assert scope_entry["playbook_id"] == "glitchtip"
    assert scope_entry["mutation_scope"] == "platform"
    assert "service:glitchtip" in scope_entry["shared_surfaces"]
    assert "service:authentik" in scope_entry["shared_surfaces"]
    assert "config/integrations/glitchtip--authentik.yaml" in scope_entry["shared_surfaces"]


def test_glitchtip_catalogs_match_tracked_topology_and_selected_oidc_provider() -> None:
    services = {
        entry["id"]: entry for entry in json.loads(SERVICE_CAPABILITY_PATH.read_text(encoding="utf-8"))["services"]
    }
    completeness = json.loads(SERVICE_COMPLETENESS_PATH.read_text(encoding="utf-8"))["services"]["glitchtip"]
    health = json.loads(HEALTH_PROBE_PATH.read_text(encoding="utf-8"))["services"]["glitchtip"]
    subdomains = json.loads(SUBDOMAIN_CATALOG_PATH.read_text(encoding="utf-8"))["subdomains"]

    assert services["glitchtip"]["internal_url"] == "http://10.10.10.20:3005"
    assert health["readiness"]["docker_publication"]["bindings"] == [{"host": "10.10.10.20", "port": 3005}]
    assert completeness["authentik_client_generated"] is True
    assert completeness["oidc_provider"] == "authentik"
    authentik_subdomain = next(entry for entry in subdomains if entry["service_id"] == "authentik")
    assert authentik_subdomain["status"] == "active"


def test_glitchtip_runbook_uses_safe_provisioner_and_worktree_resolved_artifacts() -> None:
    runbook = GLITCHTIP_RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "bootstrap-openbao-runtime-secret-provisioner" in runbook
    assert "make converge-openbao" not in runbook
    assert "runtime-secret-provisioner-bootstrap-receipt.json" in runbook
    assert "scripts/resolve_local_overlay_root.sh" in runbook
    assert "PLATFORM_TOPOLOGY_OVERLAY" in runbook
    assert "PLATFORM_INVENTORY_OVERLAY" in runbook
    assert '--api-token-file "${LOCAL_ROOT}/glitchtip/api-token.txt"' in runbook
    assert '--dsn-file "${LOCAL_ROOT}/glitchtip/platform-findings-event-url.txt"' in runbook
    assert '--client-secret-file "${LOCAL_ROOT}/authentik/glitchtip-client-secret.txt"' in runbook
    assert "Mandatory interactive browser gate" in runbook
    assert "advance to Outline" in runbook
    assert "remains blocked until the login, session, and logout evidence" in runbook
    assert "converge-glitchtip env=production" in runbook
    assert "presence alone is not rollback-health evidence" in runbook
