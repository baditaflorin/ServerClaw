#!/usr/bin/env python3

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from canonical_errors import ErrorRegistry, PlatformHTTPError
from dependency_graph import compute_impact, graph_to_dict, load_dependency_graph
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams

from platform.logging import clear_context, generate_trace_id, get_logger, set_context
from platform.memory import MemoryEntryInput, MemoryStore
from platform.world_state._db import isoformat
from platform_context_corpus import build_chunks
from slo_tracking import build_slo_status_entries, default_grafana_url, default_prometheus_url

try:
    from search_fabric import SearchClient, SearchDocument, SearchIndexer
    from search_fabric.utils import sha256_text, utc_now_iso
except ImportError:  # pragma: no cover - packaged import path
    from scripts.search_fabric import SearchClient, SearchDocument, SearchIndexer
    from scripts.search_fabric.utils import sha256_text, utc_now_iso


DEFAULT_COLLECTION = "platform_context"
DEFAULT_DIMENSION = 384
OLLAMA_EMBED_BATCH_SIZE = 32
HTTP_LOGGER = get_logger("platform_context_api", "http", name="lv3.platform_context.http")
SERVICE_LOGGER = get_logger("platform_context_api", "service", name="lv3.platform_context.service")


class QueryRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int = Field(default=5, ge=1, le=10)


class RebuildRequest(BaseModel):
    replace: bool = True
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    manifest: dict[str, Any] | None = None


class MemoryEntryRequest(BaseModel):
    memory_id: str | None = None
    scope_kind: Literal["owner", "workspace"]
    scope_id: str = Field(min_length=1, max_length=128)
    object_type: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=20000)
    provenance: str = Field(min_length=1, max_length=256)
    retention_class: str = Field(min_length=1, max_length=64)
    consent_boundary: str = Field(min_length=1, max_length=128)
    delegation_boundary: str | None = Field(default=None, max_length=128)
    source_uri: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_refreshed_at: datetime | None = None
    expires_at: datetime | None = None


class MemoryQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    scope_kind: Literal["owner", "workspace"]
    scope_id: str = Field(min_length=1, max_length=128)
    object_type: str | None = Field(default=None, min_length=2, max_length=64)
    limit: int = Field(default=5, ge=1, le=20)


class TokenHashEmbedder:
    def __init__(self, dimension: int = DEFAULT_DIMENSION) -> None:
        self.dimension = dimension

    def _vectorize(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            index = abs(hash(token)) % self.dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vectorize(text)


class SentenceTransformersEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text], normalize_embeddings=True).tolist()[0]


class OllamaEmbedder:
    def __init__(self, base_url: str, model_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama {path} returned HTTP {exc.code}: {detail}") from exc

    @staticmethod
    def _extract_embeddings(payload: dict[str, Any]) -> list[list[float]]:
        embeddings = payload.get("embeddings")
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return [[float(value) for value in vector] for vector in embeddings]
        embedding = payload.get("embedding")
        if isinstance(embedding, list):
            return [[float(value) for value in embedding]]
        raise RuntimeError("Ollama embedding response did not contain embeddings")

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model_name, "input": texts}
        try:
            response = self._request("/api/embed", payload)
            return self._extract_embeddings(response)
        except Exception:
            if len(texts) == 1:
                legacy_response = self._request("/api/embeddings", {"model": self.model_name, "prompt": texts[0]})
                return [self._extract_embeddings(legacy_response)[0]]
            midpoint = max(1, len(texts) // 2)
            return self._embed_batch(texts[:midpoint]) + self._embed_batch(texts[midpoint:])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), OLLAMA_EMBED_BATCH_SIZE):
            batch = texts[start : start + OLLAMA_EMBED_BATCH_SIZE]
            embeddings.extend(self._embed_batch(batch))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


@dataclass
class ServiceConfig:
    api_token: str
    corpus_root: Path
    error_registry_path: Path
    collection_name: str
    qdrant_url: str | None
    qdrant_location: str | None
    embedding_backend: str
    embedding_model: str
    embedding_dimension: int
    ollama_url: str | None = None
    prometheus_url: str | None = None
    grafana_url: str | None = None
    memory_dsn: str | None = None
    memory_collection_name: str = "serverclaw_memory"
    memory_index_path: Path | None = None


