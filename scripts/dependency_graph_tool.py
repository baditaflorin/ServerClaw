#!/usr/bin/env python3
"""dependency_graph_tool.py — Navigate the platform service dependency graph.

Data source: config/dependency-graph.json

Commands
--------
  nodes   [--type TYPE]              List all graph nodes (services, VMs, etc.)
  edges   [--type TYPE]              List all edges with relationship types
  depends-on  --node ID              What does this node directly depend on?
  depended-by --node ID              What nodes directly depend on this node?
  blast-radius --node ID [--depth N] Full downstream impact up to N hops (default 5)
  path   --from ID --to ID           Find if a dependency path exists between two nodes
  summary                            Graph statistics

Examples
--------
  python scripts/dependency_graph_tool.py nodes
  python scripts/dependency_graph_tool.py nodes --type service
  python scripts/dependency_graph_tool.py depends-on --node gitea
  python scripts/dependency_graph_tool.py depended-by --node postgres
  python scripts/dependency_graph_tool.py blast-radius --node postgres
  python scripts/dependency_graph_tool.py path --from gitea --to keycloak
  python scripts/dependency_graph_tool.py summary
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPH_FILE = REPO_ROOT / "config" / "dependency-graph.json"


def _load() -> dict:
    if not GRAPH_FILE.exists():
        print(f"ERROR: {GRAPH_FILE} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(GRAPH_FILE.read_text())


def _build_adj(edges: list[dict], direction: str = "forward") -> dict[str, list[dict]]:
    """Build adjacency list. direction: 'forward' = source→target, 'reverse' = target→source."""
    adj: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        if direction == "forward":
            adj[e["source"]].append(e)
        else:
            adj[e["target"]].append(e)
    return adj


def _find_node(nodes: list[dict], node_id: str) -> dict | None:
    match = next((n for n in nodes if n["id"] == node_id), None)
    if match is None:
        id_lower = node_id.lower()
        match = next((n for n in nodes if id_lower in n["id"].lower()), None)
    return match


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_nodes(args: argparse.Namespace) -> int:
    data = _load()
    nodes = data.get("nodes", [])
    type_filter = (args.type or "").lower()
    results = [n for n in nodes if not type_filter or type_filter in n.get("type", "").lower()]
    print(f"{'ID':<35}  {'TYPE':<20}  {'VM':<25}  TIER")
    print("-" * 100)
    for n in sorted(results, key=lambda x: x["id"]):
        print(f"{n['id']:<35}  {n.get('type', ''):<20}  {n.get('vm', ''):<25}  {n.get('tier', '')}")
    print(f"\n{len(results)} node(s)")
    return 0


def cmd_edges(args: argparse.Namespace) -> int:
    data = _load()
    edges = data.get("edges", [])
    type_filter = (args.type or "").lower()
    results = [e for e in edges if not type_filter or type_filter in e.get("type", "").lower()]
    print(f"{'SOURCE':<30}  {'TARGET':<30}  TYPE")
    print("-" * 80)
    for e in sorted(results, key=lambda x: (x["source"], x["target"])):
        print(f"{e['source']:<30}  {e['target']:<30}  {e.get('type', '')}")
    print(f"\n{len(results)} edge(s)")
    return 0


def cmd_depends_on(args: argparse.Namespace) -> int:
    data = _load()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node = _find_node(nodes, args.node)
    if node is None:
        print(f"ERROR: node '{args.node}' not found")
        return 1
    nid = node["id"]
    deps = [e for e in edges if e["source"] == nid]
    if not deps:
        print(f"'{nid}' has no outgoing dependencies")
        return 0
    print(f"Direct dependencies of '{nid}':\n")
    print(f"  {'TARGET':<35}  {'TYPE':<20}  NOTES")
    print("  " + "-" * 75)
    for e in sorted(deps, key=lambda x: x["target"]):
        print(f"  {e['target']:<35}  {e.get('type', ''):<20}  {e.get('notes', '')}")
    return 0


def cmd_depended_by(args: argparse.Namespace) -> int:
    data = _load()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node = _find_node(nodes, args.node)
    if node is None:
        print(f"ERROR: node '{args.node}' not found")
        return 1
    nid = node["id"]
    dependents = [e for e in edges if e["target"] == nid]
    if not dependents:
        print(f"No nodes depend on '{nid}'")
        return 0
    print(f"Nodes that depend on '{nid}':\n")
    print(f"  {'SOURCE':<35}  {'TYPE':<20}  NOTES")
    print("  " + "-" * 75)
    for e in sorted(dependents, key=lambda x: x["source"]):
        print(f"  {e['source']:<35}  {e.get('type', ''):<20}  {e.get('notes', '')}")
    return 0


def cmd_blast_radius(args: argparse.Namespace) -> int:
    data = _load()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node = _find_node(nodes, args.node)
    if node is None:
        print(f"ERROR: node '{args.node}' not found")
        return 1
    nid = node["id"]
    max_depth = args.depth

    # BFS: find all nodes that depend on nid (reverse edges)
    rev_adj = _build_adj(edges, direction="reverse")

    visited: dict[str, int] = {}  # node_id -> depth first seen
    queue: deque[tuple[str, int]] = deque([(nid, 0)])
    while queue:
        current, depth = queue.popleft()
        if current in visited or depth > max_depth:
            continue
        visited[current] = depth
        for e in rev_adj.get(current, []):
            src = e["source"]
            if src not in visited:
                queue.append((src, depth + 1))

    # Remove the origin node itself
    impacted = {k: v for k, v in visited.items() if k != nid}
    node_by_id = {n["id"]: n for n in nodes}

    if not impacted:
        print(f"No downstream dependents found for '{nid}'")
        return 0

    print(f"Blast radius of '{nid}' (max depth={max_depth}):\n")
    print(f"  {'NODE':<35}  {'DEPTH':>5}  {'TYPE':<20}  TIER")
    print("  " + "-" * 80)
    for nid2, depth in sorted(impacted.items(), key=lambda x: (x[1], x[0])):
        n2 = node_by_id.get(nid2, {})
        print(f"  {nid2:<35}  {depth:>5}  {n2.get('type', ''):<20}  {n2.get('tier', '')}")
    print(f"\n{len(impacted)} node(s) in blast radius")

    # Risk assessment
    tier1 = [n for n in impacted if node_by_id.get(n, {}).get("tier") == "1"]
    if tier1:
        print(f"RISK: CRITICAL — tier-1 services affected: {', '.join(tier1)}")
    elif len(impacted) >= 5:
        print("RISK: HIGH — 5+ services affected")
    elif len(impacted) >= 2:
        print("RISK: MEDIUM")
    else:
        print("RISK: LOW")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    data = _load()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    src_node = _find_node(nodes, args.from_node)
    dst_node = _find_node(nodes, args.to_node)

    if src_node is None:
        print(f"ERROR: source node '{args.from_node}' not found")
        return 1
    if dst_node is None:
        print(f"ERROR: target node '{args.to_node}' not found")
        return 1

    src_id = src_node["id"]
    dst_id = dst_node["id"]

    adj = _build_adj(edges, direction="forward")

    # BFS to find shortest path
    queue: deque[list[str]] = deque([[src_id]])
    visited: set[str] = {src_id}
    while queue:
        path = queue.popleft()
        current = path[-1]
        if current == dst_id:
            print(f"Dependency path from '{src_id}' to '{dst_id}':\n")
            for i, step in enumerate(path):
                indent = "  " + "  " * i
                print(f"{indent}→ {step}")
            return 0
        for e in adj.get(current, []):
            nxt = e["target"]
            if nxt not in visited:
                visited.add(nxt)
                queue.append(path + [nxt])

    print(f"No dependency path found from '{src_id}' to '{dst_id}'")
    return 1


def cmd_summary(args: argparse.Namespace) -> int:
    data = _load()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    types: dict[str, int] = defaultdict(int)
    tiers: dict[str, int] = defaultdict(int)
    edge_types: dict[str, int] = defaultdict(int)
    for n in nodes:
        types[n.get("type", "unknown")] += 1
        tiers[str(n.get("tier", "?"))] += 1
    for e in edges:
        edge_types[e.get("type", "unknown")] += 1

    print("Dependency Graph Summary\n")
    print(f"  Nodes: {len(nodes)}")
    for t, cnt in sorted(types.items(), key=lambda x: -x[1]):
        print(f"    {t:<25}  {cnt}")
    print("\n  By tier:")
    for t, cnt in sorted(tiers.items()):
        print(f"    tier {t:<20}  {cnt}")
    print(f"\n  Edges: {len(edges)}")
    for t, cnt in sorted(edge_types.items(), key=lambda x: -x[1]):
        print(f"    {t:<25}  {cnt}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dependency_graph_tool.py",
        description="Navigate the platform service dependency graph.",
    )
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    np = sub.add_parser("nodes", help="List graph nodes")
    np.add_argument("--type", metavar="TYPE", help="Filter by node type")

    ep = sub.add_parser("edges", help="List graph edges")
    ep.add_argument("--type", metavar="TYPE", help="Filter by edge type")

    dop = sub.add_parser("depends-on", help="Show what a node depends on")
    dop.add_argument("--node", required=True, metavar="ID")

    dbp = sub.add_parser("depended-by", help="Show what depends on a node")
    dbp.add_argument("--node", required=True, metavar="ID")

    brp = sub.add_parser("blast-radius", help="Full downstream blast radius")
    brp.add_argument("--node", required=True, metavar="ID")
    brp.add_argument("--depth", type=int, default=5, metavar="N")

    pp = sub.add_parser("path", help="Find dependency path between two nodes")
    pp.add_argument("--from", dest="from_node", required=True, metavar="ID")
    pp.add_argument("--to", dest="to_node", required=True, metavar="ID")

    sub.add_parser("summary", help="Graph statistics")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "nodes": cmd_nodes,
        "edges": cmd_edges,
        "depends-on": cmd_depends_on,
        "depended-by": cmd_depended_by,
        "blast-radius": cmd_blast_radius,
        "path": cmd_path,
        "summary": cmd_summary,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 0
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
