#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_HTTP_TIMEOUT_S = 10.0
MIN_SETTLE_TIMEOUT_S = 10.0
ABSENT_SETTLE_TIMEOUT_MULTIPLIER = 10.0
CONTENT_SETTLE_TIMEOUT_MULTIPLIER = 30.0


def resolve_repo_root(script_path: Path | None = None) -> Path:
    candidate = (script_path or Path(__file__)).resolve()
    for parent in (candidate.parent, *candidate.parents):
        if (
            (parent / "platform" / "__init__.py").exists()
            and (
                (parent / "platform" / "retry.py").exists()
                or (parent / "platform" / "retry").is_dir()
                or (parent / "platform" / "retry" / "__init__.py").exists()
            )
        ):
            return parent
    raise RuntimeError(f"Unable to resolve repository root from {candidate}")


REPO_ROOT = resolve_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.retry import MaxRetriesExceeded, PlatformRetryError, RetryClass, RetryPolicy, with_retry


REQUEST_RETRY_POLICY = RetryPolicy(
    max_attempts=4,
    base_delay_s=0.25,
    max_delay_s=2.0,
    multiplier=2.0,
    jitter=False,
    transient_max=0,
)


class SyncError(RuntimeError):
    pass


class RetryableSyncError(SyncError):
    pass


class SyncTransportError(RetryableSyncError):
    pass


def is_retryable_windmill_backend_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "error communicating with database" in normalized
        or "connection reset by peer" in normalized
        or "connection closed unexpectedly" in normalized
        or "broken pipe" in normalized
        or "database is starting up" in normalized
    )


def login_with_bootstrap_secret(
    base_url: str,
    secret: str,
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> str:
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
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            token = response.read().decode("utf-8").strip()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise SyncError(f"bootstrap login returned {exc.code}: {body[:500]}") from exc
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        raise SyncTransportError(f"bootstrap login transport error: {exc}") from exc
    if not token:
        raise SyncError("bootstrap login returned an empty session token")
    return token


def build_request(url: str, token: str, method: str, payload: dict | None = None) -> urllib.request.Request:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=body, headers=headers, method=method)


def request_json_or_text(
    *,
    base_url: str,
    workspace: str,
    token: str,
    path: str,
    method: str,
    payload: dict | None = None,
    expected_statuses: tuple[int, ...],
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> tuple[int, str]:
    url = f"{base_url}/api/w/{urllib.parse.quote(workspace, safe='')}/{path}"

    def execute_request(session_token: str) -> tuple[int, str]:
        request = build_request(url, session_token, method, payload)
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")
        except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
            raise SyncTransportError(f"{method} {path} transport error: {exc}") from exc

    def request_attempt() -> tuple[int, str]:
        try:
            status, body = execute_request(token)
            if status == 401:
                session_token = login_with_bootstrap_secret(base_url, token, timeout_s=timeout_s)
                status, body = execute_request(session_token)
            if status not in expected_statuses:
                error_cls = (
                    RetryableSyncError
                    if status >= 500 or status in (408, 429) or is_retryable_windmill_backend_error(body)
                    else SyncError
                )
                raise error_cls(f"{method} {path} returned {status}: {body[:500]}")
            return status, body
        except SyncTransportError as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_sync_transport",
                retry_class=RetryClass.BACKOFF,
            ) from exc

    try:
        return with_retry(
            request_attempt,
            policy=REQUEST_RETRY_POLICY,
            error_context=f"{method} {path}",
        )
    except MaxRetriesExceeded as exc:
        last_error = exc.last_error
        if isinstance(last_error, SyncTransportError):
            raise last_error
        if isinstance(last_error, PlatformRetryError) and isinstance(last_error.__cause__, SyncTransportError):
            raise last_error.__cause__
        raise


