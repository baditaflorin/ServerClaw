import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "piper.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "piper.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_playbook_converges_private_piper_runtime() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)

    assert len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == "docker-runtime-lv3"
    roles = [role["role"] for role in play["roles"]]
    assert roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.piper_runtime",
    ]


def test_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../piper.yml"}]


def test_inventory_exposes_private_piper_port_to_guests_docker_and_monitoring() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))

    assert host_vars["platform_port_assignments"]["piper_port"] == 8100
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]

    management_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "management" and 8100 in rule["ports"]
    )
    assert 8100 in management_rule["ports"]
    guest_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "all_guests" and 8100 in rule["ports"])
    assert 8100 in guest_rule["ports"]
    docker_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "172.16.0.0/12" and 8100 in rule["ports"]
    )
    assert 8100 in docker_rule["ports"]
    monitoring_rule = next(
        rule for rule in docker_runtime_rules if rule["source"] == "monitoring-lv3" and 8100 in rule["ports"]
    )
    assert 8100 in monitoring_rule["ports"]


def test_workflow_and_command_catalogs_declare_converge_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))

    workflow = workflow_catalog["workflows"]["converge-piper"]
    command = command_catalog["commands"]["converge-piper"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-piper",
        "command": "make converge-piper",
    }
    assert "syntax-check-piper" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-piper.md"
    assert "http://127.0.0.1:8100/healthz" in workflow["verification_commands"][1]
    assert "http://127.0.0.1:8100/api/voices" in workflow["verification_commands"][2]
    assert "http://127.0.0.1:8100/api/tts?voice=en_US-ryan-medium" in workflow["verification_commands"][3]
    assert command["workflow_id"] == "converge-piper"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_ansible_execution_scopes_register_the_direct_and_service_playbooks() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))
    direct = scopes["playbooks"]["playbooks/piper.yml"]
    wrapper = scopes["playbooks"]["playbooks/services/piper.yml"]

    assert direct["playbook_id"] == "piper"
    assert direct["mutation_scope"] == "host"
    assert "service:piper" in direct["shared_surfaces"]

    assert wrapper["playbook_id"] == "piper"
    assert wrapper["mutation_scope"] == "host"
    assert "service:piper" in wrapper["shared_surfaces"]