class PlatformContextService:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.error_registry = ErrorRegistry.load(config.error_registry_path)
        self.client = self._build_client()
        self.embedder = self._build_embedder()
        self.memory_store = self._build_memory_store()
        self._memory_search_client: SearchClient | None = None
        if self.memory_store is not None:
            self.memory_store.ensure_sqlite_schema()

    def _build_client(self) -> QdrantClient:
        if self.config.qdrant_location:
            return QdrantClient(location=self.config.qdrant_location)
        return QdrantClient(url=self.config.qdrant_url)

    def _build_embedder(self) -> TokenHashEmbedder | SentenceTransformersEmbedder | OllamaEmbedder:
        if self.config.embedding_backend == "token-hash":
            return TokenHashEmbedder(self.config.embedding_dimension)
        if self.config.embedding_backend == "ollama":
            if not self.config.ollama_url:
                raise ValueError(
                    "PLATFORM_CONTEXT_OLLAMA_URL is required when PLATFORM_CONTEXT_EMBEDDING_BACKEND=ollama"
                )
            return OllamaEmbedder(self.config.ollama_url, self.config.embedding_model)
        if self.config.embedding_backend == "sentence-transformers":
            try:
                return SentenceTransformersEmbedder(self.config.embedding_model)
            except Exception as exc:
                SERVICE_LOGGER.warning(
                    "Falling back to token-hash embeddings",
                    extra={
                        "trace_id": "startup",
                        "workflow_id": "converge-rag-context",
                        "target": "service:platform_context_api",
                        "error_code": "EMBEDDING_BACKEND_FALLBACK",
                        "embedding_model": self.config.embedding_model,
                        "error_detail": str(exc),
                    },
                )
                return TokenHashEmbedder(self.config.embedding_dimension)
        raise ValueError(f"unsupported embedding backend: {self.config.embedding_backend}")

    def _build_memory_store(self) -> MemoryStore | None:
        if not self.config.memory_dsn:
            return None
        return MemoryStore(dsn=self.config.memory_dsn)

    def _required_dimension(self, embeddings: list[list[float]] | None = None) -> int:
        if embeddings:
            return len(embeddings[0])
        if self.config.embedding_dimension > 0:
            return self.config.embedding_dimension
        return len(self.embedder.embed_query("platform context dimension probe"))

    def ensure_collection(self, *, replace: bool = False, dimension: int | None = None) -> None:
        if replace and self.client.collection_exists(self.config.collection_name):
            self.client.delete_collection(self.config.collection_name)
        if self.client.collection_exists(self.config.collection_name):
            return
        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config=VectorParams(
                size=dimension or self._required_dimension(),
                distance=Distance.COSINE,
            ),
        )

    def rebuild(self, chunks: list[dict[str, Any]], *, replace: bool = True) -> dict[str, Any]:
        if not chunks:
            return {"collection_name": self.config.collection_name, "indexed_chunks": 0}
        embeddings = self.embedder.embed_documents([chunk["content"] for chunk in chunks])
        self.ensure_collection(replace=replace, dimension=self._required_dimension(embeddings))
        points = [
            PointStruct(
                id=chunk["chunk_id"],
                vector=embeddings[index],
                payload={key: value for key, value in chunk.items() if key != "chunk_id"},
            )
            for index, chunk in enumerate(chunks)
        ]
        self.client.upsert(collection_name=self.config.collection_name, points=points)
        result = {
            "collection_name": self.config.collection_name,
            "indexed_chunks": len(chunks),
        }
        SERVICE_LOGGER.info(
            "Indexed context chunks",
            extra={
                "workflow_id": "platform-context-rebuild",
                "target": "collection:" + self.config.collection_name,
                "duration_ms": None,
                "indexed_chunks": len(chunks),
            },
        )
        return result

    def rebuild_from_local_corpus(self) -> dict[str, Any]:
        chunks = build_chunks(self.config.corpus_root)
        result = self.rebuild(chunks, replace=True)
        result["source"] = str(self.config.corpus_root)
        return result

    def _require_memory_store(self) -> MemoryStore:
        if self.memory_store is None:
            raise RuntimeError("ServerClaw memory substrate is not configured")
        return self.memory_store

    def _memory_index_path(self) -> Path:
        if self.config.memory_index_path is not None:
            return self.config.memory_index_path
        return self.config.corpus_root / "build" / "serverclaw-memory-index" / "documents.json"

    def _memory_search_client_instance(self) -> SearchClient:
        if self._memory_search_client is None:
            self._memory_search_client = SearchClient(
                self.config.corpus_root,
                index_path=self._memory_index_path(),
            )
        return self._memory_search_client

    def ensure_memory_collection(self, *, replace: bool = False, dimension: int | None = None) -> None:
        if replace and self.client.collection_exists(self.config.memory_collection_name):
            self.client.delete_collection(self.config.memory_collection_name)
        if self.client.collection_exists(self.config.memory_collection_name):
            return
        self.client.create_collection(
            collection_name=self.config.memory_collection_name,
            vectors_config=VectorParams(
                size=dimension or self._required_dimension(),
                distance=Distance.COSINE,
            ),
        )

    def rebuild_memory_keyword_index(self) -> dict[str, Any]:
        store = self._require_memory_store()
        entries = store.all_active_entries()
        documents = []
        for entry in entries:
            metadata = {
                "scope_kind": entry.scope_kind,
                "scope_id": entry.scope_id,
                "object_type": entry.object_type,
                "provenance": entry.provenance,
                "retention_class": entry.retention_class,
                "consent_boundary": entry.consent_boundary,
                "delegation_boundary": entry.delegation_boundary,
                "source_uri": entry.source_uri,
                "last_refreshed_at": isoformat(entry.last_refreshed_at),
            }
            documents.append(
                SearchDocument(
                    doc_id=entry.memory_id,
                    collection="serverclaw_memory",
                    title=entry.title,
                    body=entry.content,
                    url=f"memory:{entry.memory_id}",
                    metadata=metadata,
                    indexed_at=utc_now_iso(),
                    content_hash=sha256_text(
                        entry.memory_id,
                        entry.title,
                        entry.content,
                        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                    ),
                )
            )
        payload = SearchIndexer(self.config.corpus_root, index_path=self._memory_index_path()).write_index(
            documents,
            stats={
                "collection_counts": {"serverclaw_memory": len(documents)},
                "updated_count": len(documents),
                "skipped_count": 0,
            },
        )
        self._memory_search_client = None
        return payload

    def _memory_keyword_matches(
        self,
        query: str,
        *,
        scope_kind: str,
        scope_id: str,
        object_type: str | None,
        limit: int,
    ) -> dict[str, dict[str, Any]]:
        if not self._memory_index_path().exists():
            self.rebuild_memory_keyword_index()
        payload = self._memory_search_client_instance().query(
            query,
            collection="serverclaw_memory",
            facets={
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                **({"object_type": object_type} if object_type else {}),
            },
            limit=max(limit * 5, 10),
        )
        return {item["doc_id"]: item for item in payload.get("results", []) if isinstance(item, dict)}

    def _memory_semantic_matches(
        self,
        query: str,
        *,
        scope_kind: str,
        scope_id: str,
        object_type: str | None,
        limit: int,
    ) -> dict[str, dict[str, Any]]:
        if not self.client.collection_exists(self.config.memory_collection_name):
            return {}
        vector = self.embedder.embed_query(query)
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.config.memory_collection_name,
                query=vector,
                limit=max(limit * 5, 10),
                with_payload=True,
            )
            points = response.points
        else:
            points = self.client.search(
                collection_name=self.config.memory_collection_name,
                query_vector=vector,
                limit=max(limit * 5, 10),
                with_payload=True,
            )
        matches: dict[str, dict[str, Any]] = {}
        for point in points:
            payload = point.payload or {}
            if payload.get("scope_kind") != scope_kind or payload.get("scope_id") != scope_id:
                continue
            if object_type and payload.get("object_type") != object_type:
                continue
            matches[str(payload.get("memory_id") or point.id)] = {
                "score": float(point.score or 0.0),
                "payload": payload,
            }
        return matches

    def upsert_memory_entry(self, request: MemoryEntryRequest) -> dict[str, Any]:
        store = self._require_memory_store()
        entry = store.upsert(
            MemoryEntryInput(
                memory_id=request.memory_id,
                scope_kind=request.scope_kind,
                scope_id=request.scope_id,
                object_type=request.object_type,
                title=request.title,
                content=request.content,
                provenance=request.provenance,
                retention_class=request.retention_class,
                consent_boundary=request.consent_boundary,
                delegation_boundary=request.delegation_boundary,
                source_uri=request.source_uri,
                metadata=request.metadata,
                last_refreshed_at=request.last_refreshed_at,
                expires_at=request.expires_at,
            )
        )
        embedding_text = f"{entry.title}\n\n{entry.content}"
        embeddings = self.embedder.embed_documents([embedding_text])
        self.ensure_memory_collection(dimension=self._required_dimension(embeddings))
        self.client.upsert(
            collection_name=self.config.memory_collection_name,
            points=[
                PointStruct(
                    id=entry.memory_id,
                    vector=embeddings[0],
                    payload={
                        "memory_id": entry.memory_id,
                        "scope_kind": entry.scope_kind,
                        "scope_id": entry.scope_id,
                        "object_type": entry.object_type,
                        "title": entry.title,
                        "content": entry.content,
                        "provenance": entry.provenance,
                        "retention_class": entry.retention_class,
                        "consent_boundary": entry.consent_boundary,
                        "delegation_boundary": entry.delegation_boundary,
                        "source_uri": entry.source_uri,
                        "last_refreshed_at": isoformat(entry.last_refreshed_at),
                    },
                )
            ],
        )
        self.rebuild_memory_keyword_index()
        return {
            "entry": entry.to_dict(),
            "indexed_backends": ["postgres", "qdrant", "local-search"],
            "memory_collection": self.config.memory_collection_name,
            "memory_index_path": str(self._memory_index_path()),
        }

    def get_memory_entry(self, memory_id: str) -> dict[str, Any] | None:
        store = self._require_memory_store()
        entry = store.get(memory_id)
        return entry.to_dict() if entry is not None else None

    def list_memory_entries(
        self,
        *,
        scope_kind: str,
        scope_id: str,
        object_type: str | None,
        limit: int,
    ) -> dict[str, Any]:
        store = self._require_memory_store()
        entries = store.list_entries(
            scope_kind=scope_kind,
            scope_id=scope_id,
            object_type=object_type,
            limit=limit,
        )
        return {
            "count": len(entries),
            "entries": [entry.to_dict() for entry in entries],
        }

    def delete_memory_entry(self, memory_id: str) -> bool:
        store = self._require_memory_store()
        deleted = store.delete(memory_id)
        if not deleted:
            return False
        if self.client.collection_exists(self.config.memory_collection_name):
            self.client.delete(
                collection_name=self.config.memory_collection_name,
                points_selector=PointIdsList(points=[memory_id]),
            )
        self.rebuild_memory_keyword_index()
        return True

    def query_memory(self, request: MemoryQueryRequest) -> dict[str, Any]:
        store = self._require_memory_store()
        semantic_matches: dict[str, dict[str, Any]] = {}
        fallback_reason = None
        try:
            semantic_matches = self._memory_semantic_matches(
                request.query,
                scope_kind=request.scope_kind,
                scope_id=request.scope_id,
                object_type=request.object_type,
                limit=request.limit,
            )
        except Exception as exc:
            fallback_reason = str(exc)
        keyword_matches = self._memory_keyword_matches(
            request.query,
            scope_kind=request.scope_kind,
            scope_id=request.scope_id,
            object_type=request.object_type,
            limit=request.limit,
        )
        candidate_ids = list(dict.fromkeys([*semantic_matches.keys(), *keyword_matches.keys()]))
        if not candidate_ids:
            return {
                "query": request.query,
                "scope_kind": request.scope_kind,
                "scope_id": request.scope_id,
                "object_type": request.object_type,
                "retrieval_backend": "keyword-fallback" if fallback_reason else "hybrid",
                "matches": [],
                "memory_collection": self.config.memory_collection_name,
                "memory_index_path": str(self._memory_index_path()),
                **({"fallback_reason": fallback_reason} if fallback_reason else {}),
            }
        entries = {
            entry.memory_id: entry
            for entry in store.list_entries(
                scope_kind=request.scope_kind,
                scope_id=request.scope_id,
                object_type=request.object_type,
                memory_ids=candidate_ids,
                limit=max(len(candidate_ids), request.limit),
            )
        }
        ranked: list[tuple[float, str]] = []
        for memory_id in candidate_ids:
            semantic_score = float(semantic_matches.get(memory_id, {}).get("score", 0.0) or 0.0)
            keyword_score = float(keyword_matches.get(memory_id, {}).get("score", 0.0) or 0.0)
            ranked.append((semantic_score + keyword_score, memory_id))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        matches = []
        for _combined_score, memory_id in ranked[: request.limit]:
            entry = entries.get(memory_id)
            if entry is None:
                continue
            matched_backends = []
            semantic_score = float(semantic_matches.get(memory_id, {}).get("score", 0.0) or 0.0)
            keyword_score = float(keyword_matches.get(memory_id, {}).get("score", 0.0) or 0.0)
            if semantic_score > 0:
                matched_backends.append("semantic")
            if keyword_score > 0:
                matched_backends.append("keyword")
            matches.append(
                {
                    **entry.to_dict(),
                    "semantic_score": semantic_score,
                    "keyword_score": keyword_score,
                    "hybrid_score": semantic_score + keyword_score,
                    "matched_backends": matched_backends,
                }
            )
        retrieval_backend = "hybrid"
        if fallback_reason and keyword_matches:
            retrieval_backend = "keyword-fallback"
        elif semantic_matches and not keyword_matches:
            retrieval_backend = "semantic-only"
        elif keyword_matches and not semantic_matches:
            retrieval_backend = "keyword-only"
        return {
            "query": request.query,
            "scope_kind": request.scope_kind,
            "scope_id": request.scope_id,
            "object_type": request.object_type,
            "retrieval_backend": retrieval_backend,
            "matches": matches,
            "memory_collection": self.config.memory_collection_name,
            "memory_index_path": str(self._memory_index_path()),
            **({"fallback_reason": fallback_reason} if fallback_reason else {}),
        }

    def query(self, question: str, top_k: int) -> dict[str, Any]:
        fallback_reason = None
        try:
            vector = self.embedder.embed_query(question)
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.config.collection_name,
                    query=vector,
                    limit=top_k,
                    with_payload=True,
                )
                matches = response.points
            else:
                matches = self.client.search(
                    collection_name=self.config.collection_name,
                    query_vector=vector,
                    limit=top_k,
                    with_payload=True,
                )
            payload = {
                "question": question,
                "matches": [
                    {
                        "score": match.score,
                        "source_path": match.payload.get("source_path"),
                        "document_kind": match.payload.get("document_kind"),
                        "document_title": match.payload.get("document_title"),
                        "section_heading": match.payload.get("section_heading"),
                        "adr_number": match.payload.get("adr_number"),
                        "content": match.payload.get("content"),
                    }
                    for match in matches
                ],
                "retrieval_backend": "vector",
            }
        except Exception as exc:
            fallback_reason = str(exc)
            payload = {
                "question": question,
                "matches": self.keyword_query(question, top_k),
                "retrieval_backend": "keyword-fallback",
            }
            payload["fallback_reason"] = fallback_reason
        SERVICE_LOGGER.info(
            "Answered platform-context query",
            extra={
                "target": "collection:" + self.config.collection_name,
                "query_top_k": top_k,
                "match_count": len(payload["matches"]),
                "retrieval_backend": payload.get("retrieval_backend"),
                "fallback_reason": fallback_reason,
            },
        )
        return payload

    def keyword_query(self, question: str, top_k: int) -> list[dict[str, Any]]:
        query_tokens = {token for token in re.findall(r"[a-z0-9]{3,}", question.lower())}
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in build_chunks(self.config.corpus_root):
            content = str(chunk.get("content", ""))
            content_tokens = {token for token in re.findall(r"[a-z0-9]{3,}", content.lower())}
            if not content_tokens:
                continue
            overlap = query_tokens & content_tokens
            if not overlap:
                continue
            score = len(overlap) / len(query_tokens or {""})
            scored.append(
                (
                    score,
                    {
                        "score": score,
                        "source_path": chunk.get("source_path"),
                        "document_kind": chunk.get("document_kind"),
                        "document_title": chunk.get("document_title"),
                        "section_heading": chunk.get("section_heading"),
                        "adr_number": chunk.get("adr_number"),
                        "content": content,
                    },
                )
            )
        return [item for _score, item in sorted(scored, key=lambda entry: entry[0], reverse=True)[:top_k]]

    def recent_receipts(self, limit: int) -> dict[str, Any]:
        receipts_dir = self.config.corpus_root / "receipts" / "live-applies"
        receipts = []
        for path in sorted(receipts_dir.glob("*.json"), reverse=True)[:limit]:
            payload = json.loads(path.read_text())
            receipts.append(
                {
                    "receipt_id": payload["receipt_id"],
                    "workflow_id": payload["workflow_id"],
                    "adr": payload.get("adr"),
                    "applied_on": payload["applied_on"],
                    "summary": payload["summary"],
                }
            )
        return {"receipts": receipts}

    def platform_summary(self) -> dict[str, Any]:
        version = (self.config.corpus_root / "VERSION").read_text().strip()
        stack = load_yaml(self.config.corpus_root / "versions" / "stack.yaml")
        observed = stack.get("observed_state", {})
        checked_at = observed.get("checked_at")
        if hasattr(checked_at, "isoformat"):
            checked_at = checked_at.isoformat()
        return {
            "repo_version": version,
            "platform_version": stack.get("platform_version"),
            "checked_at": checked_at,
            "proxmox_version": observed.get("proxmox", {}).get("version"),
            "windmill_url": observed.get("windmill", {}).get("host_tailscale_proxy_url"),
            "netbox_url": observed.get("netbox", {}).get("host_tailscale_proxy_url"),
        }

    def workflow_contract(self, workflow_id: str) -> dict[str, Any]:
        catalog = json.loads((self.config.corpus_root / "config" / "workflow-catalog.json").read_text())
        workflow = catalog["workflows"].get(workflow_id)
        if workflow is None:
            raise KeyError(workflow_id)
        return {"workflow_id": workflow_id, "contract": workflow}

    def command_contract(self, command_id: str) -> dict[str, Any]:
        catalog = json.loads((self.config.corpus_root / "config" / "command-catalog.json").read_text())
        command = catalog["commands"].get(command_id)
        if command is None:
            raise KeyError(command_id)
        return {"command_id": command_id, "contract": command}

    def slo_status(self) -> dict[str, Any]:
        return {
            "grafana_url": self.config.grafana_url,
            "prometheus_url": self.config.prometheus_url,
            "slos": build_slo_status_entries(
                prometheus_url=self.config.prometheus_url,
                grafana_url=self.config.grafana_url,
                catalog_path=self.config.corpus_root / "config" / "slo-catalog.json",
                service_catalog_path=self.config.corpus_root / "config" / "service-capability-catalog.json",
                stack_path=self.config.corpus_root / "versions" / "stack.yaml",
            ),
        }

    def dependency_graph(self) -> dict[str, Any]:
        graph = load_dependency_graph(
            self.config.corpus_root / "config" / "dependency-graph.json",
            service_catalog_path=self.config.corpus_root / "config" / "service-capability-catalog.json",
            validate_schema=False,
        )
        return graph_to_dict(graph)

    def dependency_impact(self, service_id: str) -> dict[str, Any]:
        graph = load_dependency_graph(
            self.config.corpus_root / "config" / "dependency-graph.json",
            service_catalog_path=self.config.corpus_root / "config" / "service-capability-catalog.json",
            validate_schema=False,
        )
        return compute_impact(service_id, graph).to_dict()

    def disk_usage(self, vm_filter: list[str] | None = None) -> dict[str, Any]:
        from disk_metrics import query_disk_usage

        report = query_disk_usage(
            repo_root=self.config.corpus_root,
            vm_filter=vm_filter,
        )
        return report.to_dict()


