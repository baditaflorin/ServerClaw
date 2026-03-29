from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from platform.llm.retrieval import (
    RequestJson,
    default_platform_context_token_file,
    default_platform_context_url,
    default_request_json,
    read_token,
)


class MemorySubstrateClient:
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

    def _headers(self) -> dict[str, str]:
        token = read_token(self.token_file)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def upsert_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"{self.api_url}/v1/memory/entries",
            payload,
            self._headers(),
            self.timeout_seconds,
        )

    def get_entry(self, memory_id: str) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.api_url}/v1/memory/entries/{urllib.parse.quote(memory_id, safe='')}",
            None,
            self._headers(),
            self.timeout_seconds,
        )

    def list_entries(
        self,
        *,
        scope_kind: str,
        scope_id: str,
        object_type: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        params = {
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "limit": str(limit),
        }
        if object_type:
            params["object_type"] = object_type
        return self._request_json(
            "GET",
            f"{self.api_url}/v1/memory/entries?{urllib.parse.urlencode(params)}",
            None,
            self._headers(),
            self.timeout_seconds,
        )

    def delete_entry(self, memory_id: str) -> dict[str, Any]:
        return self._request_json(
            "DELETE",
            f"{self.api_url}/v1/memory/entries/{urllib.parse.quote(memory_id, safe='')}",
            None,
            self._headers(),
            self.timeout_seconds,
        )

    def query(
        self,
        query: str,
        *,
        scope_kind: str,
        scope_id: str,
        object_type: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "limit": limit,
        }
        if object_type:
            payload["object_type"] = object_type
        return self._request_json(
            "POST",
            f"{self.api_url}/v1/memory/query",
            payload,
            self._headers(),
            self.timeout_seconds,
        )
