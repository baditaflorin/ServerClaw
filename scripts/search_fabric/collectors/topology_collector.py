from __future__ import annotations

from pathlib import Path

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import flatten_text, load_json


def collect(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    graph_path = repo_root / "config" / "dependency-graph.json"
    service_path = repo_root / "config" / "service-capability-catalog.json"
    graph = load_json(graph_path, {"nodes": [], "edges": []})
    services = {
        item.get("id"): item
        for item in load_json(service_path, {"services": []}).get("services", [])
        if isinstance(item, dict)
    }
    relative_graph = relative_url(repo_root, graph_path)
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        service = services.get(node.get("service"), {})
        body = "\n".join(
            item
            for item in [
                str(node.get("name") or node.get("id") or ""),
                flatten_text(node),
                flatten_text(service),
            ]
            if item
        )
        title = str(node.get("name") or node.get("id") or "topology-node")
        documents.append(
            build_document(
                collection="topology",
                doc_id=f"topology:{node.get('id')}",
                title=title,
                body=body,
                url=relative_graph,
                metadata={
                    "source_path": relative_graph,
                    "service": node.get("service"),
                    "vm": node.get("vm"),
                    "tier": node.get("tier"),
                },
            )
        )
    return documents
