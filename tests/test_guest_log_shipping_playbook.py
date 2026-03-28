from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "guest-log-shipping.yml"
PROXMOX_HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_guest_log_shipping_lane_map_covers_all_production_guest_roles() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    pre_tasks = playbook[0]["pre_tasks"]
    derive_task = next(task for task in pre_tasks if task.get("name") == "Derive guest log shipping role and lane")
    lane_expression = derive_task["ansible.builtin.set_fact"]["monitoring_stack_guest_lane"]

    for role in (
        "nginx",
        "docker-runtime",
        "docker-build",
        "monitoring",
        "postgres",
        "postgres-replica",
        "backup",
        "coolify",
    ):
        assert f"'{role}':" in lane_expression

    platform_vars = load_yaml(PROXMOX_HOST_VARS_PATH)
    production_roles = {
        guest["role"]
        for guest in platform_vars["proxmox_guests"]
        if guest["name"].endswith("-lv3")
    }
    assert production_roles <= {
        "nginx",
        "docker-runtime",
        "docker-build",
        "monitoring",
        "postgres",
        "postgres-replica",
        "backup",
        "coolify",
    }
