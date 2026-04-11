from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "semaphore.yml"


def load_playbook() -> list[dict]:
    return yaml.safe_load(PLAYBOOK_PATH.read_text())


def test_semaphore_playbook_reconciles_keycloak_before_runtime_converge() -> None:
    playbook = load_playbook()
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Converge the Tailscale operator proxy for Semaphore",
        "Converge PostgreSQL access for Semaphore",
        "Converge the Semaphore Keycloak client on the Docker runtime VM",
        "Converge Semaphore on the runtime-control VM",
    ]

    postgres_roles = [role["role"] for role in playbook[1]["roles"]]
    assert postgres_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.semaphore_postgres",
    ]

    keycloak_client_play = playbook[2]
    assert keycloak_client_play["vars_files"] == ["{{ playbook_dir }}/../inventory/group_vars/platform.yml"]
    assert [role["role"] for role in keycloak_client_play["roles"]] == ["lv3.platform.docker_runtime"]
    keycloak_task = keycloak_client_play["tasks"][0]
    assert keycloak_task["ansible.builtin.include_role"]["name"] == "lv3.platform.keycloak_runtime"
    assert keycloak_task["ansible.builtin.include_role"]["tasks_from"] == "semaphore_client.yml"

    runtime_roles = [role["role"] for role in playbook[3]["roles"]]
    assert runtime_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.semaphore_runtime",
    ]
