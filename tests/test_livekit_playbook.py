import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "livekit.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "livekit.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
ANSIBLE_EXECUTION_SCOPES_PATH = REPO_ROOT / "config" / "ansible-execution-scopes.yaml"
DEPENDENCY_WAVE_PLAYBOOKS_PATH = REPO_ROOT / "config" / "dependency-wave-playbooks.yaml"


def test_livekit_playbook_imports_standard_includes_and_verification() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    imports = [entry["import_playbook"] for entry in plays if "import_playbook" in entry]

    assert imports == [
        "_includes/dns_publication.yml",
        "_includes/nginx_edge_publication.yml",
    ]

    verify_play = next(
        play for play in plays if play.get("name") == "Verify public LiveKit room lifecycle from the controller"
    )
    verify_task = verify_play["tasks"][0]
    assert verify_task["ansible.builtin.command"]["argv"][1] == "{{ livekit_tool_script }}"
    assert verify_task["ansible.builtin.command"]["argv"][2] == "verify-room-lifecycle"
    assert "https://livekit.{{ platform_domain }}" in verify_task["ansible.builtin.command"]["argv"]


def test_livekit_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper_text = SERVICE_WRAPPER_PATH.read_text()
    wrapper = yaml.safe_load(wrapper_text)

    assert "# Purpose: Provide the stable live-apply service wrapper for LiveKit." in wrapper_text
    assert wrapper == [{"import_playbook": "../livekit.yml"}]


def test_converge_livekit_target_uses_the_canonical_playbook() -> None:
    makefile = MAKEFILE_PATH.read_text()
    converge_block = makefile.split("converge-livekit:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(MAKE) preflight WORKFLOW=converge-livekit" in converge_block
    assert "uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate" in converge_block
    assert "$(MAKE) generate-edge-static-sites" in converge_block
    assert "$(REPO_ROOT)/playbooks/livekit.yml" in converge_block
    assert "HETZNER_DNS_API_TOKEN" in converge_block
    assert "$(ANSIBLE_TRACE_ARGS)" in converge_block
    assert "$(EXTRA_ARGS)" in converge_block


def test_livekit_execution_scope_advertises_the_shared_vm_and_edge_surfaces() -> None:
    scopes = yaml.safe_load(ANSIBLE_EXECUTION_SCOPES_PATH.read_text(encoding="utf-8"))
    direct = scopes["playbooks"]["playbooks/livekit.yml"]

    assert direct["playbook_id"] == "livekit"
    assert direct["mutation_scope"] == "platform"
    assert "service:livekit" in direct["shared_surfaces"]
    assert "host:proxmox-host/service:proxmox_network" in direct["shared_surfaces"]
    assert "vm:110/service:nginx_edge_publication" in direct["shared_surfaces"]
    assert "vm:120" in direct["shared_surfaces"]


def test_livekit_dependency_wave_metadata_locks_the_full_runtime_vm_and_shared_edge() -> None:
    catalog = yaml.safe_load(DEPENDENCY_WAVE_PLAYBOOKS_PATH.read_text(encoding="utf-8"))
    entries = {
        entry["path"]: entry
        for entry in catalog["playbooks"]
        if entry["path"] in {"playbooks/livekit.yml", "playbooks/services/livekit.yml"}
    }

    assert set(entries) == {"playbooks/livekit.yml", "playbooks/services/livekit.yml"}

    direct = entries["playbooks/livekit.yml"]
    wrapper = entries["playbooks/services/livekit.yml"]

    assert direct["make_target"] == "converge-livekit"
    assert "vm:120" in direct["lock_resources"]
    assert "vm:120/service:livekit" in direct["lock_resources"]
    assert "vm:110" in direct["lock_resources"]
    assert "vm:110/service:nginx_edge_publication" in direct["lock_resources"]
    assert "host:proxmox-host" in direct["lock_resources"]
    assert "host:proxmox-host/service:proxmox_network" in direct["lock_resources"]

    assert wrapper["make_target"] == "live-apply-service"
    assert wrapper["make_vars"] == {"service": "livekit"}
    assert wrapper["lock_resources"] == direct["lock_resources"]
