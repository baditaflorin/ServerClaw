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
    # ADR 0340 adds apps VM provisioning (play 1), apps convergence (play 5),
    # and deployment server registration (play 6) — 8 plays total
    assert play_names == [
        "Ensure the Coolify VM is provisioned on the Proxmox host",
        "Ensure the Coolify apps runtime VM is provisioned on the Proxmox host",
        "Converge the Coolify private controller proxy and host firewall",
        "Ensure Hetzner DNS publication for Coolify",
        "Converge Coolify on the dedicated guest",
        "Converge the Coolify apps runtime on the dedicated apps guest",
        "Register coolify-apps-lv3 as the Coolify deployment server",
        "Publish Coolify on the NGINX edge",
    ]

    # Play 0: coolify-lv3 control plane provisioning
    provision_roles = [role["role"] for role in playbook[0]["roles"]]
    assert provision_roles == ["lv3.platform.proxmox_guests"]

    # Play 1: coolify-apps-lv3 apps VM provisioning (ADR 0340)
    apps_provision_roles = [role["role"] for role in playbook[1]["roles"]]
    assert apps_provision_roles == ["lv3.platform.proxmox_guests"]
    apps_provision_vars = playbook[1].get("vars", {})
    assert "coolify-apps" in str(apps_provision_vars.get("proxmox_guests_active", ""))

    # Play 3: DNS publication
    dns_task = playbook[3]["tasks"][0]
    assert dns_task["name"] == "Ensure Hetzner DNS records are present"
    assert dns_task["ansible.builtin.include_role"]["name"] == "lv3.platform.hetzner_dns_records"
    assert dns_task["ansible.builtin.include_role"]["apply"] == {
        "delegate_to": "localhost",
        "become": False,
    }
    assert dns_task["run_once"] is True

    # Play 4: coolify-lv3 control plane convergence
    guest_roles = [role["role"] for role in playbook[4]["roles"]]
    assert guest_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.repo_deploy_image_cache",
        "lv3.platform.coolify_runtime",
    ]

    # Play 5: coolify-apps-lv3 apps runtime convergence (ADR 0340)
    apps_roles = [role["role"] for role in playbook[5]["roles"]]
    assert apps_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.docker_runtime",
        "lv3.platform.repo_deploy_image_cache",
    ]

    # Play 7: NGINX edge publication
    edge_roles = [role["role"] for role in playbook[7]["roles"]]
    assert edge_roles == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.public_edge_oidc_auth",
        "lv3.platform.nginx_edge_publication",
    ]

    # Plays that use vars_files (all except the localhost registration play at index 6)
    plays_with_vars_files = [play for play in playbook if "vars_files" in play]
    expected_vars_file = "{{ playbook_dir }}/../inventory/group_vars/platform.yml"
    for play in plays_with_vars_files:
        assert play["vars_files"] == [expected_vars_file]


def test_coolify_apps_vm_provisioning_play_uses_correct_role_filter() -> None:
    """ADR 0340: The apps VM provisioning play must select by role 'coolify-apps', not 'coolify'."""
    playbook = load_yaml(PLAYBOOK_PATH)
    apps_provision_play = next(
        p for p in playbook
        if p["name"] == "Ensure the Coolify apps runtime VM is provisioned on the Proxmox host"
    )
    guests_active_expr = apps_provision_play["vars"]["proxmox_guests_active"]
    assert "coolify-apps" in guests_active_expr


def test_coolify_apps_convergence_play_excludes_coolify_runtime_role() -> None:
    """ADR 0340: The apps VM must not run coolify_runtime — it is only a deployment target."""
    playbook = load_yaml(PLAYBOOK_PATH)
    apps_convergence_play = next(
        p for p in playbook
        if p["name"] == "Converge the Coolify apps runtime on the dedicated apps guest"
    )
    role_names = [r["role"] for r in apps_convergence_play["roles"]]
    assert "lv3.platform.coolify_runtime" not in role_names
    assert "lv3.platform.docker_runtime" in role_names
    assert "lv3.platform.linux_guest_firewall" in role_names


def test_coolify_service_wrapper_imports_the_canonical_playbook() -> None:
    wrapper = load_yaml(SERVICE_WRAPPER_PATH)
    assert wrapper == [{"import_playbook": "../coolify.yml"}]
