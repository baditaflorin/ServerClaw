from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "serverclaw.yml"


def load_playbook() -> list[dict]:
    return yaml.safe_load(PLAYBOOK_PATH.read_text())


def test_serverclaw_playbook_refreshes_host_network_runtime_and_edge() -> None:
    playbook = load_playbook()
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Ensure Hetzner DNS publication for ServerClaw",
        "Converge the Proxmox guest network policy for ServerClaw",
        "Converge the ServerClaw Keycloak client on the Docker runtime VM",
        "Converge ServerClaw on the Coolify runtime VM",
        "Publish ServerClaw through the NGINX edge",
    ]

    dns_task = playbook[0]["tasks"][0]
    assert dns_task["name"] == "Ensure Hetzner DNS records are present"
    assert dns_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_records"
    assert dns_task["ansible.builtin.include_role"]["apply"] == {
        "delegate_to": "localhost",
        "become": False,
    }
    assert dns_task["run_once"] is True

    host_roles = [role["role"] for role in playbook[1]["roles"]]
    assert host_roles == ["lv3.platform.proxmox_network"]
    assert playbook[1]["vars_files"] == ["{{ playbook_dir }}/../inventory/group_vars/platform.yml"]

    guest_roles = [role["role"] for role in playbook[3]["roles"]]
    assert guest_roles == [
        "lv3.platform.linux_guest_firewall",
    ]

    edge_roles = [role["role"] for role in playbook[4]["roles"]]
    assert edge_roles == ["lv3.platform.nginx_edge_publication"]
