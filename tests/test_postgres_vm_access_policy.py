from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"
POSTGRES_GROUP_VARS_PATH = REPO_ROOT / "inventory" / "group_vars" / "postgres_guests.yml"
POSTGRES_PREPARATION_INCLUDE_PATH = REPO_ROOT / "playbooks" / "_includes" / "postgres_preparation.yml"
POSTGRES_CLIENT_PLAYBOOKS = [
    REPO_ROOT / "playbooks" / "dify.yml",
    REPO_ROOT / "playbooks" / "keycloak.yml",
    REPO_ROOT / "playbooks" / "langfuse.yml",
    REPO_ROOT / "playbooks" / "mattermost.yml",
    REPO_ROOT / "playbooks" / "matrix-synapse.yml",
    REPO_ROOT / "playbooks" / "n8n.yml",
    REPO_ROOT / "playbooks" / "nextcloud.yml",
    REPO_ROOT / "playbooks" / "outline.yml",
    REPO_ROOT / "playbooks" / "plane.yml",
    REPO_ROOT / "playbooks" / "postgres-vm.yml",
    REPO_ROOT / "playbooks" / "semaphore.yml",
    REPO_ROOT / "playbooks" / "vaultwarden.yml",
    REPO_ROOT / "playbooks" / "windmill.yml",
]


def load_playbook(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def iter_postgres_role_lists(playbook_path: Path) -> list[list[dict]]:
    role_lists: list[list[dict]] = []
    postgres_preparation_roles = load_playbook(POSTGRES_PREPARATION_INCLUDE_PATH)[0]["roles"]

    for play in load_playbook(playbook_path):
        if play.get("import_playbook") == "_includes/postgres_preparation.yml":
            role_lists.append(postgres_preparation_roles)
        roles = play.get("roles", [])
        if any(isinstance(role, dict) and role.get("role") == "lv3.platform.postgres_vm" for role in roles):
            role_lists.append(roles)

    return role_lists


def test_postgres_guest_group_vars_use_bridge_fallback_cidrs() -> None:
    group_vars = yaml.safe_load(POSTGRES_GROUP_VARS_PATH.read_text())
    assert group_vars["postgres_vm_client_allowed_sources_extra"] == []
    assert group_vars["postgres_vm_client_allowed_sources_extra_bridge"] == [
        "172.16.0.0/12",
        "192.168.0.0/16",
        "10.200.0.0/16",
        "10.10.10.0/24",
    ]


def test_postgres_network_policy_allows_runtime_control_and_docker_runtime_sources() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    postgres_rules = host_vars["network_policy"]["guests"]["postgres"]["allowed_inbound"]
    postgres_5432_sources = {rule["source"] for rule in postgres_rules if 5432 in rule.get("ports", [])}

    assert {
        "runtime-control",
        "docker-runtime",
        "10.10.10.0/24",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "10.200.0.0/16",
    } <= postgres_5432_sources


def test_postgres_network_policy_allows_monitoring_to_scrape_alloy_metrics() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    postgres_rules = host_vars["network_policy"]["guests"]["postgres"]["allowed_inbound"]
    postgres_12345_sources = {rule["source"] for rule in postgres_rules if 12345 in rule.get("ports", [])}

    assert postgres_12345_sources == {"monitoring"}


def test_postgres_client_sources_are_centralized_in_group_vars() -> None:
    for playbook_path in POSTGRES_CLIENT_PLAYBOOKS:
        postgres_roles = [
            role
            for roles in iter_postgres_role_lists(playbook_path)
            for role in roles
            if isinstance(role, dict) and role.get("role") == "lv3.platform.postgres_vm"
        ]
        assert postgres_roles
        assert all("vars" not in role for role in postgres_roles)


def test_postgres_playbooks_apply_linux_guest_firewall_before_postgres_role() -> None:
    for playbook_path in POSTGRES_CLIENT_PLAYBOOKS:
        firewall_before_postgres = False

        for roles in iter_postgres_role_lists(playbook_path):
            role_names = [role.get("role") for role in roles if isinstance(role, dict)]
            if "lv3.platform.postgres_vm" not in role_names:
                continue
            firewall_before_postgres = "lv3.platform.linux_guest_firewall" in role_names and role_names.index(
                "lv3.platform.linux_guest_firewall"
            ) < role_names.index("lv3.platform.postgres_vm")
            break

        assert firewall_before_postgres, (
            f"{playbook_path} must apply lv3.platform.linux_guest_firewall before lv3.platform.postgres_vm"
        )
