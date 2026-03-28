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
    / "harbor_runtime"
    / "tasks"
    / "main.yml"
)
HOST_VARS = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def test_role_tracks_robot_reconcile_state_before_refreshing_secret() -> None:
    tasks = load_yaml(ROLE_TASKS)
    task_names = [task["name"] for task in tasks]

    assert "Record whether the check-runner Harbor robot account needs reconciliation" in task_names
    assert "Refresh the check-runner Harbor robot secret when local state is missing" in task_names
    assert "Read the desired Harbor registry credential password" in task_names
    assert "Record whether Harbor registry credential containers need recreation" in task_names


def test_host_network_policy_allows_nginx_edge_access_to_harbor() -> None:
    host_vars = load_yaml(HOST_VARS)
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    harbor_rule = next(rule for rule in docker_runtime_rules if rule["source"] == "nginx-lv3" and 8095 in rule["ports"])

    assert harbor_rule["description"].lower().startswith("edge access")
