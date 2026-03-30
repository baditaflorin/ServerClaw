import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "flagsmith.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "flagsmith.yml"
COLLECTION_SERVICE_WRAPPER_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "services"
    / "flagsmith.yml"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def test_flagsmith_dns_stage_converges_only_the_flags_subdomain_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "flags.lv3.org"

    select_task = next(task for task in tasks if task["name"] == "Select the Flagsmith subdomain entry")
    assert "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]

    converge_task = next(task for task in tasks if task["name"] == "Converge the Flagsmith Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"


def test_flagsmith_playbook_converges_postgres_runtime_edge_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    assert [role["role"] for role in plays[1]["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.flagsmith_postgres",
    ]
    assert [role["role"] for role in plays[2]["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.flagsmith_runtime",
    ]
    assert [role["role"] for role in plays[3]["roles"]] == ["lv3.platform.nginx_edge_publication"]
    verify_task = plays[4]["tasks"][0]
    assert verify_task["ansible.builtin.include_role"]["name"] == "lv3.platform.flagsmith_runtime"
    assert verify_task["ansible.builtin.include_role"]["tasks_from"] == "verify_public.yml"


def test_flagsmith_service_wrappers_import_the_canonical_playbook() -> None:
    wrapper = yaml.safe_load(SERVICE_WRAPPER_PATH.read_text())
    collection_wrapper = yaml.safe_load(COLLECTION_SERVICE_WRAPPER_PATH.read_text())

    assert wrapper == [{"import_playbook": "../flagsmith.yml"}]
    assert collection_wrapper == [{"import_playbook": "../flagsmith.yml"}]


def test_converge_flagsmith_target_and_catalog_entrypoints_match() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-flagsmith:\n", 1)[1].split("\n\n", 1)[0]
    workflows = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))["workflows"]
    commands = json.loads(COMMAND_CATALOG_PATH.read_text(encoding="utf-8"))["commands"]
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))

    assert "$(MAKE) preflight WORKFLOW=converge-flagsmith" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/flagsmith.yml" in converge_block
    assert workflows["converge-flagsmith"]["preferred_entrypoint"]["target"] == "converge-flagsmith"
    assert workflows["converge-flagsmith"]["preflight"]["bootstrap_manifest_ids"] == ["shared-edge-generated-portals"]
    assert "syntax-check-flagsmith" in workflows["converge-flagsmith"]["validation_targets"]
    assert commands["converge-flagsmith"]["workflow_id"] == "converge-flagsmith"
    assert commands["converge-flagsmith"]["approval_policy"] == "sensitive_live_change"
    assert scopes["playbooks"]["playbooks/flagsmith.yml"]["playbook_id"] == "flagsmith"
    assert scopes["playbooks"]["playbooks/services/flagsmith.yml"]["playbook_id"] == "flagsmith"
