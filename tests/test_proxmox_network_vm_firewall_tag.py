"""Pin the `proxmox-vm-firewall` tag of the proxmox_network role.

`ansible-playbook playbooks/guest-network-policy.yml --tags proxmox-vm-firewall` must render and
install only the per-VM Proxmox firewall files (`/etc/pve/firewall/<vmid>.fw`), compile them and
restart pve-firewall when a file changed. It must not replay the hypervisor network (interfaces,
nftables, forwarding, the conntrack helper), change a guest NIC, or stop and start a guest, and the
placeholder-address safety guards must run in it and in every other tag selection.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/proxmox_network/tasks/main.yml"
ROLE_DEFAULTS = ROLE_TASKS.parents[1] / "defaults/main.yml"
PLAYBOOK = REPO_ROOT / "playbooks/guest-network-policy.yml"
COLLECTION_PLAYBOOK = REPO_ROOT / "collections/ansible_collections/lv3/platform/playbooks/guest-network-policy.yml"
SCOPED_TAG = "proxmox-vm-firewall"

GUARDS = [
    "Validate Proxmox network inputs",
    "SAFETY GUARD — Reject a management interface that aliases the WAN bridge",
    "SAFETY GUARD — Reject RFC 5737 / placeholder management IP before writing host network config",
]
VM_FIREWALL_TASKS = [
    "Ensure Proxmox firewall configuration directory exists",
    "Read current guest configurations for firewall enablement",
    "Record guests that currently exist on the Proxmox host",
    "Select the guests whose firewall files this run manages",
    "Refuse a firewall file selection that names a guest which does not exist",
    "Render per-guest Proxmox firewall policy to staging files",
    "Compare per-guest Proxmox firewall policy with the live files",
    "Show per-guest Proxmox firewall diff against the live files",
    "Refuse to remove live Proxmox firewall rules without an explicit operator decision",
    "Install per-guest Proxmox firewall policy",
    "Show where the replaced Proxmox firewall files were saved",
    "Compile Proxmox firewall configuration",
    "Restart Proxmox firewall after guest policy changes",
]
# Everything the scoped run must leave alone: host network, nftables, forwarding, the conntrack
# helper, the guest NIC firewall flag, and the guest power state.
UNSCOPED_TASKS = [
    "Validate optional staging bridge inputs",
    "Ensure nftables is installed",
    "Persist IPv4 forwarding configuration",
    "Read the active IPv4 forwarding value",
    "Apply IPv4 forwarding configuration",
    "Render Proxmox host network interfaces",
    "Render nftables rules for VM egress",
    "Enable and start nftables",
    "Install Proxmox firewall conntrack helper",
    "Install Proxmox firewall conntrack service",
    "Reload systemd after conntrack service updates",
    "Enable Proxmox firewall conntrack service",
    "Reload nftables rules",
    "Apply network changes with ifreload",
    "Wait for SSH after network reload",
    "Refresh facts after network changes",
    "Enable Proxmox firewall on each guest net0 interface",
    "Ensure Proxmox firewall service is enabled and started",
    "Ensure Proxmox firewall conntrack rule is active",
    "Check guest SSH reachability from the Proxmox host",
    "Record guests that need restart after firewall activation",
    "Stop guests that need firewall activation restart",
    "Start guests after firewall activation restart",
    "Wait for guest SSH after firewall activation restart",
]
FORBIDDEN_IN_SCOPED_TASKS = [
    "/etc/network",
    "/etc/nftables",
    "nft ",
    "ifreload",
    "sysctl",
    "systemd",
    "iptables",
    "conntrack",
    "qm stop",
    "qm start",
    "qm shutdown",
    "qm set",
    "qm reset",
    "qm reboot",
]


def _tasks() -> list[dict]:
    return yaml.safe_load(ROLE_TASKS.read_text(encoding="utf-8"))


def _by_name() -> dict[str, dict]:
    tasks = _tasks()
    names = [task["name"] for task in tasks]
    assert len(names) == len(set(names)), "task names must be unique so the pins below are unambiguous"
    return {task["name"]: task for task in tasks}


def _tags(task: dict) -> set[str]:
    tags = task.get("tags", [])
    return {tags} if isinstance(tags, str) else set(tags)


def _selected(task: dict, tag: str) -> bool:
    """Ansible's `--tags <tag>` selection: the task carries the tag or `always`."""
    return bool(_tags(task) & {tag, "always"})


def test_every_task_is_classified_exactly_once() -> None:
    """A new task must be added to one of the three lists on purpose, not slip into the scoped run."""
    assert sorted(_by_name()) == sorted(GUARDS + VM_FIREWALL_TASKS + UNSCOPED_TASKS)


def test_scoped_selection_is_the_guards_plus_the_per_vm_firewall_tasks_in_role_order() -> None:
    selected = [task["name"] for task in _tasks() if _selected(task, SCOPED_TAG)]

    assert selected == GUARDS + VM_FIREWALL_TASKS


def test_guards_cannot_be_skipped_by_a_tag_selection() -> None:
    by_name = _by_name()

    for name in GUARDS:
        assert _tags(by_name[name]) == {"always"}, name


def test_placeholder_address_guard_still_refuses_the_documentation_ranges() -> None:
    guard = _by_name()[GUARDS[2]]
    conditions = "\n".join(guard["ansible.builtin.assert"]["that"])

    for prefix in (r"^203\.0\.113\.", r"^192\.0\.2\.", r"^198\.51\.100\.", r"^2001:db8:"):
        assert prefix in conditions
    assert "management_gateway4" in conditions


def test_guards_are_the_first_tasks_of_the_role() -> None:
    assert [task["name"] for task in _tasks()][: len(GUARDS)] == GUARDS


