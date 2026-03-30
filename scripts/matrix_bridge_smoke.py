#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from platform.retry import MaxRetriesExceeded, PlatformRetryError, RetryClass, RetryPolicy, with_retry


def decode_json_body(body: str) -> dict[str, Any]:
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw_body": body}


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
            return response.status, decode_json_body(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        response_payload = decode_json_body(body)
        return exc.code, response_payload


def persist_access_token(access_token_file: Path | None, access_token: str) -> None:
    if access_token_file is None:
        return
    access_token_file.parent.mkdir(parents=True, exist_ok=True)
    access_token_file.write_text(f"{access_token}\n", encoding="utf-8")
    access_token_file.chmod(0o600)


def whoami(base_url: str, access_token: str) -> tuple[int, dict[str, Any]]:
    return request_json(
        "GET",
        f"{base_url}/_matrix/client/v3/account/whoami",
        access_token=access_token,
    )


def request_login_with_rate_limit_retry(
    base_url: str,
    username: str,
    password: str,
    *,
    max_rate_limit_wait_seconds: int,
) -> tuple[int, dict[str, Any]]:
    waited_seconds = 0.0
    last_payload: dict[str, Any] = {}

    def perform_login() -> tuple[int, dict[str, Any]]:
        nonlocal last_payload
        status, payload = request_json(
            "POST",
            f"{base_url}/_matrix/client/v3/login",
            {
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": username},
                "password": password,
            },
        )
        last_payload = payload
        if status == 429 and payload.get("errcode") == "M_LIMIT_EXCEEDED":
            retry_after_ms = int(payload.get("retry_after_ms") or 1000)
            raise PlatformRetryError(
                f"Matrix login rate limit persisted for {username}: {payload}",
                code="http:429",
                retry_class=RetryClass.BACKOFF,
                retry_after=max(retry_after_ms / 1000.0, 1.0),
            )
        return status, payload

    def sleep_with_budget(delay_seconds: float) -> None:
        nonlocal waited_seconds
        if waited_seconds + delay_seconds > max_rate_limit_wait_seconds:
            raise PlatformRetryError(
                f"Matrix login rate limit persisted for {username}: {last_payload}",
                code="platform:budget_exceeded",
                retry_class=RetryClass.PERMANENT,
            )
        time.sleep(delay_seconds)
        waited_seconds += delay_seconds

    try:
        return with_retry(
            perform_login,
            policy=RetryPolicy(
                max_attempts=max(int(max_rate_limit_wait_seconds), 2),
                base_delay_s=1.0,
                max_delay_s=max(float(max_rate_limit_wait_seconds), 1.0),
                multiplier=1.0,
                jitter=False,
                transient_max=0,
            ),
            error_context=f"Matrix login for {username}",
            sleep_fn=sleep_with_budget,
        )
    except (MaxRetriesExceeded, PlatformRetryError):
        return 429, last_payload


def login(
    base_url: str,
    username: str,
    password: str,
    *,
    access_token_file: Path | None = None,
    max_rate_limit_wait_seconds: int = 300,
) -> dict[str, Any]:
    if access_token_file and access_token_file.exists():
        cached_access_token = access_token_file.read_text(encoding="utf-8").strip()
        if cached_access_token:
            status, payload = whoami(base_url, cached_access_token)
            if status == 200 and "user_id" in payload:
                return {"access_token": cached_access_token, **payload}

    status, payload = request_login_with_rate_limit_retry(
        base_url,
        username,
        password,
        max_rate_limit_wait_seconds=max_rate_limit_wait_seconds,
    )
    if status == 200 and "access_token" in payload:
        persist_access_token(access_token_file, str(payload["access_token"]))
        return payload
    if status == 429 and payload.get("errcode") == "M_LIMIT_EXCEEDED":
        raise RuntimeError(f"Matrix login rate limit persisted for {username}: {payload}")
    raise RuntimeError(f"Matrix login failed for {username}: {payload}")


def sync(base_url: str, access_token: str, *, since: str | None = None, timeout_ms: int = 0) -> dict[str, Any]:
    query = {"timeout": str(timeout_ms)}
    if since:
        query["since"] = since
    status, payload = request_json(
        "GET",
        f"{base_url}/_matrix/client/v3/sync?{urllib.parse.urlencode(query)}",
        access_token=access_token,
    )
    if status != 200:
        raise RuntimeError(f"Matrix sync failed: {payload}")
    return payload


def create_direct_room(base_url: str, access_token: str, bot_user_id: str) -> str:
    status, payload = request_json(
        "POST",
        f"{base_url}/_matrix/client/v3/createRoom",
        {
            "is_direct": True,
            "preset": "trusted_private_chat",
            "invite": [bot_user_id],
            "topic": f"Repo-managed bridge smoke for {bot_user_id}",
        },
        access_token=access_token,
    )
    if status != 200 or "room_id" not in payload:
        raise RuntimeError(f"Failed to create Matrix DM with {bot_user_id}: {payload}")
    return payload["room_id"]


def send_message(base_url: str, access_token: str, room_id: str, body: str) -> None:
    transaction_id = str(int(time.time() * 1000))
    status, payload = request_json(
        "PUT",
        f"{base_url}/_matrix/client/v3/rooms/{urllib.parse.quote(room_id, safe='')}/send/m.room.message/{transaction_id}",
        {"msgtype": "m.text", "body": body},
        access_token=access_token,
    )
    if status != 200:
        raise RuntimeError(f"Failed to send Matrix message into {room_id}: {payload}")


def wait_for_bot_reply(
    base_url: str,
    access_token: str,
    *,
    room_id: str,
    bot_user_id: str,
    since: str,
    timeout_seconds: int,
) -> tuple[str, str]:
    deadline = time.monotonic() + timeout_seconds
    next_batch = since
    while time.monotonic() < deadline:
        payload = sync(base_url, access_token, since=next_batch, timeout_ms=5000)
        next_batch = payload.get("next_batch", next_batch)
        room = payload.get("rooms", {}).get("join", {}).get(room_id, {})
        events = room.get("timeline", {}).get("events", [])
        for event in events:
            if event.get("sender") != bot_user_id:
                continue
            if event.get("type") != "m.room.message":
                continue
            body = event.get("content", {}).get("body", "").strip()
            if body:
                return body, next_batch
    raise RuntimeError(f"No Matrix bridge response arrived from {bot_user_id} within {timeout_seconds} seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exercise Matrix bridge management rooms by DMing the repo-managed bridge bots and waiting for a reply.",
    )
    parser.add_argument("--base-url", required=True, help="Matrix base URL, for example https://matrix.lv3.org")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-file", required=True, type=Path)
    parser.add_argument("--access-token-file", type=Path, help="Optional local file used to reuse or persist a verified Matrix access token")
    parser.add_argument("--bot-user-id", action="append", required=True, dest="bot_user_ids")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    password = args.password_file.read_text(encoding="utf-8").strip()
    login_payload = login(
        base_url,
        args.username,
        password,
        access_token_file=args.access_token_file,
    )
    access_token = login_payload["access_token"]

    versions_status, versions_payload = request_json("GET", f"{base_url}/_matrix/client/versions")
    if versions_status != 200 or "versions" not in versions_payload:
        raise RuntimeError(f"Matrix versions endpoint did not return the expected payload: {versions_payload}")

    next_batch = sync(base_url, access_token, timeout_ms=0).get("next_batch")
    if not next_batch:
        raise RuntimeError("Matrix sync did not return next_batch")

    results: list[dict[str, str]] = []
    for bot_user_id in args.bot_user_ids:
        room_id = create_direct_room(base_url, access_token, bot_user_id)
        next_batch = sync(base_url, access_token, timeout_ms=0).get("next_batch", next_batch)
        send_message(base_url, access_token, room_id, "help")
        reply, next_batch = wait_for_bot_reply(
            base_url,
            access_token,
            room_id=room_id,
            bot_user_id=bot_user_id,
            since=next_batch,
            timeout_seconds=args.timeout_seconds,
        )
        results.append({"bot_user_id": bot_user_id, "room_id": room_id, "reply": reply})

    print(json.dumps({"status": "ok", "bridges": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
