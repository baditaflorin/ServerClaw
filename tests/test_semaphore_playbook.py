from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "semaphore.yml"


def load_playbook() -> list[dict]:
    return yaml.safe_load(PLAYBOOK_PATH.read_text())


def test_semaphore_playbook_relies_on_the_authentik_manifest_before_runtime_converge() -> None:
    playbook = load_playbook()
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Converge the Tailscale operator proxy for Semaphore",
        "Converge PostgreSQL access for Semaphore",
        "Converge Semaphore on the runtime-control VM",
    ]

    postgres_roles = [role["role"] for role in playbook[1]["roles"]]
    assert postgres_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.postgres_vm",
        "lv3.platform.semaphore_postgres",
    ]

    runtime_roles = [role["role"] for role in playbook[2]["roles"]]
    assert runtime_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.semaphore_runtime",
    ]
