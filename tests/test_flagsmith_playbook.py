import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "flagsmith.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "flagsmith.yml"
COLLECTION_SERVICE_WRAPPER_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "flagsmith.yml"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"


def test_flagsmith_playbook_imports_standard_includes_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/postgres_preparation.yml",
        "_includes/docker_runtime_converge.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    verify_play = next(play for play in plays if play.get("name") == "Verify the Flagsmith public publication")
    verify_task = verify_play["tasks"][0]
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
