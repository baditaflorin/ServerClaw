#!/usr/bin/env python3
"""service_impact_tool.py — Blast-radius analysis from the platform dependency graph.

QUICKSTART FOR LLMs
-------------------
Before modifying or restarting a service or VM, run this to understand what
downstream services will be affected. Reads config/dependency-graph.json.

USAGE EXAMPLES
--------------
  # What breaks if postgres goes down?
  python3 scripts/service_impact_tool.py impact --service postgres

  # What breaks if the entire docker-runtime-lv3 VM goes down?
  python3 scripts/service_impact_tool.py vm-impact --vm docker-runtime-lv3

  # What does netbox depend on?
  python3 scripts/service_impact_tool.py depends-on --service netbox

  # Find the dependency path between two services
  python3 scripts/service_impact_tool.py path --from netbox --to postgres

  # Overview of the whole graph
  python3 scripts/service_impact_tool.py graph-summary
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = REPO_ROOT / "config" / "dependency-graph.json"


# ---------------------------------------------------------------------------
# Loader + index builders
# ---------------------------------------------------------------------------

def _load_graph() -> dict[str, Any]:
    if not GRAPH_PATH.exists():
        raise SystemExit(f"Dependency graph not found: {GRAPH_PATH}")
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def _build_indexes(graph: dict[str, Any]) -> tuple[
    dict[str, dict],   # id → node
    dict[str, list],   # id → outgoing edges (what it depends on)
    dict[str, list],   # id → incoming edges (what depends on it)
]:
    nodes: dict[str, dict] = {n["id"]: n for n in graph.get("nodes", [])}
    out_edges: dict[str, list] = {nid: [] for nid in nodes}
    in_edges: dict[str, list] = {nid: [] for nid in nodes}

    for edge in graph.get("edges", []):
        frm, to = edge.get("from", ""), edge.get("to", "")
        if frm in out_edges:
            out_edges[frm].append(edge)
        if to in in_edges:
            in_edges[to].append(edge)

    return nodes, out_edges, in_edges


def _resolve_id(nodes: dict[str, dict], query: str) -> str | None:
    """Resolve by node id, service field, name, or vm field."""
    if query in nodes:
        return query
    q = query.lower()
    for nid, node in nodes.items():
        if (node.get("service", "").lower() == q
                or node.get("name", "").lower() == q
                or node.get("vm", "").lower() == q):
            return nid
    return None


def _bfs_dependents(
    root: str,
    in_edges: dict[str, list],
    nodes: dict[str, dict],
) -> list[dict[str, Any]]:
    """Return all nodes that transitively depend on root (in_edges walk)."""
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(root, 0)])
    result: list[dict[str, Any]] = []
    while queue:
        nid, hops = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        if nid != root:
            n = nodes.get(nid, {})
            # collect the edge that brought us here
            edge_types = [e["type"] for e in in_edges.get(nid, []) if e.get("from") in visited]
            result.append({
                "id": nid,
                "name": n.get("name", nid),
                "vm": n.get("vm", ""),
                "tier": n.get("tier"),
                "hops": hops,
                "dependency_types": edge_types,
            })
        for edge in in_edges.get(nid, []):
            frm = edge.get("from", "")
            if frm and frm not in visited:
                queue.append((frm, hops + 1))
    return result


def _bfs_dependencies(
    root: str,
    out_edges: dict[str, list],
    nodes: dict[str, dict],
) -> list[dict[str, Any]]:
    """Return all nodes that root transitively depends on (out_edges walk)."""
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(root, 0)])
    result: list[dict[str, Any]] = []
    while queue:
        nid, hops = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        if nid != root:
            n = nodes.get(nid, {})
            result.append({
                "id": nid,
                "name": n.get("name", nid),
                "vm": n.get("vm", ""),
                "tier": n.get("tier"),
                "hops": hops,
            })
        for edge in out_edges.get(nid, []):
            to = edge.get("to", "")
            if to and to not in visited:
                queue.append((to, hops + 1))
    return result


def _risk_level(affected_nodes: list[dict], nodes: dict[str, dict]) -> str:
    tiers = [nodes.get(n["id"], {}).get("tier", 99) for n in affected_nodes]
    if 1 in tiers:
        return "critical"
    if len(affected_nodes) >= 5:
        return "high"
    if len(affected_nodes) >= 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# sub-command: impact
# ---------------------------------------------------------------------------

def cmd_impact(args: argparse.Namespace) -> int:
    graph = _load_graph()
    nodes, out_edges, in_edges = _build_indexes(graph)

    nid = _resolve_id(nodes, args.service)
    if not nid:
        raise SystemExit(f"Service '{args.service}' not found. Run graph-summary to list services.")

    dependents = _bfs_dependents(nid, in_edges, nodes)
    direct = [d for d in dependents if d["hops"] == 1]
    hard = [d for d in dependents if "hard" in d.get("dependency_types", [])]
    soft = [d for d in dependents if "soft" in d.get("dependency_types", [])]

    print(json.dumps({
        "target": nid,
        "name": nodes[nid].get("name"),
        "vm": nodes[nid].get("vm"),
        "tier": nodes[nid].get("tier"),
        "direct_dependents": direct,
        "transitive_dependents": dependents,
        "hard_dependents": hard,
        "soft_dependents": soft,
        "impact_summary": (
            f"{len(direct)} direct, {len(dependents)} transitive dependents"
            f" ({len(hard)} hard, {len(soft)} soft)"
        ),
        "risk_level": _risk_level(dependents, nodes),
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# sub-command: depends-on
# ---------------------------------------------------------------------------

def cmd_depends_on(args: argparse.Namespace) -> int:
    graph = _load_graph()
    nodes, out_edges, in_edges = _build_indexes(graph)

    nid = _resolve_id(nodes, args.service)
    if not nid:
        raise SystemExit(f"Service '{args.service}' not found.")

    deps = _bfs_dependencies(nid, out_edges, nodes)
    direct = [d for d in deps if d["hops"] == 1]

    print(json.dumps({
        "service": nid,
        "name": nodes[nid].get("name"),
        "direct_dependencies": direct,
        "transitive_dependencies": deps,
        "total_deps": len(deps),
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# sub-command: vm-impact
# ---------------------------------------------------------------------------

def cmd_vm_impact(args: argparse.Namespace) -> int:
    graph = _load_graph()
    nodes, out_edges, in_edges = _build_indexes(graph)

    vm_name = args.vm.lower()
    services_on_vm = [nid for nid, n in nodes.items() if n.get("vm", "").lower() == vm_name]
    if not services_on_vm:
        raise SystemExit(f"VM '{args.vm}' has no services in the dependency graph.")

    # union of all transitive dependents of all services on this VM
    all_affected: dict[str, dict] = {}
    for svc_id in services_on_vm:
        for dep in _bfs_dependents(svc_id, in_edges, nodes):
            if dep["id"] not in services_on_vm:
                all_affected[dep["id"]] = dep

    affected = sorted(all_affected.values(), key=lambda x: x.get("tier", 99))
    hard_count = sum(1 for d in affected if "hard" in d.get("dependency_types", []))

    print(json.dumps({
        "vm": args.vm,
        "services_on_vm": [{"id": s, "name": nodes[s].get("name")} for s in services_on_vm],
        "total_impact": {
            "direct_count": sum(1 for d in affected if d.get("hops") == 1),
            "transitive_count": len(affected),
            "hard_count": hard_count,
        },
        "affected_services": affected,
        "risk_level": _risk_level(affected, nodes),
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# sub-command: path
# ---------------------------------------------------------------------------

def cmd_path(args: argparse.Namespace) -> int:
    graph = _load_graph()
    nodes, out_edges, in_edges = _build_indexes(graph)

    src = _resolve_id(nodes, args.from_svc)
    dst = _resolve_id(nodes, args.to_svc)
    if not src:
        raise SystemExit(f"Source service '{args.from_svc}' not found.")
    if not dst:
        raise SystemExit(f"Destination service '{args.to_svc}' not found.")

    # BFS from src along out_edges
    visited: set[str] = set()
    queue: deque[list[str]] = deque([[src]])
    while queue:
        path = queue.popleft()
        cur = path[-1]
        if cur == dst:
            print(json.dumps({
                "from": src, "to": dst,
                "path": path,
                "hops": len(path) - 1,
                "found": True,
            }, indent=2))
            return 0
        if cur in visited:
            continue
        visited.add(cur)
        for edge in out_edges.get(cur, []):
            nxt = edge.get("to", "")
            if nxt and nxt not in visited:
                queue.append(path + [nxt])

    print(json.dumps({"from": src, "to": dst, "path": [], "hops": -1, "found": False}, indent=2))
    return 2


# ---------------------------------------------------------------------------
# sub-command: graph-summary
# ---------------------------------------------------------------------------

def cmd_graph_summary(args: argparse.Namespace) -> int:
    graph = _load_graph()
    nodes, out_edges, in_edges = _build_indexes(graph)

    by_tier: dict[int, int] = {}
    by_vm: dict[str, int] = {}
    for n in nodes.values():
        t = n.get("tier", 0)
        by_tier[t] = by_tier.get(t, 0) + 1
        vm = n.get("vm", "unknown")
        by_vm[vm] = by_vm.get(vm, 0) + 1

    # most depended-on = most incoming edges (transitive)
    dependent_counts = {
        nid: len(_bfs_dependents(nid, in_edges, nodes)) for nid in nodes
    }
    dep_counts = {
        nid: len(_bfs_dependencies(nid, out_edges, nodes)) for nid in nodes
    }

    top_depended = sorted(dependent_counts.items(), key=lambda x: -x[1])[:5]
    top_deps = sorted(dep_counts.items(), key=lambda x: -x[1])[:5]

    print(json.dumps({
        "total_nodes": len(nodes),
        "total_edges": len(graph.get("edges", [])),
        "by_tier": {str(k): v for k, v in sorted(by_tier.items())},
        "by_vm": dict(sorted(by_vm.items(), key=lambda x: -x[1])),
        "most_depended_on": [
            {"service": nid, "name": nodes[nid].get("name"), "dependent_count": cnt}
            for nid, cnt in top_depended
        ],
        "most_dependencies": [
            {"service": nid, "name": nodes[nid].get("name"), "dependency_count": cnt}
            for nid, cnt in top_deps
        ],
    }, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Parser + main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="service_impact_tool.py",
        description="Blast-radius analysis from the platform dependency graph.",
    )
    subs = p.add_subparsers(dest="command", required=True)

    p_impact = subs.add_parser("impact", help="What breaks if this service goes down?")
    p_impact.add_argument("--service", required=True, help="Service id, name, or vm name.")

    p_dep = subs.add_parser("depends-on", help="What does this service depend on?")
    p_dep.add_argument("--service", required=True)

    p_vm = subs.add_parser("vm-impact", help="Impact of an entire VM going down.")
    p_vm.add_argument("--vm", required=True, help="VM name (e.g. docker-runtime-lv3).")

    p_path = subs.add_parser("path", help="Find dependency path between two services.")
    p_path.add_argument("--from", dest="from_svc", required=True)
    p_path.add_argument("--to", dest="to_svc", required=True)

    subs.add_parser("graph-summary", help="Overview stats of the dependency graph.")

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "impact":
            return cmd_impact(args)
        if args.command == "depends-on":
            return cmd_depends_on(args)
        if args.command == "vm-impact":
            return cmd_vm_impact(args)
        if args.command == "path":
            return cmd_path(args)
        if args.command == "graph-summary":
            return cmd_graph_summary(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
