from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from urllib.parse import urlparse

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_server_routes_match_the_declared_docker_build_guest() -> None:
    config = json.loads((REPO_ROOT / "config/build-server.json").read_text(encoding="utf-8"))
    build_inventory = yaml.safe_load((REPO_ROOT / "inventory/build_server.yml").read_text(encoding="utf-8"))
    host_vars = yaml.safe_load((REPO_ROOT / "inventory/host_vars/proxmox-host.yml").read_text(encoding="utf-8"))

    username, separator, address = config["host"].partition("@")
    assert separator

    build_host = build_inventory["all"]["children"]["build_server"]["hosts"]["build"]
    assert build_host["ansible_user"] == username
    assert build_host["ansible_host"] == address

    docker_build_guest = next(guest for guest in host_vars["proxmox_guests"] if guest["name"] == "docker-build")
    assert docker_build_guest["ipv4"] == address
    assert urlparse(config["apt_proxy_url"]).hostname == address


def test_build_server_routes_use_the_same_verified_bastion_and_pinned_host_keys() -> None:
    config = json.loads((REPO_ROOT / "config/build-server.json").read_text(encoding="utf-8"))
    build_inventory = yaml.safe_load((REPO_ROOT / "inventory/build_server.yml").read_text(encoding="utf-8"))
    build_host = build_inventory["all"]["children"]["build_server"]["hosts"]["build"]

    ssh_options = config["ssh_options"]
    jump_index = ssh_options.index("-J")
    config_jump = ssh_options[jump_index + 1]
    inventory_jump = re.search(r"ProxyJump=([^\s]+)", build_host["ansible_ssh_common_args"])

    assert inventory_jump is not None
    assert inventory_jump.group(1) == config_jump
    assert config_jump
    assert "StrictHostKeyChecking=yes" in ssh_options
    assert "StrictHostKeyChecking=yes" in build_host["ansible_ssh_common_args"]
    assert not any("UserKnownHostsFile=/dev/null" in option for option in ssh_options)
    assert "UserKnownHostsFile=/dev/null" not in build_host["ansible_ssh_common_args"]


def test_full_pre_push_gates_bound_concurrency_on_the_shared_validator() -> None:
    config = json.loads((REPO_ROOT / "config/build-server.json").read_text(encoding="utf-8"))

    for command_name in ("pre-push-gate", "remote-pre-push"):
        command = config["commands"][command_name]
        for command_field in ("command", "local_fallback_command"):
            args = shlex.split(command[command_field])
            jobs_index = args.index("--jobs")
            assert args[jobs_index + 1] == "2"
