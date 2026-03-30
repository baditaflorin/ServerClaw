#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from falco_event_bridge import BridgeConfig, bridge_event


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def load_config() -> tuple[str, int, BridgeConfig]:
    listen_host = os.environ.get("FALCO_EVENT_BRIDGE_LISTEN_HOST", "0.0.0.0").strip() or "0.0.0.0"
    listen_port = env_int("FALCO_EVENT_BRIDGE_LISTEN_PORT", 18084)
    config = BridgeConfig(
        actor_id=os.environ.get("FALCO_EVENT_BRIDGE_ACTOR_ID", "falco-event-bridge").strip() or "falco-event-bridge",
        source_host=os.environ.get("FALCO_EVENT_BRIDGE_SOURCE_HOST", "docker-runtime-lv3").strip() or "docker-runtime-lv3",
        event_topic=os.environ.get("FALCO_EVENT_BRIDGE_EVENT_TOPIC", "platform.security.falco").strip() or "platform.security.falco",
        nats_subject=os.environ.get("FALCO_EVENT_BRIDGE_NATS_SUBJECT", "platform.security.falco").strip() or "platform.security.falco",
        nats_host=os.environ.get("FALCO_EVENT_BRIDGE_NATS_HOST", "127.0.0.1").strip() or "127.0.0.1",
        nats_port=env_int("FALCO_EVENT_BRIDGE_NATS_PORT", 4222),
        nats_username=os.environ.get("FALCO_EVENT_BRIDGE_NATS_USERNAME", "").strip(),
        nats_password=os.environ.get("FALCO_EVENT_BRIDGE_NATS_PASSWORD", "").strip(),
        ntfy_base_url=os.environ.get("FALCO_EVENT_BRIDGE_NTFY_BASE_URL", "http://127.0.0.1:2586").strip() or "http://127.0.0.1:2586",
        ntfy_topic=os.environ.get("FALCO_EVENT_BRIDGE_NTFY_TOPIC", "platform.security.critical").strip() or "platform.security.critical",
        ntfy_username=os.environ.get("FALCO_EVENT_BRIDGE_NTFY_USERNAME", "").strip(),
        ntfy_password=os.environ.get("FALCO_EVENT_BRIDGE_NTFY_PASSWORD", "").strip(),
        mutation_audit_file=os.environ.get(
            "FALCO_EVENT_BRIDGE_MUTATION_AUDIT_FILE",
            "/var/log/platform/mutation-audit.jsonl",
        ).strip()
        or "/var/log/platform/mutation-audit.jsonl",
        http_timeout_seconds=env_float("FALCO_EVENT_BRIDGE_HTTP_TIMEOUT_SECONDS", 5.0),
    )
    return listen_host, listen_port, config


class FalcoBridgeHandler(BaseHTTPRequestHandler):
    bridge_config: BridgeConfig

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        self._write_json(HTTPStatus.OK, {"status": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/events":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(content_length)
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid_json: {exc}"})
            return

        events = decoded if isinstance(decoded, list) else [decoded]
        try:
            action_report = [bridge_event(event, config=self.bridge_config) for event in events]
        except Exception as exc:  # pragma: no cover - exercised through live bridge path
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._write_json(HTTPStatus.ACCEPTED, {"accepted": len(events), "actions": action_report})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        print(f"falco-event-bridge {self.address_string()} {format % args}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the LV3 Falco event bridge.")
    parser.add_argument("--listen-host", help="Override the listen host.")
    parser.add_argument("--listen-port", type=int, help="Override the listen port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    listen_host, listen_port, config = load_config()
    if args.listen_host:
        listen_host = args.listen_host
    if args.listen_port:
        listen_port = args.listen_port

    FalcoBridgeHandler.bridge_config = config
    server = ThreadingHTTPServer((listen_host, listen_port), FalcoBridgeHandler)
    print(f"falco-event-bridge listening on {listen_host}:{listen_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual operator path
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
