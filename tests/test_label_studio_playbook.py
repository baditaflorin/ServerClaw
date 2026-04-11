import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "label-studio.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "label-studio.yml"
COLLECTION_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "label-studio.yml"
)
COLLECTION_SERVICE_PLAYBOOK_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "services"
    / "label-studio.yml"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def test_label_studio_playbook_converges_dns_database_runtime_edge_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    dns_play = plays[0]
    postgres_play = next(play for play in plays if play["name"] == "Prepare PostgreSQL for Label Studio")
    runtime_play = next(play for play in plays if play["name"] == "Converge Label Studio on the Docker runtime VM")
    edge_play = next(play for play in plays if play["name"] == "Publish Label Studio through the NGINX edge")
    publish_play = next(
        play for play in plays if play["name"] == "Verify the public Label Studio shared-edge publication"
    )

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "annotate.lv3.org"
    assert dns_play["vars"]["subdomain_catalog_path"] == "{{ playbook_dir }}/../config/subdomain-catalog.json"
    assert dns_play["vars"]["inventory_defaults_path"] == "{{ playbook_dir }}/../inventory/group_vars/all.yml"

    select_task = next(task for task in dns_play["tasks"] if task["name"] == "Select the Label Studio subdomain entry")
    assert (
        "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]
    )

    assert [role["role"] for role in postgres_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.label_studio_postgres",
    ]
    assert [role["role"] for role in runtime_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.label_studio_runtime",
        "lv3.platform.typesense_runtime",
        "lv3.platform.api_gateway_runtime",
    ]
    assert [role["role"] for role in edge_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.public_edge_oidc_auth",
        "lv3.platform.nginx_edge_publication",
    ]
    assert edge_play["vars_files"] == ["{{ playbook_dir }}/../inventory/group_vars/platform.yml"]

    publish_task = publish_play["tasks"][0]
    assert publish_task["ansible.builtin.include_role"]["name"] == "lv3.platform.label_studio_runtime"
    assert publish_task["ansible.builtin.include_role"]["tasks_from"] == "verify_public.yml"


def test_label_studio_service_wrappers_import_the_canonical_playbook() -> None:
    root_wrapper_text = SERVICE_PLAYBOOK_PATH.read_text()
    collection_wrapper_text = COLLECTION_SERVICE_PLAYBOOK_PATH.read_text()

    assert (
        "# Purpose: Provide the canonical service-scoped live-apply entrypoint for Label Studio." in root_wrapper_text
    )
    assert (
        "# Purpose: Provide the canonical service-scoped live-apply entrypoint for Label Studio."
        in collection_wrapper_text
    )
    assert yaml.safe_load(root_wrapper_text) == [{"import_playbook": "../label-studio.yml"}]
    assert yaml.safe_load(collection_wrapper_text) == [{"import_playbook": "../label-studio.yml"}]
    assert COLLECTION_PLAYBOOK_PATH.exists()


def test_converge_label_studio_target_and_catalog_entrypoints_match() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-label-studio:\n", 1)[1].split("\n\n", 1)[0]
    workflows = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))["workflows"]
    commands = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))["commands"]
    scopes = yaml.safe_load(EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))

    assert "$(MAKE) preflight WORKFLOW=converge-label-studio" in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/label-studio.yml" in converge_block
    assert workflows["converge-label-studio"]["preferred_entrypoint"]["target"] == "converge-label-studio"
    assert workflows["converge-label-studio"]["preflight"]["bootstrap_manifest_ids"] == [
        "shared-edge-generated-portals"
    ]
    assert "syntax-check-label-studio" in workflows["converge-label-studio"]["validation_targets"]
    assert commands["converge-label-studio"]["workflow_id"] == "converge-label-studio"
    assert commands["converge-label-studio"]["approval_policy"] == "sensitive_live_change"
    assert scopes["playbooks"]["playbooks/label-studio.yml"]["playbook_id"] == "label_studio"
    assert scopes["playbooks"]["playbooks/services/label-studio.yml"]["playbook_id"] == "label_studio"
