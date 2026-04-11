from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

from platform.graph import DependencyGraphClient
from platform.world_state.client import WorldStateClient


REPO_ROOT = Path(__file__).resolve().parents[2]


def prepare_graph_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE graph_nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            tier INTEGER,
            metadata TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_node TEXT NOT NULL,
            to_node TEXT NOT NULL,
            edge_kind TEXT NOT NULL,
            metadata TEXT NOT NULL
        )
        """
    )
    connection.executemany(
        "INSERT INTO graph_nodes (id, kind, label, tier, metadata) VALUES (?, ?, ?, ?, ?)",
        [
            ("service:postgres", "service", "Postgres", 1, '{"service_id":"postgres"}'),
            ("service:keycloak", "service", "Keycloak", 2, '{"service_id":"keycloak"}'),
            ("service:windmill", "service", "Windmill", 2, '{"service_id":"windmill"}'),
            ("service:api_gateway", "service", "Platform API Gateway", 3, '{"service_id":"api_gateway"}'),
            ("service:ops_portal", "service", "Ops Portal", 4, '{"service_id":"ops_portal"}'),
            ("host:docker-runtime-lv3", "host", "docker-runtime-lv3", None, "{}"),
        ],
    )
    connection.executemany(
        "INSERT INTO graph_edges (from_node, to_node, edge_kind, metadata) VALUES (?, ?, ?, ?)",
        [
            ("service:keycloak", "service:postgres", "depends_on", '{"source":"test"}'),
            ("service:windmill", "service:postgres", "depends_on", '{"source":"test"}'),
            ("service:api_gateway", "service:keycloak", "depends_on", '{"source":"test"}'),
            ("service:ops_portal", "service:api_gateway", "depends_on", '{"source":"test"}'),
            ("service:keycloak", "host:docker-runtime-lv3", "hosted_on", '{"source":"test"}'),
        ],
    )
    connection.commit()
    connection.close()
    return path


def prepare_world_state_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE world_state_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surface TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            data TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE world_state_current_view (
            surface TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            stale INTEGER NOT NULL DEFAULT 0,
            is_expired INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        "INSERT INTO world_state_current_view (surface, data, collected_at, stale, is_expired) VALUES (?, ?, ?, ?, ?)",
        (
            "service_health",
            '{"services":[{"service_id":"postgres","status":"degraded"},{"service_id":"keycloak","status":"ok"},{"service_id":"windmill","status":"ok"},{"service_id":"api_gateway","status":"ok"},{"service_id":"ops_portal","status":"ok"}]}',
            "2026-03-24T10:00:00+00:00",
            0,
            0,
        ),
    )
    connection.commit()
    connection.close()
    return path


@pytest.fixture()
def graph_client(tmp_path: Path) -> DependencyGraphClient:
    graph_path = prepare_graph_db(tmp_path / "graph.sqlite3")
    world_state_path = prepare_world_state_db(tmp_path / "world-state.sqlite3")
    world_state_client = WorldStateClient(
        dsn=f"sqlite:///{world_state_path}",
        current_view_name="world_state_current_view",
        snapshots_table_name="world_state_snapshots",
    )
    return DependencyGraphClient(
        dsn=f"sqlite:///{graph_path}",
        nodes_table_name="graph_nodes",
        edges_table_name="graph_edges",
        world_state_client=world_state_client,
    )


def test_descendants_and_ancestors_follow_dependency_direction(graph_client: DependencyGraphClient) -> None:
    assert graph_client.descendants("service:postgres") == [
        "service:keycloak",
        "service:windmill",
        "service:api_gateway",
        "service:ops_portal",
    ]
    assert graph_client.ancestors("service:ops_portal") == [
        "service:api_gateway",
        "service:keycloak",
        "host:docker-runtime-lv3",
        "service:postgres",
    ]


def test_path_and_neighbourhood_queries(graph_client: DependencyGraphClient) -> None:
    assert graph_client.path("service:ops_portal", "service:postgres") == [
        "service:ops_portal",
        "service:api_gateway",
        "service:keycloak",
        "service:postgres",
    ]
    assert set(graph_client.neighbourhood("service:keycloak", radius=2)) >= {
        "service:postgres",
        "service:api_gateway",
        "service:ops_portal",
        "host:docker-runtime-lv3",
    }


def test_health_propagation_marks_healthy_dependents_degraded(graph_client: DependencyGraphClient) -> None:
    affected = graph_client.health_propagation("service:postgres", status="down")
    assert [item["node"] for item in affected] == [
        "service:keycloak",
        "service:windmill",
        "service:api_gateway",
        "service:ops_portal",
    ]
    assert all(item["derived_status"] == "degraded" for item in affected)


def test_node_health_uses_upstream_graph_and_world_state(graph_client: DependencyGraphClient) -> None:
    payload = graph_client.node_health("service:keycloak")
    assert payload["current_status"] == "ok"
    assert payload["derived_status"] == "degraded"
    assert payload["upstream_issues"][0]["dependency_node"] == "service:postgres"


def test_cycle_detection_logs_and_returns_partial_result(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    graph_path = tmp_path / "graph-cycle.sqlite3"
    connection = sqlite3.connect(graph_path)
    connection.execute(
        "CREATE TABLE graph_nodes (id TEXT PRIMARY KEY, kind TEXT, label TEXT, tier INTEGER, metadata TEXT)"
    )
    connection.execute(
        "CREATE TABLE graph_edges (id INTEGER PRIMARY KEY AUTOINCREMENT, from_node TEXT, to_node TEXT, edge_kind TEXT, metadata TEXT)"
    )
    connection.executemany(
        "INSERT INTO graph_nodes (id, kind, label, tier, metadata) VALUES (?, ?, ?, ?, ?)",
        [
            ("service:a", "service", "A", 1, "{}"),
            ("service:b", "service", "B", 1, "{}"),
        ],
    )
    connection.executemany(
        "INSERT INTO graph_edges (from_node, to_node, edge_kind, metadata) VALUES (?, ?, ?, ?)",
        [
            ("service:a", "service:b", "depends_on", "{}"),
            ("service:b", "service:a", "depends_on", "{}"),
        ],
    )
    connection.commit()
    connection.close()
    client = DependencyGraphClient(
        dsn=f"sqlite:///{graph_path}",
        nodes_table_name="graph_nodes",
        edges_table_name="graph_edges",
    )
    caplog.set_level("WARNING")

    assert client.ancestors("service:a") == ["service:b"]
    assert "cycle detected" in caplog.text.lower()


def test_empty_and_single_node_graphs_are_safe(tmp_path: Path) -> None:
    empty_path = tmp_path / "graph-empty.sqlite3"
    connection = sqlite3.connect(empty_path)
    connection.execute(
        "CREATE TABLE graph_nodes (id TEXT PRIMARY KEY, kind TEXT, label TEXT, tier INTEGER, metadata TEXT)"
    )
    connection.execute(
        "CREATE TABLE graph_edges (id INTEGER PRIMARY KEY AUTOINCREMENT, from_node TEXT, to_node TEXT, edge_kind TEXT, metadata TEXT)"
    )
    connection.execute(
        "INSERT INTO graph_nodes (id, kind, label, tier, metadata) VALUES (?, ?, ?, ?, ?)",
        ("service:solo", "service", "Solo", 1, "{}"),
    )
    connection.commit()
    connection.close()
    client = DependencyGraphClient(
        dsn=f"sqlite:///{empty_path}",
        nodes_table_name="graph_nodes",
        edges_table_name="graph_edges",
    )

    assert client.descendants("service:solo") == []
    assert client.ancestors("service:solo") == []
    assert client.path("service:solo", "service:solo") == ["service:solo"]


def test_platform_package_preserves_stdlib_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    sys.modules.pop("platform", None)
    imported = importlib.import_module("platform")

    assert callable(imported.system)
    assert isinstance(imported.python_version(), str)
    imported_graph = importlib.import_module("platform.graph")
    assert hasattr(imported_graph, "DependencyGraphClient")
