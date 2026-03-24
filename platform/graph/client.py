from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, load_yaml, repo_path
from platform.world_state._db import (
    ConnectionFactory,
    connection_kind,
    create_connection_factory,
    decode_json,
    managed_connection,
    placeholder,
    rows_to_dicts,
)
from platform.world_state.client import StaleDataError, SurfaceNotFoundError, WorldStateClient


LOGGER = logging.getLogger(__name__)
GRAPH_MANIFEST_PATH = repo_path("config", "dependency-graph.yaml")
LEGACY_GRAPH_PATH = repo_path("config", "dependency-graph.json")
SERVICE_CATALOG_PATH = repo_path("config", "service-capability-catalog.json")
WORKFLOW_CATALOG_PATH = repo_path("config", "workflow-catalog.json")
SUBDOMAIN_CATALOG_PATH = repo_path("config", "subdomain-catalog.json")
VALID_EDGE_KINDS = {"depends_on", "hosted_on", "resolved_by", "secured_by", "replicates_to"}


class GraphError(RuntimeError):
    pass


class NodeNotFoundError(GraphError):
    def __init__(self, node_id: str):
        super().__init__(f"Dependency-graph node '{node_id}' was not found")
        self.node_id = node_id


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    label: str
    tier: int | None = None
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "tier": self.tier,
            "metadata": self.metadata or {},
        }


@dataclass(frozen=True)
class GraphEdge:
    from_node: str
    to_node: str
    edge_kind: str
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "edge_kind": self.edge_kind,
            "metadata": self.metadata or {},
        }


