#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Windmill script via jobs/run_wait_result.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--payload-json", default="{}")
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def login_with_bootstrap_secret(base_url: str, secret: str, timeout: int) -> str:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/auth/login",
        data=json.dumps(
            {
                "email": "superadmin_secret@windmill.dev",
                "password": secret,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        token = response.read().decode("utf-8").strip()
    if not token:
        raise RuntimeError("Windmill bootstrap login returned an empty session token")
    return token


def open_with_token(url: str, token: str, payload: dict, timeout: int):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=timeout)


def main() -> int:
    args = build_parser().parse_args()
    token = os.environ.get("WINDMILL_TOKEN", "").strip()
    if not token:
        print("WINDMILL_TOKEN is required", file=sys.stderr)
        return 2

    payload = json.loads(args.payload_json)
    url = (
        f"{args.base_url.rstrip('/')}/api/w/{urllib.parse.quote(args.workspace, safe='')}"
        f"/jobs/run_wait_result/p/{urllib.parse.quote(args.path, safe='')}"
    )
    try:
        with open_with_token(url, token, payload, args.timeout) as response:
            sys.stdout.write(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            try:
                session_token = login_with_bootstrap_secret(args.base_url, token, args.timeout)
                with open_with_token(url, session_token, payload, args.timeout) as response:
                    sys.stdout.write(response.read().decode("utf-8"))
                return 0
            except urllib.error.HTTPError as retry_exc:
                sys.stderr.write(retry_exc.read().decode("utf-8"))
                return 1
        sys.stderr.write(exc.read().decode("utf-8"))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
