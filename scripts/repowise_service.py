#!/usr/bin/env python3
"""
repowise_service.py — FastAPI semantic search service for the git repository.

Provides:
  GET  /health          liveness / readiness
  POST /search          semantic search over indexed code/docs
  POST /rebuild         trigger corpus re-index (async, returns job id)
  GET  /rebuild/{id}    poll rebuild status

Environment variables:
  REPOWISE_QDRANT_URL    http://127.0.0.1:6333
  REPOWISE_OLLAMA_URL    http://127.0.0.1:11434
  REPOWISE_MODEL         nomic-embed-text
  REPOWISE_COLLECTION    repowise
  REPOWISE_REPO_ROOT     (default: parent of scripts/)
  REPOWISE_API_TOKEN     bearer token (optional, skip auth if unset)
  REPOWISE_PORT          8080
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Embedder (self-contained, no platform_context_service import)
# ---------------------------------------------------------------------------

EMBED_BATCH_SIZE = 32


class OllamaEmbedder:
    def __init__(self, base_url: str, model_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self._dim: int | None = None

    def _request(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            return json.loads(resp.read().decode())

    @staticmethod
    def _extract(payload: dict) -> list[list[float]]:
        if isinstance(payload.get("embeddings"), list):
            return [[float(v) for v in vec] for vec in payload["embeddings"]]
        if isinstance(payload.get("embedding"), list):
            return [[float(v) for v in payload["embedding"]]]
        raise RuntimeError("no embeddings in Ollama response")

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return self._extract(self._request("/api/embed", {"model": self.model_name, "input": texts}))
        except Exception:
            if len(texts) == 1:
                return self._extract(self._request("/api/embeddings", {"model": self.model_name, "prompt": texts[0]}))
            mid = max(1, len(texts) // 2)
            return self._embed_batch(texts[:mid]) + self._embed_batch(texts[mid:])

    def embed_one(self, text: str) -> list[float]:
        vecs = []
        for i in range(0, 1, EMBED_BATCH_SIZE):
            vecs.extend(self._embed_batch([text]))
        return vecs[0]

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed_one("probe"))
        return self._dim


# ---------------------------------------------------------------------------
# Qdrant HTTP client
# ---------------------------------------------------------------------------


class QdrantHTTP:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            method=method,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Qdrant {method} {path} → {exc.code}: {body}") from exc

    def collection_exists(self, name: str) -> bool:
        try:
            self._request("GET", f"/collections/{name}")
            return True
        except RuntimeError:
            return False

    def count(self, name: str) -> int:
        try:
            resp = self._request("GET", f"/collections/{name}")
            return resp.get("result", {}).get("points_count", 0)
        except RuntimeError:
            return 0

    def search(self, collection: str, vector: list[float], top_k: int, filters: dict | None = None) -> list[dict]:
        payload: dict[str, Any] = {
            "vector": vector,
            "limit": top_k,
            "with_payload": True,
            "with_vector": False,
        }
        if filters:
            payload["filter"] = filters
        resp = self._request("POST", f"/collections/{collection}/points/search", payload)
        return resp.get("result", [])


# ---------------------------------------------------------------------------
# Config / app state
# ---------------------------------------------------------------------------


@dataclass
class Config:
    qdrant_url: str
    ollama_url: str
    model: str
    collection: str
    repo_root: Path
    api_token: str | None


@dataclass
class RebuildJob:
    job_id: str
    status: str = "running"  # running | done | error
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    manifest: dict | None = None
    error: str | None = None


_config: Config | None = None
_embedder: OllamaEmbedder | None = None
_qdrant: QdrantHTTP | None = None
_rebuild_jobs: dict[str, RebuildJob] = {}

app = FastAPI(title="Repowise", description="Semantic code search for the lv3 platform repository")


def _get_config() -> Config:
    if _config is None:
        raise RuntimeError("service not initialised")
    return _config


def _get_embedder() -> OllamaEmbedder:
    if _embedder is None:
        raise RuntimeError("embedder not initialised")
    return _embedder


def _get_qdrant() -> QdrantHTTP:
    if _qdrant is None:
        raise RuntimeError("qdrant not initialised")
    return _qdrant


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _require_auth(authorization: str | None = Header(default=None)) -> None:
    cfg = _get_config()
    if not cfg.api_token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != cfg.api_token:
        raise HTTPException(status_code=403, detail="invalid token")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)
    language: str | None = Field(default=None, description="Filter by language: python, yaml, markdown, …")
    document_kind: str | None = Field(default=None, description="Filter by kind: script, ansible_role, adr, …")


class SearchResult(BaseModel):
    score: float
    file_path: str
    language: str
    document_kind: str
    chunk_type: str
    chunk_name: str
    start_line: int
    text: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    collection_size: int


class RebuildRequest(BaseModel):
    pass


class RebuildResponse(BaseModel):
    job_id: str
    status: str


class RebuildStatusResponse(BaseModel):
    job_id: str
    status: str
    elapsed_seconds: float | None = None
    manifest: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    cfg = _get_config()
    qdrant = _get_qdrant()
    count = qdrant.count(cfg.collection)
    return {
        "status": "ok",
        "collection": cfg.collection,
        "indexed_chunks": count,
        "model": cfg.model,
    }


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, _auth: None = Depends(_require_auth)) -> SearchResponse:
    embedder = _get_embedder()
    qdrant = _get_qdrant()
    cfg = _get_config()

    try:
        vector = embedder.embed_one(req.query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"embedding failed: {exc}") from exc

    # Build optional filters
    filters: dict | None = None
    conditions = []
    if req.language:
        conditions.append({"key": "language", "match": {"value": req.language}})
    if req.document_kind:
        conditions.append({"key": "document_kind", "match": {"value": req.document_kind}})
    if conditions:
        filters = {"must": conditions}

    try:
        hits = qdrant.search(cfg.collection, vector, top_k=req.top_k, filters=filters)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"qdrant search failed: {exc}") from exc

    results = [
        SearchResult(
            score=round(float(h.get("score", 0)), 4),
            file_path=h["payload"]["file_path"],
            language=h["payload"]["language"],
            document_kind=h["payload"]["document_kind"],
            chunk_type=h["payload"]["chunk_type"],
            chunk_name=h["payload"]["chunk_name"],
            start_line=h["payload"].get("start_line", 0),
            text=h["payload"]["text"],
        )
        for h in hits
    ]

    return SearchResponse(
        query=req.query,
        results=results,
        collection_size=qdrant.count(cfg.collection),
    )


@app.post("/rebuild", response_model=RebuildResponse)
def rebuild(_req: RebuildRequest, _auth: None = Depends(_require_auth)) -> RebuildResponse:
    cfg = _get_config()
    job_id = str(uuid.uuid4())
    job = RebuildJob(job_id=job_id)
    _rebuild_jobs[job_id] = job

    def _run() -> None:
        try:
            sys.path.insert(0, str(cfg.repo_root / "scripts"))
            from repowise_index import build_index  # type: ignore[import]

            qdrant = _get_qdrant()
            embedder = _get_embedder()
            manifest = build_index(
                repo_root=cfg.repo_root,
                qdrant=qdrant,
                embedder=embedder,
                collection=cfg.collection,
                rebuild=True,
            )
            job.status = "done"
            job.manifest = manifest
        except Exception as exc:
            job.status = "error"
            job.error = str(exc)
        finally:
            job.finished_at = time.time()

    threading.Thread(target=_run, daemon=True).start()
    return RebuildResponse(job_id=job_id, status="running")


@app.get("/rebuild/{job_id}", response_model=RebuildStatusResponse)
def rebuild_status(job_id: str, _auth: None = Depends(_require_auth)) -> RebuildStatusResponse:
    job = _rebuild_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    elapsed = (job.finished_at or time.time()) - job.started_at
    return RebuildStatusResponse(
        job_id=job.job_id,
        status=job.status,
        elapsed_seconds=round(elapsed, 1),
        manifest=job.manifest,
        error=job.error,
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def _init_globals() -> None:
    global _config, _embedder, _qdrant
    repo_root_str = os.environ.get("REPOWISE_REPO_ROOT", "")
    repo_root = Path(repo_root_str) if repo_root_str else Path(__file__).resolve().parent.parent
    _config = Config(
        qdrant_url=os.environ.get("REPOWISE_QDRANT_URL", "http://127.0.0.1:6333"),
        ollama_url=os.environ.get("REPOWISE_OLLAMA_URL", "http://127.0.0.1:11434"),
        model=os.environ.get("REPOWISE_MODEL", "nomic-embed-text"),
        collection=os.environ.get("REPOWISE_COLLECTION", "repowise"),
        repo_root=repo_root,
        api_token=os.environ.get("REPOWISE_API_TOKEN") or None,
    )
    _embedder = OllamaEmbedder(_config.ollama_url, _config.model)
    _qdrant = QdrantHTTP(_config.qdrant_url)


_init_globals()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("REPOWISE_PORT", "8080"))
    uvicorn.run("repowise_service:app", host="0.0.0.0", port=port, reload=False)  # noqa: S104
