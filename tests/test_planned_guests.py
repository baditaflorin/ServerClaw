"""A guest declared with `lifecycle: planned` is inert (ADR 0494): declared, not approved, not provisioned.

VM 155 (agent-history) was declared planned ahead of its capacity decision and activated on 2026-10-29 (the line was deleted); no
real guest is planned now, so the guard is pinned with synthetic planned guests. The pinned behaviours:

* the default guest set of proxmox-install.yml (make provision-guests, bootstrap) skips planned guests, under Ansible's strict
  undefined handling, so guests without a `lifecycle` key stay selected;
* the guests role refuses a planned guest in whatever set it is given, including the empty-set fallback to every declared guest;
* the per-guest playbook refuses to run while its guest is planned: removing the line is the owner's activation;
* the inventory puts planned guests in `planned_guests` and the scoped patterns exclude that group (see also
  tests/test_generate_inventory.py and tests/test_ansible_execution_scopes.py).
"""

from __future__ import annotations

from pathlib import Path

import jinja2
import pytest
import yaml
from jinja2.nativetypes import NativeEnvironment

REPO = Path(__file__).resolve().parents[1]
HOST_VARS = REPO / "inventory" / "host_vars" / "proxmox-host.yml"
INSTALL_PLAYBOOKS = [
    REPO / "playbooks" / "proxmox-install.yml",
    REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks" / "proxmox-install.yml",
]
AGENT_HISTORY_PLAYBOOK = REPO / "playbooks" / "agent-history-vm.yml"
GUESTS_ROLE_TASKS = (
    REPO
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "proxmox_guests"
    / "tasks"
    / "main.yml"
)


def _guests() -> list[dict]:
    return yaml.safe_load(HOST_VARS.read_text(encoding="utf-8"))["proxmox_guests"]


def _env() -> NativeEnvironment:
    return NativeEnvironment(undefined=jinja2.StrictUndefined)


def _render(template: str, **context):
    return _env().from_string(template).render(**context)


def _truth(expression: str, **context) -> bool:
    return bool(_env().compile_expression(expression)(**context))


def _guest(vmid: int, name: str, **extra) -> dict:
    return {"vmid": vmid, "name": name, **extra}


def _planned_copy_of_agent_history() -> dict:
    (guest,) = [g for g in _guests() if g["vmid"] == 155]
    return {**guest, "vmid": 999, "name": "agent-history-planned-copy", "lifecycle": "planned"}


def test_agent_history_was_activated_and_no_declared_guest_is_planned() -> None:
    (guest,) = [g for g in _guests() if g["vmid"] == 155]
    assert guest["name"] == "agent-history"
    assert "lifecycle" not in guest, "activated on 2026-10-29: the owner deleted the `lifecycle: planned` line"
    assert [g["name"] for g in _guests() if g.get("lifecycle") == "planned"] == []


@pytest.mark.parametrize("playbook", INSTALL_PLAYBOOKS, ids=lambda p: p.parent.parent.name)
def test_the_default_guest_set_skips_planned_guests(playbook: Path) -> None:
    play = yaml.safe_load(playbook.read_text(encoding="utf-8"))[0]
    template = play["vars"]["proxmox_guests_active"]
    guests = _guests()
    # nothing real is planned: the default set is every declared guest, in order, agent-history included
    assert [g["vmid"] for g in _render(template, proxmox_guests=guests)] == [g["vmid"] for g in guests]
    # a planned guest is skipped and everything else stays, in order
    with_planned = [*guests, _planned_copy_of_agent_history()]
    active = _render(template, proxmox_guests=with_planned)
    assert 999 not in [g["vmid"] for g in active]
    assert [g["vmid"] for g in active] == [g["vmid"] for g in guests]


def test_guests_without_a_lifecycle_key_stay_selected_under_strict_undefined() -> None:
    template = yaml.safe_load(INSTALL_PLAYBOOKS[0].read_text(encoding="utf-8"))[0]["vars"]["proxmox_guests_active"]
    guests = [_guest(1, "a"), _guest(2, "b", lifecycle="active"), _guest(3, "c", lifecycle="planned")]
    assert [g["name"] for g in _render(template, proxmox_guests=guests)] == ["a", "b"]


def _role_assertion() -> dict:
    tasks = yaml.safe_load(GUESTS_ROLE_TASKS.read_text(encoding="utf-8"))
    (task,) = [t for t in tasks if t.get("name", "").startswith("Refuse to provision a planned guest")]
    return task["ansible.builtin.assert"]


def test_the_guests_role_refuses_a_planned_guest_in_any_selection() -> None:
    (condition,) = _role_assertion()["that"]
    planned = _guest(155, "agent-history", lifecycle="planned")
    other = _guest(110, "nginx")
    assert not _truth(condition, proxmox_guests=[other, planned], proxmox_guests_active=[planned])
    assert _truth(condition, proxmox_guests=[other, planned], proxmox_guests_active=[other])
    # an empty selection makes the role fall back to every declared guest, planned ones included: it must refuse
    assert not _truth(condition, proxmox_guests=[other, planned], proxmox_guests_active=[])
    assert _truth(condition, proxmox_guests=[other], proxmox_guests_active=[])


def test_the_guests_role_message_names_the_activation_change() -> None:
    message = _role_assertion()["fail_msg"]
    assert "lifecycle: planned" in message and "inventory/host_vars/proxmox-host.yml" in message


def _per_guest_refusal() -> dict:
    play = yaml.safe_load(AGENT_HISTORY_PLAYBOOK.read_text(encoding="utf-8"))[0]
    (task,) = [t for t in play["pre_tasks"] if "planned" in t["name"]]
    return task["ansible.builtin.assert"]


def test_the_per_guest_playbook_refuses_a_planned_guest() -> None:
    (condition,) = _per_guest_refusal()["that"]
    declared = [g for g in _guests() if g["vmid"] == 155]
    assert _truth(condition, proxmox_guests_active=declared), "as declared today (activated): runs"
    planned = [{**declared[0], "lifecycle": "planned"}]
    assert not _truth(condition, proxmox_guests_active=planned), "declared planned again: refuses"
    message = _per_guest_refusal()["fail_msg"]
    assert "lifecycle: planned" in message and "make generate-inventory" in message and "capacity decision" in message


def test_the_per_guest_playbook_still_limits_the_guests_role_to_vmid_155() -> None:
    play = yaml.safe_load(AGENT_HISTORY_PLAYBOOK.read_text(encoding="utf-8"))[0]
    template = play["vars"]["proxmox_guests_active"]
    selected = _render(template, proxmox_guests=_guests(), agent_history_vm_vmid=155)
    assert [g["vmid"] for g in selected] == [155]


def test_the_committed_inventory_keeps_planned_guests_out_of_scoped_patterns() -> None:
    inventory = yaml.safe_load((REPO / "inventory" / "hosts.yml").read_text(encoding="utf-8"))["all"]
    assert inventory["children"]["planned_guests"]["hosts"] == {}, "the group is emitted, and empty: nothing is planned"
    assert "agent-history" in inventory["children"]["lv3_guests"]["hosts"]
    patterns = inventory["vars"]["playbook_execution_host_patterns"]
    assert patterns["lv3_guests"]["production"] == "lv3_guests:&production:!planned_guests"
