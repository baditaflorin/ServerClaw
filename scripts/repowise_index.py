#!/usr/bin/env python3
"""
repowise_index.py — build or rebuild the repowise semantic index.

Usage:
    python3 scripts/repowise_index.py [--repo-root PATH] [--qdrant-url URL]
                                      [--ollama-url URL] [--model MODEL]
                                      [--collection NAME] [--rebuild]

Environment variables (override defaults):
    REPOWISE_QDRANT_URL    Qdrant HTTP URL  (default: http://127.0.0.1:6333)
    REPOWISE_OLLAMA_URL    Ollama HTTP URL  (default: http://127.0.0.1:11434)
    REPOWISE_MODEL         Embedding model  (default: nomic-embed-text)
    REPOWISE_COLLECTION    Qdrant collection (default: repowise)
    REPOWISE_REPO_ROOT     Repo root path   (default: parent of this script)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Inline OllamaEmbedder (no import from platform_context_service needed)
# ---------------------------------------------------------------------------

import urllib.error
import urllib.request

EMBED_BATCH_SIZE = 32


class OllamaEmbedder:
    def __init__(self, base_url: str, model_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def _request(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
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
        for attempt in range(5):
            try:
                return self._extract(self._request("/api/embed", {"model": self.model_name, "input": texts}))
            except Exception:
                if attempt < 4:
                    import time as _t

                    _t.sleep(10 * (attempt + 1))
        if len(texts) == 1:
            for attempt in range(3):
                try:
                    return self._extract(
                        self._request("/api/embeddings", {"model": self.model_name, "prompt": texts[0]})
                    )
                except Exception:
                    if attempt < 2:
                        import time as _t

                        _t.sleep(15)
            raise RuntimeError("Ollama embed failed after retries for single text")
        mid = max(1, len(texts) // 2)
        return self._embed_batch(texts[:mid]) + self._embed_batch(texts[mid:])

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            out.extend(self._embed_batch(batch))
        return out

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def dimension(self) -> int:
        """Probe the model to get embedding dimension."""
        vec = self.embed_one("probe")
        return len(vec)


# ---------------------------------------------------------------------------
# Qdrant helpers (raw HTTP — no qdrant-client required)
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
            with urllib.request.urlopen(req, timeout=60) as resp:
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

    def delete_collection(self, name: str) -> None:
        self._request("DELETE", f"/collections/{name}")

    def create_collection(self, name: str, dimension: int) -> None:
        self._request(
            "PUT",
            f"/collections/{name}",
            {
                "vectors": {"size": dimension, "distance": "Cosine"},
            },
        )

    def upsert(self, collection: str, points: list[dict]) -> None:
        self._request("PUT", f"/collections/{collection}/points", {"points": points})

    def search(self, collection: str, vector: list[float], top_k: int = 8) -> list[dict]:
        resp = self._request(
            "POST",
            f"/collections/{collection}/points/search",
            {
                "vector": vector,
                "limit": top_k,
                "with_payload": True,
                "with_vector": False,
            },
        )
        return resp.get("result", [])

    def count(self, collection: str) -> int:
        resp = self._request("GET", f"/collections/{collection}")
        return resp.get("result", {}).get("points_count", 0)


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------


def build_index(
    repo_root: Path,
    qdrant: QdrantHTTP,
    embedder: OllamaEmbedder,
    collection: str,
    rebuild: bool = True,
) -> dict:
    # Import corpus builder (same directory as this script)
    sys.path.insert(0, str(repo_root / "scripts"))
    from repowise_corpus import build_chunks, build_manifest

    print("Building corpus…", flush=True)
    t0 = time.time()
    chunks = build_chunks(repo_root)
    manifest = build_manifest(repo_root, chunks)
    print(
        f"  {manifest['total_chunks']} chunks from {manifest['total_files']} files in {time.time() - t0:.1f}s",
        flush=True,
    )
    print(f"  By language: {manifest['by_language']}", flush=True)

    if not chunks:
        print("No chunks produced — check INDEX_DIRS in repowise_corpus.py", flush=True)
        return manifest

    # Detect dimension
    print(f"Detecting embedding dimension for {embedder.model_name}…", flush=True)
    dim = embedder.dimension()
    print(f"  Dimension: {dim}", flush=True)

    # Prepare collection
    if rebuild and qdrant.collection_exists(collection):
        print(f"Dropping existing collection '{collection}'…", flush=True)
        qdrant.delete_collection(collection)
    if not qdrant.collection_exists(collection):
        print(f"Creating collection '{collection}' (dim={dim})…", flush=True)
        qdrant.create_collection(collection, dim)

    # Embed and upsert in batches
    UPSERT_BATCH = 64
    total = len(chunks)
    print(f"Embedding {total} chunks…", flush=True)
    t1 = time.time()

    for batch_start in range(0, total, UPSERT_BATCH):
        batch = chunks[batch_start : batch_start + UPSERT_BATCH]
        texts = [c["text"] for c in batch]
        vectors = embedder.embed(texts)
        points = [
            {
                "id": _chunk_uuid(c["id"]),
                "vector": vec,
                "payload": {
                    "text": c["text"],
                    "file_path": c["file_path"],
                    "language": c["language"],
                    "document_kind": c["document_kind"],
                    "chunk_type": c["chunk_type"],
                    "chunk_name": c["chunk_name"],
                    "start_line": c["start_line"],
                },
            }
            for c, vec in zip(batch, vectors, strict=False)
        ]
        qdrant.upsert(collection, points)
        done = min(batch_start + UPSERT_BATCH, total)
        elapsed = time.time() - t1
        print(f"  {done}/{total} ({done * 100 // total}%) — {elapsed:.0f}s elapsed", flush=True)

    total_time = time.time() - t0
    indexed_count = qdrant.count(collection)
    print(f"\nDone. {indexed_count} points in '{collection}' — {total_time:.1f}s total", flush=True)
    manifest["indexed_count"] = indexed_count
    manifest["elapsed_seconds"] = round(total_time, 1)
    return manifest


def _chunk_uuid(chunk_id: str) -> str:
    """Convert our hex-based UUID string to an integer for Qdrant (uint64)."""
    # Qdrant accepts string UUIDs or unsigned integers
    return chunk_id


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the repowise semantic index.")
    parser.add_argument("--repo-root", default=os.environ.get("REPOWISE_REPO_ROOT", ""))
    parser.add_argument("--qdrant-url", default=os.environ.get("REPOWISE_QDRANT_URL", "http://127.0.0.1:6333"))
    parser.add_argument("--ollama-url", default=os.environ.get("REPOWISE_OLLAMA_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--model", default=os.environ.get("REPOWISE_MODEL", "nomic-embed-text"))
    parser.add_argument("--collection", default=os.environ.get("REPOWISE_COLLECTION", "repowise"))
    parser.add_argument("--no-rebuild", action="store_true", help="Append to existing collection instead of rebuilding")
    parser.add_argument("--manifest-out", default="", help="Write manifest JSON to this path")
    args = parser.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parent.parent

    print(f"Repo root:   {repo_root}", flush=True)
    print(f"Qdrant:      {args.qdrant_url}", flush=True)
    print(f"Ollama:      {args.ollama_url}", flush=True)
    print(f"Model:       {args.model}", flush=True)
    print(f"Collection:  {args.collection}", flush=True)
    print(f"Rebuild:     {not args.no_rebuild}", flush=True)
    print()

    qdrant = QdrantHTTP(args.qdrant_url)
    embedder = OllamaEmbedder(args.ollama_url, args.model)

    manifest = build_index(
        repo_root=repo_root,
        qdrant=qdrant,
        embedder=embedder,
        collection=args.collection,
        rebuild=not args.no_rebuild,
    )

    if args.manifest_out:
        Path(args.manifest_out).write_text(json.dumps(manifest, indent=2))
        print(f"Manifest written to {args.manifest_out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
