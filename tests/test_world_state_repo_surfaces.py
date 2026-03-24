from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windmill_defaults_seed_world_state_scripts_and_schedules() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_paths = {entry["path"] for entry in defaults["windmill_seed_schedules"]}

    expected_scripts = {
        "f/lv3/world_state/refresh_proxmox_vms",
        "f/lv3/world_state/refresh_service_health",
        "f/lv3/world_state/refresh_container_inventory",
        "f/lv3/world_state/refresh_netbox_topology",
        "f/lv3/world_state/refresh_dns_records",
        "f/lv3/world_state/refresh_tls_certs",
        "f/lv3/world_state/refresh_opentofu_drift",
        "f/lv3/world_state/refresh_openbao_secret_expiry",
        "f/lv3/world_state/refresh_maintenance_windows",
    }
    expected_schedules = {
        "f/lv3/world_state/refresh_proxmox_vms_every_minute",
        "f/lv3/world_state/refresh_service_health_every_30s",
        "f/lv3/world_state/refresh_container_inventory_every_minute",
        "f/lv3/world_state/refresh_netbox_topology_every_5m",
        "f/lv3/world_state/refresh_dns_records_every_5m",
        "f/lv3/world_state/refresh_tls_certs_hourly",
        "f/lv3/world_state/refresh_opentofu_drift_every_15m",
        "f/lv3/world_state/refresh_openbao_secret_expiry_every_5m",
        "f/lv3/world_state/refresh_maintenance_windows_every_minute",
    }

    assert expected_scripts.issubset(script_paths)
    assert expected_schedules.issubset(schedule_paths)


def test_world_state_migration_declares_unique_current_view_index() -> None:
    migration = (REPO_ROOT / "migrations/0010_world_state_schema.sql").read_text()

    assert "CREATE MATERIALIZED VIEW world_state.current_view" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_world_state_current_view_surface" in migration
    assert "openbao_secret_expiry" in migration
