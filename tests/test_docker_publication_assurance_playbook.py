import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "docker-publication-assurance.yml"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
EXECUTION_SCOPE_CATALOG_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_docker_publication_assurance_playbook_targets_managed_docker_guests() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    assert len(plays) == 1
    play = plays[0]
    assert play["name"] == "Converge Docker publication assurance on managed Docker guests"
    assert (
        play["hosts"]
        == "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'docker-runtime-lv3:coolify-lv3' }}"
    )
    assert [role["role"] for role in play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
    ]


def test_docker_publication_assurance_playbook_selects_declared_contracts_only() -> None:
    play = yaml.safe_load(PLAYBOOK_PATH.read_text())[0]
    task_names = [task["name"] for task in play["tasks"]]
    select_task = next(
        task for task in play["tasks"] if task["name"] == "Select Docker publication contracts for this host"
    )
    run_task = next(
        task
        for task in play["tasks"]
        if task["name"] == "Run Docker publication assurance for each declared service on this host"
    )

    assert task_names == [
        "Load the health probe catalog",
        "Initialize the host-local Docker publication contract list",
        "Select Docker publication contracts for this host",
        "Run Docker publication assurance for each declared service on this host",
    ]
    assert select_task["when"] == [
        "item.value.owning_vm == inventory_hostname",
        "item.value.readiness is defined",
        "item.value.readiness.docker_publication is defined",
    ]
    assert run_task["vars"]["service_health_probe_id"] == "{{ item.service_id }}"
    assert run_task["vars"]["playbook_execution_service_probe"] == "{{ item.service_probe }}"
    assert run_task["vars"]["playbook_execution_docker_publication_contract"] == (
        "{{ item.service_probe.readiness.docker_publication }}"
    )


def test_docker_publication_assurance_workflow_catalog_declares_the_converge_entrypoint() -> None:
    catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    workflow = catalog["workflows"]["converge-docker-publication-assurance"]

    assert workflow["preferred_entrypoint"] == {
        "kind": "make_target",
        "target": "converge-docker-publication-assurance",
        "command": "make converge-docker-publication-assurance",
    }
    assert "syntax-check-docker-publication-assurance" in workflow["validation_targets"]
    assert workflow["owner_runbook"] == "docs/runbooks/docker-publication-assurance.md"


def test_docker_publication_assurance_execution_scope_catalog_declares_a_leaf_entry() -> None:
    catalog = yaml.safe_load(EXECUTION_SCOPE_CATALOG_PATH.read_text())
    entry = catalog["playbooks"]["playbooks/docker-publication-assurance.yml"]

    assert entry["playbook_id"] == "docker-publication-assurance"
    assert entry["mutation_scope"] == "platform"
    assert "config/health-probe-catalog.json" in entry["shared_surfaces"]


def test_docker_publication_assurance_command_catalog_declares_live_change_contract() -> None:
    catalog = json.loads(COMMAND_CATALOG_PATH.read_text())
    command = catalog["commands"]["converge-docker-publication-assurance"]

    assert command["workflow_id"] == "converge-docker-publication-assurance"
    assert command["approval_policy"] == "standard_live_change"
    assert command["evidence"]["live_apply_receipt_required"] is True


def test_docker_publication_assurance_make_targets_exist() -> None:
    makefile = MAKEFILE_PATH.read_text()

    assert "syntax-check-docker-publication-assurance:" in makefile
    assert "converge-docker-publication-assurance:" in makefile
