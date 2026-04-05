from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "playbooks"
    / "realtime.yml"
)
EXPECTED_COLLECTION_PLATFORM_VARS = [
    "{{ playbook_dir }}/../../../../../inventory/group_vars/platform.yml"
]


def test_realtime_playbook_converges_network_before_agents() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    network_play = next(play for play in plays if play["hosts"] == "proxmox_hosts")
    parent_play = next(play for play in plays if play["hosts"] == "monitoring-lv3")
    child_play = next(
        play
        for play in plays
        if isinstance(play.get("hosts"), str)
        and "lv3_guests:proxmox_hosts" in play["hosts"]
    )

    assert plays.index(network_play) < plays.index(parent_play) < plays.index(child_play)
    assert network_play["roles"] == [{"role": "lv3.platform.proxmox_network"}]
    assert parent_play["roles"] == [
        {"role": "lv3.platform.linux_guest_firewall"},
        {"role": "lv3.platform.monitoring_vm"},
        {"role": "lv3.platform.netdata_runtime"},
    ]
    assert all(
        play["vars_files"] == EXPECTED_COLLECTION_PLATFORM_VARS
        for play in plays
    )


def test_realtime_edge_play_builds_generated_portals_before_publication() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    edge_play = next(play for play in plays if play["hosts"] == "nginx-lv3")
    build_task = next(
        task
        for task in edge_play["pre_tasks"]
        if task.get("name") == "Build shared generated portal artifacts required by edge publication"
    )

    assert edge_play["vars"]["realtime_repo_root"] == "{{ playbook_dir }}/../../../../.."
    assert edge_play["vars_files"] == EXPECTED_COLLECTION_PLATFORM_VARS
    assert build_task["ansible.builtin.command"]["argv"] == ["make", "generate-changelog-portal", "docs"]
    assert build_task["args"]["chdir"] == "{{ realtime_repo_root }}"
    assert build_task["delegate_to"] == "localhost"
    assert build_task["run_once"] is True
