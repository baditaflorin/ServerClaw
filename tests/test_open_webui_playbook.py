from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "open-webui.yml"


def load_playbook() -> list[dict]:
    return yaml.safe_load(PLAYBOOK_PATH.read_text())


def test_open_webui_playbook_reconciles_keycloak_client_before_runtime() -> None:
    playbook = load_playbook()
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Converge the Tailscale operator proxy for Open WebUI",
        "Converge the Open WebUI Keycloak client on the Docker runtime VM",
        "Converge Open WebUI on the Docker runtime VM",
    ]

    proxy_roles = [role["role"] for role in playbook[0]["roles"]]
    assert proxy_roles == [
        "lv3.platform.proxmox_tailscale_proxy",
        "lv3.platform.proxmox_security",
    ]

    keycloak_preflight = next(task for task in playbook[1]["pre_tasks"] if task["name"] == "Run shared preflight checks")
    assert keycloak_preflight["vars"]["required_hosts"] == [
        "{{ playbook_execution_required_hosts.docker_runtime[playbook_execution_env] }}"
    ]
    keycloak_roles = [role["role"] for role in playbook[1]["roles"]]
    assert keycloak_roles == ["lv3.platform.docker_runtime"]
    include_task = playbook[1]["tasks"][0]
    assert include_task["ansible.builtin.include_role"]["name"] == "lv3.platform.keycloak_runtime"
    assert include_task["ansible.builtin.include_role"]["tasks_from"] == "open_webui_client.yml"

    runtime_preflight = next(task for task in playbook[2]["pre_tasks"] if task["name"] == "Run shared preflight checks")
    assert runtime_preflight["vars"]["required_hosts"] == [
        "{{ playbook_execution_required_hosts.docker_runtime[playbook_execution_env] }}"
    ]
    runtime_roles = [role["role"] for role in playbook[2]["roles"]]
    assert runtime_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.open_webui_runtime",
    ]
