#!/usr/bin/env python3

from __future__ import annotations

import json
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class ParsedDSN:
    scheme: str
    hostport: str
    project_id: str
    public_key: str
    path_prefix: str


def parse_dsn(url: str) -> ParsedDSN | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.username:
        return None
    if not parsed.hostname:
        return None
    path = parsed.path.rstrip("/")
    prefix, _, project_id = path.rpartition("/")
    if not project_id.isdigit():
        return None
    hostport = parsed.hostname
    if parsed.port is not None:
        hostport = f"{hostport}:{parsed.port}"
    return ParsedDSN(
        scheme=parsed.scheme,
        hostport=hostport,
        project_id=project_id,
        public_key=parsed.username,
        path_prefix=prefix,
    )


def build_store_url(dsn: ParsedDSN) -> str:
    return f"{dsn.scheme}://{dsn.hostport}{dsn.path_prefix}/api/{dsn.project_id}/store/"


def build_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    event_id = str(payload.get("event_id") or uuid.uuid4().hex)
    tags = {str(key): str(value) for key, value in dict(payload.get("tags") or {}).items() if value is not None}
    event: dict[str, Any] = {
        "event_id": event_id,
        "timestamp": payload.get("timestamp")
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "platform": payload.get("platform", "python"),
        "message": payload.get("message") or payload.get("summary") or "LV3 GlitchTip event",
        "level": payload.get("level", "error"),
        "logger": payload.get("logger", "lv3.automation"),
        "tags": tags,
    }
    if payload.get("extra") is not None:
        event["extra"] = payload["extra"]
    fingerprint = payload.get("fingerprint")
    if isinstance(fingerprint, str):
        event["fingerprint"] = [fingerprint]
    elif isinstance(fingerprint, list) and fingerprint:
        event["fingerprint"] = fingerprint
    environment = payload.get("environment") or tags.get("environment")
    if environment:
        event["environment"] = environment
    release = payload.get("release") or tags.get("release")
    if release:
        event["release"] = release
    server_name = payload.get("server_name") or tags.get("server_name")
    if server_name:
        event["server_name"] = server_name
    culprit = payload.get("culprit")
    if culprit:
        event["culprit"] = culprit
    return event


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, *, timeout: int = 10) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 300:
            raise RuntimeError(f"Webhook POST failed with HTTP {response.status}")


def emit_glitchtip_event(target_url: str, payload: dict[str, Any], *, timeout: int = 10) -> dict[str, Any]:
    parsed = parse_dsn(target_url)
    if parsed is None:
        post_json(target_url, payload, timeout=timeout)
        return {"target_kind": "webhook", "event_id": payload.get("event_id")}

    event_payload = build_event_payload(payload)
    request = urllib.request.Request(
        build_store_url(parsed),
        data=json.dumps(event_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Sentry-Auth": (
                f"Sentry sentry_version=7, sentry_client=lv3-glitchtip/1.0, sentry_key={parsed.public_key}"
            ),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 300:
            raise RuntimeError(f"GlitchTip DSN event POST failed with HTTP {response.status}")
    return {"target_kind": "dsn", "event_id": event_payload["event_id"]}
