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


def test_proxmox_network_renders_vm_firewall_from_active_role_path() -> None:
    tasks = yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))
    render_task = next(task for task in tasks if task["name"] == "Render per-guest Proxmox firewall policy to staging files")
    copy_module = render_task["ansible.builtin.copy"]

    assert copy_module["dest"] == "/root/.lv3-vm-{{ guest.vmid }}.fw"
    assert "role_path ~ '/templates/vm.fw.j2'" in copy_module["content"]
