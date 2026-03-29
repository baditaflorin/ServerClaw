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


def test_host_inventory_proxy_ports_reference_platform_port_assignments() -> None:
    host_vars_text = HOST_VARS.read_text()
    assert "listen_port: \"{{ platform_port_assignments.windmill_host_proxy_port }}\"" in host_vars_text
    assert "listen_port: \"{{ platform_port_assignments.platform_context_host_proxy_port }}\"" in host_vars_text


def test_role_restarts_changed_socket_units_after_rendering() -> None:
    tasks = load_tasks()
    enable_task = next(
        task for task in tasks if task.get("name") == "Enable Proxmox Tailscale proxy sockets"
    )
    listener_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether Proxmox Tailscale proxy sockets are listening on the declared address"
    )
    restart_task = next(
        task
        for task in tasks
        if task.get("name")
        == "Restart Proxmox Tailscale proxy sockets when their unit changed or listener is missing"
    )

    assert enable_task["ansible.builtin.systemd"]["enabled"] is True
    assert "state" not in enable_task["ansible.builtin.systemd"]
    assert "(%[^:]+)?:" in listener_check["ansible.builtin.shell"]
    assert 'systemctl stop "lv3-tailscale-proxy-{{ item.name }}.service" || true' in restart_task["ansible.builtin.shell"]
    assert 'systemctl stop "lv3-tailscale-proxy-{{ item.name }}.socket" || true' in restart_task["ansible.builtin.shell"]
    assert 'systemctl start "lv3-tailscale-proxy-{{ item.name }}.socket"' in restart_task["ansible.builtin.shell"]
    assert "proxmox_tailscale_proxy_sockets.results" in restart_task["vars"]["proxmox_tailscale_socket_unit_changed"]
    assert "proxmox_tailscale_proxy_socket_listeners.results" in restart_task["vars"][
        "proxmox_tailscale_socket_listener_missing"
    ]
    assert (
        restart_task["changed_when"]
        == "proxmox_tailscale_socket_unit_changed or proxmox_tailscale_socket_listener_missing"
    )
