from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEDICATED_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "artifact-cache-vm.yml"
CONSUMER_PLAYBOOK_PATH = REPO_ROOT / "playbooks" / "services" / "build-artifact-cache.yml"


def load_yaml(path: Path) -> list[dict] | dict:
    return yaml.safe_load(path.read_text())


def test_artifact_cache_vm_playbook_provisions_then_converges_guest() -> None:
    playbook = load_yaml(DEDICATED_PLAYBOOK_PATH)
    play_names = [play["name"] for play in playbook]

    assert play_names == [
        "Ensure the artifact cache VM is provisioned on the Proxmox host",
        "Converge the dedicated artifact cache guest",
    ]
    assert playbook[0]["vars"]["artifact_cache_vm_vmid"] == 180
    assert [role["role"] for role in playbook[0]["roles"]] == ["lv3.platform.proxmox_guests"]
    assert playbook[1]["vars"]["docker_runtime_insecure_registries"] == [
        "{{ ansible_host }}:5001",
        "{{ ansible_host }}:5002",
        "{{ ansible_host }}:5003",
        "{{ ansible_host }}:5004",
    ]
    assert [task["name"] for task in playbook[1]["pre_tasks"]] == [
        "Wait for the artifact cache VM SSH service to be reachable",
        "Gather facts after SSH is ready",
        "Wait for cloud-init first boot work to finish when present",
        "Wait for Debian package manager activity to settle after cloud-init",
    ]
    assert [role["role"] for role in playbook[1]["roles"]] == [
        "lv3.platform.linux_guest_firewall",
        "lv3.platform.linux_access",
        "lv3.platform.docker_runtime",
        "lv3.platform.artifact_cache_runtime",
    ]


def test_build_artifact_cache_playbook_repoints_consumers_and_removes_local_stack() -> None:
    playbook = load_yaml(CONSUMER_PLAYBOOK_PATH)
    play = playbook[0]

    assert play["name"] == "Converge build artifact cache consumers on the docker build guest"
    assert play["vars"]["artifact_cache_remote_host"] == "{{ hostvars['artifact-cache-lv3'].ansible_host }}"
    assert play["vars"]["docker_runtime_registry_mirrors"] == [
        "http://{{ artifact_cache_remote_host }}:5001",
        "https://mirror.gcr.io",
    ]
    assert play["vars"]["docker_runtime_insecure_registries"] == [
        "{{ artifact_cache_remote_host }}:5001",
        "{{ artifact_cache_remote_host }}:5002",
        "{{ artifact_cache_remote_host }}:5003",
        "{{ artifact_cache_remote_host }}:5004",
    ]

    artifact_role = next(role for role in play["roles"] if role["role"] == "lv3.platform.artifact_cache_runtime")
    assert artifact_role["vars"] == {"artifact_cache_state": "absent"}
