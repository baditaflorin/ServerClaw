from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_tasks(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_windmill_defaults_seed_ephemeral_vm_reaper_script_and_schedule() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
        ).read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_map = {entry["path"]: entry for entry in defaults["windmill_seed_schedules"]}

    assert "f/lv3/ephemeral_vm_reaper" in script_paths
    assert "f/lv3/ephemeral_pool_reconciler" in script_paths
    assert "f/lv3/ephemeral_vm_reaper_every_30m" in schedule_map
    assert "f/lv3/ephemeral_pool_reconciler_every_15m" in schedule_map
    assert schedule_map["f/lv3/ephemeral_vm_reaper_every_30m"]["enabled"] is True
    assert schedule_map["f/lv3/ephemeral_vm_reaper_every_30m"]["script_path"] == "f/lv3/ephemeral_vm_reaper"
    assert schedule_map["f/lv3/ephemeral_pool_reconciler_every_15m"]["enabled"] is True
    assert schedule_map["f/lv3/ephemeral_pool_reconciler_every_15m"]["script_path"] == "f/lv3/ephemeral_pool_reconciler"


def test_windmill_runtime_recovers_missing_docker_bridge_chains_before_startup() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
        ).read_text()
    )
    tasks = load_tasks(REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml")
    compose_template = (
        REPO_ROOT
        / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/docker-compose.yml.j2"
    ).read_text(encoding="utf-8")
    windmill_extra_section = compose_template.split("windmill_extra:", 1)[1].split("\nvolumes:", 1)[0]

    nat_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker nat chain exists before Windmill startup"
    )
    forward_check = next(
        task
        for task in tasks
        if task.get("name") == "Check whether the Docker forward chain exists before Windmill startup"
    )
    restart = next(
        task
        for task in tasks
        if task.get("name") == "Restart Docker when the nat or forward chain is missing before Windmill startup"
    )
    nat_recheck = next(
        task for task in tasks if task.get("name") == "Recheck the Docker nat chain before Windmill startup"
    )
    forward_recheck = next(
        task for task in tasks if task.get("name") == "Recheck the Docker forward chain before Windmill startup"
    )
    assert_task = next(
        task for task in tasks if task.get("name") == "Assert Docker bridge chains are present before Windmill startup"
    )
    startup = next(task for task in tasks if task.get("name") == "Start Windmill and wait for the API socket")
    rescue_restart = next(
        task
        for task in startup["rescue"]
        if task.get("name") == "Restart Docker to restore bridge chains before retrying Windmill startup"
    )
    retry_task = next(
        task
        for task in startup["rescue"]
        if task.get("name")
        == "Recreate the full Windmill stack after stale-network cleanup or Docker bridge-chain recovery"
    )

    assert defaults["windmill_server_network_mode"] == "host"
    assert defaults["windmill_server_requires_docker_nat"] == "{{ windmill_server_network_mode != 'host' }}"
    assert defaults["windmill_worker_network_mode"] == "{{ windmill_server_network_mode }}"
    assert defaults["windmill_requires_docker_bridge_chains"] is True
    assert "127.0.0.1" in defaults["windmill_worker_api_base_url"]
    assert "network_mode: {{ windmill_server_network_mode }}" in compose_template
    assert "network_mode: {{ windmill_worker_network_mode }}" in compose_template
    assert "windmill_extra:" in compose_template
    assert "network_mode:" not in windmill_extra_section
    assert "WINDMILL_BASE_URL: {{ windmill_private_base_url }}" in compose_template
    assert nat_check["ansible.builtin.command"]["argv"] == ["iptables", "-t", "nat", "-S", "DOCKER"]
    assert forward_check["ansible.builtin.command"]["argv"] == ["iptables", "-S", "DOCKER-FORWARD"]
    assert nat_check["when"] == "windmill_requires_docker_bridge_chains | bool"
    assert forward_check["when"] == "windmill_requires_docker_bridge_chains | bool"
    assert restart["when"] == (
        "windmill_requires_docker_bridge_chains | bool and (windmill_docker_nat_chain_check.rc == 1 or "
        "windmill_docker_forward_chain_check.rc == 1)"
    )
    assert nat_recheck["retries"] == 6
    assert forward_recheck["retries"] == 6
    assert nat_recheck["when"] == "windmill_requires_docker_bridge_chains | bool"
    assert forward_recheck["when"] == "windmill_requires_docker_bridge_chains | bool"
    assert assert_task["when"] == "windmill_requires_docker_bridge_chains | bool"
    assert assert_task["ansible.builtin.assert"]["that"] == [
        "windmill_docker_nat_chain_recheck.rc == 0",
        "windmill_docker_forward_chain_recheck.rc == 0",
    ]
    rescue_fact = next(
        task
        for task in startup["rescue"]
        if task.get("name") == "Detect stale Windmill compose-network startup failures"
    )
    assert (
        "No chain/target/match by that name"
        in rescue_fact["ansible.builtin.set_fact"]["windmill_docker_bridge_chain_missing"]
    )
    assert (
        "Unable to enable ACCEPT OUTGOING rule"
        in rescue_fact["ansible.builtin.set_fact"]["windmill_docker_bridge_chain_missing"]
    )
    assert rescue_restart["when"] == (
        "windmill_requires_docker_bridge_chains | bool and (windmill_missing_network_failure | bool or "
        "windmill_docker_bridge_chain_missing | bool)"
    )
    assert (
        retry_task["when"] == "windmill_missing_network_failure | bool or windmill_docker_bridge_chain_missing | bool"
    )


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
    assert (
        "TF_VAR_proxmox_api_token={{ windmill_proxmox_api_token_payload.full_token_id }}={{ windmill_proxmox_api_token_payload.value }}"
        in env_template
    )
    assert "[[ .Data.data.TF_VAR_proxmox_endpoint ]]" in ctmpl_template
    assert "[[ .Data.data.TF_VAR_proxmox_api_token ]]" in ctmpl_template


def test_windmill_runtime_keeps_ephemeral_runtime_paths_writable_after_checkout_sync() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
        ).read_text()
    )
    tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml"
    ).read_text(encoding="utf-8")

    writable_paths = {
        entry["path"]: entry["mode"] for entry in defaults["windmill_worker_runtime_writable_directories"]
    }

    assert writable_paths["{{ windmill_worker_repo_checkout_host_path }}/receipts/fixtures"] == "1777"
    assert writable_paths["{{ windmill_worker_repo_checkout_host_path }}/.local"] == "0755"
    assert writable_paths["{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures"] == "1777"
    assert writable_paths["{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/reaper-runs"] == "1777"
    assert writable_paths["{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/runtime"] == "1777"
    assert writable_paths["{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/archive"] == "1777"
    assert writable_paths["{{ windmill_worker_repo_checkout_host_path }}/.local/fixtures/locks"] == "1777"
    assert "Ensure repo-backed Windmill runtime paths stay writable after checkout sync" in tasks
    assert "windmill_worker_runtime_writable_directories" in tasks