def load_yaml(path: Path) -> Any:
    import yaml

    return yaml.safe_load(path.read_text())


def build_config() -> ServiceConfig:
    corpus_root = Path(os.environ.get("PLATFORM_CONTEXT_CORPUS_ROOT", "/srv/platform-context/corpus"))
    return ServiceConfig(
        api_token=os.environ["PLATFORM_CONTEXT_API_TOKEN"],
        corpus_root=corpus_root,
        error_registry_path=Path(
            os.environ.get("PLATFORM_CONTEXT_ERROR_REGISTRY_PATH", corpus_root / "config" / "error-codes.yaml")
        ),
        collection_name=os.environ.get("PLATFORM_CONTEXT_COLLECTION", DEFAULT_COLLECTION),
        qdrant_url=os.environ.get("PLATFORM_CONTEXT_QDRANT_URL"),
        qdrant_location=os.environ.get("PLATFORM_CONTEXT_QDRANT_LOCATION"),
        embedding_backend=os.environ.get("PLATFORM_CONTEXT_EMBEDDING_BACKEND", "sentence-transformers"),
        embedding_model=os.environ.get(
            "PLATFORM_CONTEXT_EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        ),
        embedding_dimension=int(os.environ.get("PLATFORM_CONTEXT_EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION))),
        ollama_url=os.environ.get("PLATFORM_CONTEXT_OLLAMA_URL"),
        prometheus_url=os.environ.get("PLATFORM_CONTEXT_PROMETHEUS_URL")
        or default_prometheus_url(stack_path=corpus_root / "versions" / "stack.yaml"),
        grafana_url=os.environ.get("PLATFORM_CONTEXT_GRAFANA_URL")
        or default_grafana_url(service_catalog_path=corpus_root / "config" / "service-capability-catalog.json"),
        memory_dsn=os.environ.get("PLATFORM_CONTEXT_MEMORY_DSN") or None,
        memory_collection_name=os.environ.get("PLATFORM_CONTEXT_MEMORY_COLLECTION", "serverclaw_memory"),
        memory_index_path=Path(
            os.environ.get(
                "PLATFORM_CONTEXT_MEMORY_INDEX_PATH",
                corpus_root / "build" / "serverclaw-memory-index" / "documents.json",
            )
        ),
    )


def build_service(config: ServiceConfig | None = None) -> PlatformContextService:
    return PlatformContextService(config or build_config())


app = FastAPI(title="LV3 Platform Context API", version="1.0.0")
service: PlatformContextService | None = None


def get_service() -> PlatformContextService:
    global service
    if service is None:
        service = build_service()
    return service


def request_trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "") or generate_trace_id()


def raise_platform_error(
    request: Request,
    code: str,
    *,
    message: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    error = get_service().error_registry.create(
        code,
        trace_id=request_trace_id(request),
        message=message,
        context=context,
    )
    raise PlatformHTTPError(error)


def validation_error_context(exc: RequestValidationError) -> dict[str, Any]:
    errors = exc.errors()
    if not errors:
        return {}
    first = errors[0]
    return {
        "field_path": ".".join(str(item) for item in first.get("loc", [])) or "request",
        "error_type": str(first.get("type") or "validation_error"),
        "validation_message": str(first.get("msg") or "request validation failed"),
    }


def require_auth(request: Request, authorization: str | None = Header(default=None)) -> None:
    current_service = get_service()
    if authorization != f"Bearer {current_service.config.api_token}":
        code = "AUTH_TOKEN_MISSING" if authorization is None else "AUTH_TOKEN_INVALID"
        message = "Bearer token is required for this endpoint." if authorization is None else "Bearer token is invalid."
        raise_platform_error(request, code, message=message, context={"header": "Authorization"})
    set_context(actor_id="platform-context-client")


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request.state.trace_id = request.headers.get("X-Trace-Id") or generate_trace_id()
    set_context(trace_id=request.state.trace_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        HTTP_LOGGER.exception(
            "Unhandled platform-context request failure",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": 500,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "target": request.url.path,
            },
        )
        clear_context()
        raise
    response.headers["X-Trace-Id"] = request.state.trace_id
    HTTP_LOGGER.info(
        "Request completed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
            "target": request.url.path,
        },
    )
    clear_context()
    return response


@app.exception_handler(PlatformHTTPError)
async def handle_platform_http_error(request: Request, exc: PlatformHTTPError) -> JSONResponse:
    response = JSONResponse(status_code=exc.error.http_status, content=exc.error.to_response())
    if exc.error.retry_after_s is not None:
        response.headers["Retry-After"] = str(exc.error.retry_after_s)
    return response


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    error = get_service().error_registry.create(
        "INPUT_SCHEMA_INVALID",
        trace_id=request_trace_id(request),
        message="Request payload or parameters failed validation.",
        context=validation_error_context(exc),
    )
    return JSONResponse(status_code=error.http_status, content=error.to_response())


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    error = get_service().error_registry.create(
        "INTERNAL_UNEXPECTED_ERROR",
        trace_id=request_trace_id(request),
        message="Unexpected internal platform-context error.",
        context={"detail": type(exc).__name__},
    )
    return JSONResponse(status_code=error.http_status, content=error.to_response())


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    current_service = get_service()
    return {
        "status": "ok",
        "collection": current_service.config.collection_name,
        "memory_collection": current_service.config.memory_collection_name,
        "memory_enabled": current_service.memory_store is not None,
    }


@app.get("/v1/platform-summary", dependencies=[Depends(require_auth)])
def platform_summary() -> dict[str, Any]:
    return get_service().platform_summary()


@app.get("/v1/platform/dependency-graph", dependencies=[Depends(require_auth)])
def platform_dependency_graph() -> dict[str, Any]:
    return get_service().dependency_graph()


@app.get("/v1/platform/dependency-graph/{service_id}/impact", dependencies=[Depends(require_auth)])
def platform_dependency_impact(service_id: str, request: Request) -> dict[str, Any]:
    try:
        return get_service().dependency_impact(service_id)
    except ValueError as exc:
        raise_platform_error(
            request,
            "INPUT_UNKNOWN_SERVICE",
            message=str(exc),
            context={"service_id": service_id},
        )


@app.get("/v1/receipts/recent", dependencies=[Depends(require_auth)])
def recent_receipts(limit: int = Query(default=5, ge=1, le=20)) -> dict[str, Any]:
    return get_service().recent_receipts(limit)


@app.get("/v1/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
def workflow_contract(workflow_id: str, request: Request) -> dict[str, Any]:
    try:
        return get_service().workflow_contract(workflow_id)
    except KeyError:
        raise_platform_error(
            request,
            "INPUT_UNKNOWN_WORKFLOW",
            message=f"Unknown workflow: {workflow_id}",
            context={"workflow_id": workflow_id},
        )


@app.get("/v1/commands/{command_id}", dependencies=[Depends(require_auth)])
def command_contract(command_id: str, request: Request) -> dict[str, Any]:
    try:
        return get_service().command_contract(command_id)
    except KeyError:
        raise_platform_error(
            request,
            "INPUT_UNKNOWN_COMMAND",
            message=f"Unknown command: {command_id}",
            context={"command_id": command_id},
        )


@app.get("/v1/platform/slos", dependencies=[Depends(require_auth)])
def platform_slos() -> dict[str, Any]:
    return get_service().slo_status()


@app.get("/v1/platform/disk-usage", dependencies=[Depends(require_auth)])
def platform_disk_usage(
    vm: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    return get_service().disk_usage(vm_filter=vm)


@app.post("/v1/context/query", dependencies=[Depends(require_auth)])
def query_context(request: QueryRequest) -> dict[str, Any]:
    return get_service().query(request.question, request.top_k)


@app.post("/v1/memory/entries", dependencies=[Depends(require_auth)])
def upsert_memory_entry(request: MemoryEntryRequest) -> dict[str, Any]:
    return get_service().upsert_memory_entry(request)


@app.get("/v1/memory/entries", dependencies=[Depends(require_auth)])
def list_memory_entries(
    scope_kind: Literal["owner", "workspace"],
    scope_id: str = Query(min_length=1, max_length=128),
    object_type: str | None = Query(default=None, min_length=2, max_length=64),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    return get_service().list_memory_entries(
        scope_kind=scope_kind,
        scope_id=scope_id,
        object_type=object_type,
        limit=limit,
    )


@app.get("/v1/memory/entries/{memory_id}", dependencies=[Depends(require_auth)])
def get_memory_entry(memory_id: str, request: Request) -> dict[str, Any]:
    payload = get_service().get_memory_entry(memory_id)
    if payload is None:
        raise_platform_error(
            request,
            "INPUT_UNKNOWN_MEMORY_ENTRY",
            message=f"Unknown memory entry: {memory_id}",
            context={"memory_id": memory_id},
        )
    return payload


@app.delete("/v1/memory/entries/{memory_id}", dependencies=[Depends(require_auth)])
def delete_memory_entry(memory_id: str, request: Request) -> dict[str, Any]:
    deleted = get_service().delete_memory_entry(memory_id)
    if not deleted:
        raise_platform_error(
            request,
            "INPUT_UNKNOWN_MEMORY_ENTRY",
            message=f"Unknown memory entry: {memory_id}",
            context={"memory_id": memory_id},
        )
    return {"deleted": True, "memory_id": memory_id}


@app.post("/v1/memory/query", dependencies=[Depends(require_auth)])
def query_memory(request: MemoryQueryRequest) -> dict[str, Any]:
    return get_service().query_memory(request)


@app.post("/v1/admin/rebuild", dependencies=[Depends(require_auth)])
def rebuild_index(request: RebuildRequest) -> dict[str, Any]:
    return get_service().rebuild(request.chunks, replace=request.replace)


@app.post("/v1/admin/rebuild-local", dependencies=[Depends(require_auth)])
def rebuild_local() -> dict[str, Any]:
    return get_service().rebuild_from_local_corpus()
