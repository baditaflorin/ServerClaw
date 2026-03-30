#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - exercised on older controller Python runtimes
    from datetime import timezone

    UTC = timezone.utc


REPO_ROOT = Path(__file__).resolve().parent.parent


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

HTTP_TIMEOUT_SECONDS = 10
HTTP_RETRY_ATTEMPTS = 6
HTTP_RETRY_DELAY_SECONDS = 5


class AuthzError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeycloakPrincipal:
    name: str
    principal: str
    grant_type: str
    expected_claims: dict[str, str]
    client_id: str | None = None
    client_secret_file: Path | None = None
    username: str | None = None
    password_file: Path | None = None


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


def keycloak_principal(kind: str, identifier: str) -> str:
    return f"principal:{kind}__{identifier}"


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    form_body: dict[str, str] | None = None,
    expected_status: int | tuple[int, ...] = 200,
    timeout_seconds: int = HTTP_TIMEOUT_SECONDS,
    retries: int = HTTP_RETRY_ATTEMPTS,
    retry_delay_seconds: int = HTTP_RETRY_DELAY_SECONDS,
) -> Any:
    body = None
    request_headers = dict(headers or {})
    if json_body is not None and form_body is not None:
        raise ValueError("only one of json_body or form_body may be provided")
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers["content-type"] = "application/json"
    elif form_body is not None:
        body = urllib.parse.urlencode(form_body).encode("utf-8")
        request_headers["content-type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    last_error: Exception | None = None
    for attempt in range(max(retries, 1)):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                if isinstance(expected_status, tuple):
                    if response.status not in expected_status:
                        raise AuthzError(f"{method} {url} returned unexpected status {response.status}")
                elif response.status != expected_status:
                    raise AuthzError(f"{method} {url} returned unexpected status {response.status}")
                return response.status, json.loads(payload) if payload else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AuthzError(f"{method} {url} failed with status {exc.code}: {detail}") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
            if attempt == max(retries, 1) - 1:
                break
            if retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)
    assert last_error is not None
    raise AuthzError(f"{method} {url} failed after {max(retries, 1)} attempts: {last_error}") from last_error


def bearer_headers(preshared_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {preshared_key}"}


def decode_jwt_unverified(token: str) -> dict[str, Any]:
    try:
        _header, payload, _signature = token.split(".")
    except ValueError as exc:
        raise AuthzError("unexpected JWT format returned by Keycloak") from exc
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding)
    return json.loads(decoded.decode("utf-8"))


def load_principals(config: dict[str, Any]) -> list[KeycloakPrincipal]:
    principals = []
    for name, item in config["principals"].items():
        principals.append(
            KeycloakPrincipal(
                name=name,
                principal=item["principal"],
                grant_type=item["grant_type"],
                expected_claims=dict(item.get("expected_claims", {})),
                client_id=item.get("client_id"),
                client_secret_file=repo_path(item["client_secret_file"]) if item.get("client_secret_file") else None,
                username=item.get("username"),
                password_file=repo_path(item["password_file"]) if item.get("password_file") else None,
            )
        )
    return principals