def delete_script(
    *,
    base_url: str,
    workspace: str,
    token: str,
    script_path: str,
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> None:
    status, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"scripts/delete/p/{urllib.parse.quote(script_path, safe='')}",
        method="POST",
        expected_statuses=(200, 400, 404),
        timeout_s=timeout_s,
    )
    if status == 400 and "no rows returned" not in body.lower():
        raise SyncError(f"delete {script_path} returned 400: {body[:500]}")


def get_script(
    *,
    base_url: str,
    workspace: str,
    token: str,
    script_path: str,
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> tuple[int, dict | None]:
    status, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"scripts/get/p/{urllib.parse.quote(script_path, safe='')}",
        method="GET",
        expected_statuses=(200, 404),
        timeout_s=timeout_s,
    )
    if status == 404:
        return status, None
    return status, json.loads(body)


def wait_for_absent(
    *,
    base_url: str,
    workspace: str,
    token: str,
    script_path: str,
    timeout_s: float,
    interval_s: float,
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status, _ = get_script(
            base_url=base_url,
            workspace=workspace,
            token=token,
            script_path=script_path,
            timeout_s=timeout_s,
        )
        if status == 404:
            return
        time.sleep(interval_s)
    raise SyncError(f"timed out waiting for {script_path} to disappear")


def create_script(
    *,
    base_url: str,
    workspace: str,
    token: str,
    spec: dict,
    content: str,
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> tuple[int, str]:
    payload = {
        "path": spec["path"],
        "language": spec["language"],
        "summary": spec["summary"],
        "description": spec["description"],
        "kind": "script",
        "deployment_message": "Repo-managed Windmill seed sync",
        "content": content,
    }
    return request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path="scripts/create",
        method="POST",
        payload=payload,
        expected_statuses=(201, 400),
        timeout_s=timeout_s,
    )


def wait_for_content(
    *,
    base_url: str,
    workspace: str,
    token: str,
    script_path: str,
    expected_content: str,
    timeout_s: float,
    interval_s: float,
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status, payload = get_script(
            base_url=base_url,
            workspace=workspace,
            token=token,
            script_path=script_path,
            timeout_s=timeout_s,
        )
        if status == 200 and payload and payload.get("content") == expected_content:
            return
        time.sleep(interval_s)
    raise SyncError(f"timed out waiting for {script_path} to match expected content")


def settle_timeout(settle_interval_s: float, multiplier: float) -> float:
    return max(MIN_SETTLE_TIMEOUT_S, settle_interval_s * multiplier)


def remote_script_matches_spec(remote_payload: dict | None, spec: dict, content: str) -> bool:
    if not remote_payload:
        return False
    return (
        remote_payload.get("content") == content
        and remote_payload.get("language") == spec["language"]
        and remote_payload.get("summary") == spec["summary"]
        and remote_payload.get("description") == spec["description"]
    )


def sync_script(
    *,
    base_url: str,
    workspace: str,
    token: str,
    spec: dict,
    max_attempts: int,
    settle_interval_s: float,
    request_timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> dict:
    content = Path(spec["local_file"]).read_text(encoding="utf-8")
    attempts = 0
    absent_timeout_s = settle_timeout(settle_interval_s, ABSENT_SETTLE_TIMEOUT_MULTIPLIER)
    content_timeout_s = settle_timeout(settle_interval_s, CONTENT_SETTLE_TIMEOUT_MULTIPLIER)

    def sync_attempt() -> dict:
        nonlocal attempts
        attempts += 1
        script_absent_after_delete = False
        status, remote_payload = get_script(
            base_url=base_url,
            workspace=workspace,
            token=token,
            script_path=spec["path"],
            timeout_s=request_timeout_s,
        )
        if status == 200 and remote_script_matches_spec(remote_payload, spec, content):
            return {"path": spec["path"], "attempts": attempts, "status": "synced"}
        try:
            delete_script(
                base_url=base_url,
                workspace=workspace,
                token=token,
                script_path=spec["path"],
                timeout_s=request_timeout_s,
            )
        except SyncTransportError as exc:
            try:
                status, remote_payload = get_script(
                    base_url=base_url,
                    workspace=workspace,
                    token=token,
                    script_path=spec["path"],
                    timeout_s=request_timeout_s,
                )
            except (RetryableSyncError, SyncError, OSError):
                raise PlatformRetryError(
                    str(exc),
                    code="platform:windmill_seed_sync_pending",
                    retry_class=RetryClass.BACKOFF,
                ) from exc
            if status == 404:
                script_absent_after_delete = True
            elif remote_script_matches_spec(remote_payload, spec, content):
                return {"path": spec["path"], "attempts": attempts, "status": "synced"}
            else:
                raise PlatformRetryError(
                    str(exc),
                    code="platform:windmill_seed_sync_pending",
                    retry_class=RetryClass.BACKOFF,
                ) from exc
        except (RetryableSyncError, OSError) as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            ) from exc
        try:
            if not script_absent_after_delete:
                time.sleep(settle_interval_s)
                wait_for_absent(
                    base_url=base_url,
                    workspace=workspace,
                    token=token,
                    script_path=spec["path"],
                    timeout_s=absent_timeout_s,
                    interval_s=settle_interval_s,
                )
        except (RetryableSyncError, SyncError, OSError) as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            ) from exc
        try:
            status, body = create_script(
                base_url=base_url,
                workspace=workspace,
                token=token,
                spec=spec,
                content=content,
                timeout_s=request_timeout_s,
            )
        except (RetryableSyncError, OSError) as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            ) from exc
        if status != 201:
            status, remote_payload = get_script(
                base_url=base_url,
                workspace=workspace,
                token=token,
                script_path=spec["path"],
                timeout_s=request_timeout_s,
            )
            if status == 200 and remote_script_matches_spec(remote_payload, spec, content):
                return {"path": spec["path"], "attempts": attempts, "status": "synced"}
            raise PlatformRetryError(
                f"failed to sync {spec['path']}: {body[:500]}",
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            )
        try:
            wait_for_content(
                base_url=base_url,
                workspace=workspace,
                token=token,
                script_path=spec["path"],
                expected_content=content,
                timeout_s=content_timeout_s,
                interval_s=settle_interval_s,
            )
        except (RetryableSyncError, SyncError, OSError) as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            ) from exc
        return {"path": spec["path"], "attempts": attempts, "status": "synced"}

    try:
        return with_retry(
            sync_attempt,
            policy=RetryPolicy(
                max_attempts=max_attempts,
                base_delay_s=settle_interval_s,
                max_delay_s=settle_interval_s,
                multiplier=1.0,
                jitter=False,
                transient_max=0,
            ),
            error_context=f"windmill seed sync for {spec['path']}",
        )
    except Exception as exc:
        detail = str(exc)
        if isinstance(exc, MaxRetriesExceeded) and exc.last_error is not None:
            detail = f"{detail}; last error: {exc.last_error}"
        raise SyncError(f"failed to sync {spec['path']} after {max_attempts} attempts: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize repo-managed Windmill seed scripts.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--settle-interval", type=float, default=1.0)
    parser.add_argument("--http-timeout", type=float, default=DEFAULT_HTTP_TIMEOUT_S)
    args = parser.parse_args()

    token = os.environ.get("WINDMILL_TOKEN", "").strip()
    if not token:
        print(json.dumps({"status": "error", "reason": "WINDMILL_TOKEN is required"}), file=sys.stderr)
        return 2

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results: list[dict] = []
    try:
        for spec in manifest:
            results.append(
                sync_script(
                    base_url=args.base_url.rstrip("/"),
                    workspace=args.workspace,
                    token=token,
                    spec=spec,
                    max_attempts=args.max_attempts,
                    settle_interval_s=args.settle_interval,
                    request_timeout_s=args.http_timeout,
                )
            )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "results": results,
                    "failed_path": spec.get("path"),
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"status": "ok", "count": len(results), "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
