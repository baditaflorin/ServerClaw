#!/usr/bin/env python3
"""Shared Outline API client and helpers for LV3 platform scripts."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from platform.retry import MaxRetriesExceeded, PlatformRetryError, RetryPolicy, with_retry

DEFAULT_BASE_URL = "https://wiki.localhost"
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
        retry_count = 0

        def call_once() -> dict[str, Any]:
            nonlocal retry_count
            try:
                if self.opener is not None:
                    response_ctx = self.opener.open(req, timeout=60)
                else:
                    response_ctx = request.urlopen(req, timeout=60)
                with response_ctx as response:
                    return json.loads(response.read().decode("utf-8"))
            except error.HTTPError as exc:
                if exc.code == 429:
                    retry_count += 1
                    raise PlatformRetryError(
                        f"{endpoint} rate limited",
                        code="http:429",
                        retry_after=30 * retry_count,
                    ) from exc
                detail = exc.read().decode("utf-8", errors="replace")
                raise OutlineError(f"{endpoint} failed with HTTP {exc.code}: {detail}") from exc

        try:
            return with_retry(
                call_once,
                policy=RetryPolicy(
                    max_attempts=4,
                    base_delay_s=0,
                    max_delay_s=0,
                    multiplier=1,
                    jitter=False,
                    transient_max=0,
                ),
                error_context=f"Outline {endpoint}",
                sleep_fn=time.sleep,
            )
        except MaxRetriesExceeded as exc:
            rate_limit_error = exc.last_error
            http_error = rate_limit_error.__cause__ if isinstance(rate_limit_error, PlatformRetryError) else None
            if isinstance(http_error, error.HTTPError):
                detail = http_error.read().decode("utf-8", errors="replace")
                raise OutlineError(f"{endpoint} failed with HTTP 429: {detail}") from http_error
            raise OutlineError(f"{endpoint} failed: exhausted retries") from exc


# ---------------------------------------------------------------------------
# Best-effort receipt publishing (ADR 0418)
# ---------------------------------------------------------------------------

_OUTLINE_TOOL = Path(__file__).resolve().parent / "outline_tool.py"
_TOKEN_FILE = REPO_ROOT / ".local" / "outline" / "api-token.txt"


def publish_receipt_to_outline(receipt_path: Path) -> None:
    """Best-effort: convert a receipt JSON to markdown and push to Outline.

    Reads ``OUTLINE_API_TOKEN`` from the environment, falling back to
    ``.local/outline/api-token.txt``.  Silent on any failure — never blocks
    the caller.
    """
    import os
    import subprocess
    import sys as _sys

    token = os.environ.get("OUTLINE_API_TOKEN", "")
    if not token and _TOKEN_FILE.exists():
        token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token or not receipt_path.exists():
        return
    if not _OUTLINE_TOOL.exists():
        return
    try:
        subprocess.run(
            [_sys.executable, str(_OUTLINE_TOOL), "receipt.publish", "--file", str(receipt_path)],
            capture_output=True,
            check=False,
            timeout=30,
            env={**os.environ, "OUTLINE_API_TOKEN": token},
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


# ---------------------------------------------------------------------------


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
