from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "step-ca.yml"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"


def test_step_ca_playbook_converges_runtime_control_locally_before_guest_trust_wave() -> None:
    playbook = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))

    runtime_play = playbook[1]
    managed_guests_play = playbook[3]

    assert runtime_play["name"] == "Converge the private step-ca runtime on runtime-control-lv3"
    assert runtime_play["hosts"] == (
        "{{ 'docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'runtime-control-lv3' }}"
    )
    assert runtime_play["gather_facts"] is False
    assert [role["role"] for role in runtime_play["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.step_ca_runtime",
        "lv3.platform.step_ca_ssh_trust",
    ]
    assert [task["name"] for task in runtime_play["pre_tasks"][:3]] == [
        "Reset the runtime-control SSH connection after Proxmox-side step-ca changes",
        "Wait for the runtime-control SSH connection after Proxmox-side step-ca changes",
        "Gather runtime-control facts after the SSH transport reset",
    ]
    assert runtime_play["pre_tasks"][2]["ansible.builtin.setup"] == {
        "gather_subset": ["!all", "min", "network"],
        "gather_timeout": 15,
    }

    assert managed_guests_play["name"] == "Converge SSH CA trust on managed guests"
    assert managed_guests_play["hosts"] == (
        "{{ 'lv3_guests:&staging:!docker-runtime-staging-lv3' if (env | default('production')) == 'staging' else 'lv3_guests:&production:!runtime-control-lv3' }}"
    )
    assert managed_guests_play["gather_facts"] is False
    assert [task["name"] for task in managed_guests_play["pre_tasks"][:3]] == [
        "Reset managed guest SSH connections after the Proxmox step-ca trust changes",
        "Wait for managed guest SSH connections after the Proxmox step-ca trust changes",
        "Gather managed guest facts after the SSH transport reset",
    ]
    assert managed_guests_play["pre_tasks"][2]["ansible.builtin.setup"] == {
        "gather_subset": ["!all", "min", "network"],
        "gather_timeout": 15,
    }


def test_runtime_control_firewall_allows_private_step_ca_api_callers() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text(encoding="utf-8"))
    runtime_control_rules = host_vars["network_policy"]["guests"]["runtime-control-lv3"]["allowed_inbound"]

    all_guests_rule = next(rule for rule in runtime_control_rules if rule["source"] == "all_guests")
    docker_172_rule = next(rule for rule in runtime_control_rules if rule["source"] == "172.16.0.0/12")
    docker_192_rule = next(rule for rule in runtime_control_rules if rule["source"] == "192.168.0.0/16")

    assert 9000 in all_guests_rule["ports"]
    assert 9000 in docker_172_rule["ports"]
    assert 9000 in docker_192_rule["ports"]
    assert "step-ca" in all_guests_rule["description"]
