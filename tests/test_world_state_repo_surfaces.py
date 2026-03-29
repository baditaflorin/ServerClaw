from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windmill_defaults_seed_world_state_scripts_and_schedules() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )
    for package in ("make", "python3-psycopg"):
        assert package in defaults["windmill_runtime_packages"]
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedules = {entry["path"]: entry for entry in defaults["windmill_seed_schedules"]}
    schedule_paths = set(schedules)

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
    for schedule_path in expected_schedules:
        assert schedules[schedule_path]["enabled"] is True
        assert schedules[schedule_path]["args"] == {"dsn": "{{ windmill_platform_dsn }}"}


def test_world_state_migration_declares_unique_current_view_index() -> None:
    migration = (REPO_ROOT / "migrations/0010_world_state_schema.sql").read_text()

    assert "CREATE MATERIALIZED VIEW world_state.current_view" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_world_state_current_view_surface" in migration
    assert "openbao_secret_expiry" in migration


def test_windmill_runtime_templates_export_world_state_and_nats_env() -> None:
    env_template = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill-runtime.env.j2"
    ).read_text()
    env_ctmpl = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/templates/windmill-runtime.env.ctmpl.j2"
    ).read_text()

    for token in (
        "LV3_GRAPH_DSN",
        "WORLD_STATE_DSN",
        "LV3_NATS_URL",
        "LV3_NATS_USERNAME",
        "LV3_NATS_PASSWORD",
        "LV3_LEDGER_DSN",
        "LV3_LEDGER_NATS_URL",
        "TF_VAR_proxmox_endpoint",
        "TF_VAR_proxmox_api_token",
        "LV3_TEST_RUNNER_USERNAME",
        "LV3_TEST_RUNNER_PASSWORD",
        "LV3_INTEGRATION_ENVIRONMENT",
        "LV3_WINDMILL_BASE_URL",
    ):
        assert token in env_template
        assert token in env_ctmpl

    for token in (
        'index .Data.data "LV3_GRAPH_DSN"',
        'index .Data.data "WORLD_STATE_DSN"',
        'index .Data.data "LV3_NATS_URL"',
        'index .Data.data "LV3_NATS_USERNAME"',
        'index .Data.data "LV3_NATS_PASSWORD"',
        'index .Data.data "LV3_LEDGER_DSN"',
        'index .Data.data "LV3_LEDGER_NATS_URL"',
        'index .Data.data "LV3_TEST_RUNNER_USERNAME"',
        'index .Data.data "LV3_TEST_RUNNER_PASSWORD"',
        'index .Data.data "LV3_INTEGRATION_ENVIRONMENT"',
    ):
        assert token in env_ctmpl


def test_windmill_postgres_tasks_grant_world_state_schema_access() -> None:
    tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_postgres/tasks/main.yml"
    ).read_text()

    for statement in (
        "GRANT USAGE ON SCHEMA world_state TO {{ windmill_database_support_role }}",
        "GRANT ALL ON ALL TABLES IN SCHEMA world_state TO {{ windmill_database_support_role }}",
        "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA world_state TO {{ windmill_database_support_role }}",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA world_state GRANT ALL ON TABLES TO {{ windmill_database_support_role }}",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA world_state GRANT ALL ON SEQUENCES TO {{ windmill_database_support_role }}",
    ):
        assert statement in tasks


def test_windmill_postgres_support_role_enforces_bypassrls() -> None:
    tasks = (
        REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_postgres/tasks/main.yml"
    ).read_text()

    assert "CREATE ROLE {{ windmill_database_support_role }} BYPASSRLS" in tasks
    assert "ALTER ROLE {{ windmill_database_support_role }} BYPASSRLS" in tasks
