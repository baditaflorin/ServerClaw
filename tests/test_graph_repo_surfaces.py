from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windmill_defaults_seed_graph_scripts_and_schedules() -> None:
    defaults = yaml.safe_load(
        (
            REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml"
        ).read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedules = {entry["path"]: entry for entry in defaults["windmill_seed_schedules"]}
    schedule_paths = set(schedules)

    assert {
        "f/lv3/graph/import_from_catalog",
        "f/lv3/graph/import_from_netbox",
        "f/lv3/graph/propagate_health",
    }.issubset(script_paths)
    assert {
        "f/lv3/graph/import_from_catalog_every_5m",
        "f/lv3/graph/import_from_netbox_every_5m",
    }.issubset(schedule_paths)
    assert schedules["f/lv3/graph/import_from_catalog_every_5m"]["enabled"] is True
    assert schedules["f/lv3/graph/import_from_catalog_every_5m"]["args"] == {
        "dsn": "{{ windmill_platform_dsn }}",
        "world_state_dsn": "{{ windmill_platform_dsn }}",
    }
    assert schedules["f/lv3/graph/import_from_netbox_every_5m"]["enabled"] is True
    assert schedules["f/lv3/graph/import_from_netbox_every_5m"]["args"] == {
        "dsn": "{{ windmill_platform_dsn }}",
        "world_state_dsn": "{{ windmill_platform_dsn }}",
    }


def test_graph_migration_declares_schema_and_unique_edges() -> None:
    migration = (REPO_ROOT / "migrations/0012_graph_schema.sql").read_text()
    windmill_runtime_tasks = (
        REPO_ROOT
        / "collections"
        / "ansible_collections"
        / "lv3"
        / "platform"
        / "roles"
        / "windmill_runtime"
        / "tasks"
        / "main.yml"
    ).read_text()

    assert "CREATE SCHEMA IF NOT EXISTS graph" in migration
    assert "CREATE TABLE IF NOT EXISTS graph.nodes" in migration
    assert "CREATE TABLE IF NOT EXISTS graph.edges" in migration
    assert "CONSTRAINT graph_edges_unique UNIQUE (from_node, to_node, edge_kind)" in migration
    assert "REFRESH MATERIALIZED VIEW world_state.current_view" in windmill_runtime_tasks
    assert "SELECT ispopulated::text FROM pg_matviews" in windmill_runtime_tasks
    assert "ALTER SCHEMA graph OWNER TO {{ windmill_database_user }}" in windmill_runtime_tasks
    assert "GRANT USAGE ON SCHEMA graph TO {{ windmill_database_user }}" in windmill_runtime_tasks


def test_workstream_registry_tracks_adr_0117() -> None:
    registry = (REPO_ROOT / "workstreams.yaml").read_text()

    assert "id: adr-0117-dependency-graph-runtime" in registry
    assert "branch: codex/ws-0117-live-apply" in registry
    assert "live_applied: true" in registry


def test_graph_windmill_wrappers_bootstrap_repo_platform_and_runtime_dependencies() -> None:
    import_catalog = (REPO_ROOT / "config" / "windmill" / "scripts" / "graph" / "import-from-catalog.py").read_text()
    import_netbox = (REPO_ROOT / "config" / "windmill" / "scripts" / "graph" / "import-from-netbox.py").read_text()
    propagate_health = (REPO_ROOT / "config" / "windmill" / "scripts" / "graph" / "propagate-health.py").read_text()
    api_gateway_requirements = (REPO_ROOT / "requirements" / "api-gateway.txt").read_text()

    for script_source in (import_catalog, import_netbox, propagate_health):
        assert 'if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__")' in script_source
        assert 'del sys.modules["platform"]' in script_source
        assert 'repo_root / "scripts"' in script_source
        assert '"uv"' in script_source
        assert '"run"' in script_source
        assert '"--isolated"' in script_source
        assert '"--no-project"' in script_source
        assert '"psycopg[binary]"' in script_source
        assert '"psycopg is required for postgres"' in script_source
        assert '"Missing dependency: PyYAML"' in script_source

    assert '"nats-py"' in propagate_health
    assert "psycopg[binary]==" in api_gateway_requirements
