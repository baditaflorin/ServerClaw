#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 180


def read_secret(path: str | Path) -> str:
    secret_path = Path(path).expanduser()
    value = secret_path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"secret file is empty: {secret_path}")
    return value


def build_headers(
    *,
    api_key: str | None = None,
    api_key_header: str = "X-LV3-Dify-Api-Key",
    bearer_token: str | None = None,
) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers[api_key_header] = api_key
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


def normalize_session_payload(payload: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("session payload string must contain a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("session payload must be a JSON object")
    return payload


def request_json(
    base_url: str,
    path: str,
    *,
    method: str,
    payload: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    target = f"{base_url}{path}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = dict(headers or {})
    if body is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(target, method=method.upper(), data=body, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"{target} returned HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request to {target} failed: {exc.reason}") from exc


def get_health(
    base_url: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return request_json(
        base_url,
        "/healthz",
        method="GET",
        timeout_seconds=timeout_seconds,
        headers=headers,
    )


def run_session(
    base_url: str,
    payload: dict[str, Any] | str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = normalize_session_payload(payload)
    return request_json(
        base_url,
        "/sessions",
        method="POST",
        payload=payload,
        timeout_seconds=timeout_seconds,
        headers=headers,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Call the private LV3 browser runner service.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Check the browser runner health endpoint.")
    health_parser.add_argument("--base-url", required=True, help="Service or gateway base URL")
    health_parser.add_argument("--api-key-file", help="Optional API key file for Dify-style auth")
    health_parser.add_argument("--api-key-header", default="X-LV3-Dify-Api-Key")
    health_parser.add_argument("--bearer-token-file", help="Optional bearer token file")
    health_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    run_parser = subparsers.add_parser("run", help="Create a browser-runner session.")
    run_parser.add_argument("--base-url", required=True, help="Service or gateway base URL")
    run_parser.add_argument("--payload-file", required=True, help="Path to the JSON request payload")
    run_parser.add_argument("--api-key-file", help="Optional API key file for Dify-style auth")
    run_parser.add_argument("--api-key-header", default="X-LV3-Dify-Api-Key")
    run_parser.add_argument("--bearer-token-file", help="Optional bearer token file")
    run_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)

    args = parser.parse_args()

    api_key = read_secret(args.api_key_file) if getattr(args, "api_key_file", None) else None
    bearer_token = read_secret(args.bearer_token_file) if getattr(args, "bearer_token_file", None) else None
    headers = build_headers(api_key=api_key, api_key_header=args.api_key_header, bearer_token=bearer_token)

    if args.command == "health":
        payload = get_health(args.base_url, timeout_seconds=args.timeout_seconds, headers=headers)
    else:
        payload = run_session(
            args.base_url,
            json.loads(Path(args.payload_file).read_text(encoding="utf-8")),
            timeout_seconds=args.timeout_seconds,
            headers=headers,
        )

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
