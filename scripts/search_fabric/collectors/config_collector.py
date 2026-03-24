from __future__ import annotations

from pathlib import Path

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import read_text


ALLOWED_SUFFIXES = {".json", ".yaml", ".yml"}


def collect(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    for path in sorted((repo_root / "config").glob("*")):
        if path.is_dir() or path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        relative_path = relative_url(repo_root, path)
        documents.append(
            build_document(
                collection="configs",
                doc_id=f"config:{path.name}",
                title=path.name,
                body=read_text(path),
                url=relative_path,
                metadata={
                    "source_path": relative_path,
                    "suffix": path.suffix.lower(),
                },
            )
        )
    return documents
