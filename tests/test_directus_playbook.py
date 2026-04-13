import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "directus.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "directus.yml"
COLLECTION_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "directus.yml"
)
COLLECTION_SERVICE_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "directus.yml"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def test_directus_playbook_imports_standard_includes_and_exposes_access_model_seed() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/postgres_preparation.yml",
        "_includes/docker_runtime_converge.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    access_model_play = next(
        play for play in plays if play.get("name") == "Seed the Directus access model in PostgreSQL"
    )
    access_task = access_model_play["tasks"][0]
    assert access_task["ansible.builtin.include_role"]["name"] == "lv3.platform.directus_postgres"
    assert access_task["ansible.builtin.include_role"]["tasks_from"] == "access_model.yml"

    public_verify_play = next(play for play in plays if play.get("name") == "Verify the public Directus publication")
    verify_task = public_verify_play["tasks"][0]
    assert verify_task["ansible.builtin.include_role"]["name"] == "lv3.platform.directus_runtime"
    assert verify_task["ansible.builtin.include_role"]["tasks_from"] == "publish.yml"


def test_directus_service_wrappers_import_root_playbook_with_metadata() -> None:
    root_wrapper_text = SERVICE_PLAYBOOK_PATH.read_text()
    collection_wrapper_text = COLLECTION_SERVICE_PLAYBOOK_PATH.read_text()

    assert "# Purpose: Provide the canonical service-scoped live-apply entrypoint for Directus." in root_wrapper_text
    assert (
        "# Purpose: Provide the canonical service-scoped live-apply entrypoint for Directus." in collection_wrapper_text
    )
    assert yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text()) == [{"import_playbook": "../directus.yml"}]
    assert yaml.safe_load(COLLECTION_SERVICE_PLAYBOOK_PATH.read_text()) == [{"import_playbook": "../directus.yml"}]
    assert COLLECTION_PLAYBOOK_PATH.exists()


def test_directus_workflow_command_and_scope_catalog_entries_exist() -> None:
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    execution_scopes = yaml.safe_load(EXECUTION_SCOPES_PATH.read_text())

    assert command_catalog["commands"]["converge-directus"]["workflow_id"] == "converge-directus"
    assert command_catalog["commands"]["converge-directus"]["approval_policy"] == "sensitive_live_change"
    assert workflow_catalog["workflows"]["converge-directus"]["preferred_entrypoint"]["target"] == "converge-directus"
    assert workflow_catalog["workflows"]["converge-directus"]["owner_runbook"] == "docs/runbooks/configure-directus.md"
    assert execution_scopes["playbooks"]["playbooks/directus.yml"] == {
        "playbook_id": "directus",
        "mutation_scope": "platform",
        "shared_surfaces": [
            "service:directus",
            "inventory/host_vars/proxmox-host.yml",
        ],
    }
    assert workflow_catalog["workflows"]["converge-directus"]["preflight"]["bootstrap_manifest_ids"] == [
        "shared-edge-generated-portals"
    ]


def test_converge_directus_target_builds_shared_edge_artifacts_first() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-directus:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight WORKFLOW=converge-directus" in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/directus.yml" in converge_block
