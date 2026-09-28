from pathlib import Path

import yaml


def test_proxmox_host_ssh_port_has_breakglass_override_and_default() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    group_vars = yaml.safe_load((repo_root / "inventory/group_vars/proxmox_hosts.yml").read_text())

    assert group_vars["ansible_port"] == "{{ lookup('env', 'LV3_PROXMOX_HOST_PORT') | default(22, true) }}"
