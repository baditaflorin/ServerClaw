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

    assert "$(MAKE) preflight WORKFLOW=converge-glitchtip" in converge_block
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
        "command": "HETZNER_DNS_API_TOKEN=... make converge-glitchtip",
    }
    assert workflow["owner_runbook"] == "docs/runbooks/configure-glitchtip.md"
    assert "syntax-check-glitchtip" in workflow["validation_targets"]
    assert "keycloak_glitchtip_client_secret" in workflow["preflight"]["generated_secret_ids"]
    assert "glitchtip_platform_findings_event_url" in workflow["preflight"]["generated_secret_ids"]
    assert command["workflow_id"] == "converge-glitchtip"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


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
