from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windmill_defaults_seed_graph_scripts_and_schedules() -> None:
    defaults = yaml.safe_load(
        (REPO_ROOT / "collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml").read_text()
    )
    script_paths = {entry["path"] for entry in defaults["windmill_seed_scripts"]}
    schedule_paths = {entry["path"] for entry in defaults["windmill_seed_schedules"]}

    assert {
        "f/lv3/graph/import_from_catalog",
        "f/lv3/graph/import_from_netbox",
        "f/lv3/graph/propagate_health",
    }.issubset(script_paths)
    assert {
        "f/lv3/graph/import_from_catalog_every_5m",
        "f/lv3/graph/import_from_netbox_every_5m",
    }.issubset(schedule_paths)


def test_graph_migration_declares_schema_and_unique_edges() -> None:
    migration = (REPO_ROOT / "migrations/0012_graph_schema.sql").read_text()

    assert "CREATE SCHEMA IF NOT EXISTS graph" in migration
    assert "CREATE TABLE IF NOT EXISTS graph.nodes" in migration
    assert "CREATE TABLE IF NOT EXISTS graph.edges" in migration
    assert "CONSTRAINT graph_edges_unique UNIQUE (from_node, to_node, edge_kind)" in migration


def test_workstream_registry_tracks_adr_0117() -> None:
    registry = (REPO_ROOT / "workstreams.yaml").read_text()

    assert "id: adr-0117-dependency-graph-runtime" in registry
    assert "branch: codex/adr-0117-dependency-graph" in registry