def verify_keycloak_principal(base_url: str, principal: KeycloakPrincipal) -> dict[str, Any]:
    if principal.grant_type == "declared":
        if not principal.username:
            raise AuthzError(f"declared principal '{principal.name}' is missing username")
        expected_principal = keycloak_principal("keycloak-user", principal.username)
        if principal.principal != expected_principal:
            raise AuthzError(
                f"declared principal '{principal.name}' must match the stable Keycloak username reference "
                f"'{expected_principal}'"
            )
        return {
            "principal_name": principal.name,
            "principal": principal.principal,
            "client_id": None,
            "grant_type": principal.grant_type,
            "verification": "declared_principal",
            "claims": {
                "preferred_username": principal.username,
            },
        }

    if not principal.client_id or principal.client_secret_file is None:
        raise AuthzError(f"token-backed principal '{principal.name}' is missing client_id or client_secret_file")

    token_url = f"{base_url.rstrip('/')}/realms/lv3/protocol/openid-connect/token"
    form = {
        "client_id": principal.client_id,
        "client_secret": read_text(principal.client_secret_file),
    }
    if principal.grant_type == "password":
        if not principal.username or principal.password_file is None:
            raise AuthzError(f"password grant principal '{principal.name}' is missing username or password_file")
        form.update(
            {
                "grant_type": "password",
                "username": principal.username,
                "password": read_text(principal.password_file),
            }
        )
    elif principal.grant_type == "client_credentials":
        form["grant_type"] = "client_credentials"
    else:
        raise AuthzError(f"unsupported grant type '{principal.grant_type}' for principal '{principal.name}'")

    _status, payload = http_json("POST", token_url, form_body=form, expected_status=200)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise AuthzError(f"Keycloak did not return an access_token for principal '{principal.name}'")
    claims = decode_jwt_unverified(token)
    mismatches = {
        claim: {"expected": expected, "actual": claims.get(claim)}
        for claim, expected in principal.expected_claims.items()
        if claims.get(claim) != expected
    }
    if mismatches:
        raise AuthzError(f"token claims for principal '{principal.name}' did not match expectations: {mismatches}")
    return {
        "principal_name": principal.name,
        "principal": principal.principal,
        "client_id": principal.client_id,
        "grant_type": principal.grant_type,
        "verification": "token",
        "claims": {claim: claims.get(claim) for claim in sorted(set(principal.expected_claims) | {"sub", "azp", "preferred_username", "client_id"}) if claims.get(claim) is not None},
    }


def normalize_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                if key in {"id", "module", "source_info"}:
                    continue
                if key == "condition" and item == "":
                    continue
                normalized_item = normalize(item)
                if normalized_item in ({}, [], None) and key not in {"relations", "metadata", "conditions"}:
                    continue
                result[key] = normalized_item
            return result
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    normalized = normalize(payload)
    if "conditions" not in normalized:
        normalized["conditions"] = {}
    return normalized


def list_stores(openfga_url: str, preshared_key: str) -> list[dict[str, Any]]:
    _status, payload = http_json(
        "GET",
        f"{openfga_url.rstrip('/')}/stores",
        headers=bearer_headers(preshared_key),
        expected_status=200,
    )
    return payload.get("stores", [])


def ensure_store(openfga_url: str, preshared_key: str, store_name: str) -> tuple[str, bool]:
    for store in list_stores(openfga_url, preshared_key):
        if store.get("name") == store_name:
            return str(store["id"]), False
    _status, payload = http_json(
        "POST",
        f"{openfga_url.rstrip('/')}/stores",
        headers=bearer_headers(preshared_key),
        json_body={"name": store_name},
        expected_status=201,
    )
    return str(payload["id"]), True


def get_latest_authorization_model(openfga_url: str, preshared_key: str, store_id: str) -> dict[str, Any] | None:
    _status, payload = http_json(
        "GET",
        f"{openfga_url.rstrip('/')}/stores/{store_id}/authorization-models",
        headers=bearer_headers(preshared_key),
        expected_status=200,
    )
    models = payload.get("authorization_models", [])
    return models[0] if models else None


def ensure_authorization_model(
    openfga_url: str,
    preshared_key: str,
    store_id: str,
    desired_model: dict[str, Any],
) -> tuple[str, bool]:
    current = get_latest_authorization_model(openfga_url, preshared_key, store_id)
    if current is not None and normalize_model_payload(current) == normalize_model_payload(desired_model):
        return str(current["id"]), False
    _status, payload = http_json(
        "POST",
        f"{openfga_url.rstrip('/')}/stores/{store_id}/authorization-models",
        headers=bearer_headers(preshared_key),
        json_body=desired_model,
        expected_status=201,
    )
    return str(payload["authorization_model_id"]), True


