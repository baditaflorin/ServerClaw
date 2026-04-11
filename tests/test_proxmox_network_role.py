from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "proxmox_network"
    / "tasks"
    / "main.yml"
)
DEFAULTS_PATH = REPO_ROOT / "roles" / "proxmox_network" / "defaults" / "main.yml"
META_PATH = REPO_ROOT / "roles" / "proxmox_network" / "meta" / "argument_specs.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "proxmox_network" / "templates" / "nftables.conf.j2"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"


def test_proxmox_network_renders_vm_firewall_from_active_role_path() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    render_task = next(
        task for task in tasks if task["name"] == "Render per-guest Proxmox firewall policy to staging files"
    )
    template_module = render_task["ansible.builtin.template"]

    assert template_module["src"] == "vm.fw.j2"
    assert template_module["dest"] == "/root/.lv3-vm-{{ guest.vmid }}.fw"


def test_proxmox_network_defaults_define_udp_forward_contract() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["proxmox_public_ingress_tcp_forwards"] == []
    assert defaults["proxmox_public_ingress_udp_forwards"] == []


def test_proxmox_network_argument_specs_accept_udp_forward_rules() -> None:
    specs = yaml.safe_load(META_PATH.read_text(encoding="utf-8"))
    options = specs["argument_specs"]["main"]["options"]

    assert options["proxmox_public_ingress_tcp_forwards"]["type"] == "list"
    assert options["proxmox_public_ingress_udp_forwards"]["type"] == "list"
    assert options["proxmox_public_ingress_udp_forwards"]["default"] == []


def test_proxmox_network_template_renders_udp_filter_and_nat_rules() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "proxmox_public_ingress_udp_forwards | default([]) | length > 0" in template
    assert "udp dport {{ forward.target_port }} accept" in template
    assert (
        "udp dport {{ forward.listen_port }} dnat ip to {{ forward.target_host }}:{{ forward.target_port }}" in template
    )


def test_host_vars_define_livekit_public_tcp_and_udp_forwards() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))

    assert host_vars["platform_port_assignments"]["livekit_signal_port"] == 7880
    assert host_vars["platform_port_assignments"]["livekit_tcp_port"] == 7881
    assert host_vars["platform_port_assignments"]["livekit_udp_port"] == 7882
    assert 7881 in host_vars["proxmox_public_ingress_tcp_ports"]
    assert {
        "listen_port": 7882,
        "target_host": "10.10.10.20",
        "target_port": 7882,
    } in host_vars["proxmox_public_ingress_udp_forwards"]
