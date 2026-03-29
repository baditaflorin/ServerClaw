from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "proxmox_tailscale_proxy" / "tasks" / "main.yml"
ARGUMENT_SPECS = REPO_ROOT / "roles" / "proxmox_tailscale_proxy" / "meta" / "argument_specs.yml"
HOST_VARS = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def load_tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text())


def test_role_prefers_resolved_platform_proxy_catalog() -> None:
    tasks = load_tasks()
    resolve_task = next(task for task in tasks if task.get("name") == "Resolve Proxmox Tailscale proxy inputs")
    effective_value = resolve_task["ansible.builtin.set_fact"]["proxmox_tailscale_effective_tcp_proxies"]
    assert "platform_host.network.tailscale_tcp_proxies" in effective_value
    assert "proxmox_tailscale_tcp_proxies | default([])" in effective_value


def test_role_argument_spec_declares_proxy_inputs() -> None:
    argument_specs = yaml.safe_load(ARGUMENT_SPECS.read_text())
    options = argument_specs["argument_specs"]["main"]["options"]
    assert options["proxmox_tailscale_tcp_proxies"]["type"] == "list"
    assert options["platform_host"]["type"] == "dict"


def test_role_only_starts_socket_units_when_no_proxy_service_owns_the_listener() -> None:
    tasks = load_tasks()
    state_task = next(task for task in tasks if task.get("name") == "Read current Proxmox Tailscale proxy unit states")
    start_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Start Proxmox Tailscale proxy sockets when the listener is not already owned by an active proxy service"
    )
    assert state_task["register"] == "proxmox_tailscale_proxy_unit_states"
    assert "proxmox_tailscale_proxy_unit_states.results" in start_task["vars"]["proxmox_tailscale_proxy_unit_state_lines"]
    assert start_task["when"] == "proxmox_tailscale_service_active_state != 'active'"


def test_role_asserts_proxy_listener_remains_available_after_converge() -> None:
    tasks = load_tasks()
    assert_task = next(
        task
        for task in tasks
        if task.get("name") == "Assert Proxmox Tailscale proxy listeners remain active after converge"
    )
    assert (
        assert_task["ansible.builtin.assert"]["that"][0]
        == "proxmox_tailscale_socket_active_state == 'active' or proxmox_tailscale_service_active_state == 'active'"
    )


def test_host_inventory_proxy_ports_reference_platform_port_assignments() -> None:
    host_vars_text = HOST_VARS.read_text()
    assert "listen_port: \"{{ platform_port_assignments.windmill_host_proxy_port }}\"" in host_vars_text
    assert "listen_port: \"{{ platform_port_assignments.nomad_host_proxy_port }}\"" in host_vars_text
    assert "listen_port: \"{{ platform_port_assignments.platform_context_host_proxy_port }}\"" in host_vars_text


def test_role_recycles_active_services_before_restarting_changed_sockets() -> None:
    tasks_text = ROLE_TASKS.read_text()

    assert "Stop active Proxmox Tailscale proxy services before restarting changed sockets" in tasks_text
    assert tasks_text.index("Read active Proxmox Tailscale proxy service command lines") < tasks_text.index(
        "Stop active Proxmox Tailscale proxy services before restarting changed sockets"
    )
    assert tasks_text.index("Read current Proxmox Tailscale proxy socket states") < tasks_text.index(
        "Stop active Proxmox Tailscale proxy services before restarting changed sockets"
    )
    assert tasks_text.index("Stop active Proxmox Tailscale proxy services before restarting changed sockets") < tasks_text.index(
        "Enable and start Proxmox Tailscale proxy sockets"
    )
    assert "proxmox_tailscale_socket_unit_changed" in tasks_text
    assert "proxmox_tailscale_socket_state != 'active'" in tasks_text