def ensure_tuples(
    openfga_url: str,
    preshared_key: str,
    store_id: str,
    model_id: str,
    tuples: list[dict[str, str]],
) -> None:
    http_json(
        "POST",
        f"{openfga_url.rstrip('/')}/stores/{store_id}/write",
        headers=bearer_headers(preshared_key),
        json_body={
            "writes": {
                "tuple_keys": tuples,
                "on_duplicate": "ignore",
            },
            "authorization_model_id": model_id,
        },
        expected_status=200,
    )


def run_checks(
    openfga_url: str,
    preshared_key: str,
    store_id: str,
    model_id: str,
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results = []
    for item in checks:
        _status, payload = http_json(
            "POST",
            f"{openfga_url.rstrip('/')}/stores/{store_id}/check",
            headers=bearer_headers(preshared_key),
            json_body={
                "authorization_model_id": model_id,
                "tuple_key": {
                    "user": item["user"],
                    "relation": item["relation"],
                    "object": item["object"],
                },
            },
            expected_status=200,
        )
        allowed = bool(payload.get("allowed"))
        results.append(
            {
                "name": item["name"],
                "user": item["user"],
                "relation": item["relation"],
                "object": item["object"],
                "expected": bool(item["allowed"]),
                "actual": allowed,
                "passed": allowed == bool(item["allowed"]),
            }
        )
    return results


def build_report(
    config: dict[str, Any],
    *,
    mode: str,
    openfga_url: str,
    store_id: str,
    store_created: bool,
    model_id: str,
    model_changed: bool,
    principal_reports: list[dict[str, Any]],
    check_results: list[dict[str, Any]],
) -> dict[str, Any]:
    verification_passed = all(item["passed"] for item in check_results)
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "changed": bool(store_created or model_changed),
        "openfga_url": openfga_url,
        "store_name": config["store"]["name"],
        "store_id": store_id,
        "store_created": store_created,
        "authorization_model_id": model_id,
        "authorization_model_changed": model_changed,
        "tuple_count": len(config["tuples"]),
        "principals": principal_reports,
        "checks": check_results,
        "verification_passed": verification_passed,
    }


def write_report(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(mode: str, config_path: Path, openfga_url: str, openfga_preshared_key: str, keycloak_url: str, report_path: Path | None) -> dict[str, Any]:
    config = load_json(config_path)
    model = load_json(repo_path(config["model_path"]))
    principal_reports = [verify_keycloak_principal(keycloak_url, item) for item in load_principals(config)]
    store_id, store_created = ensure_store(openfga_url, openfga_preshared_key, config["store"]["name"])
    model_id, model_changed = ensure_authorization_model(openfga_url, openfga_preshared_key, store_id, model)
    if mode == "apply":
        ensure_tuples(openfga_url, openfga_preshared_key, store_id, model_id, list(config["tuples"]))
    check_results = run_checks(openfga_url, openfga_preshared_key, store_id, model_id, list(config["checks"]))
    report = build_report(
        config,
        mode=mode,
        openfga_url=openfga_url,
        store_id=store_id,
        store_created=store_created,
        model_id=model_id,
        model_changed=model_changed,
        principal_reports=principal_reports,
        check_results=check_results,
    )
    write_report(report_path, report)
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap and verify the repo-managed ServerClaw delegated authorization model.")
    parser.add_argument("mode", choices=("apply", "verify"))
    parser.add_argument("--config", default=str(REPO_ROOT / "config" / "serverclaw-authz" / "bootstrap.json"))
    parser.add_argument("--openfga-url", required=True)
    parser.add_argument("--openfga-preshared-key-file", required=True)
    parser.add_argument("--keycloak-url", required=True)
    parser.add_argument("--write-report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = run(
            args.mode,
            repo_path(args.config),
            args.openfga_url,
            read_text(repo_path(args.openfga_preshared_key_file)),
            args.keycloak_url,
            repo_path(args.write_report) if args.write_report else None,
        )
    except AuthzError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
