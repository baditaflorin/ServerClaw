"""Guests keep their SSH host keys when cloud-init decides it is a new instance.

Proxmox derives the cloud-init instance id from the VM's cloud-init settings: any change plus a reboot is a "new instance", and cloud-init then deletes and regenerates the SSH host keys (its default).
The Tier-0 failover chain (the runner on infer-tier0) pins the host keys of the 0mcp guests it drives; on 2026-10-17 VM 200 got a new instance at a reboot, its keys changed, and the daily rehearsal and the
daily simulation failed until the pin was repaired by hand. `ssh_deletekeys: false` in the user-data every guest is rendered from (and as /etc/cloud/cloud.cfg.d/99-keep-ssh-hostkeys.cfg in the guests that
already exist) stops that. This pins the template side.
"""
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "proxmox_guests" / "templates" / "user-data.yml.j2"


def test_user_data_template_keeps_ssh_host_keys() -> None:
    text = TEMPLATE.read_text()
    assert text.startswith("#cloud-config")
    assert "\nssh_deletekeys: false\n" in text


def test_it_is_a_top_level_cloud_config_key_not_nested_in_a_list() -> None:
    lines = TEMPLATE.read_text().splitlines()
    assert "ssh_deletekeys: false" in lines                                               # exactly at column 0
