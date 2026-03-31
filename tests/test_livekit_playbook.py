import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "livekit.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "livekit.yml"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def test_livekit_dns_stage_converges_only_the_livekit_subdomain_record() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())
    dns_play = plays[0]
    tasks = dns_play["tasks"]

    assert dns_play["hosts"] == "localhost"
    assert dns_play["connection"] == "local"
    assert dns_play["vars"]["subdomain_fqdn"] == "livekit.lv3.org"

    select_task = next(task for task in tasks if task.get("name") == "Select the LiveKit subdomain entry")
    assert "selectattr('fqdn', 'equalto', subdomain_fqdn)" in select_task["ansible.builtin.set_fact"]["selected_subdomain"]

    converge_task = next(task for task in tasks if task.get("name") == "Converge the LiveKit Hetzner DNS record")
    assert converge_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_record"
    assert converge_task["vars"]["hetzner_dns_record_name"] == "{{ selected_subdomain_record_name }}"


def test_livekit_playbook_converges_network_runtime_edge_and_public_verification() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    network_roles = [role["role"] for role in plays[1]["roles"]]
    runtime_roles = [role["role"] for role in plays[2]["roles"]]
    edge_roles = [role["role"] for role in plays[3]["roles"]]
    verify_task = plays[4]["tasks"][0]

    assert network_roles == ["lv3.platform.proxmox_network"]
    assert runtime_roles == [
        "lv3.platform.docker_runtime",
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.livekit_runtime",
    ]
    assert edge_roles == ["lv3.platform.nginx_edge_publication"]
    assert verify_task["ansible.builtin.command"]["argv"][1] == "{{ livekit_tool_script }}"
    assert verify_task["ansible.builtin.command"]["argv"][2] == "verify-room-lifecycle"
    assert "https://livekit.lv3.org" in verify_task["ansible.builtin.command"]["argv"]


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
