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
    / "dozzle.yml"
)


def test_dozzle_playbook_converges_proxmox_network_before_runtime() -> None:
    plays = yaml.safe_load(PLAYBOOK_PATH.read_text())

    proxmox_play = next(play for play in plays if play["hosts"] == "proxmox_hosts")
    runtime_play = next(
        play for play in plays if play["hosts"] == "docker-runtime-lv3:docker-build-lv3:monitoring-lv3"
    )

    assert plays.index(proxmox_play) < plays.index(runtime_play)
    assert proxmox_play["roles"] == [{"role": "lv3.platform.proxmox_network"}]
