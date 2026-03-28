#!/usr/bin/env python3

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Final

from controller_automation_toolkit import load_json, repo_path


DEPENDENCY_GRAPH_PATH: Final[Path] = repo_path("config", "dependency-graph.json")
DEPENDENCY_GRAPH_SCHEMA_PATH: Final[Path] = repo_path(
    "docs", "schema", "service-dependency-graph.schema.json"
)
SERVICE_CATALOG_PATH: Final[Path] = repo_path("config", "service-capability-catalog.json")
ALLOWED_EDGE_TYPES: Final[set[str]] = {"hard", "soft", "startup_only", "reads_from"}
EDGE_TYPE_LABELS: Final[dict[str, str]] = {
    "hard": "Hard dependencies",
    "soft": "Soft dependencies",
    "startup_only": "Startup-only dependencies",
    "reads_from": "Read dependencies",
}


class DependencyGraphError(ValueError):
    pass


@dataclass(frozen=True)
class DependencyNode:
    id: str
    service: str
    name: str
    vm: str
    tier: int
    category: str | None = None
    adr: str | None = None


@dataclass(frozen=True)
class DependencyEdge:
    source: str
    target: str
    edge_type: str
    description: str


@dataclass(frozen=True)
class ImpactReport:
    service_id: str
    direct_hard: tuple[str, ...]
    transitive_hard: tuple[str, ...]
    direct_soft: tuple[str, ...]
    direct_startup_only: tuple[str, ...]
    direct_reads_from: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service_id,
            "direct_hard": list(self.direct_hard),
            "transitive_hard": list(self.transitive_hard),
            "direct_soft": list(self.direct_soft),
            "direct_startup_only": list(self.direct_startup_only),
            "direct_reads_from": list(self.direct_reads_from),
            "affected": sorted(
                set(self.direct_hard)
                | set(self.transitive_hard)
                | set(self.direct_soft)
                | set(self.direct_startup_only)
                | set(self.direct_reads_from)
            ),
        }


@dataclass(frozen=True)
class DependencyGraph:
    nodes: dict[str, DependencyNode]
    edges: tuple[DependencyEdge, ...]
    schema_version: str

    def dependencies_for(self, service_id: str, edge_type: str | None = None) -> list[DependencyEdge]:
        self.require_service(service_id)
        return [
            edge
            for edge in self.edges
            if edge.source == service_id and (edge_type is None or edge.edge_type == edge_type)
        ]

    def dependents_for(self, service_id: str, edge_type: str | None = None) -> list[DependencyEdge]:
        self.require_service(service_id)
        return [
            edge
            for edge in self.edges
            if edge.target == service_id and (edge_type is None or edge.edge_type == edge_type)
        ]

    def require_service(self, service_id: str) -> None:
        if service_id not in self.nodes:
            raise DependencyGraphError(f"unknown service '{service_id}'")


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DependencyGraphError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise DependencyGraphError(f"{path} must be a list")
    return value


def _require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DependencyGraphError(f"{path} must be a non-empty string")
    return value


