"""`network_policy_all_guests: false` keeps a guest out of every `all_guests` source expansion (ADR 0494, least privilege).

The agent-history store (VM 155) holds every secret an agent ever saw and has no business reaching the NATS, Mailpit, Redpanda,
n8n and directus ports that other services open to "all guests". Four places expand `all_guests` and must agree: the guest
nftables template (input and forward chains), the Proxmox VM firewall template, and scripts/firewall_drift.py, which mirrors both.
Named-source rules (`source: agent-history`, the OpenBao tcp 8201 flow on runtime-control) are not affected.
"""

from __future__ import annotations

import copy
import importlib.util
import re
import sys
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLES = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
NFT_TEMPLATE = ROLES / "linux_guest_firewall" / "templates" / "nftables.conf.j2"
NFT_TASKS = ROLES / "linux_guest_firewall" / "tasks" / "main.yml"
VM_FW_TEMPLATE = ROLES / "proxmox_network" / "templates" / "vm.fw.j2"
HOST_VARS = REPO / "inventory" / "host_vars" / "proxmox-host.yml"
INTERNAL_TOKEN = "{{ proxmox_internal_ipv4 }}"
STORE = "agent-history"
STORE_IP = "10.10.10.55"


def _host_vars() -> dict:
    return yaml.safe_load(HOST_VARS.read_text(encoding="utf-8"))


def _policy(host_vars: dict) -> dict:
    internal = str(host_vars["proxmox_internal_ipv4"])
    policy = copy.deepcopy(host_vars["network_policy"])
    policy["host_source"] = str(policy["host_source"]).replace(INTERNAL_TOKEN, internal)
    policy["guest_management_sources"] = [
        str(item).replace(INTERNAL_TOKEN, internal) for item in policy["guest_management_sources"]
    ]
    return policy


def _env() -> jinja2.Environment:
    env = jinja2.Environment(trim_blocks=True)  # Ansible's default for templates
    env.filters["zip"] = lambda left, right: list(zip(left, right))  # ansible.builtin.zip
    return env


def _excluded(guests: list[dict]) -> list[str]:
    return [guest["name"] for guest in guests if guest.get("network_policy_all_guests", True) is False]


def render_nft(host_vars: dict, guest: str) -> str:
    guests = host_vars["proxmox_guests"]
    context = {
        "linux_guest_firewall_policy": _policy(host_vars),
        "linux_guest_firewall_guest_ip_map": {g["name"]: g["ipv4"] for g in guests},
        "linux_guest_firewall_guest_role_map": {g["name"]: g["role"] for g in guests},
        "linux_guest_firewall_all_guests_excluded": _excluded(guests),
        "linux_guest_firewall_container_forward_source_cidrs": ["172.16.0.0/12", "192.168.0.0/16", "10.200.0.0/16"],
        "inventory_hostname": guest,
        "hostvars": {},
        "linux_guest_firewall_host_id": "proxmox-host",
    }
    return _env().from_string(NFT_TEMPLATE.read_text(encoding="utf-8")).render(**context)


def render_vm_fw(host_vars: dict, guest: str) -> str:
    guests = host_vars["proxmox_guests"]
    context = {
        "network_policy": _policy(host_vars),
        "proxmox_guests": guests,
        "guest": next(g for g in guests if g["name"] == guest),
    }
    return _env().from_string(VM_FW_TEMPLATE.read_text(encoding="utf-8")).render(**context)


def _guests_with_all_guests_rule(host_vars: dict) -> list[str]:
    policy = host_vars["network_policy"]["guests"]
    return sorted(
        name
        for name, guest in policy.items()
        if any(rule.get("source") == "all_guests" for rule in guest["allowed_inbound"])
    )


def _lines_naming(text: str, ip: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if re.search(rf"{re.escape(ip)}/32", line)]


def test_only_the_store_opts_out_and_the_default_is_true() -> None:
    host_vars = _host_vars()
    assert _excluded(host_vars["proxmox_guests"]) == [STORE]
    others = [g for g in host_vars["proxmox_guests"] if g["name"] != STORE]
    assert all("network_policy_all_guests" not in g for g in others), (
        "an opt-out elsewhere would silently narrow that guest's access"
    )


def test_guest_nftables_never_name_the_store_through_all_guests() -> None:
    host_vars = _host_vars()
    guests = _guests_with_all_guests_rule(host_vars)
    assert "runtime-control" in guests and "docker-runtime" in guests
    for guest in guests:
        lines = _lines_naming(render_nft(host_vars, guest), STORE_IP)
        # only the rule that names the store explicitly may mention it: OpenBao on runtime-control, once in input and once in forward
        expected = (
            [f"ip saddr {STORE_IP}/32 tcp dport {{ 8201 }} accept", f"ip saddr {STORE_IP}/32 accept"]
            if guest == "runtime-control"
            else []
        )
        assert lines == expected, f"{guest}: {lines}"


def test_vm_firewall_files_never_name_the_store_through_all_guests() -> None:
    host_vars = _host_vars()
    for guest in _guests_with_all_guests_rule(host_vars):
        lines = _lines_naming(render_vm_fw(host_vars, guest), STORE_IP)
        expected = [f"IN ACCEPT -source {STORE_IP}/32 -p tcp -dport 8201"] if guest == "runtime-control" else []
        assert lines == expected, f"{guest}: {lines}"


