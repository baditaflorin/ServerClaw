from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import SearchDocument
from ..utils import sha256_text, truncate_body, utc_now_iso


def relative_url(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def build_document(
    *,
    collection: str,
    doc_id: str,
    title: str,
    body: str,
    url: str | None,
    metadata: dict[str, Any],
) -> SearchDocument:
    normalized_body = truncate_body(body)
    return SearchDocument(
        doc_id=doc_id,
        collection=collection,
        title=title.strip(),
        body=normalized_body,
        url=url,
        metadata=metadata,
        indexed_at=utc_now_iso(),
        content_hash=sha256_text(collection, doc_id, title, normalized_body, str(sorted(metadata.items()))),
    )
