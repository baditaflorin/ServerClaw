from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
TEMPLATE_PATH = REPO_ROOT / "roles" / "linux_guest_firewall" / "templates" / "nftables.conf.j2"


def test_container_forwarding_guests_use_the_source_only_forward_path() -> None:
    template = TEMPLATE_PATH.read_text()

    assert "guest_policy.allow_container_forwarding | default(false)" in template


def test_coolify_guest_policy_enables_container_forwarding_for_published_ports() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    coolify_policy = host_vars["network_policy"]["guests"]["coolify-lv3"]

    assert coolify_policy["allow_container_forwarding"] is True

    published_sources = {
        rule["source"]: tuple(rule["ports"])
        for rule in coolify_policy["allowed_inbound"]
        if rule["source"] == "nginx-lv3"
    }
    assert published_sources["nginx-lv3"] == (80, 443, 8000, 8096)
