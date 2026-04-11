from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

from .indexer import DEFAULT_INDEX_PATH, SearchIndexer
from .models import SearchDocument, SearchResult
from .utils import flatten_text, load_yaml, normalize_text, similarity, tokenize


class SearchClient:
    def __init__(
        self,
        repo_root: Path,
        *,
        index_path: Path | None = None,
        synonyms_path: Path | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.index_path = (index_path or self.repo_root / DEFAULT_INDEX_PATH).resolve()
        self.synonyms_path = (synonyms_path or self.repo_root / "config" / "search-synonyms.yaml").resolve()
        self.indexer = SearchIndexer(self.repo_root, index_path=self.index_path)
        self._documents: list[SearchDocument] | None = None
        self._synonym_groups: list[dict[str, Any]] | None = None

    def _load_documents(self, *, rebuild: bool = False) -> list[SearchDocument]:
        if rebuild or self._documents is None:
            if rebuild or not self.index_path.exists():
                payload = self.indexer.index_all(write=True)
                self._documents = list(payload["documents"])
            else:
                payload = self.indexer.load_index()
                self._documents = [SearchDocument(**item) for item in payload.get("documents", [])]
        return self._documents

    def _load_synonym_groups(self) -> list[dict[str, Any]]:
        if self._synonym_groups is None:
            payload = load_yaml(self.synonyms_path, {"groups": []})
            groups = payload.get("groups", []) if isinstance(payload, dict) else []
            self._synonym_groups = [group for group in groups if isinstance(group, dict)]
        return self._synonym_groups

    def expand_query(self, query: str) -> str:
        expanded_parts = [query.strip()]
        normalized_query = normalize_text(query)
        for group in self._load_synonym_groups():
            canonical = str(group.get("canonical", "")).strip()
            aliases = [str(item).strip() for item in group.get("aliases", []) if str(item).strip()]
            expand = [str(item).strip() for item in group.get("expand", []) if str(item).strip()]
            candidates = [canonical, *aliases]
            if any(candidate and normalize_text(candidate) in normalized_query for candidate in candidates):
                expanded_parts.extend(item for item in [canonical, *aliases, *expand] if item)
        return " ".join(dict.fromkeys(part for part in expanded_parts if part))

    def _filtered_documents(
        self,
        *,
        collection: str | None,
        facets: dict[str, Any] | None,
        rebuild: bool = False,
    ) -> list[SearchDocument]:
        documents = self._load_documents(rebuild=rebuild)
        selected = [document for document in documents if collection in {None, document.collection}]
        if not facets:
            return selected
        filtered: list[SearchDocument] = []
        for document in selected:
            keep = True
            for key, expected in facets.items():
                actual = document.metadata.get(key)
                if isinstance(actual, list):
                    if expected not in actual:
                        keep = False
                        break
                elif actual != expected:
                    keep = False
                    break
            if keep:
                filtered.append(document)
        return filtered

    def _bm25_stats(self, documents: list[SearchDocument]) -> tuple[list[Counter[str]], dict[str, int], float]:
        counters: list[Counter[str]] = []
        document_frequency: dict[str, int] = {}
        total_length = 0
        for document in documents:
            tokens = tokenize(f"{document.title} {document.title} {document.body} {flatten_text(document.metadata)}")
            counter = Counter(tokens)
            counters.append(counter)
            total_length += sum(counter.values())
            for term in counter:
                document_frequency[term] = document_frequency.get(term, 0) + 1
        average_length = total_length / max(len(documents), 1)
        return counters, document_frequency, average_length or 1.0

    def _score_document(
        self,
        document: SearchDocument,
        query: str,
        query_tokens: list[str],
        counter: Counter[str],
        *,
        doc_count: int,
        document_frequency: dict[str, int],
        average_length: float,
    ) -> float:
        k1 = 1.5
        b = 0.75
        length = sum(counter.values()) or 1
        bm25 = 0.0
        for term in query_tokens:
            term_frequency = counter.get(term, 0)
            if term_frequency == 0:
                continue
            frequency = document_frequency.get(term, 0)
            idf = math.log(1 + ((doc_count - frequency + 0.5) / (frequency + 0.5)))
            numerator = term_frequency * (k1 + 1)
            denominator = term_frequency + (k1 * (1 - b + b * (length / average_length)))
            bm25 += idf * (numerator / denominator)

        trigram = max(
            similarity(document.title, query),
            similarity(document.doc_id, query),
        )
        if bm25 <= 0 and trigram <= 0.08:
            return 0.0
        return (bm25 * 0.7) + (trigram * 0.3)

    def query(
        self,
        query: str,
        *,
        collection: str | None = None,
        facets: dict[str, Any] | None = None,
        limit: int = 10,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        expanded_query = self.expand_query(query)
        documents = self._filtered_documents(collection=collection, facets=facets, rebuild=rebuild)
        if not documents:
            return {"query": query, "expanded_query": expanded_query, "count": 0, "results": []}
        counters, document_frequency, average_length = self._bm25_stats(documents)
        query_tokens = tokenize(expanded_query)
        scored: list[SearchResult] = []
        for index, document in enumerate(documents):
            score = self._score_document(
                document,
                expanded_query,
                query_tokens,
                counters[index],
                doc_count=len(documents),
                document_frequency=document_frequency,
                average_length=average_length,
            )
            if score <= 0:
                continue
            scored.append(
                SearchResult(
                    doc_id=document.doc_id,
                    collection=document.collection,
                    title=document.title,
                    url=document.url,
                    metadata=document.metadata,
                    score=round(score, 6),
                    snippet=document.body[:240],
                )
            )
        scored.sort(key=lambda item: (-item.score, item.collection, item.title.lower()))
        return {
            "query": query,
            "expanded_query": expanded_query,
            "count": len(scored[:limit]),
            "results": [result.to_dict() for result in scored[:limit]],
        }

    def suggest(
        self,
        prefix: str,
        *,
        collection: str | None = None,
        limit: int = 5,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        documents = self._filtered_documents(collection=collection, facets=None, rebuild=rebuild)
        normalized_prefix = normalize_text(prefix)
        suggestions: list[SearchResult] = []
        for document in documents:
            title_normalized = normalize_text(document.title)
            score = 0.0
            if title_normalized.startswith(normalized_prefix):
                score += 1.0
            if normalized_prefix and normalized_prefix in normalize_text(document.doc_id):
                score += 0.6
            score += similarity(document.title, prefix) * 0.4
            if score <= 0:
                continue
            suggestions.append(
                SearchResult(
                    doc_id=document.doc_id,
                    collection=document.collection,
                    title=document.title,
                    url=document.url,
                    metadata=document.metadata,
                    score=round(score, 6),
                    snippet=document.body[:120],
                )
            )
        suggestions.sort(key=lambda item: (-item.score, item.title.lower()))
        return {
            "prefix": prefix,
            "count": len(suggestions[:limit]),
            "results": [item.to_dict() for item in suggestions[:limit]],
        }

    def filter(
        self,
        *,
        collection: str | None = None,
        facets: dict[str, Any] | None = None,
        limit: int = 10,
        rebuild: bool = False,
    ) -> dict[str, Any]:
        documents = self._filtered_documents(collection=collection, facets=facets, rebuild=rebuild)
        results = [
            SearchResult(
                doc_id=document.doc_id,
                collection=document.collection,
                title=document.title,
                url=document.url,
                metadata=document.metadata,
                score=1.0,
                snippet=document.body[:240],
            ).to_dict()
            for document in sorted(documents, key=lambda item: (item.collection, item.title.lower()))[:limit]
        ]
        return {"count": len(results), "results": results}
