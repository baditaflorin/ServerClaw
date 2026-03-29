from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "loki_log_agent" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "loki_log_agent" / "tasks" / "main.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_use_proxmox_host_service_topology_for_loki_push_url() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert defaults["loki_log_agent_loki_push_url"] == (
        "{{ hostvars['proxmox_florin'].platform_service_topology | platform_service_url('grafana', 'loki_push') }}"
    )


def test_validate_task_requires_the_resolved_loki_push_url() -> None:
    tasks = load_yaml(TASKS_PATH)
    validate_task = next(task for task in tasks if task.get("name") == "Validate Loki log agent inputs")

    assert "loki_log_agent_loki_push_url | length > 0" in validate_task["ansible.builtin.assert"]["that"]
