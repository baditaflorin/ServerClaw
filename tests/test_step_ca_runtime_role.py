from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "step_ca_runtime"
    / "defaults"
    / "main.yml"
)
TASKS_PATH = (
    REPO_ROOT
    / "collections"
    / "ansible_collections"
    / "lv3"
    / "platform"
    / "roles"
    / "step_ca_runtime"
    / "tasks"
    / "main.yml"
)


def test_step_ca_runtime_defaults_anchor_service_topology_to_proxmox_hostvars() -> None:
    defaults = yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8"))

    assert defaults["step_ca_service_topology"] == "{{ hostvars['proxmox_florin'].platform_service_topology }}"
    assert defaults["step_ca_api_port"] == "{{ step_ca_service_topology | platform_service_port('step_ca', 'internal') }}"
    assert defaults["step_ca_internal_url"] == "{{ step_ca_service_topology | platform_service_url('step_ca', 'internal') }}"
    assert defaults["step_ca_controller_url"] == "{{ step_ca_service_topology | platform_service_url('step_ca', 'controller') }}"
    assert defaults["step_ca_default_network_name"] == "{{ step_ca_site_dir | basename }}_default"
    assert defaults["step_ca_server_names"][2] == "{{ step_ca_service_topology | platform_service_host('step_ca') }}"


def test_step_ca_runtime_recovers_detached_empty_default_network_before_compose_up() -> None:
    tasks = TASKS_PATH.read_text(encoding="utf-8")

    assert "Inspect the managed step-ca default network before compose up" in tasks
    assert "Remove the detached managed step-ca default network before compose up" in tasks
    assert "step_ca_default_network_inspect.stdout | from_json | first" in tasks
    assert ".Containers | default({})" in tasks
    assert '      - network\n      - rm' in tasks
