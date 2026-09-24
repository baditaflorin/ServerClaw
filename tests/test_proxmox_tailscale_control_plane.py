from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "proxmox_tailscale"


def test_mesh_provider_is_an_explicit_required_role_input() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    argument_specs = yaml.safe_load((ROLE_ROOT / "meta" / "argument_specs.yml").read_text())
    options = argument_specs["argument_specs"]["main"]["options"]

    assert "proxmox_tailscale_provider" not in defaults
    assert options["proxmox_tailscale_provider"]["required"] is True
    assert options["proxmox_tailscale_provider"]["choices"] == ["tailscale", "headscale"]


def test_control_plane_pair_is_validated_before_any_client_mutation() -> None:
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    validate_index = next(
        index
        for index, task in enumerate(tasks)
        if task.get("name") == "Validate the selected Tailscale-compatible mesh control plane"
    )
    first_mutation_index = next(
        index
        for index, task in enumerate(tasks)
        if task.get("name") == "Attach the Proxmox host to the tailnet with the supplied auth key"
    )
    expressions = tasks[validate_index]["ansible.builtin.assert"]["that"]

    assert validate_index < first_mutation_index
    assert "proxmox_tailscale_provider in ['tailscale', 'headscale']" in expressions
    assert "proxmox_tailscale_login_server is defined" in expressions
    assert any("proxmox_tailscale_provider == 'tailscale'" in value for value in expressions)
    assert any("proxmox_tailscale_provider == 'headscale'" in value for value in expressions)
    assert any("^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$" in value for value in expressions)


def test_control_plane_migration_is_refused_by_default() -> None:
    defaults = yaml.safe_load((ROLE_ROOT / "defaults" / "main.yml").read_text())
    tasks = yaml.safe_load((ROLE_ROOT / "tasks" / "main.yml").read_text())
    guard_index = next(
        index
        for index, task in enumerate(tasks)
        if task.get("name") == "Refuse an implicit change to the active mesh control plane"
    )
    up_task_indices = [
        index
        for index, task in enumerate(tasks)
        if task.get("name")
        in {
            "Attach the Proxmox host to the tailnet with the supplied auth key",
            "Refresh the subnet-router settings on an authenticated host",
        }
    ]
    expressions = tasks[guard_index]["ansible.builtin.assert"]["that"]
    argument_specs = yaml.safe_load((ROLE_ROOT / "meta" / "argument_specs.yml").read_text())
    options = argument_specs["argument_specs"]["main"]["options"]

    assert defaults["proxmox_tailscale_allow_control_plane_migration"] is False
    assert options["proxmox_tailscale_allow_control_plane_migration"]["type"] == "bool"
    assert all(guard_index < up_index for up_index in up_task_indices)
    assert "proxmox_tailscale_active_control_url == proxmox_tailscale_expected_control_url" in expressions[0]
    assert "proxmox_tailscale_allow_control_plane_migration | bool" in expressions[0]


def test_proxmox_host_config_selects_headscale_and_keeps_tailscale_client() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml").read_text())

    assert host_vars["proxmox_tailscale_provider"] == "headscale"
    assert host_vars["proxmox_tailscale_login_server"] == "https://headscale.{{ platform_domain }}"
