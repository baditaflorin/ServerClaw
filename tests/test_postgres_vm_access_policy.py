from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
POSTGRES_GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "postgres_guests.yml"
POSTGRES_CLIENT_PLAYBOOKS = [
    REPO_ROOT / "playbooks" / "dify.yml",
    REPO_ROOT / "playbooks" / "keycloak.yml",
    REPO_ROOT / "playbooks" / "langfuse.yml",
    REPO_ROOT / "playbooks" / "n8n.yml",
    REPO_ROOT / "playbooks" / "outline.yml",
    REPO_ROOT / "playbooks" / "plane.yml",
]


def test_postgres_guest_group_vars_allow_docker_runtime_bridge_sources() -> None:
    group_vars = yaml.safe_load(POSTGRES_GROUP_VARS_PATH.read_text())
    host_source = group_vars["postgres_vm_client_allowed_sources_extra"][0]

    assert "playbook_execution_host_patterns.docker_runtime[playbook_execution_env]" in host_source
    assert host_source.endswith("}}/32")
    assert group_vars["postgres_vm_client_allowed_sources_extra"][1:] == ["172.16.0.0/12", "192.168.0.0/16"]


def test_postgres_network_policy_allows_docker_runtime_bridge_sources() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    postgres_rules = host_vars["network_policy"]["guests"]["postgres-lv3"]["allowed_inbound"]
    postgres_5432_sources = {rule["source"] for rule in postgres_rules if 5432 in rule.get("ports", [])}

    assert {"docker-runtime-lv3", "172.16.0.0/12", "192.168.0.0/16"} <= postgres_5432_sources


def test_postgres_client_sources_are_centralized_in_group_vars() -> None:
    for playbook_path in POSTGRES_CLIENT_PLAYBOOKS:
        plays = yaml.safe_load(playbook_path.read_text())
        postgres_roles = [
            role
            for play in plays
            for role in play.get("roles", [])
            if isinstance(role, dict) and role.get("role") == "lv3.platform.postgres_vm"
        ]
        assert postgres_roles
        assert all("vars" not in role for role in postgres_roles)
