from __future__ import annotations

import re
from pathlib import Path

from .common import build_document, relative_url
from ..models import SearchDocument
from ..utils import first_heading, metadata_from_markdown, read_text


ADR_NUMBER_PATTERN = re.compile(r"(?P<number>\d{4})-")


def collect(repo_root: Path) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    for path in sorted((repo_root / "docs" / "adr").glob("*.md")):
        text = read_text(path)
        relative_path = relative_url(repo_root, path)
        title = first_heading(text, path.stem.replace("-", " "))
        metadata = metadata_from_markdown(text)
        match = ADR_NUMBER_PATTERN.match(path.name)
        if match:
            metadata["adr_number"] = match.group("number")
        metadata["source_path"] = relative_path
        documents.append(
            build_document(
                collection="adrs",
                doc_id=f"adr:{metadata.get('adr_number', path.stem)}",
                title=title,
                body=text,
                url=relative_path,
                metadata=metadata,
            )
        )
    return documents
