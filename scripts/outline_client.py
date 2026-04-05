#!/usr/bin/env python3
"""Shared Outline API client and helpers for LV3 platform scripts."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_BASE_URL = "https://wiki.lv3.org"
DEFAULT_TOKEN_FILE = Path(".local/outline/api-token.txt")
UUID_NAMESPACE = uuid.UUID("e7dc945f-7c87-4a79-aaab-9a1c6655a7aa")


class OutlineError(RuntimeError):
    pass


class OutlineClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_token: str | None = None,
        app_token: str | None = None,
        opener: request.OpenerDirector | None = None,
        csrf_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.app_token = app_token
        self.opener = opener
        self.csrf_token = csrf_token

    def call(self, endpoint: str, payload: dict[str, Any], *, use_app_token: bool = False) -> dict[str, Any]:
        import time
        body = json.dumps(payload).encode("utf-8")
        token = self.app_token if use_app_token else self.api_token
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token
        req = request.Request(
            f"{self.base_url}/api/{endpoint}",
            data=body,
            headers=headers,
            method="POST",
        )
        for attempt in range(4):
            try:
                if self.opener is not None:
                    response_ctx = self.opener.open(req, timeout=60)
                else:
                    response_ctx = request.urlopen(req, timeout=60)  # noqa: S310
                with response_ctx as response:
                    return json.loads(response.read().decode("utf-8"))
            except error.HTTPError as exc:  # noqa: PERF203
                if exc.code == 429 and attempt < 3:
                    wait = 30 * (attempt + 1)
                    time.sleep(wait)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")
                raise OutlineError(f"{endpoint} failed with HTTP {exc.code}: {detail}") from exc
        raise OutlineError(f"{endpoint} failed: exhausted retries")


def deterministic_id(prefix: str, value: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{prefix}:{value}"))


def load_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_api_token(path: Path) -> str:
    if not path.exists():
        raise OutlineError(f"missing API token file: {path}")
    return load_file(path)


def collections_by_name(client: OutlineClient) -> dict[str, dict[str, Any]]:
    response = client.call("collections.list", {})
    return {item["name"]: item for item in response.get("data", [])}


def documents_in_collection(client: OutlineClient, collection_id: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    offset = 0
    limit = 100
    while True:
        response = client.call(
            "documents.list",
            {"collectionId": collection_id, "limit": limit, "offset": offset},
        )
        page = response.get("data", [])
        docs.extend(page)
        if len(page) < limit:
            break
        offset += limit
    return docs


def ensure_document(
    client: OutlineClient,
    *,
    collection_id: str,
    title: str,
    markdown: str,
    dry_run: bool,
) -> str:
    matching = [item for item in documents_in_collection(client, collection_id) if item.get("title") == title]
    current = matching[0] if matching else None
    duplicates = matching[1:]
    if dry_run:
        return "updated" if current else "created"
    if current:
        client.call(
            "documents.update",
            {
                "id": current["id"],
                "title": title,
                "text": markdown,
                "publish": True,
                "done": True,
            },
        )
        outcome = "updated"
    else:
        client.call(
            "documents.create",
            {
                "collectionId": collection_id,
                "title": title,
                "text": markdown,
                "publish": True,
            },
        )
        outcome = "created"
    for duplicate in duplicates:
        client.call("documents.delete", {"id": duplicate["id"]})
    return outcome