def test_nothing_outside_the_per_vm_firewall_set_carries_the_scoped_tag() -> None:
    by_name = _by_name()

    for name in UNSCOPED_TASKS:
        assert not _selected(by_name[name], SCOPED_TAG), name
        assert "always" not in _tags(by_name[name]), name
    for name in VM_FIREWALL_TASKS:
        assert _tags(by_name[name]) == {SCOPED_TAG}, name


def test_scoped_tasks_do_not_reach_host_network_nftables_forwarding_or_guest_power() -> None:
    by_name = _by_name()

    for name in VM_FIREWALL_TASKS:
        text = json.dumps(by_name[name], ensure_ascii=False)
        for fragment in FORBIDDEN_IN_SCOPED_TASKS:
            assert fragment not in text, f"{name!r} mentions {fragment!r}"


def test_scoped_tasks_only_write_the_per_vm_firewall_files() -> None:
    by_name = _by_name()
    render = by_name["Render per-guest Proxmox firewall policy to staging files"]["ansible.builtin.template"]
    install = by_name["Install per-guest Proxmox firewall policy"]["ansible.builtin.script"]["cmd"]
    defaults = yaml.safe_load(ROLE_DEFAULTS.read_text(encoding="utf-8"))

    assert render["src"] == "vm.fw.j2"
    assert render["dest"] == "{{ proxmox_network_firewall_stage_dir }}/.lv3-vm-{{ guest.vmid }}.fw"
    assert "--live-dir {{ proxmox_network_firewall_live_dir | quote }}" in install
    assert by_name["Ensure Proxmox firewall configuration directory exists"]["ansible.builtin.file"]["path"] == (
        "{{ proxmox_network_firewall_live_dir }}"
    )
    # the variables are only a seam for tests: production writes exactly where it always did
    assert defaults["proxmox_network_firewall_live_dir"] == "/etc/pve/firewall"
    assert defaults["proxmox_network_firewall_stage_dir"] == "/root"
    assert by_name["Restart Proxmox firewall after guest policy changes"]["ansible.builtin.command"] == (
        "pve-firewall restart"
    )


def test_scoped_tasks_only_read_variables_that_a_scoped_run_still_defines() -> None:
    """A task skipped by tag leaves its `register` and `set_fact` undefined, unlike one skipped by `when`."""
    tasks = _tasks()
    unscoped_names: set[str] = set()
    for task in tasks:
        if _selected(task, SCOPED_TAG):
            continue
        if "register" in task:
            unscoped_names.add(task["register"])
        unscoped_names.update(task.get("ansible.builtin.set_fact", {}))
    assert "proxmox_network_guest_firewall_interfaces" in unscoped_names

    for task in tasks:
        if not _selected(task, SCOPED_TAG) or task["name"] in GUARDS:
            continue
        text = json.dumps({key: value for key, value in task.items() if key != "register"}, ensure_ascii=False)
        for name in unscoped_names:
            for match in re.finditer(rf"\b{re.escape(name)}\b", text):
                assert re.match(r"\s*\|\s*default\(", text[match.end() :]), (
                    f"{task['name']!r} reads {name} without a default, so a scoped run would fail on an undefined variable"
                )


def test_restart_condition_still_covers_changed_files_and_changed_nics() -> None:
    restart = _by_name()["Restart Proxmox firewall after guest policy changes"]
    condition = " ".join(str(restart["when"]).split())

    files_changed = "proxmox_network_vm_firewall_install.changed | default(false)"
    nics_changed = (
        "(proxmox_network_guest_firewall_interfaces | default({})).results | default([]) | selectattr('changed')"
    )
    assert files_changed in condition
    assert nics_changed in condition
    assert restart["changed_when"] is True


def test_playbook_copies_are_identical_and_the_guest_play_gathers_no_facts_in_a_scoped_run() -> None:
    assert PLAYBOOK.read_text(encoding="utf-8") == COLLECTION_PLAYBOOK.read_text(encoding="utf-8")

    host_play, guest_play = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))

    assert host_play["hosts"] == "proxmox_hosts"
    assert host_play["roles"] == [{"role": "lv3.platform.proxmox_network"}]
    assert guest_play["hosts"] == "lv3_guests"
    # Fact gathering ignores --tags: without this the scoped run would connect to every guest.
    assert guest_play["gather_facts"] == "{{ ansible_run_tags | difference(['proxmox-vm-firewall']) | length > 0 }}"


@pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook is not installed")
def test_ansible_selects_exactly_the_pinned_tasks_for_the_scoped_tag() -> None:
    """Ask Ansible itself (no host is contacted by --list-tasks), so role-level tag plumbing is covered."""
    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(REPO_ROOT / "inventory/hosts.yml"),
            str(PLAYBOOK),
            "--list-tasks",
            "--tags",
            SCOPED_TAG,
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "ANSIBLE_LOCALHOST_WARNING": "False"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    plays = re.split(r"\n  play #\d+ ", result.stdout)[1:]
    assert len(plays) == 2
    host_tasks = re.findall(r"^\s+lv3\.platform\.proxmox_network : (.+?)\tTAGS:", plays[0], flags=re.M)
    assert host_tasks[0].startswith("Validating arguments against arg spec")
    assert host_tasks[1:] == GUARDS + VM_FIREWALL_TASKS

    guest_tasks = re.findall(r"^\s+(?:\S+) : (.+?)\tTAGS:", plays[1], flags=re.M)
    assert guest_tasks, "the guest play lists its argument-spec validation"
    assert all(task.startswith("Validating arguments against arg spec") for task in guest_tasks)
