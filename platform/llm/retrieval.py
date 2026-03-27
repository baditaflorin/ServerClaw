from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


RequestJson = Callable[[str, str, dict[str, Any] | None, dict[str, str] | None, float], dict[str, Any]]

DEFAULT_PLATFORM_CONTEXT_URL = "http://100.64.0.1:8010"
DEFAULT_PLATFORM_CONTEXT_TOKEN_PATH = Path(
    "/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/platform-context/api-token.txt"
)


@dataclass(frozen=True)
class RetrievalMatch:
    score: float
    source_path: str
    document_kind: str | None
    document_title: str | None
    section_heading: str | None
    adr_number: str | None
    content: str


def default_platform_context_url() -> str:
    return os.environ.get("LV3_PLATFORM_CONTEXT_API_URL", DEFAULT_PLATFORM_CONTEXT_URL).rstrip("/")


def default_platform_context_token_file() -> Path:
    configured = os.environ.get("LV3_PLATFORM_CONTEXT_API_TOKEN_FILE", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_PLATFORM_CONTEXT_TOKEN_PATH


def read_token(path: Path) -> str:
    token = path.expanduser().read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError(f"platform context token file is empty: {path}")
    return token


def default_request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    headers: dict[str, str] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, method=method, data=body, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised through caller behavior
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {urllib.parse.urlsplit(url).path} returned HTTP {exc.code}: {detail}") from exc


class PlatformContextRetriever:
    def __init__(
        self,
        *,
        api_url: str | None = None,
        token_file: Path | str | None = None,
        timeout_seconds: float = 10.0,
        request_json: RequestJson | None = None,
    ) -> None:
        self.api_url = (api_url or default_platform_context_url()).rstrip("/")
        self.token_file = Path(token_file).expanduser() if token_file else default_platform_context_token_file()
        self.timeout_seconds = timeout_seconds
        self._request_json = request_json or default_request_json

    def retrieve_payload(self, query: str, *, top_k: int = 5) -> dict[str, Any]:
        token = read_token(self.token_file)
        return self._request_json(
            "POST",
            f"{self.api_url}/v1/context/query",
            {"question": query, "top_k": top_k},
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            self.timeout_seconds,
        )

    def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievalMatch]:
        payload = self.retrieve_payload(query, top_k=top_k)
        matches = payload.get("matches", [])
        if not isinstance(matches, list):
            return []
        results: list[RetrievalMatch] = []
        for item in matches:
            if not isinstance(item, dict):
                continue
            results.append(
                RetrievalMatch(
                    score=float(item.get("score", 0.0) or 0.0),
                    source_path=str(item.get("source_path", "") or ""),
                    document_kind=str(item.get("document_kind")) if item.get("document_kind") is not None else None,
                    document_title=str(item.get("document_title")) if item.get("document_title") is not None else None,
                    section_heading=str(item.get("section_heading")) if item.get("section_heading") is not None else None,
                    adr_number=str(item.get("adr_number")) if item.get("adr_number") is not None else None,
                    content=str(item.get("content", "") or ""),
                )
            )
        return results


def render_context_block(matches: list[RetrievalMatch]) -> str:
    if not matches:
        return ""
    lines = [
        "Use this retrieved platform context when it is relevant and prefer it over unstated assumptions.",
        "",
        "Retrieved platform context:",
    ]
    for index, match in enumerate(matches, start=1):
        citation_parts = [match.source_path]
        if match.adr_number:
            citation_parts.append(f"ADR {match.adr_number}")
        if match.section_heading:
            citation_parts.append(match.section_heading)
        lines.append(f"[{index}] {' | '.join(part for part in citation_parts if part)}")
        lines.append(match.content.strip())
        lines.append("")
    return "\n".join(lines).strip()
