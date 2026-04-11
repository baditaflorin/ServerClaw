import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "plausible.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "plausible.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"


def test_plausible_dns_stage_converges_only_the_analytics_subdomain_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "analytics.lv3.org"

    select_task = next(task for task in tasks if task.get("name") == "Select the Plausible subdomain entry")
    assert (
        "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]
    )

    converge_task = next(task for task in tasks if task.get("name") == "Converge the Plausible Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"
    assert converge_task["vars"]["hetzner_dns_record_value"] == "{{ selected_subdomain.target }}"


def test_plausible_playbook_converges_runtime_and_edge_roles() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    runtime_roles = [role["role"] for role in plays[1]["roles"]]
    edge_roles = [role["role"] for role in plays[2]["roles"]]

    assert runtime_roles == [
        "lv3.platform.docker_runtime",
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.plausible_runtime",
    ]
    assert edge_roles == ["lv3.platform.nginx_edge_publication"]


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
