#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from json import JSONDecodeError
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

REPO_ROOT = ensure_repo_root_on_path(__file__)
from platform.retry import MaxRetriesExceeded, RetryPolicy, with_retry
try:
    from datetime import UTC
except ImportError:  # pragma: no cover
    from datetime import timezone

    UTC = timezone.utc

def detect_common_repo_root(repo_root: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return repo_root
    common_dir = Path(result.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = (repo_root / common_dir).resolve()
    if common_dir.name == ".git":
        return common_dir.parent
    return repo_root


COMMON_REPO_ROOT = detect_common_repo_root(REPO_ROOT)
HTTP_TIMEOUT_SECONDS = 20
HTTP_RETRY_ATTEMPTS = 8
HTTP_RETRY_DELAY_SECONDS = 3


class BootstrapError(RuntimeError):
    pass


def repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    worktree_path = REPO_ROOT / path
    if worktree_path.exists():
        return worktree_path
    common_path = COMMON_REPO_ROOT / path
    if path.parts and path.parts[0] == ".local":
        return common_path
    if common_path.exists():
        return common_path
    return worktree_path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def write_text_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    expected_status: int | tuple[int, ...] = 200,
    timeout_seconds: int = HTTP_TIMEOUT_SECONDS,
    retries: int = HTTP_RETRY_ATTEMPTS,
    retry_delay_seconds: int = HTTP_RETRY_DELAY_SECONDS,
) -> Any:
    request_headers = dict(headers or {})
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)

    def perform_request() -> Any:
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                if isinstance(expected_status, tuple):
                    if response.status not in expected_status:
                        raise BootstrapError(f"{method} {url} returned unexpected status {response.status}")
                elif response.status != expected_status:
                    raise BootstrapError(f"{method} {url} returned unexpected status {response.status}")
                return response.status, json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise BootstrapError(f"{method} {url} failed with status {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, JSONDecodeError) as exc:
            raise BootstrapError(f"{method} {url} failed: {exc}") from exc

    attempts = max(retries, 1)
    last_error: BootstrapError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return perform_request()
        except BootstrapError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(max(float(retry_delay_seconds), 0.0))
    assert last_error is not None
    raise BootstrapError(f"{method} {url} failed after {attempts} attempts: {last_error}") from last_error


def expect_success(payload: dict[str, Any], url: str) -> Any:
    if not payload.get("success", False):
        raise BootstrapError(f"{url} returned success=false: {payload.get('message', '')}")
    return payload.get("data")


def admin_headers(root_access_token: str) -> dict[str, str]:
    return {"Authorization": root_access_token}


def bearer_headers(token_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_key}"}


def normalize_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return sorted(item.strip() for item in value.split(",") if item.strip())


def normalize_json_mapping(value: str | dict[str, str] | None) -> dict[str, str]:
    if value in (None, "", "{}"):
        return {}
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    return {str(key): str(item) for key, item in json.loads(value).items()}


def maybe_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def search_channels(base_url: str, root_access_token: str, keyword: str) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/channel/search?keyword={urllib.parse.quote(keyword)}"
    _status, payload = http_json("GET", url, headers=admin_headers(root_access_token))
    return list(expect_success(payload, url) or [])


def get_channel(base_url: str, root_access_token: str, channel_id: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/channel/{channel_id}"
    _status, payload = http_json("GET", url, headers=admin_headers(root_access_token))
    data = expect_success(payload, url)
    if not isinstance(data, dict):
        raise BootstrapError(f"{url} did not return a channel object")
    return data


def search_tokens(base_url: str, root_access_token: str, keyword: str) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/token/search?keyword={urllib.parse.quote(keyword)}"
    _status, payload = http_json("GET", url, headers=admin_headers(root_access_token))
    return list(expect_success(payload, url) or [])


def get_token(base_url: str, root_access_token: str, token_id: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/token/{token_id}"
    _status, payload = http_json("GET", url, headers=admin_headers(root_access_token))
    data = expect_success(payload, url)
    if not isinstance(data, dict):
        raise BootstrapError(f"{url} did not return a token object")
    return data


def get_self(base_url: str, root_access_token: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/user/self"
    _status, payload = http_json("GET", url, headers=admin_headers(root_access_token))
    data = expect_success(payload, url)
    if not isinstance(data, dict):
        raise BootstrapError(f"{url} did not return a user object")
    return data


def get_status(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/status"
    _status, payload = http_json("GET", url)
    data = expect_success(payload, url)
    if not isinstance(data, dict):
        raise BootstrapError(f"{url} did not return a status object")
    return data


def find_exact_by_name(items: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    exact = [item for item in items if item.get("name") == name]
    if len(exact) > 1:
        raise BootstrapError(f"multiple resources matched exact name {name!r}")
    return exact[0] if exact else None


def channel_payload_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "name": spec["name"],
        "type": int(spec["type"]),
        "key": spec["key"],
        "status": int(spec.get("status", 1)),
        "weight": int(spec.get("weight", 100)),
        "priority": int(spec.get("priority", 0)),
        "base_url": spec.get("base_url", ""),
        "group": spec.get("group", "default"),
        "models": ",".join(spec.get("models", [])),
        "model_mapping": json.dumps(spec.get("model_mapping", {}), sort_keys=True),
        "config": json.dumps(spec.get("config", {}), sort_keys=True) if spec.get("config") else "",
    }
    if spec.get("system_prompt"):
        payload["system_prompt"] = spec["system_prompt"]
    return payload


def normalize_channel_for_compare(channel: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(channel.get("name", "")),
        "type": maybe_int(channel.get("type")),
        "status": maybe_int(channel.get("status") or 1),
        "weight": maybe_int(channel.get("weight")),
        "priority": maybe_int(channel.get("priority")),
        "base_url": str(channel.get("base_url") or ""),
        "group": normalize_csv(channel.get("group")),
        "models": normalize_csv(channel.get("models")),
        "model_mapping": normalize_json_mapping(channel.get("model_mapping")),
        "config": json.dumps(json.loads(channel.get("config") or "{}"), sort_keys=True),
        "system_prompt": str(channel.get("system_prompt") or ""),
    }


def normalize_channel_payload_for_compare(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload["name"],
        "type": maybe_int(payload["type"]),
        "status": maybe_int(payload["status"]),
        "weight": maybe_int(payload["weight"]),
        "priority": maybe_int(payload["priority"]),
        "base_url": str(payload.get("base_url") or ""),
        "group": normalize_csv(payload.get("group")),
        "models": normalize_csv(payload.get("models")),
        "model_mapping": normalize_json_mapping(payload.get("model_mapping")),
        "config": json.dumps(json.loads(payload.get("config") or "{}"), sort_keys=True),
        "system_prompt": str(payload.get("system_prompt") or ""),
    }


def ensure_channel(base_url: str, root_access_token: str, spec: dict[str, Any]) -> dict[str, Any]:
    payload = channel_payload_from_spec(spec)
    desired = normalize_channel_payload_for_compare(payload)
    existing = find_exact_by_name(search_channels(base_url, root_access_token, spec["name"]), spec["name"])
    changed = False
    if existing is None:
        url = f"{base_url.rstrip('/')}/api/channel/"
        _status, response = http_json("POST", url, headers=admin_headers(root_access_token), json_body=payload)
        expect_success(response, url)
        changed = True
        existing = find_exact_by_name(search_channels(base_url, root_access_token, spec["name"]), spec["name"])
        if existing is None:
            raise BootstrapError(f"channel {spec['name']!r} was created but could not be found afterwards")
    channel_id = int(existing["id"])
    current = normalize_channel_for_compare(get_channel(base_url, root_access_token, channel_id))
    if current != desired:
        url = f"{base_url.rstrip('/')}/api/channel/"
        update_payload = dict(payload)
        update_payload["id"] = channel_id
        _status, response = http_json("PUT", url, headers=admin_headers(root_access_token), json_body=update_payload)
        expect_success(response, url)
        changed = True
    verified = get_channel(base_url, root_access_token, channel_id)
    return {
        "id": channel_id,
        "name": spec["name"],
        "changed": changed,
        "models": normalize_csv(verified.get("models")),
        "group": normalize_csv(verified.get("group")),
        "priority": maybe_int(verified.get("priority")),
        "base_url": str(verified.get("base_url") or ""),
    }


def verify_channel(base_url: str, root_access_token: str, spec: dict[str, Any]) -> dict[str, Any]:
    payload = channel_payload_from_spec(spec)
    desired = normalize_channel_payload_for_compare(payload)
    existing = find_exact_by_name(search_channels(base_url, root_access_token, spec["name"]), spec["name"])
    if existing is None:
        raise BootstrapError(f"channel {spec['name']!r} is missing")
    channel_id = int(existing["id"])
    verified = get_channel(base_url, root_access_token, channel_id)
    current = normalize_channel_for_compare(verified)
    if current != desired:
        raise BootstrapError(
            f"channel {spec['name']!r} drifted from repo truth: current={current} desired={desired}"
        )
    return {
        "id": channel_id,
        "name": spec["name"],
        "changed": False,
        "models": normalize_csv(verified.get("models")),
        "group": normalize_csv(verified.get("group")),
        "priority": maybe_int(verified.get("priority")),
        "base_url": str(verified.get("base_url") or ""),
    }


def token_payload_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "status": int(spec.get("status", 1)),
        "expired_time": int(spec.get("expired_time", -1)),
        "remain_quota": int(spec.get("remain_quota", -1)),
        "unlimited_quota": bool(spec.get("unlimited_quota", True)),
        "models": ",".join(spec.get("models", [])),
        "subnet": spec.get("subnet", ""),
    }


def normalize_token_for_compare(token: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(token.get("name", "")),
        "status": maybe_int(token.get("status") or 1),
        "expired_time": maybe_int(token.get("expired_time", -1)),
        "remain_quota": maybe_int(token.get("remain_quota", -1)),
        "unlimited_quota": bool(token.get("unlimited_quota", False)),
        "models": normalize_csv(token.get("models")),
        "subnet": str(token.get("subnet") or ""),
    }


def normalize_token_payload_for_compare(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": payload["name"],
        "status": maybe_int(payload["status"]),
        "expired_time": maybe_int(payload["expired_time"]),
        "remain_quota": maybe_int(payload["remain_quota"]),
        "unlimited_quota": bool(payload["unlimited_quota"]),
        "models": normalize_csv(payload.get("models")),
        "subnet": str(payload.get("subnet") or ""),
    }


def ensure_token(base_url: str, root_access_token: str, spec: dict[str, Any]) -> dict[str, Any]:
    payload = token_payload_from_spec(spec)
    desired = normalize_token_payload_for_compare(payload)
    existing = find_exact_by_name(search_tokens(base_url, root_access_token, spec["name"]), spec["name"])
    changed = False
    if existing is None:
        url = f"{base_url.rstrip('/')}/api/token/"
        _status, response = http_json("POST", url, headers=admin_headers(root_access_token), json_body=payload)
        created = expect_success(response, url)
        if not isinstance(created, dict):
            raise BootstrapError(f"{url} did not return a token object")
        existing = created
        changed = True
    token_id = int(existing["id"])
    current = normalize_token_for_compare(get_token(base_url, root_access_token, token_id))
    if current != desired:
        url = f"{base_url.rstrip('/')}/api/token/"
        update_payload = dict(payload)
        update_payload["id"] = token_id
        _status, response = http_json("PUT", url, headers=admin_headers(root_access_token), json_body=update_payload)
        expect_success(response, url)
        changed = True
    verified = get_token(base_url, root_access_token, token_id)
    token_key = str(verified.get("key") or "")
    if not token_key:
        raise BootstrapError(f"token {spec['name']!r} did not return a usable key")
    return {
        "id": token_id,
        "name": spec["name"],
        "key": token_key,
        "changed": changed,
        "models": normalize_csv(verified.get("models")),
        "provider_env_path": spec.get("provider_env_path", ""),
        "provider_base_url": spec.get("provider_base_url", ""),
    }


def verify_token(base_url: str, root_access_token: str, spec: dict[str, Any]) -> dict[str, Any]:
    payload = token_payload_from_spec(spec)
    desired = normalize_token_payload_for_compare(payload)
    existing = find_exact_by_name(search_tokens(base_url, root_access_token, spec["name"]), spec["name"])
    if existing is None:
        raise BootstrapError(f"token {spec['name']!r} is missing")
    token_id = int(existing["id"])
    verified = get_token(base_url, root_access_token, token_id)
    current = normalize_token_for_compare(verified)
    if current != desired:
        raise BootstrapError(
            f"token {spec['name']!r} drifted from repo truth: current={current} desired={desired}"
        )
    token_key = str(verified.get("key") or "")
    if not token_key:
        raise BootstrapError(f"token {spec['name']!r} did not return a usable key")
    return {
        "id": token_id,
        "name": spec["name"],
        "key": token_key,
        "changed": False,
        "models": normalize_csv(verified.get("models")),
        "provider_env_path": spec.get("provider_env_path", ""),
        "provider_base_url": spec.get("provider_base_url", ""),
    }


def update_root_profile(base_url: str, root_access_token: str, root_password: str, root_user: dict[str, Any]) -> None:
    payload = {
        "username": root_user["username"],
        "password": root_password,
        "display_name": root_user["display_name"],
    }
    url = f"{base_url.rstrip('/')}/api/user/self"
    _status, response = http_json("PUT", url, headers=admin_headers(root_access_token), json_body=payload)
    expect_success(response, url)


def render_provider_env(token_key: str, provider_base_url: str) -> str:
    return f"OPENAI_API_KEY={token_key}\nOPENAI_API_BASE_URL={provider_base_url}\n"


def write_provider_envs(token_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for token in token_results:
        provider_env_path = token.get("provider_env_path")
        provider_base_url = token.get("provider_base_url")
        if not provider_env_path or not provider_base_url:
            continue
        resolved = repo_path(str(provider_env_path))
        changed = write_text_if_changed(resolved, render_provider_env(token["key"], str(provider_base_url)))
        results.append(
            {
                "name": token["name"],
                "path": str(resolved),
                "base_url": str(provider_base_url),
                "changed": changed,
            }
        )
    return results


def verify_runtime(
    base_url: str,
    root_access_token: str,
    verification: dict[str, Any],
    token_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status_data = get_status(base_url)
    root_user = get_self(base_url, root_access_token)
    verifier_name = str(verification["token_name"])
    if verifier_name not in token_by_name:
        raise BootstrapError(f"verification token {verifier_name!r} was not declared")
    token_key = token_by_name[verifier_name]["key"]

    models_url = f"{base_url.rstrip('/')}/v1/models"
    _status, models_payload = http_json("GET", models_url, headers=bearer_headers(token_key))
    if isinstance(models_payload, dict) and isinstance(models_payload.get("data"), list):
        model_data = models_payload["data"]
    else:
        model_data = expect_success(models_payload, models_url)
    if not isinstance(model_data, list):
        raise BootstrapError(f"{models_url} did not return a model list")
    available_models = sorted(item["id"] for item in model_data if isinstance(item, dict) and isinstance(item.get("id"), str))

    expected_chat_model = str(verification["chat_model"])
    expected_embedding_model = str(verification["embedding_model"])
    for expected_model in (expected_chat_model, expected_embedding_model):
        if expected_model not in available_models:
            raise BootstrapError(f"expected model alias {expected_model!r} was not exposed by /v1/models")

    chat_url = f"{base_url.rstrip('/')}/v1/chat/completions"
    chat_request = {
        "model": expected_chat_model,
        "messages": [{"role": "user", "content": str(verification["chat_prompt"])}],
        "max_tokens": 24,
        "temperature": 0,
        "stream": False,
    }
    _status, chat_payload = http_json("POST", chat_url, headers=bearer_headers(token_key), json_body=chat_request)
    if not isinstance(chat_payload, dict):
        raise BootstrapError(f"{chat_url} did not return a completion object")
    chat_choices = chat_payload.get("choices")
    if not isinstance(chat_choices, list) or not chat_choices:
        raise BootstrapError("One-API chat completion returned no choices")
    first_choice = chat_choices[0]
    first_message = first_choice.get("message") if isinstance(first_choice, dict) else None
    chat_content = ""
    if isinstance(first_message, dict):
        chat_content = str(first_message.get("content") or "").strip()
    if not chat_content:
        raise BootstrapError("One-API chat completion returned an empty assistant message")

    embeddings_url = f"{base_url.rstrip('/')}/v1/embeddings"
    embeddings_request = {
        "model": expected_embedding_model,
        "input": str(verification["embedding_input"]),
    }
    _status, embeddings_payload = http_json(
        "POST",
        embeddings_url,
        headers=bearer_headers(token_key),
        json_body=embeddings_request,
    )
    if not isinstance(embeddings_payload, dict):
        raise BootstrapError(f"{embeddings_url} did not return an embeddings object")
    embedding_data = embeddings_payload.get("data")
    if not isinstance(embedding_data, list) or not embedding_data:
        raise BootstrapError("One-API embeddings response returned no data rows")
    first_embedding = embedding_data[0].get("embedding") if isinstance(embedding_data[0], dict) else None
    if not isinstance(first_embedding, list) or not first_embedding:
        raise BootstrapError("One-API embeddings response returned an empty embedding vector")

    return {
        "status": status_data,
        "root_user": {
            "username": root_user.get("username"),
            "display_name": root_user.get("display_name"),
            "role": root_user.get("role"),
        },
        "available_models": available_models,
        "chat_model": expected_chat_model,
        "chat_response_excerpt": chat_content[:120],
        "embedding_model": expected_embedding_model,
        "embedding_dimensions": len(first_embedding),
    }


def apply_configuration(config: dict[str, Any], base_url: str, root_access_token: str, root_password: str) -> dict[str, Any]:
    root_user = config["root_user"]
    update_root_profile(base_url, root_access_token, root_password, root_user)

    channel_results = [ensure_channel(base_url, root_access_token, spec) for spec in config.get("channels", [])]
    token_results = [ensure_token(base_url, root_access_token, spec) for spec in config.get("tokens", [])]
    provider_env_results = write_provider_envs(token_results)
    token_by_name = {item["name"]: item for item in token_results}
    verification = verify_runtime(base_url, root_access_token, config["verification"], token_by_name)

    changed = any(item["changed"] for item in channel_results) or any(item["changed"] for item in token_results)
    changed = changed or any(item["changed"] for item in provider_env_results)

    return {
        "changed": changed,
        "verification_passed": True,
        "channels": [{key: value for key, value in item.items() if key != "key"} for item in channel_results],
        "tokens": [
            {
                "id": item["id"],
                "name": item["name"],
                "changed": item["changed"],
                "models": item["models"],
                "key_suffix": item["key"][-8:],
            }
            for item in token_results
        ],
        "provider_env_files": provider_env_results,
        "verification": verification,
    }


def verify_configuration(config: dict[str, Any], base_url: str, root_access_token: str) -> dict[str, Any]:
    channel_results = [verify_channel(base_url, root_access_token, spec) for spec in config.get("channels", [])]
    token_results = [verify_token(base_url, root_access_token, spec) for spec in config.get("tokens", [])]
    token_by_name = {item["name"]: item for item in token_results}
    verification = verify_runtime(base_url, root_access_token, config["verification"], token_by_name)
    provider_env_results = []
    for spec in config.get("tokens", []):
        provider_env_path = spec.get("provider_env_path")
        provider_base_url = spec.get("provider_base_url")
        if not provider_env_path or not provider_base_url:
            continue
        resolved = repo_path(str(provider_env_path))
        provider_env_results.append(
            {
                "name": spec["name"],
                "path": str(resolved),
                "exists": resolved.exists(),
            }
        )
    return {
        "changed": False,
        "verification_passed": True,
        "channels": [{key: value for key, value in item.items() if key != "key"} for item in channel_results],
        "tokens": [
            {
                "id": item["id"],
                "name": item["name"],
                "changed": False,
                "models": item["models"],
                "key_suffix": item["key"][-8:],
            }
            for item in token_results
        ],
        "provider_env_files": provider_env_results,
        "verification": verification,
    }


def emit_report(report: dict[str, Any], write_report: Path | None) -> None:
    enriched = {
        "schema_version": "1.0.0",
        "executed_at": datetime.now(UTC).isoformat(),
        **report,
    }
    rendered = json.dumps(enriched, indent=2, sort_keys=True)
    if write_report is not None:
        write_report.parent.mkdir(parents=True, exist_ok=True)
        write_report.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap repo-managed One-API channels, tokens, and provider env files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply the declared One-API configuration and verify it.")
    verify_parser = subparsers.add_parser("verify", help="Verify the declared One-API configuration without mutating provider env files.")

    for subparser in (apply_parser, verify_parser):
        subparser.add_argument("--config", required=True, type=Path, help="Path to config/one-api/bootstrap.json.")
        subparser.add_argument("--one-api-url", required=True, help="Base URL for the One-API admin and data plane.")
        subparser.add_argument(
            "--root-access-token-file",
            required=True,
            type=Path,
            help="Controller-local file containing the root access token.",
        )
        subparser.add_argument(
            "--write-report",
            type=Path,
            help="Optional report path that receives the rendered JSON result.",
        )

    apply_parser.add_argument(
        "--root-password-file",
        required=True,
        type=Path,
        help="Controller-local file containing the root password to enforce via /api/user/self.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_json(repo_path(str(args.config)))
    base_url = args.one_api_url.rstrip("/")
    root_access_token = read_text(repo_path(str(args.root_access_token_file)))

    if args.command == "apply":
        root_password = read_text(repo_path(str(args.root_password_file)))
        report = apply_configuration(config, base_url, root_access_token, root_password)
    else:
        report = verify_configuration(config, base_url, root_access_token)

    emit_report(report, repo_path(str(args.write_report)) if args.write_report else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
