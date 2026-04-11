from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_health_schema_migration_declares_composite_table() -> None:
    migration = (REPO_ROOT / "migrations" / "0013_health_schema.sql").read_text()

    assert "CREATE SCHEMA IF NOT EXISTS health;" in migration
    assert "CREATE TABLE IF NOT EXISTS health.composite" in migration
    assert "health_composite_status_idx" in migration
    assert "health_composite_safe_idx" in migration


def test_windmill_defaults_seed_health_refresh_script_and_schedule() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
        ).read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_paths = {entry["path"] for entry in defaults["windmill_seed_schedules"]}

    assert "f/lv3/health/refresh_composite" in script_paths
    assert "f/lv3/health/refresh_composite_every_minute" in schedule_paths


def test_windmill_defaults_seed_scheduler_watchdog_script_and_schedule() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
        ).read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule = next(
        entry
        for entry in defaults["windmill_seed_schedules"]
        if entry["path"] == "f/lv3/scheduler_watchdog_loop_every_10s"
    )

    assert "f/lv3/scheduler_watchdog_loop" in script_paths
    assert schedule["schedule"] == "*/10 * * * * *"
    assert schedule["enabled"] is True
