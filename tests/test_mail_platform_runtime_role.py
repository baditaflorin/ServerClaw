from pathlib import Path

import json
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "defaults" / "main.yml"
COMPOSE_TEMPLATE_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "templates" / "docker-compose.yml.j2"
STALWART_TEMPLATE_PATH = REPO_ROOT / "roles" / "mail_platform_runtime" / "templates" / "stalwart-config.toml.j2"
HOST_VARS_PATH = REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml"
CONTROL_PLANE_LANES_PATH = REPO_ROOT / "config" / "control-plane-lanes.json"


def test_defaults_define_private_submission_port() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text())
    assert defaults["mail_platform_internal_submission_port"] == (
        "{{ hostvars['proxmox_florin'].platform_port_assignments.mail_platform_internal_submission_port | default(1587) }}"
    )


def test_stalwart_template_adds_private_submission_listener() -> None:
    template = STALWART_TEMPLATE_PATH.read_text()
    assert "[server.listener.internal_submission]" in template
    assert 'bind = "[::]:{{ mail_platform_internal_submission_port }}"' in template
    assert """{ if = "listener == 'internal_submission'", then = "[plain, login]" }""" in template
    assert 'allow-plain-text = true' in template


def test_compose_template_publishes_private_submission_port_on_vm_ip() -> None:
    template = COMPOSE_TEMPLATE_PATH.read_text()
    assert '"{{ ansible_host }}:{{ mail_platform_internal_submission_port }}:{{ mail_platform_internal_submission_port }}"' in template


def test_host_firewall_only_opens_private_submission_for_local_docker_networks() -> None:
    host_vars = yaml.safe_load(HOST_VARS_PATH.read_text())
    docker_runtime_rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]
    relay_rules = [rule for rule in docker_runtime_rules if 1587 in rule["ports"]]
    assert {rule["source"] for rule in relay_rules} == {"172.16.0.0/12", "192.168.0.0/16"}


def test_control_plane_lane_points_at_private_submission_relay() -> None:
    lanes = json.loads(CONTROL_PLANE_LANES_PATH.read_text())
    message_surfaces = lanes["lanes"]["message"]["current_surfaces"]
    submission = next(surface for surface in message_surfaces if surface["id"] == "mail-platform-submission")
    assert submission["endpoint"] == "10.10.10.20:1587"
