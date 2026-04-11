from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "proxmox_guests" / "tasks" / "main.yml"
ROLE_DEFAULTS = REPO_ROOT / "roles" / "proxmox_guests" / "defaults" / "main.yml"
ROLE_USER_DATA_TEMPLATE = REPO_ROOT / "roles" / "proxmox_guests" / "templates" / "user-data.yml.j2"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_role_defaults_expose_template_catalog() -> None:
    defaults = load_yaml(ROLE_DEFAULTS)
    assert defaults["proxmox_vm_templates"] == {}


def test_role_clones_from_declared_template_catalog() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_names = [task["name"] for task in tasks]
    assert "Validate each guest references a declared template" in task_names
    assert "Download official Debian 13 cloud image" not in task_names

    clone_task = next(task for task in tasks if task["name"] == "Clone guest VMs from template")
    assert (
        clone_task["ansible.builtin.command"]["argv"][2]
        == "{{ proxmox_vm_templates[item.item.template_key].vmid | string }}"
    )


def test_cloud_init_template_does_not_start_docker_early() -> None:
    template = ROLE_USER_DATA_TEMPLATE.read_text()
    assert "systemctl enable --now qemu-guest-agent" in template
    assert "systemctl enable --now docker" not in template
