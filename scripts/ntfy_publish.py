#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def resolve_repo_root(script_path: Path | None = None) -> Path:
    candidate = (script_path or Path(__file__)).resolve()
    for parent in (candidate.parent, *candidate.parents):
        if (parent / "platform" / "__init__.py").exists() and (parent / "config").is_dir():
            return parent
    raise RuntimeError(f"Unable to resolve repository root from {candidate}")


REPO_ROOT = resolve_repo_root()
TOPIC_REGISTRY_PATH = REPO_ROOT / "config" / "ntfy" / "topics.yaml"
SECRET_MANIFEST_PATH = REPO_ROOT / "config" / "controller-local-secrets.json"

if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from controller_automation_toolkit import emit_cli_error, load_yaml  # noqa: E402


NTFY_SEQUENCE_ID_REGEX = re.compile(r"^[-_A-Za-z0-9]{1,64}$")
NTFY_SEQUENCE_ID_INVALID_CHARS = re.compile(r"[^-_A-Za-z0-9]+")
NTFY_SEQUENCE_ID_HASH_LEN = 12
NTFY_SEQUENCE_ID_FALLBACK_PREFIX = "seq"


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def load_topic_registry(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    registry = require_mapping(data, str(path))
    require_string(registry.get("schema_version"), f"{path}.schema_version")
    require_mapping(registry.get("topics"), f"{path}.topics")
    require_mapping(registry.get("users"), f"{path}.users")
    return registry


def load_secret_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    manifest = require_mapping(data, str(path))
    secrets = require_mapping(manifest.get("secrets"), f"{path}.secrets")
    return secrets


def read_secret_file(path: str | None) -> str:
    if not path:
        return ""
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return ""
    return candidate.read_text(encoding="utf-8").strip()


def resolve_secret_path(secret_manifest: dict[str, Any], secret_id: str | None) -> str | None:
    if not secret_id:
        return None
    payload = require_mapping(secret_manifest.get(secret_id), f"config/controller-local-secrets.json.secrets.{secret_id}")
    return require_string(payload.get("path"), f"config/controller-local-secrets.json.secrets.{secret_id}.path")


def lookup_registry_user(registry: dict[str, Any], publisher: str | None) -> dict[str, Any] | None:
    if not publisher:
        return None
    users = require_mapping(registry.get("users"), "config/ntfy/topics.yaml.users")
    if publisher not in users:
        raise ValueError(f"Unknown ntfy publisher '{publisher}'")
    return require_mapping(users[publisher], f"config/ntfy/topics.yaml.users.{publisher}")


def require_registered_topic(registry: dict[str, Any], topic: str) -> dict[str, Any]:
    topics = require_mapping(registry.get("topics"), "config/ntfy/topics.yaml.topics")
    if topic not in topics:
        raise ValueError(f"Topic '{topic}' is not registered in config/ntfy/topics.yaml")
    return require_mapping(topics[topic], f"config/ntfy/topics.yaml.topics.{topic}")


def assert_publisher_topic_access(user: dict[str, Any] | None, publisher: str | None, topic: str) -> None:
    if not publisher or user is None:
        return
    publish_topics = user.get("publish_topics", [])
    if topic not in publish_topics:
        raise ValueError(f"Publisher '{publisher}' is not allowed to publish to '{topic}'")


def resolve_base_url(registry: dict[str, Any], explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip().rstrip("/")
    env_value = os.environ.get("LV3_NTFY_BASE_URL", "").strip()
    if env_value:
        return env_value.rstrip("/")
    publication = require_mapping(registry.get("publication", {}), "config/ntfy/topics.yaml.publication")
    public_base_url = publication.get("public_base_url")
    if public_base_url:
        return require_string(public_base_url, "config/ntfy/topics.yaml.publication.public_base_url").rstrip("/")
    raise ValueError("An ntfy base URL is required")


def resolve_auth(
    *,
    registry: dict[str, Any],
    secret_manifest: dict[str, Any],
    publisher: str | None,
    token: str | None,
    token_file: str | None,
    username: str | None,
    password: str | None,
    password_file: str | None,
) -> tuple[dict[str, str], str]:
    explicit_token = (token or os.environ.get("LV3_NTFY_TOKEN", "")).strip()
    explicit_token_file = (token_file or os.environ.get("LV3_NTFY_TOKEN_FILE", "")).strip()
    explicit_username = (username or os.environ.get("LV3_NTFY_USERNAME", "")).strip()
    explicit_password = (password or os.environ.get("LV3_NTFY_PASSWORD", "")).strip()
    explicit_password_file = (password_file or os.environ.get("LV3_NTFY_PASSWORD_FILE", "")).strip()

    user = lookup_registry_user(registry, publisher)
    if user is not None:
        explicit_username = explicit_username or require_string(user.get("username"), f"publisher '{publisher}'.username")
        if not explicit_token and not explicit_token_file:
            registry_token_file = resolve_secret_path(secret_manifest, user.get("token_secret_id"))
            explicit_token = read_secret_file(registry_token_file)
        if not explicit_password and not explicit_password_file:
            registry_password_file = resolve_secret_path(secret_manifest, user.get("password_secret_id"))
            explicit_password = read_secret_file(registry_password_file)

    if explicit_token_file and not explicit_token:
        explicit_token = read_secret_file(explicit_token_file)
    if explicit_password_file and not explicit_password:
        explicit_password = read_secret_file(explicit_password_file)

    if explicit_token:
        return {"Authorization": f"Bearer {explicit_token}"}, "token"

    if explicit_username and explicit_password:
        payload = base64.b64encode(f"{explicit_username}:{explicit_password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {payload}"}, "basic"

    raise ValueError("No ntfy authentication material was available")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def normalize_sequence_id(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("ntfy sequence id must be a non-empty string")
    if NTFY_SEQUENCE_ID_REGEX.fullmatch(raw):
        return raw

    normalized = NTFY_SEQUENCE_ID_INVALID_CHARS.sub("-", raw)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-_")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:NTFY_SEQUENCE_ID_HASH_LEN]
    prefix = normalized or NTFY_SEQUENCE_ID_FALLBACK_PREFIX
    max_prefix_length = 64 - len(digest) - 1
    prefix = prefix[:max_prefix_length].rstrip("-_") or NTFY_SEQUENCE_ID_FALLBACK_PREFIX
    candidate = f"{prefix}-{digest}"
    if not NTFY_SEQUENCE_ID_REGEX.fullmatch(candidate):
        raise ValueError("Unable to derive an ntfy-safe sequence id")
    return candidate


def load_dedupe_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} must contain valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return {str(key): require_string(value, f"{path}.{key}") for key, value in data.items()}


def write_dedupe_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_dedupe_window(path: Path | None, key: str | None, window_seconds: int) -> bool:
    if path is None or not key or window_seconds <= 0:
        return False
    state = load_dedupe_state(path)
    existing = state.get(key)
    if not existing:
        return False
    ts = dt.datetime.fromisoformat(existing.replace("Z", "+00:00"))
    return (now_utc() - ts).total_seconds() < window_seconds


def record_dedupe_window(path: Path | None, key: str | None) -> None:
    if path is None or not key:
        return
    state = load_dedupe_state(path)
    state[key] = now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write_dedupe_state(path, state)


def publish_message(
    *,
    base_url: str,
    topic: str,
    message: str,
    headers: dict[str, str],
) -> tuple[int, str]:
    request = urllib.request.Request(
        f"{base_url}/{urllib.parse.quote(topic, safe='')}",
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"ntfy publish returned HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ntfy publish failed: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a governed ntfy notification.")
    parser.add_argument("--registry", type=Path, default=TOPIC_REGISTRY_PATH)
    parser.add_argument("--secret-manifest", type=Path, default=SECRET_MANIFEST_PATH)
    parser.add_argument("--publisher", help="Registry publisher/user id to use for governance checks.")
    parser.add_argument("--topic", required=True, help="Registered ntfy topic.")
    parser.add_argument("--message", required=True, help="Notification body.")
    parser.add_argument("--title", help="Notification title.")
    parser.add_argument("--priority", type=int, choices=[1, 2, 3, 4, 5], help="Notification priority.")
    parser.add_argument("--tags", help="Comma-separated ntfy tag list.")
    parser.add_argument("--base-url", help="Override the ntfy base URL.")
    parser.add_argument("--token", help="Bearer token.")
    parser.add_argument("--token-file", help="Path to a bearer token file.")
    parser.add_argument("--username", help="Basic-auth username.")
    parser.add_argument("--password", help="Basic-auth password.")
    parser.add_argument("--password-file", help="Path to a Basic-auth password file.")
    parser.add_argument(
        "--sequence-id",
        help="Stable logical sequence id used to update or deduplicate a logical event. Values are normalized into ntfy-safe ids.",
    )
    parser.add_argument(
        "--dedupe-state-file",
        type=Path,
        help="Optional local JSON state file used to skip re-sends within the dedupe window.",
    )
    parser.add_argument(
        "--dedupe-window-seconds",
        type=int,
        default=0,
        help="Skip publishes when the same sequence id was sent within this many seconds.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        registry = load_topic_registry(args.registry)
        secret_manifest = load_secret_manifest(args.secret_manifest) if args.secret_manifest.exists() else {}
        topic_config = require_registered_topic(registry, args.topic)
        user = lookup_registry_user(registry, args.publisher)
        assert_publisher_topic_access(user, args.publisher, args.topic)
        base_url = resolve_base_url(registry, args.base_url)
        auth_headers, auth_mode = resolve_auth(
            registry=registry,
            secret_manifest=secret_manifest,
            publisher=args.publisher,
            token=args.token,
            token_file=args.token_file,
            username=args.username,
            password=args.password,
            password_file=args.password_file,
        )

        requested_sequence_id = (args.sequence_id or "").strip()
        sequence_id = normalize_sequence_id(requested_sequence_id) if requested_sequence_id else ""
        title = (args.title or topic_config.get("default_title") or "").strip()
        tags = (args.tags or ",".join(topic_config.get("default_tags", []))).strip()
        priority = args.priority or topic_config.get("default_priority")

        if check_dedupe_window(args.dedupe_state_file, sequence_id or None, args.dedupe_window_seconds):
            print(
                json.dumps(
                    {
                        "status": "skipped",
                        "topic": args.topic,
                        "publisher": args.publisher or "",
                        "reason": "dedupe_window",
                        "sequence_id": sequence_id,
                        "requested_sequence_id": requested_sequence_id,
                    },
                    indent=2,
                )
            )
            return 0

        headers = {
            **auth_headers,
            "Content-Type": "text/plain; charset=utf-8",
        }
        if title:
            headers["Title"] = title
        if tags:
            headers["Tags"] = tags
        if priority:
            headers["Priority"] = str(priority)
        if sequence_id:
            headers["X-Sequence-ID"] = sequence_id

        if args.dry_run:
            print(
                json.dumps(
                    {
                        "status": "dry-run",
                        "topic": args.topic,
                        "publisher": args.publisher or "",
                        "base_url": base_url,
                        "auth_mode": auth_mode,
                        "sequence_id": sequence_id,
                        "requested_sequence_id": requested_sequence_id,
                        "headers": headers,
                    },
                    indent=2,
                )
            )
            return 0

        status, body = publish_message(
            base_url=base_url,
            topic=args.topic,
            message=args.message,
            headers=headers,
        )
        record_dedupe_window(args.dedupe_state_file, sequence_id or None)
        rendered_body = body.strip()
        payload: Any
        try:
            payload = json.loads(rendered_body) if rendered_body else {}
        except json.JSONDecodeError:
            payload = rendered_body
        print(
            json.dumps(
                {
                    "status": "published",
                    "http_status": status,
                    "topic": args.topic,
                    "publisher": args.publisher or "",
                    "auth_mode": auth_mode,
                    "sequence_id": sequence_id,
                    "requested_sequence_id": requested_sequence_id,
                    "response": payload,
                },
                indent=2,
            )
        )
        return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return emit_cli_error("ntfy publish", exc)


if __name__ == "__main__":
    sys.exit(main())
