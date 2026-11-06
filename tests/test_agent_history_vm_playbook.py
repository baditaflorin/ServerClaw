"""Static guards for playbooks/agent-history-vm.yml (ADR 0494).

The first provisioning (2026-10-29) lost its first boot because the play hard-stopped the VM seconds after the guests role
started it: cloud-init was cut off, leaving zero-byte netplan, ssh host keys and apt lists plus a saved instance-id, so the next
boot never configured the network. These tests pin the fix: no forced stop, and no restart before the first boot has finished.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PLAYBOOK = REPO / "playbooks" / "agent-history-vm.yml"
HOST_VARS = REPO / "inventory" / "host_vars" / "proxmox-host.yml"


def _plays() -> list[dict]:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))


def _walk(tasks: list[dict]):
    """Yield every task, descending into blocks, in order."""
    for task in tasks or []:
        yield task
        for key in ("block", "rescue", "always"):
            if key in task:
                yield from _walk(task[key])


def _command(task: dict) -> str:
    for key in ("ansible.builtin.command", "ansible.builtin.shell", "command", "shell"):
        value = task.get(key)
        if isinstance(value, dict):
            value = value.get("cmd") or " ".join(value.get("argv", []))
        if value:
            return str(value)
    return ""


def _all_tasks(play: dict) -> list[dict]:
    return list(_walk(play.get("pre_tasks"))) + list(_walk(play.get("tasks"))) + list(_walk(play.get("post_tasks")))


def test_no_task_hard_stops_the_vm() -> None:
    commands = [_command(task) for play in _plays() for task in _all_tasks(play)]
    assert not [c for c in commands if "qm stop" in c], "a forced qm stop can cut cloud-init's first boot off"


def test_proxmox_play_does_not_restart_the_vm() -> None:
    proxmox_play = _plays()[0]
    assert proxmox_play["hosts"] == "proxmox_hosts"
    commands = [_command(task) for task in _all_tasks(proxmox_play)]
    assert not [c for c in commands if "qm shutdown" in c or "qm start" in c or "qm reboot" in c]
    # the balloon floor is applied live, the discard option stays pending until the restart in the guest play
    assert any("--balloon" in c for c in commands)
    assert any("discard=on" in c for c in commands)


def test_restart_waits_for_cloud_init_and_is_graceful() -> None:
    guest_play = _plays()[1]
    assert guest_play["hosts"] == "agent-history"
    tasks = list(_walk(guest_play["pre_tasks"]))
    commands = [_command(task) for task in tasks]
    first_boot_wait = next(i for i, c in enumerate(commands) if "cloud-init status --wait" in c)
    shutdown = next(i for i, c in enumerate(commands) if "qm shutdown" in c)
    start = next(i for i, c in enumerate(commands) if c.startswith("qm start"))
    assert first_boot_wait < shutdown < start
    assert "--forceStop 1" in commands[shutdown] and "--timeout" in commands[shutdown]
    for index in (shutdown, start):
        assert tasks[index].get("delegate_to"), "qm runs on the Proxmox host"


def test_restart_only_when_hardware_settings_are_pending() -> None:
    guest_play = _plays()[1]
    restart_blocks = [task for task in guest_play["pre_tasks"] if "block" in task]
    assert len(restart_blocks) == 1
    condition = restart_blocks[0]["when"]
    assert "agent_history_vm_config_pending" in condition and "agent_history_vm_config_running" in condition
    commands = [_command(task) for task in _walk(guest_play["pre_tasks"])]
    assert any(c.endswith("--current 1") for c in commands), "the running config is read with --current 1"


def test_restart_is_followed_by_a_connection_and_cloud_init_wait() -> None:
    block = next(task for task in _plays()[1]["pre_tasks"] if "block" in task)
    names = [task["name"] for task in block["block"]]
    assert names.index("Start the agent-history VM") < names.index(
        "Wait for the agent-history VM SSH service after the restart"
    )
    assert any("cloud-init status --wait" in _command(task) for task in block["block"])


def test_guest_does_not_install_docker_io_through_cloud_init() -> None:
    guests = yaml.safe_load(HOST_VARS.read_text(encoding="utf-8"))["proxmox_guests"]
    guest = next(g for g in guests if g["name"] == "agent-history")
    roles = [role["role"] if isinstance(role, dict) else role for role in _plays()[1]["roles"]]
    assert "lv3.platform.docker_runtime" in roles, "the docker_runtime role converges Docker CE"
    assert "docker.io" not in guest["packages"], (
        "docker.io conflicts with Docker CE and ends every new cloud-init instance in error"
    )
