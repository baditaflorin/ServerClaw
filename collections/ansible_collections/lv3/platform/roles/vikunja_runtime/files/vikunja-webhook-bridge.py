#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


WEBHOOK_SECRET = os.environ["VIKUNJA_WEBHOOK_SECRET"]
NATS_URL = os.environ.get("VIKUNJA_EVENT_NATS_URL", "nats://127.0.0.1:4222")
NATS_USERNAME = os.environ.get("VIKUNJA_EVENT_NATS_USERNAME", "")
NATS_PASSWORD = os.environ.get("VIKUNJA_EVENT_NATS_PASSWORD", "")
SUBJECT_PREFIX = os.environ.get("VIKUNJA_EVENT_SUBJECT_PREFIX", "platform.task").rstrip(".")
LISTEN_HOST = os.environ.get("VIKUNJA_WEBHOOK_BRIDGE_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("VIKUNJA_WEBHOOK_BRIDGE_PORT", "8081"))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def verify_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def nats_target() -> tuple[str, int]:
    parsed = urlparse(NATS_URL)
    if parsed.scheme != "nats":
        raise RuntimeError(f"unsupported nats url: {NATS_URL}")
    return parsed.hostname or "127.0.0.1", parsed.port or 4222


def publish(subject: str, payload: dict) -> None:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    host, port = nats_target()
    connect_payload = {"verbose": False, "pedantic": False}
    if NATS_USERNAME:
      connect_payload["user"] = NATS_USERNAME
    if NATS_PASSWORD:
      connect_payload["pass"] = NATS_PASSWORD

    with socket.create_connection((host, port), timeout=5) as conn:
        reader = conn.makefile("rb", buffering=0)
        writer = conn.makefile("wb", buffering=0)
        first = reader.readline()
        if first and not first.startswith(b"INFO"):
            raise RuntimeError(f"unexpected NATS preamble: {first!r}")
        writer.write(f"CONNECT {json.dumps(connect_payload)}\r\n".encode("utf-8"))
        writer.write(f"PUB {subject} {len(body)}\r\n".encode("utf-8"))
        writer.write(body)
        writer.write(b"\r\nPING\r\n")
        writer.flush()
        response = reader.readline()
        if response and response.startswith(b"-ERR"):
            raise RuntimeError(response.decode("utf-8", errors="replace").strip())
        if response and not response.startswith(b"PONG") and not response.startswith(b"+OK"):
            second = reader.readline()
            if second and second.startswith(b"-ERR"):
                raise RuntimeError(second.decode("utf-8", errors="replace").strip())


def subjects_for_event(event_name: str, task: dict) -> list[str]:
    subjects = [f"{SUBJECT_PREFIX}.{event_name.replace('.', '_')}"]
    if event_name == "task.created":
        subjects.append(f"{SUBJECT_PREFIX}.created")
    elif event_name == "task.updated":
        subjects.append(f"{SUBJECT_PREFIX}.updated")
        if task.get("done") is True:
            subjects.append(f"{SUBJECT_PREFIX}.completed")
    elif event_name == "task.deleted":
        subjects.append(f"{SUBJECT_PREFIX}.deleted")
    elif event_name == "task.overdue":
        subjects.append(f"{SUBJECT_PREFIX}.overdue")
    elif event_name == "task.comment.created":
        subjects.append(f"{SUBJECT_PREFIX}.comment_created")
    return list(dict.fromkeys(subjects))


def event_payload(event_name: str, payload: dict) -> dict:
    task = payload.get("data", {}).get("task", {}) if isinstance(payload, dict) else {}
    return {
        "emitted_at": now_iso(),
        "event_name": event_name,
        "task_id": task.get("id"),
        "task_identifier": task.get("identifier"),
        "task_title": task.get("title"),
        "task_done": task.get("done"),
        "project_id": task.get("project_id"),
        "payload": payload,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "vikunja-webhook-bridge/1.0"

    def _json_response(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path != "/healthz":
            self._json_response(HTTPStatus.NOT_FOUND, {"status": "not_found"})
            return
        self._json_response(HTTPStatus.OK, {"status": "ok"})

    def do_POST(self) -> None:
        if self.path != "/webhook":
            self._json_response(HTTPStatus.NOT_FOUND, {"status": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        signature = self.headers.get("X-Vikunja-Signature", "")
        if not verify_signature(body, signature):
            self._json_response(HTTPStatus.UNAUTHORIZED, {"status": "invalid_signature"})
            return
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._json_response(HTTPStatus.BAD_REQUEST, {"status": "invalid_json"})
            return
        event_name = str(payload.get("event_name", "")).strip()
        if not event_name:
            self._json_response(HTTPStatus.BAD_REQUEST, {"status": "missing_event_name"})
            return
        task = payload.get("data", {}).get("task", {})
        emitted_payload = event_payload(event_name, payload)
        try:
            for subject in subjects_for_event(event_name, task):
                publish(subject, emitted_payload)
        except Exception as exc:  # noqa: BLE001
            self._json_response(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "publish_failed", "error": str(exc)})
            return
        self._json_response(HTTPStatus.OK, {"status": "ok", "subjects": subjects_for_event(event_name, task)})

    def log_message(self, fmt: str, *args) -> None:
        message = fmt % args
        print(f"{now_iso()} {threading.current_thread().name} {message}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    server.serve_forever()
