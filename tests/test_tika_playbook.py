import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "tika.yml"
ROOT_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "tika.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "tika.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
RUNTIME_AI_HOSTS = "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'runtime-ai-lv3' }}"


def test_tika_playbook_converges_firewall_before_runtime_verification() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    play = plays[0]

    assert play["hosts"] == RUNTIME_AI_HOSTS
    assert play["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.docker_runtime"},
        {"role": "lv3.platform.tika_runtime"},
    ]


def test_root_tika_playbook_imports_the_collection_entrypoint() -> None:
    wrapper = yaml.safe_load(ROOT_PLAYBOOK_PATH.read_text())
    assert wrapper == [{"import_playbook": "../collections/ansible_collections/lv3/platform/playbooks/tika.yml"}]


def test_service_wrapper_imports_the_root_tika_playbook() -> None:
    wrapper = yaml.safe_load(SERVICE_WRAPPER_PATH.read_text())
    assert wrapper == [{"import_playbook": "../tika.yml"}]


def test_workflow_and_command_catalogs_declare_converge_tika_entrypoint() -> None:
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())

    workflow = workflow_catalog["workflows"]["converge-tika"]
    command = command_catalog["commands"]["converge-tika"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-tika",
        "command": "make converge-tika",
    }
    assert "syntax-check-tika" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/configure-tika.md"
    assert command["workflow_id"] == "converge-tika"
    assert command["approval_policy"] == "sensitive_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_ansible_execution_scopes_registers_the_direct_tika_playbook() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text())
    entry = scopes["playbooks"]["playbooks/tika.yml"]

    assert entry["playbook_id"] == "tika"
    assert entry["mutation_scope"] == "lane"
    assert entry["target_lane"] == "lane:runtime-ai"
    assert "service:tika" in entry["shared_surfaces"]
