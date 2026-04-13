import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "plausible.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "plausible.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"


def test_plausible_playbook_imports_standard_includes() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/docker_runtime_converge.yml",
        "_includes/nginx_edge_publication.yml",
    ]


def test_plausible_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper_text = SERVICE_WRAPPER_PATH.read_text()
    wrapper = yaml.safe_load(wrapper_text)

    assert "# Purpose: Provide the stable live-apply service wrapper for Plausible Analytics." in wrapper_text
    assert wrapper == [{"import_playbook": "../plausible.yml"}]


def test_converge_plausible_target_uses_the_canonical_playbook() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-plausible:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight WORKFLOW=converge-plausible" in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/plausible.yml" in converge_block


def test_converge_plausible_workflow_bootstraps_shared_edge_generated_portals() -> None:
    workflows = json.loads(WORKFLOW_CATALOG_PATH.read_text(encoding="utf-8"))["workflows"]

    assert workflows["converge-plausible"]["preflight"]["bootstrap_manifest_ids"] == ["shared-edge-generated-portals"]
