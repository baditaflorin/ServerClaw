from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .collectors import COLLECTORS, available_collections
from .models import SearchDocument
from .utils import utc_now_iso


DEFAULT_INDEX_PATH = Path("build/search-index/documents.json")


class SearchIndexer:
    def __init__(self, repo_root: Path, *, index_path: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.index_path = (index_path or self.repo_root / DEFAULT_INDEX_PATH).resolve()

    def load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"manifest": {"generated_at": None, "repo_root": str(self.repo_root)}, "documents": []}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def write_index(self, documents: list[SearchDocument], *, stats: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "manifest": {
                "generated_at": utc_now_iso(),
                "repo_root": str(self.repo_root),
                "document_count": len(documents),
                "collection_counts": stats["collection_counts"],
                "updated_count": stats["updated_count"],
                "skipped_count": stats["skipped_count"],
            },
            "documents": [document.to_dict() for document in documents],
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    def upsert_document(
        self,
        documents_by_key: dict[tuple[str, str], SearchDocument],
        document: SearchDocument,
        *,
        unchanged_hashes: dict[tuple[str, str], str],
    ) -> bool:
        key = (document.collection, document.doc_id)
        if unchanged_hashes.get(key) == document.content_hash:
            existing = documents_by_key.get(key)
            if existing is not None:
                documents_by_key[key] = replace(document, indexed_at=existing.indexed_at)
            else:
                documents_by_key[key] = document
            return False
        documents_by_key[key] = document
        return True

    def index_collection(self, collection: str) -> list[SearchDocument]:
        try:
            collector = COLLECTORS[collection]
        except KeyError as exc:
            raise ValueError(f"Unknown search collection '{collection}'.") from exc
        return collector(self.repo_root)

    def index_all(
        self,
        *,
        collections: list[str] | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        selected = collections or available_collections()
        existing = self.load_index()
        existing_documents = {
            (item["collection"], item["doc_id"]): SearchDocument(**item)
            for item in existing.get("documents", [])
        }
        existing_hashes = {key: document.content_hash for key, document in existing_documents.items()}

        retained_documents = {
            key: document
            for key, document in existing_documents.items()
            if key[0] not in selected
        }
        updated_count = 0
        skipped_count = 0
        collection_counts: dict[str, int] = {}

        for collection in selected:
            produced = self.index_collection(collection)
            collection_counts[collection] = len(produced)
            for document in produced:
                changed = self.upsert_document(retained_documents, document, unchanged_hashes=existing_hashes)
                if changed:
                    updated_count += 1
                else:
                    skipped_count += 1

        ordered = sorted(retained_documents.values(), key=lambda item: (item.collection, item.title.lower(), item.doc_id))
        stats = {
            "repo_root": str(self.repo_root),
            "index_path": str(self.index_path),
            "document_count": len(ordered),
            "collection_counts": collection_counts,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "collections": selected,
        }
        if write:
            payload = self.write_index(ordered, stats=stats)
            stats["manifest"] = payload["manifest"]
        else:
            stats["manifest"] = {
                "generated_at": utc_now_iso(),
                "repo_root": str(self.repo_root),
                "document_count": len(ordered),
                "collection_counts": collection_counts,
            }
        stats["documents"] = ordered
        return stats
