from __future__ import annotations

from pathlib import Path

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import flatten_text, load_json


def collect(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    candidate_roots = [repo_root / "cases", repo_root / "receipts" / "failure-cases"]
    for root in candidate_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.json")):
            payload = load_json(path, {})
            if not isinstance(payload, dict):
                continue
            relative_path = relative_url(repo_root, path)
            title = str(payload.get("title") or path.stem)
            body = "\n".join(
                item
                for item in [
                    title,
                    flatten_text(payload.get("symptoms")),
                    flatten_text(payload.get("root_cause")),
                    flatten_text(payload.get("remediation_steps")),
                ]
                if item
            )
            documents.append(
                build_document(
                    collection="failure_cases",
                    doc_id=f"case:{relative_path}",
                    title=title,
                    body=body,
                    url=relative_path,
                    metadata={
                        "source_path": relative_path,
                        "root_cause_category": payload.get("root_cause_category"),
                        "service": payload.get("service"),
                    },
                )
            )
    return documents
