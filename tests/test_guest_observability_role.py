from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "guest_observability" / "defaults" / "main.yml"
TASKS_PATH = REPO_ROOT / "roles" / "guest_observability" / "tasks" / "setup.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_defaults_use_proxmox_host_service_topology_for_influx_url() -> None:
    defaults = load_yaml(DEFAULTS_PATH)

    assert defaults["guest_observability_influx_url"] == (
        "{{ hostvars['proxmox-host'].platform_service_topology | platform_service_url('grafana', 'influxdb') }}"
    )
    assert defaults["guest_observability_writer_token_local_file"] == "{{ monitoring_guest_writer_token_local_file }}"


def test_setup_validates_required_observability_inputs() -> None:
    tasks = load_yaml(TASKS_PATH)

    validate_task = next(task for task in tasks if task.get("name") == "Validate guest observability inputs")
    assert "{{ guest_observability_state_dir }}" not in str(validate_task)
    assert "guest_observability_influx_url | length > 0" in validate_task["ansible.builtin.assert"]["that"]
