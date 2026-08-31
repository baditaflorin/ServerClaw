from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "roles" / "proxmox_tailscale_proxy" / "tasks" / "main.yml"
ARGUMENT_SPECS = REPO_ROOT / "roles" / "proxmox_tailscale_proxy" / "meta" / "argument_specs.yml"
HOST_VARS = REPO_ROOT / "inventory" / "host_vars" / "proxmox-host.yml"


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
    assert state_task["become"] is False
    assert (
        "proxmox_tailscale_proxy_unit_states.results" in start_task["vars"]["proxmox_tailscale_proxy_unit_state_lines"]
    )
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
    assert 'listen_port: "{{ platform_port_assignments.windmill_host_proxy_port }}"' in host_vars_text
    assert 'listen_port: "{{ platform_port_assignments.nomad_host_proxy_port }}"' in host_vars_text
    assert 'listen_port: "{{ platform_port_assignments.platform_context_host_proxy_port }}"' in host_vars_text


def test_role_rearms_or_restarts_changed_proxy_units_after_rendering() -> None:
    tasks = load_tasks()
    enable_task = next(task for task in tasks if task.get("name") == "Enable Proxmox Tailscale proxy sockets")
    changed_socket_rearm_task = next(
        task for task in tasks if task.get("name") == "Re-arm changed Proxmox Tailscale proxy socket listeners"
    )
    stop_task = next(
        task
        for task in tasks
        if task.get("name") == "Stop active Proxmox Tailscale proxy services before re-arming changed proxy listeners"
    )
    restart_task = next(
        task
        for task in tasks
        if task.get("name") == "Restart active Proxmox Tailscale proxy services when their unit or upstream changes"
    )
    rearm_task = next(
        task
        for task in tasks
        if task.get("name") == "Start Proxmox Tailscale proxy sockets after re-arming changed proxy listeners"
    )
    cmdline_task = next(
        task for task in tasks if task.get("name") == "Read active Proxmox Tailscale proxy service command lines"
    )

    assert enable_task["ansible.builtin.systemd"]["enabled"] is True
    assert "state" not in enable_task["ansible.builtin.systemd"]
    assert changed_socket_rearm_task["ansible.builtin.systemd"]["state"] == "restarted"
    assert (
        "proxmox_tailscale_proxy_sockets.results"
        in changed_socket_rearm_task["vars"]["proxmox_tailscale_socket_unit_changed"]
    )
    assert changed_socket_rearm_task["when"] == "proxmox_tailscale_socket_unit_changed"
    assert cmdline_task["become"] is False
    assert stop_task["ansible.builtin.systemd"]["state"] == "stopped"
    assert "proxmox_tailscale_proxy_cmdlines.results" in stop_task["vars"]["proxmox_tailscale_running_cmdline"]
    assert stop_task["when"] == [
        "proxmox_tailscale_restart_required",
        "proxmox_tailscale_service_active_state == 'active'",
        "proxmox_tailscale_socket_active_state != 'active'",
    ]
    assert rearm_task["ansible.builtin.systemd"]["state"] == "started"
    assert "proxmox_tailscale_proxy_cmdlines.results" in rearm_task["vars"]["proxmox_tailscale_running_cmdline"]
    assert rearm_task["when"] == [
        "proxmox_tailscale_restart_required",
        "proxmox_tailscale_service_active_state == 'active'",
        "proxmox_tailscale_socket_active_state != 'active'",
    ]
    assert restart_task["ansible.builtin.systemd"]["state"] == "restarted"
    assert "proxmox_tailscale_proxy_sockets.results" in restart_task["vars"]["proxmox_tailscale_socket_unit_changed"]
    assert "proxmox_tailscale_proxy_services.results" in restart_task["vars"]["proxmox_tailscale_service_unit_changed"]
    assert "proxmox_tailscale_proxy_cmdlines.results" in restart_task["vars"]["proxmox_tailscale_running_cmdline"]
    assert "proxmox_tailscale_restart_required" in restart_task["when"]
    assert "proxmox_tailscale_socket_active_state == 'active'" in restart_task["when"]


def test_role_removes_units_that_are_not_in_the_declared_proxy_catalog() -> None:
    tasks = load_tasks()
    expected_units_task = next(
        task for task in tasks if task.get("name") == "Resolve declared Proxmox Tailscale proxy unit names"
    )
    find_task = next(
        task for task in tasks if task.get("name") == "Find previously managed Proxmox Tailscale proxy units"
    )
    stop_task = next(
        task for task in tasks if task.get("name") == "Stop and disable stale Proxmox Tailscale proxy units"
    )
    reset_task = next(
        task for task in tasks if task.get("name") == "Clear failed state from stale Proxmox Tailscale proxy units"
    )
    remove_task = next(task for task in tasks if task.get("name") == "Remove stale Proxmox Tailscale proxy unit files")

    expected_units = expected_units_task["ansible.builtin.set_fact"]["proxmox_tailscale_proxy_expected_unit_names"]
    assert "map('regex_replace', '^', 'lv3-tailscale-proxy-')" in expected_units
    assert "map('regex_replace', '$', '.socket')" in expected_units
    assert "map('regex_replace', '$', '.service')" in expected_units
    assert find_task["ansible.builtin.find"]["patterns"] == [
        "lv3-tailscale-proxy-*.socket",
        "lv3-tailscale-proxy-*.service",
    ]
    assert stop_task["ansible.builtin.systemd"] == {
        "name": "{{ item.path | basename }}",
        "enabled": False,
        "state": "stopped",
    }
    assert stop_task["when"] == "(item.path | basename) not in proxmox_tailscale_proxy_expected_unit_names"
    assert reset_task["ansible.builtin.command"]["argv"] == [
        "systemctl",
        "reset-failed",
        "{{ item.path | basename }}",
    ]
    assert reset_task["changed_when"] is False
    assert remove_task["ansible.builtin.file"]["state"] == "absent"
    assert remove_task["notify"] == "Reload systemd"
