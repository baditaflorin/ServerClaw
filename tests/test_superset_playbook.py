import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "superset.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "superset.yml"
COLLECTION_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "superset.yml"
)
COLLECTION_SERVICE_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "superset.yml"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def test_superset_playbook_orders_dns_database_runtime_edge_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    dns_play = plays[0]
    postgres_play = next(play for play in plays if play["name"] == "Prepare PostgreSQL for Superset")
    runtime_play = next(play for play in plays if play["name"] == "Converge Superset on the Docker runtime VM")
    edge_play = next(play for play in plays if play["name"] == "Publish Superset through the NGINX edge")
    publish_play = next(play for play in plays if play["name"] == "Verify the public Superset publication")

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "bi.example.com"

    assert [role["role"] for role in postgres_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.superset_postgres",
    ]
    assert [role["role"] for role in runtime_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.keycloak_runtime",
        "lv3.platform.superset_runtime",
    ]
    assert edge_play["vars_files"] == ["{{ playbook_dir }}/../inventory/group_vars/platform.yml"]
    publish_task = publish_play["tasks"][0]
    assert publish_task["ansible.builtin.include_role"]["name"] == "lv3.platform.superset_runtime"
    assert publish_task["ansible.builtin.include_role"]["tasks_from"] == "publish.yml"


def test_superset_service_wrappers_import_root_playbook_with_metadata() -> None:
    root_wrapper_text = SERVICE_PLAYBOOK_PATH.read_text()
    collection_wrapper_text = COLLECTION_SERVICE_PLAYBOOK_PATH.read_text()

    assert "# Purpose: Provide the canonical service-scoped live-apply entrypoint for Superset." in root_wrapper_text
    assert (
        "# Purpose: Provide the canonical service-scoped live-apply entrypoint for Superset." in collection_wrapper_text
    )
    assert yaml.safe_load(root_wrapper_text) == [{"import_playbook": "../superset.yml"}]
    assert yaml.safe_load(collection_wrapper_text) == [{"import_playbook": "../superset.yml"}]
    assert COLLECTION_PLAYBOOK_PATH.exists()


def test_superset_workflow_command_and_scope_catalog_entries_exist() -> None:
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    execution_scopes = yaml.safe_load(EXECUTION_SCOPES_PATH.read_text())

    assert command_catalog["commands"]["converge-superset"]["workflow_id"] == "converge-superset"
    assert command_catalog["commands"]["converge-superset"]["approval_policy"] == "sensitive_live_change"
    assert workflow_catalog["workflows"]["converge-superset"]["preferred_entrypoint"]["target"] == "converge-superset"
    assert workflow_catalog["workflows"]["converge-superset"]["owner_runbook"] == "docs/runbooks/configure-superset.md"
    assert execution_scopes["playbooks"]["playbooks/superset.yml"] == {
        "playbook_id": "superset",
        "mutation_scope": "platform",
        "shared_surfaces": [
            "service:superset",
            "inventory/host_vars/proxmox-host.yml",
        ],
    }


def test_converge_superset_target_builds_shared_edge_artifacts_first() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-superset:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight WORKFLOW=converge-superset" in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/superset.yml" in converge_block