def _require_int(value: Any, path: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DependencyGraphError(f"{path} must be an integer")
    if value < minimum:
        raise DependencyGraphError(f"{path} must be >= {minimum}")
    return value


def load_service_catalog_ids(path: Path = SERVICE_CATALOG_PATH) -> set[str]:
    payload = load_json(path)
    services = _require_list(payload.get("services"), "service-capability-catalog.services")
    return {
        _require_str(service.get("id"), f"service-capability-catalog.services[{index}].id")
        for index, service in enumerate(services)
        for service in [_require_mapping(service, f"service-capability-catalog.services[{index}]")]
    }


def load_dependency_graph_payload(path: Path = DEPENDENCY_GRAPH_PATH) -> dict[str, Any]:
    payload = load_json(path)
    return _require_mapping(payload, str(path))


def load_dependency_graph(
    path: Path = DEPENDENCY_GRAPH_PATH,
    *,
    service_catalog_path: Path = SERVICE_CATALOG_PATH,
    validate_schema: bool = False,
) -> DependencyGraph:
    payload = load_dependency_graph_payload(path)
    return parse_dependency_graph(
        payload,
        service_catalog_ids=load_service_catalog_ids(service_catalog_path),
        validate_schema=validate_schema,
    )


def parse_dependency_graph(
    payload: dict[str, Any],
    *,
    service_catalog_ids: set[str] | None = None,
    validate_schema: bool = False,
    schema_path: Path = DEPENDENCY_GRAPH_SCHEMA_PATH,
) -> DependencyGraph:
    if validate_schema:
        try:
            import jsonschema
        except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
            raise RuntimeError(
                "Missing dependency: jsonschema. Run via 'uv run --with jsonschema python ...'."
            ) from exc
        jsonschema.validate(instance=payload, schema=load_json(schema_path))

    schema_version = _require_str(payload.get("schema_version"), "dependency-graph.schema_version")
    raw_nodes = _require_list(payload.get("nodes"), "dependency-graph.nodes")
    raw_edges = _require_list(payload.get("edges"), "dependency-graph.edges")

    nodes: dict[str, DependencyNode] = {}
    for index, raw_node in enumerate(raw_nodes):
        raw_node = _require_mapping(raw_node, f"dependency-graph.nodes[{index}]")
        node_id = _require_str(raw_node.get("id"), f"dependency-graph.nodes[{index}].id")
        if node_id in nodes:
            raise DependencyGraphError(f"duplicate dependency graph node '{node_id}'")
        node = DependencyNode(
            id=node_id,
            service=_require_str(raw_node.get("service"), f"dependency-graph.nodes[{index}].service"),
            name=_require_str(raw_node.get("name"), f"dependency-graph.nodes[{index}].name"),
            vm=_require_str(raw_node.get("vm"), f"dependency-graph.nodes[{index}].vm"),
            tier=_require_int(raw_node.get("tier"), f"dependency-graph.nodes[{index}].tier"),
            category=raw_node.get("category"),
            adr=raw_node.get("adr"),
        )
        if node.service != node.id:
            raise DependencyGraphError(
                f"dependency-graph.nodes[{index}].service must match id for '{node.id}'"
            )
        nodes[node.id] = node

    edges: list[DependencyEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for index, raw_edge in enumerate(raw_edges):
        raw_edge = _require_mapping(raw_edge, f"dependency-graph.edges[{index}]")
        source = _require_str(raw_edge.get("from"), f"dependency-graph.edges[{index}].from")
        target = _require_str(raw_edge.get("to"), f"dependency-graph.edges[{index}].to")
        if source not in nodes:
            raise DependencyGraphError(
                f"dependency-graph.edges[{index}].from references unknown service '{source}'"
            )
        if target not in nodes:
            raise DependencyGraphError(
                f"dependency-graph.edges[{index}].to references unknown service '{target}'"
            )
        if source == target:
            raise DependencyGraphError(
                f"dependency-graph.edges[{index}] must not create a self dependency for '{source}'"
            )
        edge_type = _require_str(raw_edge.get("type"), f"dependency-graph.edges[{index}].type")
        if edge_type not in ALLOWED_EDGE_TYPES:
            raise DependencyGraphError(
                f"dependency-graph.edges[{index}].type must be one of {sorted(ALLOWED_EDGE_TYPES)}"
            )
        signature = (source, target, edge_type)
        if signature in seen_edges:
            raise DependencyGraphError(
                f"duplicate dependency edge '{source}' -> '{target}' ({edge_type})"
            )
        seen_edges.add(signature)
        edges.append(
            DependencyEdge(
                source=source,
                target=target,
                edge_type=edge_type,
                description=_require_str(
                    raw_edge.get("description"),
                    f"dependency-graph.edges[{index}].description",
                ),
            )
        )

    graph = DependencyGraph(nodes=nodes, edges=tuple(edges), schema_version=schema_version)
    validate_graph_integrity(graph, service_catalog_ids=service_catalog_ids)
    return graph


def validate_graph_integrity(
    graph: DependencyGraph,
    *,
    service_catalog_ids: set[str] | None = None,
) -> None:
    if service_catalog_ids is not None:
        missing = sorted(service_catalog_ids - set(graph.nodes))
        extra = sorted(set(graph.nodes) - service_catalog_ids)
        if missing:
            raise DependencyGraphError(
                "dependency graph is missing nodes for catalog services: " + ", ".join(missing)
            )
        if extra:
            raise DependencyGraphError(
                "dependency graph contains unknown services not present in the catalog: "
                + ", ".join(extra)
            )

    detect_hard_dependency_cycles(graph)
    expected_tiers = compute_recovery_tiers(graph)
    mismatched_tiers = [
        f"{service_id}={graph.nodes[service_id].tier} (expected {expected_tiers[service_id]})"
        for service_id in sorted(graph.nodes)
        if graph.nodes[service_id].tier != expected_tiers[service_id]
    ]
    if mismatched_tiers:
        raise DependencyGraphError(
            "dependency graph node tiers must match hard-dependency ordering: "
            + ", ".join(mismatched_tiers)
        )


def detect_hard_dependency_cycles(graph: DependencyGraph) -> None:
    adjacency = {
        service_id: [edge.target for edge in graph.dependencies_for(service_id, "hard")]
        for service_id in graph.nodes
    }
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(service_id: str) -> None:
        if service_id in visited:
            return
        if service_id in visiting:
            cycle_start = stack.index(service_id)
            cycle = stack[cycle_start:] + [service_id]
            raise DependencyGraphError(
                "hard dependency cycle detected: " + " -> ".join(cycle)
            )
        visiting.add(service_id)
        stack.append(service_id)
        for dependency in adjacency[service_id]:
            visit(dependency)
        stack.pop()
        visiting.remove(service_id)
        visited.add(service_id)

    for service_id in sorted(graph.nodes):
        visit(service_id)


def compute_recovery_tiers(graph: DependencyGraph) -> dict[str, int]:
    cache: dict[str, int] = {}

    def tier_for(service_id: str) -> int:
        if service_id in cache:
            return cache[service_id]
        hard_dependencies = [edge.target for edge in graph.dependencies_for(service_id, "hard")]
        if not hard_dependencies:
            cache[service_id] = 1
            return 1
        cache[service_id] = 1 + max(tier_for(dependency) for dependency in hard_dependencies)
        return cache[service_id]

    return {service_id: tier_for(service_id) for service_id in sorted(graph.nodes)}


def deployment_order(service_ids: list[str], graph: DependencyGraph) -> list[str]:
    if not service_ids:
        return []
    selected = []
    seen: set[str] = set()
    for service_id in service_ids:
        graph.require_service(service_id)
        if service_id not in seen:
            seen.add(service_id)
            selected.append(service_id)

    indegree = {service_id: 0 for service_id in selected}
    adjacency: dict[str, list[str]] = {service_id: [] for service_id in selected}
    selected_set = set(selected)
    for service_id in selected:
        for edge in graph.dependencies_for(service_id, "hard"):
            if edge.target not in selected_set:
                continue
            adjacency[edge.target].append(service_id)
            indegree[service_id] += 1

    queue = deque(sorted(service_id for service_id, count in indegree.items() if count == 0))
    ordered: list[str] = []
    while queue:
        service_id = queue.popleft()
        ordered.append(service_id)
        for dependent in sorted(adjacency[service_id]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)

    if len(ordered) != len(selected):
        remaining = sorted(service_id for service_id, count in indegree.items() if count > 0)
        raise DependencyGraphError(
            "cannot determine deployment order because the selected services contain a cycle: "
            + ", ".join(remaining)
        )
    return ordered


def compute_impact(service_id: str, graph: DependencyGraph) -> ImpactReport:
    graph.require_service(service_id)
    direct: dict[str, set[str]] = defaultdict(set)
    reverse_by_target: dict[str, list[DependencyEdge]] = defaultdict(list)
    for edge in graph.edges:
        reverse_by_target[edge.target].append(edge)
        if edge.target == service_id:
            direct[edge.edge_type].add(edge.source)

    direct_hard = sorted(direct["hard"])
    transitive_hard: list[str] = []
    seen = set([service_id, *direct_hard])
    queue = deque(direct_hard)
    while queue:
        failed_dependency = queue.popleft()
        for edge in reverse_by_target.get(failed_dependency, []):
            if edge.edge_type != "hard" or edge.source in seen:
                continue
            seen.add(edge.source)
            transitive_hard.append(edge.source)
            queue.append(edge.source)

    return ImpactReport(
        service_id=service_id,
        direct_hard=tuple(sorted(direct_hard)),
        transitive_hard=tuple(sorted(transitive_hard)),
        direct_soft=tuple(sorted(direct["soft"])),
        direct_startup_only=tuple(sorted(direct["startup_only"])),
        direct_reads_from=tuple(sorted(direct["reads_from"])),
    )


def dependency_summary(service_id: str, graph: DependencyGraph) -> dict[str, Any]:
    graph.require_service(service_id)
    dependencies = {
        edge_type: sorted(edge.target for edge in graph.dependencies_for(service_id, edge_type))
        for edge_type in ALLOWED_EDGE_TYPES
    }
    dependents = {
        edge_type: sorted(edge.source for edge in graph.dependents_for(service_id, edge_type))
        for edge_type in ALLOWED_EDGE_TYPES
    }
    impact = compute_impact(service_id, graph)
    return {
        "service": service_id,
        "name": graph.nodes[service_id].name,
        "tier": graph.nodes[service_id].tier,
        "depends_on": dependencies,
        "required_by": dependents,
        "impact": impact.to_dict(),
    }


def render_mermaid(graph: DependencyGraph) -> str:
    lines = ["graph TD"]
    for node in sorted(graph.nodes.values(), key=lambda item: (item.tier, item.name.lower())):
        safe_name = node.name.replace('"', '\\"')
        lines.append(f'    {node.id}["{safe_name}\\nTier {node.tier}"]')
    for edge in sorted(graph.edges, key=lambda item: (item.source, item.target, item.edge_type)):
        lines.append(f"    {edge.source} -->|{edge.edge_type}| {edge.target}")
    return "\n".join(lines)


def render_dependency_markdown(graph: DependencyGraph) -> str:
    tier_rows: dict[int, list[str]] = defaultdict(list)
    for node in graph.nodes.values():
        tier_rows[node.tier].append(node.name)

    table_lines = [
        "| Tier | Services |",
        "| --- | --- |",
    ]
    for tier in sorted(tier_rows):
        table_lines.append(
            f"| `{tier}` | {', '.join(sorted(tier_rows[tier]))} |"
        )

    return "\n".join(
        [
            "# Service Dependency Graph",
            "",
            "Generated from `config/dependency-graph.json`.",
            "",
            "## Recovery Tiers",
            "",
            *table_lines,
            "",
            "## Mermaid Diagram",
            "",
            "```mermaid",
            render_mermaid(graph),
            "```",
        ]
    ).strip() + "\n"


def render_dependency_page(graph: DependencyGraph) -> str:
    return "\n".join(
        [
            "---",
            "sensitivity: INTERNAL",
            "portal_display: full",
            "tags:",
            "  - architecture",
            "  - dependency-graph",
            "---",
            "",
            '!!! note "Sensitivity: INTERNAL"',
            "    This page is intended for authenticated operators and internal collaborators.",
            "",
            render_dependency_markdown(graph).lstrip(),
        ]
    ).strip() + "\n"


def graph_to_dict(graph: DependencyGraph) -> dict[str, Any]:
    return {
        "schema_version": graph.schema_version,
        "nodes": [
            {
                "id": node.id,
                "service": node.service,
                "name": node.name,
                "vm": node.vm,
                "tier": node.tier,
                **({"category": node.category} if node.category else {}),
                **({"adr": node.adr} if node.adr else {}),
            }
            for node in sorted(graph.nodes.values(), key=lambda item: item.id)
        ],
        "edges": [
            {
                "from": edge.source,
                "to": edge.target,
                "type": edge.edge_type,
                "description": edge.description,
            }
            for edge in sorted(graph.edges, key=lambda item: (item.source, item.target, item.edge_type))
        ],
    }


def pretty_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"
