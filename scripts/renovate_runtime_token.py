#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def build_api_url(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/")
    return f"{normalized}/api/v1/{path.lstrip('/')}"


def request_json(
    *,
    method: str,
    url: str,
    username: str,
    password: str,
    payload: dict[str, Any] | None = None,
    expected_status: int,
) -> dict[str, Any]:
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": "Basic "
        + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii"),
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            if response.status != expected_status:
                raise SystemExit(f"{method} {url} returned {response.status}, expected {expected_status}")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"{method} {url} failed: {exc.reason}") from exc


def delete_token(*, base_url: str, username: str, password: str, token_id_or_name: str) -> None:
    url = build_api_url(
        base_url,
        f"/users/{urllib.parse.quote(username, safe='')}/tokens/{urllib.parse.quote(token_id_or_name, safe='')}",
    )
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": "Basic "
        + base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii"),
    }
    request = urllib.request.Request(url, data=data, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 204:
                raise SystemExit(f"DELETE {url} returned {response.status}, expected 204")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 404:
            return
        raise SystemExit(f"DELETE {url} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"DELETE {url} failed: {exc.reason}") from exc


def create_runtime_token(*, state_file: Path, env_file: Path) -> None:
    base_url = require_env("RENOVATE_GITEA_BASE_URL")
    username = require_env("RENOVATE_GITEA_USERNAME")
    password = require_env("RENOVATE_GITEA_PASSWORD")
    repository = require_env("RENOVATE_REPOSITORY")
    clone_host = os.environ.get("RENOVATE_GIT_CLONE_HOST", "").strip()
    clone_host_address = os.environ.get("RENOVATE_GIT_CLONE_HOST_ADDRESS", "").strip()
    scope_names = [
        scope.strip()
        for scope in require_env("RENOVATE_GITEA_TOKEN_SCOPES").split(",")
        if scope.strip()
    ]
    token_name = f"renovate-{time.strftime('%Y%m%d%H%M%S', time.gmtime())}"

    response = request_json(
        method="POST",
        url=build_api_url(base_url, f"/users/{urllib.parse.quote(username, safe='')}/tokens"),
        username=username,
        password=password,
        payload={"name": token_name, "scopes": scope_names},
        expected_status=201,
    )

    token = response.get("sha1", "").strip()
    token_id = str(response.get("id", "")).strip()
    if not token or not token_id:
        raise SystemExit("Gitea token creation response did not include both 'sha1' and 'id'")

    state_payload = {
        "base_url": base_url,
        "username": username,
        "token_id": token_id,
        "token_name": response.get("name", token_name),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")

    endpoint = build_api_url(base_url, "/")
    env_lines = [
        "LOG_LEVEL=info",
        "RENOVATE_PLATFORM=gitea",
        f"RENOVATE_ENDPOINT={endpoint}",
        f"RENOVATE_REPOSITORIES={repository}",
        f"RENOVATE_TOKEN={token}",
    ]
    if clone_host and clone_host_address:
        env_lines.extend(
            [
                f"RENOVATE_GIT_CLONE_HOST={clone_host}",
                f"RENOVATE_GIT_CLONE_HOST_ADDRESS={clone_host_address}",
            ]
        )
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(env_lines) + "\n", encoding="utf-8")


def cleanup_runtime_token(*, state_file: Path) -> None:
    if not state_file.exists():
        return

    username = require_env("RENOVATE_GITEA_USERNAME")
    password = require_env("RENOVATE_GITEA_PASSWORD")
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    base_url = str(payload["base_url"])
    token_id_or_name = str(payload.get("token_id") or payload.get("token_name") or "").strip()
    if not token_id_or_name:
        raise SystemExit(f"{state_file} is missing both token_id and token_name")
    delete_token(
        base_url=base_url,
        username=username,
        password=password,
        token_id_or_name=token_id_or_name,
    )
    state_file.unlink(missing_ok=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mint and clean up a short-lived Gitea token for Renovate job runs."
    )
    parser.add_argument("action", choices=("create", "cleanup"))
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--env-file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    state_file = Path(args.state_file)

    if args.action == "create":
        if not args.env_file:
            raise SystemExit("--env-file is required for the create action")
        create_runtime_token(state_file=state_file, env_file=Path(args.env_file))
        return 0

    cleanup_runtime_token(state_file=state_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
