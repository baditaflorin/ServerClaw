from __future__ import annotations

from pathlib import Path

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import first_heading, read_text


def collect(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    for path in sorted((repo_root / "docs" / "runbooks").glob("*.md")):
        text = read_text(path)
        relative_path = relative_url(repo_root, path)
        documents.append(
            build_document(
                collection="runbooks",
                doc_id=f"runbook:{path.stem}",
                title=first_heading(text, path.stem.replace("-", " ")),
                body=text,
                url=relative_path,
                metadata={
                    "source_path": relative_path,
                    "slug": path.stem,
                    "tags": path.stem.replace("-", " "),
                },
            )
        )
    return documents
