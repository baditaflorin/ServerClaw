from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SearchDocument:
    doc_id: str
    collection: str
    title: str
    body: str
    url: str | None
    metadata: dict[str, Any]
    indexed_at: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchResult:
    doc_id: str
    collection: str
    title: str
    url: str | None
    metadata: dict[str, Any]
    score: float
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
