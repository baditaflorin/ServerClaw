import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "ntfy.yml"
SERVICE_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "ntfy.yml"
COLLECTION_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "ntfy.yml"
)
COLLECTION_SERVICE_PLAYBOOK_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "ntfy.yml"
)
MAKEFILE_PATH = REPO_ROOT / "Makefile"
COMMAND_CATALOG_PATH = REPO_ROOT / "config" / "command-catalog.json"
WORKFLOW_CATALOG_PATH = REPO_ROOT / "config" / "workflow-catalog.json"
EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
DEPENDENCY_WAVE_PLAYBOOKS_PATH = REPO_ROOT / "config" / "dependency-wave-playbooks.yaml"
CERTIFICATE_CATALOG_PATH = REPO_ROOT / "config" / "certificate-catalog.json"


def test_ntfy_playbook_imports_standard_includes_and_public_verify() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    docker_play = next(play for play in plays if play.get("name") == "Converge ntfy on the Docker runtime VM")
    assert [role["role"] for role in docker_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.ntfy_runtime",
    ]

    public_verify_play = next(
        play for play in plays if play.get("name") == "Verify the ntfy public health endpoint from the controller"
    )
    verify_task = public_verify_play["tasks"][0]
    assert verify_task["ansible.builtin.uri"]["url"] == "https://ntfy.{{ platform_domain }}/v1/health"
    assert verify_task["retries"] == 12


def test_ntfy_service_wrappers_import_root_playbook_with_metadata() -> None:
    root_wrapper_text = SERVICE_PLAYBOOK_PATH.read_text()
    collection_wrapper_text = COLLECTION_SERVICE_PLAYBOOK_PATH.read_text()

    assert (
        "# Purpose: Provide a leaf service import for ntfy so governed live-apply automation can target the notification channel directly."
        in root_wrapper_text
    )
    assert (
        "# Purpose: Provide a leaf service import for ntfy so governed live-apply automation can target the notification channel directly."
        in collection_wrapper_text
    )
    assert yaml.safe_load(SERVICE_PLAYBOOK_PATH.read_text()) == [{"import_playbook": "../ntfy.yml"}]
    assert yaml.safe_load(COLLECTION_SERVICE_PLAYBOOK_PATH.read_text()) == [{"import_playbook": "../ntfy.yml"}]
    assert COLLECTION_PLAYBOOK_PATH.exists()


def test_ntfy_workflow_command_and_scope_catalog_entries_exist() -> None:
    command_catalog = json.loads(COMMAND_CATALOG_PATH.read_text())
    workflow_catalog = json.loads(WORKFLOW_CATALOG_PATH.read_text())
    execution_scopes = yaml.safe_load(EXECUTION_SCOPES_PATH.read_text())

    assert command_catalog["commands"]["converge-ntfy"]["workflow_id"] == "converge-ntfy"
    assert command_catalog["commands"]["converge-ntfy"]["approval_policy"] == "sensitive_live_change"
    assert any(
        item["name"] == "hetzner_dns_api_token" for item in command_catalog["commands"]["converge-ntfy"]["inputs"]
    )
    assert (
        workflow_catalog["workflows"]["converge-ntfy"]["preferred_entrypoint"]["command"]
        == "HETZNER_DNS_API_TOKEN=... make converge-ntfy"
    )
    assert workflow_catalog["workflows"]["converge-ntfy"]["owner_runbook"] == "docs/runbooks/configure-ntfy.md"
    assert execution_scopes["playbooks"]["playbooks/ntfy.yml"] == {
        "playbook_id": "ntfy",
        "mutation_scope": "platform",
        "shared_surfaces": [
            "service:ntfy",
            "vm:110/service:nginx_edge_publication",
            "vm:120",
            "vm:120/service:ntfy",
            "config/subdomain-catalog.json",
            "inventory/host_vars/proxmox-host.yml",
        ],
    }


def test_converge_ntfy_target_builds_shared_edge_prerequisites() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-ntfy:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight WORKFLOW=converge-ntfy" in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "HETZNER_DNS_API_TOKEN" in converge_block
    assert "$(REPO_ROOT)/playbooks/ntfy.yml" in converge_block
    assert "$(ANSIBLE_TRACE_ARGS)" in converge_block
    assert "$(EXTRA_ARGS)" in converge_block


def test_ntfy_dependency_wave_metadata_locks_the_runtime_vm_and_shared_edge() -> None:
    catalog = yaml.safe_load(DEPENDENCY_WAVE_PLAYBOOKS_PATH.read_text(encoding="utf-8"))
    entries = {
        entry["path"]: entry
        for entry in catalog["playbooks"]
        if entry["path"] in {"playbooks/ntfy.yml", "playbooks/services/ntfy.yml"}
    }

    assert set(entries) == {"playbooks/ntfy.yml", "playbooks/services/ntfy.yml"}

    direct = entries["playbooks/ntfy.yml"]
    wrapper = entries["playbooks/services/ntfy.yml"]

    assert direct["make_target"] == "converge-ntfy"
    assert "vm:110" in direct["lock_resources"]
    assert "vm:110/service:nginx_edge_publication" in direct["lock_resources"]
    assert "vm:120" in direct["lock_resources"]
    assert "vm:120/service:ntfy" in direct["lock_resources"]

    assert wrapper["make_target"] == "live-apply-service"
    assert wrapper["make_vars"] == {"service": "ntfy"}
    assert wrapper["lock_resources"] == direct["lock_resources"]


def test_ntfy_public_hostname_is_present_in_the_certificate_catalog() -> None:
    certificates = json.loads(CERTIFICATE_CATALOG_PATH.read_text())["certificates"]
    ntfy_certificate = next(
        certificate for certificate in certificates if certificate["endpoint"]["host"] == "ntfy.example.com"
    )

    assert ntfy_certificate["id"] == "ntfy-edge"
    assert ntfy_certificate["service_id"] == "ntfy"
    assert ntfy_certificate["expected_issuer"] == "letsencrypt"
