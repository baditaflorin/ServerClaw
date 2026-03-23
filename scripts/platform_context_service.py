#!/usr/bin/env python3

import json
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from platform_context_corpus import build_chunks


DEFAULT_COLLECTION = "platform_context"
DEFAULT_DIMENSION = 384
LOGGER = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int = Field(default=5, ge=1, le=10)


class RebuildRequest(BaseModel):
    replace: bool = True
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    manifest: dict[str, Any] | None = None


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


@dataclass
class ServiceConfig:
    api_token: str
    corpus_root: Path
    collection_name: str
    qdrant_url: str | None
    qdrant_location: str | None
    embedding_backend: str
    embedding_model: str
    embedding_dimension: int


class PlatformContextService:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.client = self._build_client()
        self.embedder = self._build_embedder()
        self.ensure_collection()

    def _build_client(self) -> QdrantClient:
        if self.config.qdrant_location:
            return QdrantClient(location=self.config.qdrant_location)
        return QdrantClient(url=self.config.qdrant_url)

    def _build_embedder(self) -> TokenHashEmbedder | SentenceTransformersEmbedder:
        if self.config.embedding_backend == "token-hash":
            return TokenHashEmbedder(self.config.embedding_dimension)
        if self.config.embedding_backend == "sentence-transformers":
            try:
                return SentenceTransformersEmbedder(self.config.embedding_model)
            except Exception as exc:
                LOGGER.warning(
                    "Falling back to token-hash embeddings because %s could not be initialized: %s",
                    self.config.embedding_model,
                    exc,
                )
                return TokenHashEmbedder(self.config.embedding_dimension)
        raise ValueError(f"unsupported embedding backend: {self.config.embedding_backend}")

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.config.collection_name):
            return
        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config=VectorParams(
                size=self.config.embedding_dimension,
                distance=Distance.COSINE,
            ),
        )

    def rebuild(self, chunks: list[dict[str, Any]], *, replace: bool = True) -> dict[str, Any]:
        if replace:
            self.ensure_collection()
        if not chunks:
            return {"collection_name": self.config.collection_name, "indexed_chunks": 0}
        embeddings = self.embedder.embed_documents([chunk["content"] for chunk in chunks])
        points = [
            PointStruct(
                id=chunk["chunk_id"],
                vector=embeddings[index],
                payload={
                    key: value
                    for key, value in chunk.items()
                    if key != "chunk_id"
                },
            )
            for index, chunk in enumerate(chunks)
        ]
        self.client.upsert(collection_name=self.config.collection_name, points=points)
        return {
            "collection_name": self.config.collection_name,
            "indexed_chunks": len(chunks),
        }

    def rebuild_from_local_corpus(self) -> dict[str, Any]:
        chunks = build_chunks(self.config.corpus_root)
        result = self.rebuild(chunks, replace=True)
        result["source"] = str(self.config.corpus_root)
        return result

    def query(self, question: str, top_k: int) -> dict[str, Any]:
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
        return {
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
        }

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
        stack = json.loads(json.dumps(load_yaml(self.config.corpus_root / "versions" / "stack.yaml")))
        observed = stack.get("observed_state", {})
        return {
            "repo_version": version,
            "platform_version": stack.get("platform_version"),
            "checked_at": observed.get("checked_at"),
            "proxmox_version": observed.get("proxmox", {}).get("version"),
            "open_webui_url": observed.get("open_webui", {}).get("host_tailscale_proxy_url"),
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


def load_yaml(path: Path) -> Any:
    import yaml

    return yaml.safe_load(path.read_text())


def build_config() -> ServiceConfig:
    return ServiceConfig(
        api_token=os.environ["PLATFORM_CONTEXT_API_TOKEN"],
        corpus_root=Path(os.environ.get("PLATFORM_CONTEXT_CORPUS_ROOT", "/srv/platform-context/corpus")),
        collection_name=os.environ.get("PLATFORM_CONTEXT_COLLECTION", DEFAULT_COLLECTION),
        qdrant_url=os.environ.get("PLATFORM_CONTEXT_QDRANT_URL"),
        qdrant_location=os.environ.get("PLATFORM_CONTEXT_QDRANT_LOCATION"),
        embedding_backend=os.environ.get("PLATFORM_CONTEXT_EMBEDDING_BACKEND", "sentence-transformers"),
        embedding_model=os.environ.get(
            "PLATFORM_CONTEXT_EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        ),
        embedding_dimension=int(
            os.environ.get("PLATFORM_CONTEXT_EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION))
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


def require_auth(authorization: str | None = Header(default=None)) -> None:
    current_service = get_service()
    if authorization != f"Bearer {current_service.config.api_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    current_service = get_service()
    return {"status": "ok", "collection": current_service.config.collection_name}


@app.get("/v1/platform-summary", dependencies=[Depends(require_auth)])
def platform_summary() -> dict[str, Any]:
    return get_service().platform_summary()


@app.get("/v1/receipts/recent", dependencies=[Depends(require_auth)])
def recent_receipts(limit: int = Query(default=5, ge=1, le=20)) -> dict[str, Any]:
    return get_service().recent_receipts(limit)


@app.get("/v1/workflows/{workflow_id}", dependencies=[Depends(require_auth)])
def workflow_contract(workflow_id: str) -> dict[str, Any]:
    try:
        return get_service().workflow_contract(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown workflow: {workflow_id}") from exc


@app.get("/v1/commands/{command_id}", dependencies=[Depends(require_auth)])
def command_contract(command_id: str) -> dict[str, Any]:
    try:
        return get_service().command_contract(command_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown command: {command_id}") from exc


@app.post("/v1/context/query", dependencies=[Depends(require_auth)])
def query_context(request: QueryRequest) -> dict[str, Any]:
    return get_service().query(request.question, request.top_k)


@app.post("/v1/admin/rebuild", dependencies=[Depends(require_auth)])
def rebuild_index(request: RebuildRequest) -> dict[str, Any]:
    return get_service().rebuild(request.chunks, replace=request.replace)


@app.post("/v1/admin/rebuild-local", dependencies=[Depends(require_auth)])
def rebuild_local() -> dict[str, Any]:
    return get_service().rebuild_from_local_corpus()
