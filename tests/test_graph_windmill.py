from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prepare_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {
                "services": [
                    {
                        "id": "windmill",
                        "name": "Windmill",
                        "category": "automation",
                        "lifecycle_status": "active",
                        "vm": "docker-runtime-lv3",
                        "vmid": 120,
                        "adr": "0044",
                    },
                    {
                        "id": "postgres",
                        "name": "Postgres",
                        "category": "data",
                        "lifecycle_status": "active",
                        "vm": "postgres-lv3",
                        "vmid": 150,
                        "adr": "0026",
                    },
                ]
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps({"workflows": {"deploy-and-promote": {"description": "deploy"}}}, indent=2) + "\n",
    )
    write(
        tmp_path / "config" / "dependency-graph.json",
        json.dumps(
            {
                "schema_version": "1.0.0",
                "nodes": [
                    {"id": "windmill", "tier": 2},
                    {"id": "postgres", "tier": 1},
                ],
                "edges": [{"from": "windmill", "to": "postgres", "type": "hard", "description": "stores state"}],
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "dependency-graph.yaml",
        """
schema_version: 1.0.0
extra_nodes: []
extra_edges: []
""".strip()
        + "\n",
    )
    return tmp_path


def prepare_graph_db(path: Path) -> str:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE graph_nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, tier INTEGER, metadata TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE graph_edges (id INTEGER PRIMARY KEY AUTOINCREMENT, from_node TEXT NOT NULL, to_node TEXT NOT NULL, edge_kind TEXT NOT NULL, metadata TEXT NOT NULL)"
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"


def prepare_world_state_db(path: Path) -> str:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE world_state_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, surface TEXT NOT NULL, collected_at TEXT NOT NULL, data TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0)"
    )
    connection.execute(
        "CREATE TABLE world_state_current_view (surface TEXT PRIMARY KEY, data TEXT NOT NULL, collected_at TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0, is_expired INTEGER NOT NULL DEFAULT 0)"
    )
    connection.executemany(
        "INSERT INTO world_state_current_view (surface, data, collected_at, stale, is_expired) VALUES (?, ?, ?, ?, ?)",
        [
            (
                "service_health",
                '{"services":[{"service_id":"postgres","status":"degraded"},{"service_id":"windmill","status":"ok"}]}',
                "2026-03-24T10:00:00+00:00",
                0,
                0,
            ),
            (
                "netbox_topology",
                '{"devices":[{"name":"proxmox_florin","role":"proxmox-host"}],"virtual_machines":[{"name":"docker-runtime-lv3","ansible_host":"10.10.10.20"}],"vlans":[{"name":"guest-network","vid":10,"prefix":"10.10.10.0/24"}]}',
                "2026-03-24T10:00:00+00:00",
                0,
                0,
            ),
            (
                "dns_records",
                '[{"fqdn":"windmill.lv3.org","service_id":"windmill","target":"10.10.10.20"}]',
                "2026-03-24T10:00:00+00:00",
                0,
                0,
            ),
        ],
    )
    connection.commit()
    connection.close()
    return f"sqlite:///{path}"


def test_graph_import_wrappers_rebuild_graph(tmp_path: Path) -> None:
    repo_root = prepare_repo(tmp_path)
    graph_dsn = prepare_graph_db(tmp_path / "graph.sqlite3")
    world_state_dsn = prepare_world_state_db(tmp_path / "world-state.sqlite3")

    module = load_module("graph_import_catalog", "config/windmill/scripts/graph/import-from-catalog.py")
    result = module.main(repo_path=str(repo_root), dsn=graph_dsn, world_state_dsn=world_state_dsn)

    assert result["status"] == "ok"
    assert result["node_count"] >= 4
    assert result["edge_count"] >= 3


def test_graph_netbox_wrapper_rebuilds_with_world_state(tmp_path: Path) -> None:
    repo_root = prepare_repo(tmp_path)
    graph_dsn = prepare_graph_db(tmp_path / "graph-netbox.sqlite3")
    world_state_dsn = prepare_world_state_db(tmp_path / "world-state-netbox.sqlite3")

    module = load_module("graph_import_netbox", "config/windmill/scripts/graph/import-from-netbox.py")
    result = module.main(repo_path=str(repo_root), dsn=graph_dsn, world_state_dsn=world_state_dsn)

    assert result["status"] == "ok"
    assert result["source"] == "netbox_topology"


def test_graph_propagation_wrapper_emits_derived_events(tmp_path: Path) -> None:
    repo_root = prepare_repo(tmp_path)
    graph_dsn = prepare_graph_db(tmp_path / "graph-propagate.sqlite3")
    world_state_dsn = prepare_world_state_db(tmp_path / "world-state-propagate.sqlite3")

    import_wrapper = load_module("graph_import_for_propagation", "config/windmill/scripts/graph/import-from-catalog.py")
    import_wrapper.main(repo_path=str(repo_root), dsn=graph_dsn, world_state_dsn=world_state_dsn)

    module = load_module("graph_propagate_health", "config/windmill/scripts/graph/propagate-health.py")
    result = module.main(
        event_payload={"surface": "service_health", "collected_at": "2026-03-24T10:00:00Z"},
        repo_path=str(repo_root),
        dsn=graph_dsn,
        world_state_dsn=world_state_dsn,
        publish_nats=False,
    )

    assert result["status"] == "ok"
    assert result["derived_event_count"] >= 1
    assert result["derived_events"][0]["derived_status"] == "degraded"
