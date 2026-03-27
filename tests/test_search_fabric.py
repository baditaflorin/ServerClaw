from __future__ import annotations

import json
from pathlib import Path

from search_fabric import SearchClient, SearchIndexer


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / "docs" / "adr" / "0121-local-search-and-indexing-fabric.md",
        "# ADR 0121: Local Search and Indexing Fabric\n\n- Status: Accepted\n- Implementation Status: Implemented\n\nCertificate renewal and local search are handled here.\n",
    )
    write(
        tmp_path / "docs" / "runbooks" / "rotate-certificates.md",
        "# Rotate Certificates\n\nRenew the TLS certificate before it expires.\n",
    )
    write(
        tmp_path / "config" / "command-catalog.json",
        json.dumps(
            {
                "commands": {
                    "converge-netbox": {
                        "description": "Deploy the NetBox service.",
                        "workflow_id": "deploy-and-promote",
                    }
                }
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps({"workflows": {"deploy-and-promote": {"description": "Deploy a service."}}}, indent=2) + "\n",
    )
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps({"services": [{"id": "netbox", "name": "NetBox", "vm": "docker-runtime-lv3"}]}, indent=2) + "\n",
    )
    write(
        tmp_path / "config" / "dependency-graph.json",
        json.dumps(
            {"nodes": [{"id": "netbox", "service": "netbox", "name": "NetBox", "vm": "docker-runtime-lv3", "tier": 1}]},
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "search-synonyms.yaml",
        """schema_version: 1.0.0
groups:
  - canonical: certificate
    aliases: [cert, certs]
    expand: [renewal, expires]
""",
    )
    write(
        tmp_path / "receipts" / "live-applies" / "2026-03-23-netbox.json",
        json.dumps({"summary": "netbox deploy", "workflow_id": "converge-netbox"}, indent=2) + "\n",
    )
    (tmp_path / "receipts" / "live-applies" / "2026-03-24-binaryish.json").write_bytes(
        b'{"summary":"caf\xe9 deploy","workflow_id":"converge-netbox"}\n'
    )
    (tmp_path / "config" / "binaryish.json").write_bytes(b'{"name":"caf\xe9","\xa3":"value"}\n')
    return tmp_path


def test_indexer_writes_documents_json(tmp_path: Path) -> None:
    repo_root = make_repo(tmp_path)
    payload = SearchIndexer(repo_root).index_all()
    assert payload["document_count"] > 0
    assert (repo_root / "build" / "search-index" / "documents.json").exists()


def test_query_ranks_runbook_for_certificate_terms(tmp_path: Path) -> None:
    client = SearchClient(make_repo(tmp_path))
    payload = client.query("certificate renewal", collection="runbooks")
    assert payload["results"]
    assert payload["results"][0]["title"] == "Rotate Certificates"


def test_query_uses_synonym_expansion(tmp_path: Path) -> None:
    client = SearchClient(make_repo(tmp_path))
    payload = client.query("tls cert expires", collection="runbooks")
    assert payload["results"]
    assert payload["expanded_query"] != "tls cert expires"


def test_suggest_uses_trigram_fallback(tmp_path: Path) -> None:
    client = SearchClient(make_repo(tmp_path))
    payload = client.suggest("converj netbox", collection="command_catalog")
    assert payload["results"]
    assert payload["results"][0]["title"] == "converge-netbox"


def test_filter_by_collection_metadata(tmp_path: Path) -> None:
    client = SearchClient(make_repo(tmp_path))
    payload = client.filter(collection="receipts", facets={"workflow_id": "converge-netbox"})
    assert payload["count"] == 2


def test_empty_corpus_returns_no_results(tmp_path: Path) -> None:
    client = SearchClient(tmp_path)
    payload = client.query("xyzzy")
    assert payload["results"] == []


def test_indexer_tolerates_non_utf8_config_text(tmp_path: Path) -> None:
    payload = SearchIndexer(make_repo(tmp_path)).index_all()
    config_docs = [document for document in payload["documents"] if document.collection == "configs"]
    assert any(document.title == "binaryish.json" for document in config_docs)


def test_indexer_tolerates_non_utf8_receipt_json(tmp_path: Path) -> None:
    payload = SearchIndexer(make_repo(tmp_path)).index_all()
    receipt_docs = [document for document in payload["documents"] if document.collection == "receipts"]
    assert any(document.doc_id == "receipt:receipts/live-applies/2026-03-24-binaryish.json" for document in receipt_docs)


def test_indexer_skips_malformed_receipt_json(tmp_path: Path) -> None:
    repo_root = make_repo(tmp_path)
    (repo_root / "receipts" / "live-applies" / "2026-03-25-malformed.json").write_text("{not-json}\n", encoding="utf-8")
    payload = SearchIndexer(repo_root).index_all()
    receipt_docs = [document for document in payload["documents"] if document.collection == "receipts"]
    assert not any(document.doc_id == "receipt:receipts/live-applies/2026-03-25-malformed.json" for document in receipt_docs)
