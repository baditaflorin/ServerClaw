from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "coolify.yml"
SERVICE_WRAPPER_PATH = REPO_ROOT / "playbooks" / "services" / "coolify.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_coolify_playbook_covers_vm_provision_guest_runtime_and_edge() -> None:
    playbook = load_yaml(PLAYBOOK_PATH)
    play_names = [play["name"] for play in playbook]
    assert play_names == [
        "Ensure the Coolify VM is provisioned on the Proxmox host",
        "Converge the Coolify private controller proxy and host firewall",
        "Ensure Hetzner DNS publication for Coolify",
        "Converge Coolify on the dedicated guest",
        "Publish Coolify on the NGINX edge",
    ]

    provision_roles = [role["role"] for role in playbook[0]["roles"]]
    assert provision_roles == ["lv3.platform.proxmox_guests"]

    dns_task = playbook[2]["tasks"][0]
    assert dns_task["name"] == "Ensure Hetzner DNS records are present"
    assert dns_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_records"
    assert dns_task["ansible.builtin.include_role"]["apply"] == {
        "delegate_to": "localhost",
        "become": False,
    }
    assert dns_task["run_once"] is True

    guest_roles = [role["role"] for role in playbook[3]["roles"]]
    assert guest_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.coolify_runtime",
    ]

    edge_roles = [role["role"] for role in playbook[4]["roles"]]
    assert edge_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.public_edge_oidc_auth",
        "lv3.platform.nginx_edge_publication",
    ]
    expected_vars_file = "{{ playbook_dir }}/../inventory/group_vars/platform.yml"
    assert [play["vars_files"] for play in playbook] == [[expected_vars_file]] * 5


def test_coolify_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../coolify.yml"}]
