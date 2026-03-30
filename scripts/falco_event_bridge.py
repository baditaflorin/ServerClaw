#!/usr/bin/env python3

from __future__ import annotations

import base64
import datetime as dt
import json
import socket
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PRIORITY_ORDER = {
    "EMERGENCY": 7,
    "ALERT": 6,
    "CRITICAL": 5,
    "ERROR": 4,
    "WARNING": 3,
    "NOTICE": 2,
    "INFORMATIONAL": 1,
    "INFO": 1,
    "DEBUG": 0,
}


@dataclass(frozen=True)
class BridgeConfig:
    actor_id: str
    source_host: str
    event_topic: str
    nats_subject: str
    nats_host: str
    nats_port: int
    nats_username: str
    nats_password: str
    ntfy_base_url: str
    ntfy_topic: str
    ntfy_username: str
    ntfy_password: str
    mutation_audit_file: str
    http_timeout_seconds: float = 5.0


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_priority(priority: Any) -> str:
    value = str(priority or "INFO").strip().upper()
    if value not in PRIORITY_ORDER:
        return "INFO"
    if value == "INFORMATIONAL":
        return "INFO"
    return value


def priority_at_least(priority: Any, threshold: str) -> bool:
    normalized = normalize_priority(priority)
    return PRIORITY_ORDER[normalized] >= PRIORITY_ORDER[normalize_priority(threshold)]


def infer_source_host(event: dict[str, Any], fallback_host: str) -> str:
    output_fields = event.get("output_fields")
    if isinstance(output_fields, dict):
        for key in ("evt.hostname", "container.host", "k8s.ns.name"):
            value = output_fields.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("hostname", "host", "hostname_output"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback_host


def infer_event_time(event: dict[str, Any]) -> str:
    for key in ("time", "output_time", "evt.time"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return utc_now_iso()


def build_correlation_id(event: dict[str, Any], source_host: str) -> str:
    rule = str(event.get("rule") or "unknown-rule").strip() or "unknown-rule"
    ts = infer_event_time(event).replace(":", "").replace("-", "")
    return f"falco:{source_host}:{rule}:{ts}"


def build_security_payload(event: dict[str, Any], *, topic: str, source_host: str) -> dict[str, Any]:
    payload = {
        "event": topic,
        "host": source_host,
        "rule": str(event.get("rule") or "unknown-rule"),
        "priority": normalize_priority(event.get("priority")),
        "time": infer_event_time(event),
        "source": "falco",
        "output": str(event.get("output") or ""),
        "tags": event.get("tags") if isinstance(event.get("tags"), list) else [],
        "output_fields": event.get("output_fields") if isinstance(event.get("output_fields"), dict) else {},
    }
    return payload


def build_event_envelope(
    topic: str,
    payload: dict[str, Any],
    *,
    actor_id: str,
    context_id: str,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "topic": topic,
        "schema_ver": "1.0",
        "ts": payload["time"],
        "actor_id": actor_id,
        "context_id": context_id,
        "payload": payload,
    }


def build_mutation_audit_event(
    event: dict[str, Any],
    *,
    actor_id: str,
    source_host: str,
    correlation_id: str,
) -> dict[str, Any]:
    rule = str(event.get("rule") or "unknown-rule")
    return {
        "ts": utc_now_iso(),
        "actor": {
            "class": "service",
            "id": actor_id,
        },
        "surface": "falco",
        "action": "security_anomaly_detected",
        "target": f"{source_host}:{rule}",
        "outcome": "success",
        "correlation_id": correlation_id,
        "evidence_ref": f"falco://{source_host}/{rule}",
    }


def append_jsonl(path: str, event: dict[str, Any]) -> None:
    sink = Path(path)
    sink.parent.mkdir(parents=True, exist_ok=True)
    with sink.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _read_control_line(connection: socket.socket) -> str:
    data = b""
    while not data.endswith(b"\r\n"):
        chunk = connection.recv(1)
        if not chunk:
            raise RuntimeError("NATS connection closed before control line was read")
        data += chunk
    return data.decode("utf-8").strip()


def _await_pong(connection: socket.socket) -> None:
    while True:
        line = _read_control_line(connection)
        if line.startswith("INFO"):
            continue
        if line == "PONG":
            return
        if line.startswith("-ERR"):
            raise RuntimeError(f"NATS server rejected publish: {line}")
        if line == "+OK":
            continue
        raise RuntimeError(f"Unexpected NATS control line: {line}")


def publish_nats_message(*, subject: str, payload: dict[str, Any], config: BridgeConfig) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    connect_payload = {
        "verbose": False,
        "pedantic": False,
        "tls_required": False,
        "lang": "python",
        "version": "1.0",
        "protocol": 1,
        "name": "lv3-falco-event-bridge",
        "user": config.nats_username,
        "pass": config.nats_password,
    }
    with socket.create_connection((config.nats_host, config.nats_port), timeout=config.http_timeout_seconds) as connection:
        connection.settimeout(config.http_timeout_seconds)
        initial = _read_control_line(connection)
        if not initial.startswith("INFO"):
            raise RuntimeError(f"Unexpected NATS greeting: {initial}")
        connection.sendall(f"CONNECT {json.dumps(connect_payload, separators=(',', ':'))}\r\nPING\r\n".encode("utf-8"))
        _await_pong(connection)
        connection.sendall(f"PUB {subject} {len(body)}\r\n".encode("utf-8") + body + b"\r\nPING\r\n")
        _await_pong(connection)


def publish_ntfy_message(*, event: dict[str, Any], source_host: str, config: BridgeConfig) -> None:
    title = f"Falco critical alert on {source_host}"
    output = str(event.get("output") or event.get("rule") or "Falco critical event")
    body = f"[{normalize_priority(event.get('priority'))}] {source_host}: {output}".encode("utf-8")
    url = f"{config.ntfy_base_url.rstrip('/')}/{config.ntfy_topic}"
    credentials = base64.b64encode(f"{config.ntfy_username}:{config.ntfy_password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "text/plain; charset=utf-8",
            "Title": title,
            "Priority": "urgent",
            "Tags": "rotating_light,shield",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.http_timeout_seconds) as response:
            if response.status >= 300:
                raise RuntimeError(f"ntfy publish failed with HTTP {response.status}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ntfy publish failed: {exc}") from exc


def bridge_event(event: dict[str, Any], *, config: BridgeConfig) -> list[str]:
    if not isinstance(event, dict):
        raise ValueError("Falco bridge expects one JSON object per event")

    source_host = infer_source_host(event, config.source_host)
    correlation_id = build_correlation_id(event, source_host)
    actions: list[str] = []

    if priority_at_least(event.get("priority"), "WARNING"):
        payload = build_security_payload(event, topic=config.event_topic, source_host=source_host)
        envelope = build_event_envelope(
            config.event_topic,
            payload,
            actor_id=config.actor_id,
            context_id=correlation_id,
        )
        publish_nats_message(subject=config.nats_subject, payload=envelope, config=config)
        append_jsonl(
            config.mutation_audit_file,
            build_mutation_audit_event(
                event,
                actor_id=config.actor_id,
                source_host=source_host,
                correlation_id=correlation_id,
            ),
        )
        actions.append("nats")
        actions.append("mutation_audit")

    if priority_at_least(event.get("priority"), "CRITICAL"):
        publish_ntfy_message(event=event, source_host=source_host, config=config)
        actions.append("ntfy")

    return actions
