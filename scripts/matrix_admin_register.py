#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    access_token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        response_payload = json.loads(body) if body else {}
        return exc.code, response_payload


def login(base_url: str, username: str, password: str) -> tuple[bool, dict[str, Any]]:
    status, payload = request_json(
        "POST",
        f"{base_url}/_matrix/client/v3/login",
        {
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": username},
            "password": password,
        },
    )
    return status == 200 and "access_token" in payload, payload


def compute_mac(nonce: str, username: str, password: str, shared_secret: str, *, admin: bool) -> str:
    mac = hmac.new(shared_secret.encode("utf-8"), digestmod=hashlib.sha1)
    mac.update(nonce.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(username.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(password.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    return mac.hexdigest()


def register_user(
    base_url: str,
    username: str,
    password: str,
    shared_secret: str,
    *,
    admin: bool,
) -> tuple[int, dict[str, Any]]:
    nonce_status, nonce_payload = request_json("GET", f"{base_url}/_synapse/admin/v1/register")
    if nonce_status != 200 or "nonce" not in nonce_payload:
        raise RuntimeError(f"failed to obtain Matrix shared-secret registration nonce from {base_url}")
    nonce = nonce_payload["nonce"]
    mac = compute_mac(nonce, username, password, shared_secret, admin=admin)
    return request_json(
        "POST",
        f"{base_url}/_synapse/admin/v1/register",
        {
            "nonce": nonce,
            "username": username,
            "password": password,
            "admin": admin,
            "mac": mac,
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify a Matrix user through Synapse shared-secret registration.",
    )
    parser.add_argument("--base-url", required=True, help="Matrix base URL, for example https://matrix.lv3.org")
    parser.add_argument("--shared-secret-file", required=True, type=Path)
    parser.add_argument("--username", required=True, help="Localpart or full MXID to register and verify")
    parser.add_argument("--password-file", required=True, type=Path)
    parser.add_argument("--admin", action="store_true", help="Register the user as a Synapse admin")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = args.password_file.read_text(encoding="utf-8").strip()
    shared_secret = args.shared_secret_file.read_text(encoding="utf-8").strip()
    base_url = args.base_url.rstrip("/")

    ok, login_payload = login(base_url, args.username, password)
    if ok:
        print(json.dumps({"status": "existing", "user_id": login_payload.get("user_id")}, sort_keys=True))
        return 0

    status, payload = register_user(
        base_url,
        args.username,
        password,
        shared_secret,
        admin=args.admin,
    )
    if status not in {200, 201}:
        raise RuntimeError(f"Matrix shared-secret registration failed: {payload}")

    ok, login_payload = login(base_url, args.username, password)
    if not ok:
        raise RuntimeError("Matrix shared-secret registration succeeded, but password login verification failed")

    print(json.dumps({"status": "registered", "user_id": login_payload.get("user_id")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
