#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    if args.runtime_env_file:
        env = _read_env_file(Path(args.runtime_env_file))
        api_key = env.get("LIVEKIT_API_KEY", "").strip()
        api_secret = env.get("LIVEKIT_API_SECRET", "").strip()
    else:
        api_key = (args.api_key or "").strip()
        api_secret = (args.api_secret or "").strip()
        if args.api_key_file:
            api_key = Path(args.api_key_file).read_text(encoding="utf-8").strip()
        if args.api_secret_file:
            api_secret = Path(args.api_secret_file).read_text(encoding="utf-8").strip()
    if not api_key or not api_secret:
        raise ValueError("LiveKit API credentials are required.")
    return api_key, api_secret


def build_token(*, api_key: str, api_secret: str, claims: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(_json_dumps(header).encode("utf-8"))
    encoded_claims = _b64url_encode(_json_dumps(claims).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = hmac.new(api_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_claims}.{_b64url_encode(signature)}"


def build_admin_claims(*, api_key: str, identity: str, ttl_seconds: int) -> dict[str, Any]:
    now = int(time.time())
    return {
        "iss": api_key,
        "sub": identity,
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "video": {
            "roomCreate": True,
            "roomList": True,
            "roomAdmin": True,
        },
    }


def build_participant_claims(
    *,
    api_key: str,
    identity: str,
    room: str,
    ttl_seconds: int,
    can_publish: bool,
    can_subscribe: bool,
    metadata: str | None,
) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": api_key,
        "sub": identity,
        "nbf": now - 5,
        "exp": now + ttl_seconds,
        "video": {
            "roomJoin": True,
            "room": room,
            "canPublish": can_publish,
            "canSubscribe": can_subscribe,
        },
    }
    if metadata:
        claims["metadata"] = metadata
    return claims


def _twirp_request(
    *,
    url: str,
    path: str,
    token: str,
    body: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8").strip()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised through CLI use
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LiveKit request {path} failed with HTTP {exc.code}: {detail}") from exc


def create_room(
    *,
    url: str,
    api_key: str,
    api_secret: str,
    room_name: str,
    metadata: str | None,
    identity: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    token = build_token(
        api_key=api_key,
        api_secret=api_secret,
        claims=build_admin_claims(api_key=api_key, identity=identity, ttl_seconds=timeout_seconds),
    )
    body: dict[str, Any] = {"name": room_name}
    if metadata:
        body["metadata"] = metadata
    return _twirp_request(
        url=url,
        path="/twirp/livekit.RoomService/CreateRoom",
        token=token,
        body=body,
        timeout_seconds=timeout_seconds,
    )


def list_rooms(
    *,
    url: str,
    api_key: str,
    api_secret: str,
    identity: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    token = build_token(
        api_key=api_key,
        api_secret=api_secret,
        claims=build_admin_claims(api_key=api_key, identity=identity, ttl_seconds=timeout_seconds),
    )
    return _twirp_request(
        url=url,
        path="/twirp/livekit.RoomService/ListRooms",
        token=token,
        body={},
        timeout_seconds=timeout_seconds,
    )


def delete_room(
    *,
    url: str,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    token = build_token(
        api_key=api_key,
        api_secret=api_secret,
        claims=build_admin_claims(api_key=api_key, identity=identity, ttl_seconds=timeout_seconds),
    )
    return _twirp_request(
        url=url,
        path="/twirp/livekit.RoomService/DeleteRoom",
        token=token,
        body={"room": room_name},
        timeout_seconds=timeout_seconds,
    )


def command_admin_token(args: argparse.Namespace) -> int:
    api_key, api_secret = resolve_credentials(args)
    claims = build_admin_claims(api_key=api_key, identity=args.identity, ttl_seconds=args.ttl_seconds)
    print(build_token(api_key=api_key, api_secret=api_secret, claims=claims))
    return 0


def command_participant_token(args: argparse.Namespace) -> int:
    api_key, api_secret = resolve_credentials(args)
    claims = build_participant_claims(
        api_key=api_key,
        identity=args.identity,
        room=args.room,
        ttl_seconds=args.ttl_seconds,
        can_publish=args.can_publish,
        can_subscribe=args.can_subscribe,
        metadata=args.metadata,
    )
    print(build_token(api_key=api_key, api_secret=api_secret, claims=claims))
    return 0


def command_create_room(args: argparse.Namespace) -> int:
    api_key, api_secret = resolve_credentials(args)
    payload = create_room(
        url=args.url,
        api_key=api_key,
        api_secret=api_secret,
        room_name=args.room,
        metadata=args.metadata,
        identity=args.identity,
        timeout_seconds=args.timeout_seconds,
    )
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_list_rooms(args: argparse.Namespace) -> int:
    api_key, api_secret = resolve_credentials(args)
    payload = list_rooms(
        url=args.url,
        api_key=api_key,
        api_secret=api_secret,
        identity=args.identity,
        timeout_seconds=args.timeout_seconds,
    )
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_delete_room(args: argparse.Namespace) -> int:
    api_key, api_secret = resolve_credentials(args)
    payload = delete_room(
        url=args.url,
        api_key=api_key,
        api_secret=api_secret,
        room_name=args.room,
        identity=args.identity,
        timeout_seconds=args.timeout_seconds,
    )
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_verify_room_lifecycle(args: argparse.Namespace) -> int:
    api_key, api_secret = resolve_credentials(args)
    room_name = f"{args.room_prefix}-{int(time.time())}"
    create_payload = create_room(
        url=args.url,
        api_key=api_key,
        api_secret=api_secret,
        room_name=room_name,
        metadata=args.metadata,
        identity=args.identity,
        timeout_seconds=args.timeout_seconds,
    )
    after_create = list_rooms(
        url=args.url,
        api_key=api_key,
        api_secret=api_secret,
        identity=args.identity,
        timeout_seconds=args.timeout_seconds,
    )
    delete_payload = delete_room(
        url=args.url,
        api_key=api_key,
        api_secret=api_secret,
        room_name=room_name,
        identity=args.identity,
        timeout_seconds=args.timeout_seconds,
    )
    after_delete = list_rooms(
        url=args.url,
        api_key=api_key,
        api_secret=api_secret,
        identity=args.identity,
        timeout_seconds=args.timeout_seconds,
    )
    listed_after_create = any(room.get("name") == room_name for room in after_create.get("rooms", []))
    listed_after_delete = any(room.get("name") == room_name for room in after_delete.get("rooms", []))
    payload = {
        "verification_passed": listed_after_create and not listed_after_delete,
        "room_name": room_name,
        "created": create_payload.get("name") == room_name,
        "listed_after_create": listed_after_create,
        "deleted": delete_payload == {},
        "listed_after_delete": listed_after_delete,
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if payload["verification_passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage and verify LiveKit rooms from repo-managed credentials.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_credentials(target: argparse.ArgumentParser) -> None:
        target.add_argument("--api-key")
        target.add_argument("--api-secret")
        target.add_argument("--api-key-file")
        target.add_argument("--api-secret-file")
        target.add_argument("--runtime-env-file")

    token_common = {
        "identity": ("--identity", {"default": "livekit-cli", "help": "Token subject / identity."}),
        "ttl_seconds": ("--ttl-seconds", {"type": int, "default": 300, "help": "Token lifetime in seconds."}),
    }

    admin_parser = subparsers.add_parser("admin-token", help="Emit an admin room-management token.")
    add_credentials(admin_parser)
    for flag, options in token_common.values():
        admin_parser.add_argument(flag, **options)
    admin_parser.set_defaults(func=command_admin_token)

    participant_parser = subparsers.add_parser("participant-token", help="Emit a participant room-join token.")
    add_credentials(participant_parser)
    for flag, options in token_common.values():
        participant_parser.add_argument(flag, **options)
    participant_parser.add_argument("--room", required=True, help="LiveKit room name.")
    participant_parser.add_argument("--metadata", help="Optional participant metadata string.")
    participant_parser.add_argument("--can-publish", action=argparse.BooleanOptionalAction, default=True)
    participant_parser.add_argument("--can-subscribe", action=argparse.BooleanOptionalAction, default=True)
    participant_parser.set_defaults(func=command_participant_token)

    for name, func in (
        ("create-room", command_create_room),
        ("list-rooms", command_list_rooms),
        ("delete-room", command_delete_room),
        ("verify-room-lifecycle", command_verify_room_lifecycle),
    ):
        subparser = subparsers.add_parser(name, help=f"{name.replace('-', ' ')} against the LiveKit Twirp API.")
        add_credentials(subparser)
        subparser.add_argument("--url", required=True, help="Base LiveKit URL, such as https://livekit.lv3.org.")
        subparser.add_argument("--identity", default="livekit-cli", help="Admin identity used for room management.")
        subparser.add_argument("--timeout-seconds", type=int, default=120, help="HTTP timeout and admin token TTL.")
        if name in {"create-room", "delete-room"}:
            subparser.add_argument("--room", required=True, help="LiveKit room name.")
        if name in {"create-room", "verify-room-lifecycle"}:
            subparser.add_argument("--metadata", help="Optional room metadata string.")
        if name == "verify-room-lifecycle":
            subparser.add_argument("--room-prefix", default="lv3-livekit-verify", help="Synthetic room prefix.")
        subparser.set_defaults(func=func)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
      return args.func(args)
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"livekit_tool error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
