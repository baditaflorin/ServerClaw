from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "keycloak.yml"
GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "platform.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"


def test_keycloak_playbook_targets_the_runtime_control_vm() -> None:
    playbook = yaml.safe_load(PLAYBOOK_PATH.read_text())

    runtime_play = next(play for play in playbook if play["name"] == "Converge Keycloak on the runtime-control VM")
    assert runtime_play["hosts"] == (
        "{{ 'docker-runtime' if (env | default('production')) == 'staging' else 'runtime-control' }}"
    )

    runtime_preflight = next(
        task for task in runtime_play["pre_tasks"] if task["name"] == "Run shared preflight checks"
    )
    assert runtime_preflight["vars"]["required_hosts"] == [
        "{{ playbook_execution_required_hosts.runtime_control[playbook_execution_env] }}"
    ]

    grafana_play = next(play for play in playbook if play["name"] == "Converge Grafana SSO against Keycloak")
    grafana_role = next(role for role in grafana_play["roles"] if role.get("role") == "lv3.platform.grafana_sso")
    assert grafana_role["vars"]["grafana_sso_client_secret"] == (
        "{{ hostvars[playbook_execution_host_patterns.runtime_control[playbook_execution_env]].keycloak_grafana_client_secret }}"
    )


def test_keycloak_service_topology_points_at_runtime_control() -> None:
    group_vars = yaml.safe_load(GROUP_VARS_PATH.read_text())
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())

    group_topology = group_vars["platform_service_topology"]["keycloak"]
    public_edge_topology = group_vars["public_edge_service_topology"]["keycloak"]
    host_topology = host_vars["lv3_service_topology"]["keycloak"]

    for topology in (group_topology, public_edge_topology):
        assert topology["owning_vm"] == "runtime-control"
        assert topology["private_ip"] == "10.10.10.92"
        assert topology["edge"]["upstream"] == "http://10.10.10.92:8091"
        assert topology["urls"]["public"] == "https://sso.example.com"

    assert host_topology["owning_vm"] == "runtime-control"
    assert "runtime-control" in host_topology["private_ip"]
    assert "runtime-control" in host_topology["edge"]["upstream"]
    assert "runtime-control" in host_topology["urls"]["internal"]
