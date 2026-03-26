from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windmill_defaults_seed_ephemeral_vm_reaper_script_and_schedule() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_map = {entry["path"]: entry for entry in defaults["windmill_seed_schedules"]}

    assert "f/lv3/ephemeral_vm_reaper" in script_paths
    assert "f/lv3/ephemeral_vm_reaper_every_30m" in schedule_map
    assert schedule_map["f/lv3/ephemeral_vm_reaper_every_30m"]["enabled"] is True
    assert schedule_map["f/lv3/ephemeral_vm_reaper_every_30m"]["script_path"] == "f/lv3/ephemeral_vm_reaper"


def test_windmill_runtime_retries_nat_chain_recheck_before_startup() -> None:
    tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml"
    ).read_text(encoding="utf-8")

    assert "Recheck Docker nat chain before Windmill startup" in tasks
    assert "failed_when: windmill_docker_nat_chain_recheck.rc not in [0, 1]" in tasks
    assert "retries: 5" in tasks
    assert "delay: 2" in tasks
    assert "until: windmill_docker_nat_chain_recheck.rc == 0" in tasks


def test_windmill_runtime_exports_proxmox_api_credentials_for_ephemeral_reaper() -> None:
    tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml"
    ).read_text(encoding="utf-8")
    env_template = (
        REPO_ROOT
        / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill-runtime.env.j2"
    ).read_text(encoding="utf-8")
    ctmpl_template = (
        REPO_ROOT
        / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill-runtime.env.ctmpl.j2"
    ).read_text(encoding="utf-8")

    assert "Ensure the Proxmox API token payload exists on the control machine" in tasks
    assert "proxmox_api_token_local_file" in tasks
    assert "windmill_proxmox_api_token_payload" in tasks
    assert "windmill_worker_proxmox_api_token_payload_dir" in tasks
    assert "windmill_worker_proxmox_api_token_payload_file" in tasks
    assert "Mirror the Proxmox API token payload into the Windmill worker checkout" in tasks
    assert "TF_VAR_proxmox_endpoint" in tasks
    assert "TF_VAR_proxmox_api_token" in tasks
    assert "TF_VAR_proxmox_endpoint={{ windmill_proxmox_api_token_payload.api_url }}" in env_template
    assert "TF_VAR_proxmox_api_token={{ windmill_proxmox_api_token_payload.full_token_id }}={{ windmill_proxmox_api_token_payload.value }}" in env_template
    assert '[[ .Data.data.TF_VAR_proxmox_endpoint ]]' in ctmpl_template
    assert '[[ .Data.data.TF_VAR_proxmox_api_token ]]' in ctmpl_template
