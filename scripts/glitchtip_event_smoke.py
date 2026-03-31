#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from glitchtip_event import emit_glitchtip_event


def read_secret_file(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8").strip()


def load_json_response(url: str, *, token: str, timeout_seconds: float) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "lv3-glitchtip-smoke/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_issue_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    return []


def main(
    *,
    base_url: str,
    organization_slug: str,
    api_token: str,
    dsn: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
    request_timeout_seconds: float = 60.0,
) -> int:
    marker = f"adr-0281-smoke-{uuid.uuid4().hex[:12]}"
    emitted = emit_glitchtip_event(
        dsn,
        {
            "message": f"ADR 0281 GlitchTip smoke {marker}",
            "level": "error",
            "logger": "lv3.glitchtip.smoke",
            "tags": {
                "component": "glitchtip-smoke",
                "marker": marker,
            },
            "extra": {
                "smoke_test": True,
                "organization_slug": organization_slug,
            },
        },
    )

    deadline = time.time() + timeout_seconds
    last_error = ""
    query = urllib.parse.quote(marker, safe="")
    issues_url = f"{base_url.rstrip('/')}/api/0/organizations/{organization_slug}/issues/?query={query}"
    while time.time() < deadline:
        try:
            payload = load_json_response(
                issues_url,
                token=api_token,
                timeout_seconds=request_timeout_seconds,
            )
            issues = extract_issue_list(payload)
            if issues:
                print(
                    json.dumps(
                        {
                            "status": "ok",
                            "marker": marker,
                            "event_id": emitted["event_id"],
                            "issue": issues[0],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(poll_interval_seconds)

    print(
        json.dumps(
            {
                "status": "timeout",
                "marker": marker,
                "event_id": emitted["event_id"],
                "issues_url": issues_url,
                "last_error": last_error,
                "request_timeout_seconds": request_timeout_seconds,
            },
            indent=2,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit and verify a GlitchTip DSN smoke event.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--organization-slug", default="lv3")
    parser.add_argument("--api-token")
    parser.add_argument("--api-token-file")
    parser.add_argument("--dsn")
    parser.add_argument("--dsn-file")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--request-timeout-seconds", type=float, default=60.0)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    api_token = args.api_token or read_secret_file(args.api_token_file)
    dsn = args.dsn or read_secret_file(args.dsn_file)
    raise SystemExit(
        main(
            base_url=args.base_url,
            organization_slug=args.organization_slug,
            api_token=api_token,
            dsn=dsn,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            request_timeout_seconds=args.request_timeout_seconds,
        )
    )
