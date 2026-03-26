from __future__ import annotations

from pathlib import Path

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import flatten_text, load_json


def collect(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    receipts_root = repo_root / "receipts"
    if not receipts_root.exists():
        return documents
    for path in sorted(receipts_root.rglob("*.json")):
        payload = load_json(path, {})
        if not isinstance(payload, dict) or not payload:
            continue
        relative_path = relative_url(repo_root, path)
        title = str(payload.get("summary") or payload.get("receipt_id") or path.stem)
        body = "\n".join(
            item
            for item in [
                title,
                str(payload.get("workflow_id", "")),
                flatten_text(payload.get("targets")),
                flatten_text(payload.get("summary")),
                flatten_text(payload.get("result")),
            ]
            if item
        )
        documents.append(
            build_document(
                collection="receipts",
                doc_id=f"receipt:{relative_path}",
                title=title,
                body=body,
                url=relative_path,
                metadata={
                    "source_path": relative_path,
                    "workflow_id": payload.get("workflow_id"),
                    "recorded_on": payload.get("recorded_on") or payload.get("applied_on"),
                },
            )
        )
    return documents
