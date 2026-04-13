from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "keycloak.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "keycloak.yml"
COLLECTION_SERVICE_WRAPPER_PATH = (
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "services" / "keycloak.yml"
)


def test_keycloak_playbook_targets_the_runtime_control_vm() -> None:
    playbook = yaml.safe_load(PLAYBOOK_PATH.read_text())

    runtime_play = next(play for play in playbook if play["name"] == "Converge Keycloak on the runtime-control VM")
    assert runtime_play["hosts"] == (
        "{{ 'docker-runtime-staging' if (env | default('production')) == 'staging' else 'runtime-control' }}"
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
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())

    host_topology = host_vars["lv3_service_topology"]["keycloak"]

    assert host_topology["owning_vm"] == "runtime-control"
    assert "runtime-control" in host_topology["private_ip"]
    assert "docker-runtime" in host_topology["edge"]["upstream"]
    assert "docker-runtime" in host_topology["urls"]["internal"]
    assert host_topology["urls"]["public"] == "https://sso.{{ platform_domain }}"


def test_keycloak_service_wrappers_import_the_canonical_playbook() -> None:
    root_wrapper_text = SERVICE_WRAPPER_PATH.read_text()
    collection_wrapper_text = COLLECTION_SERVICE_WRAPPER_PATH.read_text()

    assert "# Purpose: Provide the stable live-apply service wrapper for Keycloak." in root_wrapper_text
    assert "# Purpose: Provide the stable live-apply service wrapper for Keycloak." in collection_wrapper_text
    assert yaml.safe_load(root_wrapper_text) == [{"import_playbook": "../keycloak.yml"}]
    assert yaml.safe_load(collection_wrapper_text) == [{"import_playbook": "../keycloak.yml"}]