def graph_dsn_from_env() -> str | None:
    for key in ("LV3_GRAPH_DSN", "WORLD_STATE_DSN", "LV3_LEDGER_DSN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def load_dependency_graph_manifest(path: Path = GRAPH_MANIFEST_PATH) -> dict[str, Any]:
    payload = load_yaml(path) if path.exists() else {}
    return payload if isinstance(payload, dict) else {}


def _legacy_service_metadata(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(repo_root / "config" / "dependency-graph.json", default={})
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in nodes:
        if not isinstance(item, dict):
            continue
        node_id = item.get("id")
        if isinstance(node_id, str) and node_id.strip():
            result[node_id] = item
    return result


def _legacy_service_edges(repo_root: Path) -> list[GraphEdge]:
    payload = load_json(repo_root / "config" / "dependency-graph.json", default={})
    edges = payload.get("edges", [])
    result: list[GraphEdge] = []
    if not isinstance(edges, list):
        return result
    for item in edges:
        if not isinstance(item, dict):
            continue
        source = item.get("from")
        target = item.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        result.append(
            GraphEdge(
                from_node=f"service:{source}",
                to_node=f"service:{target}",
                edge_kind="depends_on",
                metadata={
                    "source": "legacy_dependency_graph",
                    "legacy_type": item.get("type", "hard"),
                    "description": item.get("description", ""),
                },
            )
        )
    return result


def _service_node_id(service_id: str) -> str:
    return f"service:{service_id}"


def _host_node_id(host_id: str) -> str:
    return f"host:{host_id}"


def _ensure_node(nodes: dict[str, GraphNode], node: GraphNode) -> None:
    current = nodes.get(node.id)
    if current is None:
        nodes[node.id] = node
        return
    merged_metadata = dict(current.metadata or {})
    merged_metadata.update(node.metadata or {})
    tier = node.tier if node.tier is not None else current.tier
    label = node.label or current.label
    nodes[node.id] = GraphNode(id=node.id, kind=node.kind, label=label, tier=tier, metadata=merged_metadata)


def _ensure_edge(edges: dict[tuple[str, str, str], GraphEdge], edge: GraphEdge, *, replace: bool = False) -> None:
    if edge.edge_kind not in VALID_EDGE_KINDS:
        raise GraphError(f"unsupported edge kind '{edge.edge_kind}'")
    key = (edge.from_node, edge.to_node, edge.edge_kind)
    if replace or key not in edges:
        edges[key] = edge


def _infer_workflow_service_id(workflow_id: str, workflow: dict[str, Any], known_service_ids: set[str]) -> str | None:
    for field in ("service_id", "target_service", "service"):
        value = workflow.get(field)
        if isinstance(value, str) and value in known_service_ids:
            return value
    normalized = workflow_id.replace("-", "_")
    for service_id in sorted(known_service_ids, key=len, reverse=True):
        if service_id in normalized:
            return service_id
    return None


def build_graph_documents(
    repo_root: Path | None = None,
    *,
    world_state_client: WorldStateClient | None = None,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    base = repo_root or repo_path()
    services_payload = load_json(base / "config" / "service-capability-catalog.json", default={"services": []})
    services = services_payload.get("services", [])
    workflows_payload = load_json(base / "config" / "workflow-catalog.json", default={"workflows": {}})
    workflows = workflows_payload.get("workflows", {})
    manifest = load_dependency_graph_manifest(base / "config" / "dependency-graph.yaml")
    legacy_metadata = _legacy_service_metadata(base)

    nodes: dict[str, GraphNode] = {}
    edges: dict[tuple[str, str, str], GraphEdge] = {}
    host_ids: set[str] = set()

    _ensure_node(
        nodes,
        GraphNode(
            id="host:proxmox_florin",
            kind="host",
            label="proxmox_florin",
            metadata={"source": "derived_default", "host_role": "hypervisor"},
        ),
    )
    _ensure_node(
        nodes,
        GraphNode(
            id="cert:step-ca-internal",
            kind="cert",
            label="step-ca internal PKI",
            metadata={"source": "derived_default", "service_id": "step_ca"},
        ),
    )

    known_service_ids: set[str] = set()
    if isinstance(services, list):
        for service in services:
            if not isinstance(service, dict):
                continue
            service_id = service.get("id")
            if not isinstance(service_id, str) or not service_id.strip():
                continue
            known_service_ids.add(service_id)
            legacy_node = legacy_metadata.get(service_id, {})
            service_node = GraphNode(
                id=_service_node_id(service_id),
                kind="service",
                label=str(service.get("name") or service_id),
                tier=legacy_node.get("tier") if isinstance(legacy_node.get("tier"), int) else None,
                metadata={
                    "service_id": service_id,
                    "vm": service.get("vm"),
                    "vmid": service.get("vmid"),
                    "category": service.get("category"),
                    "adr": service.get("adr"),
                    "exposure": service.get("exposure"),
                    "health_probe_id": service.get("health_probe_id"),
                    "source": "service_catalog",
                },
            )
            _ensure_node(nodes, service_node)

            vm = service.get("vm")
            if isinstance(vm, str) and vm.strip():
                host_ids.add(vm)
                _ensure_node(
                    nodes,
                    GraphNode(
                        id=_host_node_id(vm),
                        kind="host",
                        label=vm,
                        metadata={"source": "service_catalog", "vmid": service.get("vmid")},
                    ),
                )
                _ensure_edge(
                    edges,
                    GraphEdge(
                        from_node=service_node.id,
                        to_node=_host_node_id(vm),
                        edge_kind="hosted_on",
                        metadata={"source": "service_catalog", "relationship": "runtime_host"},
                    ),
                )
                if vm != "proxmox_florin":
                    _ensure_edge(
                        edges,
                        GraphEdge(
                            from_node=_host_node_id(vm),
                            to_node="host:proxmox_florin",
                            edge_kind="hosted_on",
                            metadata={"source": "derived_default", "relationship": "proxmox_guest"},
                        ),
                    )

            if service_id != "step_ca":
                _ensure_edge(
                    edges,
                    GraphEdge(
                        from_node=service_node.id,
                        to_node="cert:step-ca-internal",
                        edge_kind="secured_by",
                        metadata={"source": "derived_default", "relationship": "internal_pki"},
                    ),
                )

    for edge in _legacy_service_edges(base):
        _ensure_edge(edges, edge)

    extra_nodes = manifest.get("extra_nodes", [])
    if isinstance(extra_nodes, list):
        for item in extra_nodes:
            if not isinstance(item, dict):
                continue
            node_id = item.get("id")
            kind = item.get("kind")
            label = item.get("label")
            if not all(isinstance(value, str) and value.strip() for value in (node_id, kind, label)):
                continue
            tier = item.get("tier")
            _ensure_node(
                nodes,
                GraphNode(
                    id=node_id,
                    kind=kind,
                    label=label,
                    tier=tier if isinstance(tier, int) else None,
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                ),
            )

    extra_edges = manifest.get("extra_edges", [])
    if isinstance(extra_edges, list):
        for item in extra_edges:
            if not isinstance(item, dict):
                continue
            from_node = item.get("from")
            to_node = item.get("to")
            edge_kind = item.get("edge_kind")
            if not all(isinstance(value, str) and value.strip() for value in (from_node, to_node, edge_kind)):
                continue
            _ensure_edge(
                edges,
                GraphEdge(
                    from_node=from_node,
                    to_node=to_node,
                    edge_kind=edge_kind,
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                ),
                replace=True,
            )

    if isinstance(workflows, dict):
        for workflow_id, workflow in workflows.items():
            if not isinstance(workflow, dict):
                continue
            depends_on = workflow.get("depends_on")
            if not isinstance(depends_on, list) or not depends_on:
                continue
            service_id = _infer_workflow_service_id(str(workflow_id), workflow, known_service_ids)
            if not service_id:
                continue
            for dependency in depends_on:
                if not isinstance(dependency, str) or not dependency.strip():
                    continue
                dependency_node = dependency if dependency.startswith(("service:", "host:", "cert:", "dns:", "network:")) else _service_node_id(dependency)
                if dependency_node not in nodes:
                    continue
                _ensure_edge(
                    edges,
                    GraphEdge(
                        from_node=_service_node_id(service_id),
                        to_node=dependency_node,
                        edge_kind="depends_on",
                        metadata={"source": "workflow_catalog", "workflow_id": workflow_id},
                    ),
                )

    if world_state_client is not None:
        try:
            netbox_topology = world_state_client.get("netbox_topology", allow_stale=True)
        except (SurfaceNotFoundError, StaleDataError):
            netbox_topology = None
        if isinstance(netbox_topology, dict):
            for device in netbox_topology.get("devices", []):
                if not isinstance(device, dict):
                    continue
                name = device.get("name")
                if isinstance(name, str) and name.strip():
                    _ensure_node(
                        nodes,
                        GraphNode(
                            id=_host_node_id(name),
                            kind="host",
                            label=name,
                            metadata={"source": "world_state.netbox_topology", "role": device.get("role")},
                        ),
                    )
            for vm in netbox_topology.get("virtual_machines", []):
                if not isinstance(vm, dict):
                    continue
                name = vm.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                _ensure_node(
                    nodes,
                    GraphNode(
                        id=_host_node_id(name),
                        kind="host",
                        label=name,
                        metadata={"source": "world_state.netbox_topology", "ansible_host": vm.get("ansible_host")},
                    ),
                )
                if name != "proxmox_florin":
                    _ensure_edge(
                        edges,
                        GraphEdge(
                            from_node=_host_node_id(name),
                            to_node="host:proxmox_florin",
                            edge_kind="hosted_on",
                            metadata={"source": "world_state.netbox_topology", "relationship": "proxmox_guest"},
                        ),
                        replace=True,
                    )
            for vlan in netbox_topology.get("vlans", []):
                if not isinstance(vlan, dict):
                    continue
                vid = vlan.get("vid")
                label = vlan.get("name") or vlan.get("prefix")
                if vid is None or not isinstance(label, str) or not label.strip():
                    continue
                network_id = f"network:vlan:{vid}"
                _ensure_node(
                    nodes,
                    GraphNode(
                        id=network_id,
                        kind="network",
                        label=label,
                        metadata={"source": "world_state.netbox_topology", "prefix": vlan.get("prefix")},
                    ),
                )
            if any(node.id == "network:vlan:10" for node in nodes.values()):
                for host_id in sorted(host_ids):
                    if host_id == "proxmox_florin":
                        continue
                    _ensure_edge(
                        edges,
                        GraphEdge(
                            from_node=_host_node_id(host_id),
                            to_node="network:vlan:10",
                            edge_kind="depends_on",
                            metadata={"source": "world_state.netbox_topology", "relationship": "guest_network"},
                        ),
                    )

        try:
            dns_records = world_state_client.get("dns_records", allow_stale=True)
        except (SurfaceNotFoundError, StaleDataError):
            dns_records = None
        if isinstance(dns_records, list):
            for record in dns_records:
                if not isinstance(record, dict):
                    continue
                fqdn = record.get("fqdn")
                service_id = record.get("service_id")
                if not isinstance(fqdn, str) or not fqdn.strip():
                    continue
                dns_id = f"dns:{fqdn}"
                _ensure_node(
                    nodes,
                    GraphNode(
                        id=dns_id,
                        kind="dns",
                        label=fqdn,
                        metadata={"source": "world_state.dns_records", "target": record.get("target")},
                    ),
                )
                if isinstance(service_id, str) and _service_node_id(service_id) in nodes:
                    _ensure_edge(
                        edges,
                        GraphEdge(
                            from_node=_service_node_id(service_id),
                            to_node=dns_id,
                            edge_kind="resolved_by",
                            metadata={"source": "world_state.dns_records", "target": record.get("target")},
                        ),
                    )

    return (
        sorted(nodes.values(), key=lambda item: item.id),
        sorted(edges.values(), key=lambda item: (item.from_node, item.to_node, item.edge_kind)),
    )


class DependencyGraphClient:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        nodes_table_name: str = "graph.nodes",
        edges_table_name: str = "graph.edges",
        world_state_client: WorldStateClient | None = None,
        world_state_dsn: str | None = None,
    ) -> None:
        resolved_dsn = dsn or graph_dsn_from_env()
        if connection_factory is None and not resolved_dsn:
            raise RuntimeError("LV3_GRAPH_DSN is not set")
        sqlite_graph = bool(resolved_dsn and resolved_dsn.startswith("sqlite:///"))
        self._connection_factory = connection_factory or create_connection_factory(resolved_dsn)
        self.nodes_table_name = "graph_nodes" if sqlite_graph and nodes_table_name == "graph.nodes" else nodes_table_name
        self.edges_table_name = "graph_edges" if sqlite_graph and edges_table_name == "graph.edges" else edges_table_name
        self.world_state_client = world_state_client
        if self.world_state_client is None and world_state_dsn:
            sqlite_world_state = world_state_dsn.startswith("sqlite:///")
            self.world_state_client = WorldStateClient(
                dsn=world_state_dsn,
                current_view_name="world_state_current_view" if sqlite_world_state else "world_state.current_view",
                snapshots_table_name="world_state_snapshots" if sqlite_world_state else "world_state.snapshots",
            )

    def list_nodes(self) -> list[dict[str, Any]]:
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT id, kind, label, tier, metadata FROM {self.nodes_table_name} ORDER BY id"
            )
            rows = rows_to_dicts(cursor)
        return [self._decode_node(row) for row in rows]

    def get_node(self, node_id: str) -> dict[str, Any]:
        row = self._fetch_one(
            lambda parameter: (
                f"SELECT id, kind, label, tier, metadata FROM {self.nodes_table_name} WHERE id = {parameter}"
            ),
            [node_id],
        )
        if row is None:
            raise NodeNotFoundError(node_id)
        return self._decode_node(row)

    def replace_graph(self, nodes: list[GraphNode], edges: list[GraphEdge]) -> dict[str, int]:
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM {self.edges_table_name}")
            cursor.execute(f"DELETE FROM {self.nodes_table_name}")
            kind = connection_kind(connection)
            node_parameter = placeholder(connection)
            edge_parameter = placeholder(connection)
            for node in nodes:
                if kind == "sqlite":
                    cursor.execute(
                        f"INSERT INTO {self.nodes_table_name} (id, kind, label, tier, metadata) VALUES ({node_parameter}, {node_parameter}, {node_parameter}, {node_parameter}, {node_parameter})",
                        [node.id, node.kind, node.label, node.tier, json.dumps(node.metadata or {})],
                    )
                else:
                    cursor.execute(
                        f"INSERT INTO {self.nodes_table_name} (id, kind, label, tier, metadata) VALUES ({node_parameter}, {node_parameter}, {node_parameter}, {node_parameter}, {node_parameter}::jsonb)",
                        [node.id, node.kind, node.label, node.tier, json.dumps(node.metadata or {})],
                    )
            for edge in edges:
                if kind == "sqlite":
                    cursor.execute(
                        f"INSERT INTO {self.edges_table_name} (from_node, to_node, edge_kind, metadata) VALUES ({edge_parameter}, {edge_parameter}, {edge_parameter}, {edge_parameter})",
                        [edge.from_node, edge.to_node, edge.edge_kind, json.dumps(edge.metadata or {})],
                    )
                else:
                    cursor.execute(
                        f"INSERT INTO {self.edges_table_name} (from_node, to_node, edge_kind, metadata) VALUES ({edge_parameter}, {edge_parameter}, {edge_parameter}, {edge_parameter}::jsonb)",
                        [edge.from_node, edge.to_node, edge.edge_kind, json.dumps(edge.metadata or {})],
                    )
            connection.commit()
        return {"node_count": len(nodes), "edge_count": len(edges)}

    def ancestors(self, node_id: str) -> list[str]:
        self.get_node(node_id)
        return self._walk(node_id, reverse=False)

    def descendants(self, node_id: str) -> list[str]:
        self.get_node(node_id)
        return self._walk(node_id, reverse=True)

    def neighbourhood(self, node_id: str, *, radius: int = 1) -> list[str]:
        self.get_node(node_id)
        if radius < 1:
            return []
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            sql, params = self._neighbourhood_sql(connection, node_id, radius)
            cursor.execute(sql, params)
            rows = rows_to_dicts(cursor)
        nodes = [str(row["node_id"]) for row in rows if str(row["node_id"]) != node_id]
        return sorted(set(nodes))

    def path(self, from_node: str, to_node: str) -> list[str]:
        self.get_node(from_node)
        self.get_node(to_node)
        if from_node == to_node:
            return [from_node]
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            sql, params = self._path_sql(connection, from_node, to_node)
            cursor.execute(sql, params)
            rows = rows_to_dicts(cursor)
        if not rows:
            return []
        row = rows[0]
        return self._decode_path(row["path"], kind=connection_kind(connection))

    def node_health(self, node_id: str, *, world_state_client: WorldStateClient | None = None) -> dict[str, Any]:
        node = self.get_node(node_id)
        health_client = world_state_client or self.world_state_client
        current_status = "unknown"
        derived_status = "unknown"
        upstream_issues: list[dict[str, Any]] = []
        if node["kind"] == "service":
            service_id = str(node["metadata"].get("service_id") or node_id.removeprefix("service:"))
            health_map = self._service_health_map(health_client)
            current_status = health_map.get(service_id, "unknown")
            derived_status = current_status
            for dependency_id in self.ancestors(node_id):
                if not dependency_id.startswith("service:"):
                    continue
                dependency_service_id = dependency_id.removeprefix("service:")
                dependency_status = health_map.get(dependency_service_id, "unknown")
                if dependency_status not in {"degraded", "down"}:
                    continue
                upstream_issues.append(
                    {
                        "dependency_node": dependency_id,
                        "dependency_status": dependency_status,
                        "path": self.path(node_id, dependency_id),
                    }
                )
            if upstream_issues and current_status in {"ok", "healthy"}:
                derived_status = "degraded"
        return {
            "node_id": node_id,
            "current_status": current_status,
            "derived_status": derived_status,
            "upstream_issues": upstream_issues,
        }

    def health_propagation(
        self,
        node_id: str,
        *,
        status: str,
        world_state_client: WorldStateClient | None = None,
    ) -> list[dict[str, Any]]:
        self.get_node(node_id)
        if status not in {"degraded", "down"}:
            return []
        health_client = world_state_client or self.world_state_client
        health_map = self._service_health_map(health_client)
        affected: list[dict[str, Any]] = []
        for dependent_id in self.descendants(node_id):
            if not dependent_id.startswith("service:"):
                continue
            service_id = dependent_id.removeprefix("service:")
            if health_map.get(service_id) not in {"ok", "healthy"}:
                continue
            affected.append(
                {
                    "node": dependent_id,
                    "service_id": service_id,
                    "derived_status": "degraded",
                    "path": self.path(dependent_id, node_id),
                    "cause_node": node_id,
                    "cause_status": status,
                }
            )
        return affected

    def _walk(self, node_id: str, *, reverse: bool) -> list[str]:
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            sql, params = self._walk_sql(connection, node_id, reverse=reverse)
            cursor.execute(sql, params)
            rows = rows_to_dicts(cursor)
        cycle_detected = any(bool(row.get("cycle")) for row in rows)
        if cycle_detected:
            LOGGER.warning("Dependency graph cycle detected while traversing from %s", node_id)
        seen: dict[str, int] = {}
        for row in rows:
            candidate = str(row["node_id"])
            if candidate == node_id or bool(row.get("cycle")):
                continue
            depth = int(row.get("depth", 0))
            previous_depth = seen.get(candidate)
            if previous_depth is None or depth < previous_depth:
                seen[candidate] = depth
        return [candidate for candidate, _depth in sorted(seen.items(), key=lambda item: (item[1], item[0]))]

    def _fetch_one(self, query_builder, params: list[Any]) -> dict[str, Any] | None:
        with managed_connection(self._connection_factory) as connection:
            cursor = connection.cursor()
            cursor.execute(query_builder(placeholder(connection)), params)
            rows = rows_to_dicts(cursor)
            return rows[0] if rows else None

    def _service_health_map(self, client: WorldStateClient | None) -> dict[str, str]:
        if client is None:
            return {}
        try:
            payload = client.get("service_health", allow_stale=True)
        except (SurfaceNotFoundError, StaleDataError):
            return {}
        services = payload.get("services", []) if isinstance(payload, dict) else []
        result: dict[str, str] = {}
        if not isinstance(services, list):
            return result
        for service in services:
            if not isinstance(service, dict):
                continue
            service_id = service.get("service_id")
            status = service.get("status")
            if isinstance(service_id, str) and isinstance(status, str):
                result[service_id] = status
        return result

    @staticmethod
    def _decode_node(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "kind": str(row["kind"]),
            "label": str(row["label"]),
            "tier": row.get("tier"),
            "metadata": decode_json(row.get("metadata") or "{}"),
        }

    @staticmethod
    def _decode_path(value: Any, *, kind: str) -> list[str]:
        if kind == "sqlite":
            if not isinstance(value, str):
                return []
            return [part for part in value.split("|") if part]
        if isinstance(value, str):
            return list(json.loads(value))
        if isinstance(value, list):
            return [str(part) for part in value]
        return []

    def _walk_sql(self, connection: Any, node_id: str, *, reverse: bool) -> tuple[str, list[Any]]:
        if connection_kind(connection) == "sqlite":
            next_column = "from_node" if reverse else "to_node"
            join_column = "to_node" if reverse else "from_node"
            parameter = placeholder(connection)
            return (
                f"""
                WITH RECURSIVE walk(node_id, path, depth, cycle) AS (
                    SELECT
                        e.{next_column} AS node_id,
                        '|' || {parameter} || '|' || e.{next_column} || '|' AS path,
                        1 AS depth,
                        0 AS cycle
                    FROM {self.edges_table_name} AS e
                    WHERE e.{join_column} = {parameter}
                    UNION ALL
                    SELECT
                        e.{next_column} AS node_id,
                        walk.path || e.{next_column} || '|',
                        walk.depth + 1,
                        CASE WHEN instr(walk.path, '|' || e.{next_column} || '|') > 0 THEN 1 ELSE 0 END
                    FROM {self.edges_table_name} AS e
                    JOIN walk ON e.{join_column} = walk.node_id
                    WHERE walk.cycle = 0
                )
                SELECT node_id, depth, cycle FROM walk
                """,
                [node_id, node_id],
            )
        next_column = "from_node" if reverse else "to_node"
        join_column = "to_node" if reverse else "from_node"
        parameter = placeholder(connection)
        return (
            f"""
            WITH RECURSIVE walk(node_id, path, depth, cycle) AS (
                SELECT
                    e.{next_column} AS node_id,
                    ARRAY[{parameter}::text, e.{next_column}] AS path,
                    1 AS depth,
                    FALSE AS cycle
                FROM {self.edges_table_name} AS e
                WHERE e.{join_column} = {parameter}
                UNION ALL
                SELECT
                    e.{next_column} AS node_id,
                    walk.path || e.{next_column},
                    walk.depth + 1,
                    e.{next_column} = ANY(walk.path) AS cycle
                FROM {self.edges_table_name} AS e
                JOIN walk ON e.{join_column} = walk.node_id
                WHERE walk.cycle = FALSE
            )
            SELECT node_id, depth, cycle FROM walk
            """,
            [node_id, node_id],
        )

    def _path_sql(self, connection: Any, from_node: str, to_node: str) -> tuple[str, list[Any]]:
        parameter = placeholder(connection)
        if connection_kind(connection) == "sqlite":
            return (
                f"""
                WITH RECURSIVE walk(node_id, path, depth, cycle) AS (
                    SELECT {parameter} AS node_id, '|' || {parameter} || '|' AS path, 0 AS depth, 0 AS cycle
                    UNION ALL
                    SELECT
                        e.to_node AS node_id,
                        walk.path || e.to_node || '|',
                        walk.depth + 1,
                        CASE WHEN instr(walk.path, '|' || e.to_node || '|') > 0 THEN 1 ELSE 0 END
                    FROM {self.edges_table_name} AS e
                    JOIN walk ON e.from_node = walk.node_id
                    WHERE walk.cycle = 0
                )
                SELECT path, depth FROM walk
                WHERE node_id = {parameter} AND cycle = 0
                ORDER BY depth ASC
                LIMIT 1
                """,
                [from_node, from_node, to_node],
            )
        return (
            f"""
            WITH RECURSIVE walk(node_id, path, depth, cycle) AS (
                SELECT {parameter}::text AS node_id, ARRAY[{parameter}::text] AS path, 0 AS depth, FALSE AS cycle
                UNION ALL
                SELECT
                    e.to_node AS node_id,
                    walk.path || e.to_node,
                    walk.depth + 1,
                    e.to_node = ANY(walk.path) AS cycle
                FROM {self.edges_table_name} AS e
                JOIN walk ON e.from_node = walk.node_id
                WHERE walk.cycle = FALSE
            )
            SELECT to_json(path) AS path, depth FROM walk
            WHERE node_id = {parameter} AND cycle = FALSE
            ORDER BY depth ASC
            LIMIT 1
            """,
            [from_node, from_node, to_node],
        )

    def _neighbourhood_sql(self, connection: Any, node_id: str, radius: int) -> tuple[str, list[Any]]:
        parameter = placeholder(connection)
        if connection_kind(connection) == "sqlite":
            return (
                f"""
                WITH RECURSIVE adjacency(left_node, right_node) AS (
                    SELECT from_node, to_node FROM {self.edges_table_name}
                    UNION ALL
                    SELECT to_node, from_node FROM {self.edges_table_name}
                ),
                walk(node_id, path, depth, cycle) AS (
                    SELECT {parameter} AS node_id, '|' || {parameter} || '|' AS path, 0 AS depth, 0 AS cycle
                    UNION ALL
                    SELECT
                        adjacency.right_node AS node_id,
                        walk.path || adjacency.right_node || '|',
                        walk.depth + 1,
                        CASE WHEN instr(walk.path, '|' || adjacency.right_node || '|') > 0 THEN 1 ELSE 0 END
                    FROM adjacency
                    JOIN walk ON adjacency.left_node = walk.node_id
                    WHERE walk.cycle = 0 AND walk.depth < {parameter}
                )
                SELECT DISTINCT node_id FROM walk WHERE depth > 0 AND cycle = 0
                """,
                [node_id, node_id, radius],
            )
        return (
            f"""
            WITH RECURSIVE adjacency(left_node, right_node) AS (
                SELECT from_node, to_node FROM {self.edges_table_name}
                UNION ALL
                SELECT to_node, from_node FROM {self.edges_table_name}
            ),
            walk(node_id, path, depth, cycle) AS (
                SELECT {parameter}::text AS node_id, ARRAY[{parameter}::text] AS path, 0 AS depth, FALSE AS cycle
                UNION ALL
                SELECT
                    adjacency.right_node AS node_id,
                    walk.path || adjacency.right_node,
                    walk.depth + 1,
                    adjacency.right_node = ANY(walk.path) AS cycle
                FROM adjacency
                JOIN walk ON adjacency.left_node = walk.node_id
                WHERE walk.cycle = FALSE AND walk.depth < {parameter}
            )
            SELECT DISTINCT node_id FROM walk WHERE depth > 0 AND cycle = FALSE
            """,
            [node_id, node_id, radius],
        )


def rebuild_graph_from_repo(
    *,
    repo_root: Path | None = None,
    dsn: str | None = None,
    connection_factory: ConnectionFactory | None = None,
    world_state_client: WorldStateClient | None = None,
    world_state_dsn: str | None = None,
    nodes_table_name: str = "graph.nodes",
    edges_table_name: str = "graph.edges",
) -> dict[str, Any]:
    client = DependencyGraphClient(
        dsn=dsn,
        connection_factory=connection_factory,
        nodes_table_name=nodes_table_name,
        edges_table_name=edges_table_name,
        world_state_client=world_state_client,
        world_state_dsn=world_state_dsn or dsn,
    )
    nodes, edges = build_graph_documents(repo_root, world_state_client=client.world_state_client)
    counts = client.replace_graph(nodes, edges)
    return {
        "status": "ok",
        "node_count": counts["node_count"],
        "edge_count": counts["edge_count"],
    }
