#!/usr/bin/env python3

from __future__ import annotations

import os

import importlib.util
import sys
from pathlib import Path
from typing import Any


SEARCH_FABRIC_MODULE_NAME = "lv3_search_fabric_runtime"


def load_search_client(repo_root: Path) -> type:
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)
    if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
        del sys.modules["platform"]

    existing = sys.modules.get(SEARCH_FABRIC_MODULE_NAME)
    if existing is not None and hasattr(existing, "SearchClient"):
        return existing.SearchClient

    search_fabric_dir = repo_root / "scripts" / "search_fabric"
    spec = importlib.util.spec_from_file_location(
        SEARCH_FABRIC_MODULE_NAME,
        search_fabric_dir / "__init__.py",
        submodule_search_locations=[str(search_fabric_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load search_fabric package from {search_fabric_dir}.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[SEARCH_FABRIC_MODULE_NAME] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "SearchClient"):
        raise RuntimeError("search_fabric package did not expose SearchClient.")
    return module.SearchClient


DOCS_BASE_URL = "https://docs.localhost"
SEARCH_COLLECTIONS = ("runbooks", "adrs")
COLLECTION_KIND = {
    "runbooks": "runbook",
    "adrs": "adr",
}


def docs_href_for_source_path(source_path: str) -> str:
    path = Path(source_path)
    if path.parts[:2] == ("docs", "runbooks"):
        return f"{DOCS_BASE_URL}/runbooks/{path.stem}/"
    if path.parts[:2] == ("docs", "adr"):
        return f"{DOCS_BASE_URL}/architecture/decisions/{path.stem}/"
    return DOCS_BASE_URL


def lane_for_result(collection: str, source_path: str) -> str:
    if collection == "runbooks":
        lowered = source_path.lower()
        if any(token in lowered for token in ("break-glass", "recover", "recovery", "repair", "incident", "offboard")):
            return "recover"
    return "learn"


def normalize_snippet(snippet: str) -> str:
    return " ".join(snippet.replace("`", "").split())


def format_result(result: dict[str, Any]) -> dict[str, Any]:
    collection = str(result.get("collection", "")).strip()
    metadata = result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {}
    source_path = str(metadata.get("source_path", result.get("url") or "")).strip()
    kind = COLLECTION_KIND.get(collection, "runbook")
    keywords = [
        source_path,
        str(metadata.get("slug", "")),
        str(metadata.get("adr_number", "")),
        collection,
        kind,
    ]
    if kind == "adr" and metadata.get("adr_number"):
        keywords.append(f"ADR {metadata['adr_number']}")
    return {
        "id": str(result.get("doc_id", "")).strip(),
        "title": str(result.get("title", "")).strip(),
        "description": normalize_snippet(str(result.get("snippet", "")).strip()),
        "href": docs_href_for_source_path(source_path),
        "lane": lane_for_result(collection, source_path),
        "kind": kind,
        "collection": collection,
        "keywords": [item for item in keywords if item],
        "score": float(result.get("score", 0.0)),
        "sourcePath": source_path,
    }


def main(
    query: str = "",
    repo_path: str = os.environ.get("PLATFORM_REPO_ROOT", "/srv/platform_server"),
    limit: int = 8,
) -> dict[str, Any]:
    query_text = query.strip()
    if not query_text:
        return {
            "status": "ok",
            "query": query,
            "count": 0,
            "results": [],
        }

    repo_root = Path(repo_path).resolve()
    SearchClient = load_search_client(repo_root)
    client = SearchClient(repo_root)
    combined: list[dict[str, Any]] = []

    for collection in SEARCH_COLLECTIONS:
        payload = client.query(query_text, collection=collection, limit=max(limit, 1))
        combined.extend(payload.get("results", []))

    combined.sort(key=lambda item: (-float(item.get("score", 0.0)), str(item.get("title", "")).lower()))
    formatted = [format_result(item) for item in combined[: max(limit, 1)]]

    return {
        "status": "ok",
        "query": query_text,
        "count": len(formatted),
        "results": formatted,
    }


if __name__ == "__main__":
    raise SystemExit("This Windmill script is meant to be invoked by Windmill, not from the CLI entrypoint.")