def test_the_explicit_openbao_flow_for_the_store_still_renders_in_both_layers() -> None:
    host_vars = _host_vars()
    nft = _lines_naming(render_nft(host_vars, "runtime-control"), STORE_IP)
    assert f"ip saddr {STORE_IP}/32 tcp dport {{ 8201 }} accept" in nft
    fw = _lines_naming(render_vm_fw(host_vars, "runtime-control"), STORE_IP)
    assert fw == [f"IN ACCEPT -source {STORE_IP}/32 -p tcp -dport 8201"]


def test_removing_the_opt_out_restores_the_old_fan_out_and_nothing_else_changes() -> None:
    host_vars = _host_vars()
    restored = copy.deepcopy(host_vars)
    for guest in restored["proxmox_guests"]:
        guest.pop("network_policy_all_guests", None)
    for guest in _guests_with_all_guests_rule(host_vars):
        for render in (render_nft, render_vm_fw):
            kept = render(host_vars, guest).splitlines()
            old = render(restored, guest).splitlines()
            assert [line for line in old if STORE_IP not in line] == [line for line in kept if STORE_IP not in line], (
                f"{guest}: the flag must only remove lines that name {STORE_IP}"
            )
    # and the flag really does something: the old rendering names the store on runtime-control through all_guests
    assert len(_lines_naming(render_nft(restored, "runtime-control"), STORE_IP)) > 1
    assert len(_lines_naming(render_vm_fw(restored, "runtime-control"), STORE_IP)) > 1


def test_a_guest_without_the_flag_stays_in_the_fan_out() -> None:
    guests = [
        {"name": "alpha", "ipv4": "10.0.0.1", "role": "docker-runtime"},
        {"name": "beta", "ipv4": "10.0.0.2", "role": "docker-runtime"},
        {"name": "quiet", "ipv4": "10.0.0.3", "role": "docker-runtime", "network_policy_all_guests": False},
    ]
    host_vars = {
        "proxmox_internal_ipv4": "10.0.0.254",
        "proxmox_guests": guests,
        "network_policy": {
            "host_source": "10.0.0.254/32",
            "guest_management_sources": [],
            "guests": {
                "alpha": {"allowed_inbound": [{"source": "all_guests", "protocol": "tcp", "ports": [8080]}]},
                "beta": {"allowed_inbound": [{"source": "quiet", "protocol": "tcp", "ports": [9090]}]},
                "quiet": {"allowed_inbound": []},
            },
        },
    }
    nft = render_nft(host_vars, "alpha")
    assert "ip saddr 10.0.0.2/32 tcp dport { 8080 } accept" in nft  # beta stays in
    assert "10.0.0.3/32" not in nft  # quiet is out of all_guests
    assert "ip saddr 10.0.0.3/32 tcp dport { 9090 } accept" in render_nft(
        host_vars, "beta"
    )  # but a named rule still renders
    fw = render_vm_fw(host_vars, "alpha")
    assert "-source 10.0.0.2/32 -p tcp -dport 8080" in fw and "10.0.0.3/32" not in fw


def test_the_role_defines_the_excluded_list_and_the_template_has_a_safe_default() -> None:
    tasks = yaml.safe_load(NFT_TASKS.read_text(encoding="utf-8"))
    facts = next(
        task["ansible.builtin.set_fact"] for task in tasks if "linux_guest_firewall_all_guests_excluded" in str(task)
    )
    expression = " ".join(str(facts["linux_guest_firewall_all_guests_excluded"]).split())
    assert "selectattr('network_policy_all_guests', 'defined')" in expression
    assert "rejectattr('network_policy_all_guests')" in expression
    assert "linux_guest_firewall_all_guests_excluded | default([])" in NFT_TEMPLATE.read_text(encoding="utf-8")


def test_firewall_drift_mirrors_the_templates() -> None:
    spec = importlib.util.spec_from_file_location("firewall_drift_under_test", REPO / "scripts" / "firewall_drift.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    host_vars = _host_vars()
    policy = module._resolve_policy(host_vars)
    assert policy["all_guests_excluded"] == [STORE]
    ip_map = module._guest_ip_map(host_vars)
    fan_out = module.resolve_rule_sources(
        {"source": "all_guests"}, policy=policy, guest_ip_map=ip_map, guest_name="runtime-control"
    )
    assert f"{STORE_IP}/32" not in fan_out and "10.10.10.30/32" in fan_out
    named = module.resolve_rule_sources(
        {"source": STORE}, policy=policy, guest_ip_map=ip_map, guest_name="runtime-control"
    )
    assert named == [f"{STORE_IP}/32"]


def _accept_rules(text: str) -> set[str]:
    return {line.split(" #", 1)[0].strip() for line in text.splitlines() if line.startswith("IN ACCEPT")}


def test_the_store_vm_firewall_file_matches_what_the_netpolicy_file_declares() -> None:
    """/etc/pve/firewall/155.fw did not exist after the first provisioning (nothing had rendered it): the render must equal the declaration."""
    import subprocess

    declared = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "netpolicy.py"),
            "render",
            "pve",
            "--policy",
            str(REPO / "config" / "network-policy" / "0mcp.yaml"),
            "--vm",
            "155",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rendered = render_vm_fw(_host_vars(), STORE)
    assert _accept_rules(rendered) == _accept_rules(declared)
    assert "policy_in: DROP" in rendered and "enable: 1" in rendered
