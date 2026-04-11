#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_HTTP_TIMEOUT_S = 10.0


def resolve_repo_root(script_path: Path | None = None) -> Path:
    candidate = (script_path or Path(__file__)).resolve()
    for parent in (candidate.parent, *candidate.parents):
        if (parent / "platform" / "__init__.py").exists() and (
            (parent / "platform" / "retry.py").exists()
            or (parent / "platform" / "retry").is_dir()
            or (parent / "platform" / "retry" / "__init__.py").exists()
        ):
            return parent
    raise RuntimeError(f"Unable to resolve repository root from {candidate}")


REPO_ROOT = resolve_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.retry import PlatformRetryError, RetryClass, RetryPolicy, with_retry


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
    request = build_request(url, token, method, payload)
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
        raise SyncTransportError(f"{method} {path} transport failure: {exc}") from exc
    if status not in expected_statuses:
        error_cls = (
            RetryableSyncError
            if status >= 500 or status in (408, 429) or is_retryable_windmill_backend_error(body)
            else SyncError
        )
        raise error_cls(f"{method} {path} returned {status}: {body[:500]}")
    return status, body


def schedule_payload(spec: dict) -> dict:
    return {
        "schedule": spec["schedule"],
        "timezone": spec["timezone"],
        "script_path": spec["script_path"],
        "is_flow": False,
        "args": spec.get("args", {}),
        "enabled": spec.get("enabled", False),
        "summary": spec["summary"],
        "description": spec["description"],
        "no_flow_overlap": spec.get("no_flow_overlap", True),
    }


def script_exists(*, base_url: str, workspace: str, token: str, script_path: str, timeout_s: float) -> bool:
    status, _ = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"scripts/get/p/{urllib.parse.quote(script_path, safe='')}",
        method="GET",
        expected_statuses=(200, 404),
        timeout_s=timeout_s,
    )
    return status == 200


def is_missing_schedule_target_error(message: str) -> bool:
    normalized = message.lower()
    return "script not found at name" in normalized or "flow not found at name" in normalized


def schedule_exists(*, base_url: str, workspace: str, token: str, schedule_path: str, timeout_s: float) -> bool:
    _, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"schedules/exists/{urllib.parse.quote(schedule_path, safe='')}",
        method="GET",
        expected_statuses=(200,),
        timeout_s=timeout_s,
    )
    return body.strip().lower() == "true"


def create_schedule(*, base_url: str, workspace: str, token: str, spec: dict, timeout_s: float) -> None:
    payload = {
        "path": spec["path"],
        "schedule": spec["schedule"],
        "timezone": spec["timezone"],
        "script_path": spec["script_path"],
        "is_flow": False,
        "args": spec.get("args", {}),
        "enabled": spec.get("enabled", False),
        "summary": spec["summary"],
        "description": spec["description"],
        "no_flow_overlap": spec.get("no_flow_overlap", True),
    }
    status, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path="schedules/create",
        method="POST",
        payload=payload,
        expected_statuses=(200, 201, 400),
        timeout_s=timeout_s,
    )
    if status == 400 and is_missing_schedule_target_error(body):
        raise RetryableSyncError(f"create {spec['path']} returned 400: {body[:500]}")
    if status == 400 and "already exists" not in body.lower():
        raise SyncError(f"create {spec['path']} returned 400: {body[:500]}")


def update_schedule(*, base_url: str, workspace: str, token: str, spec: dict, timeout_s: float) -> None:
    try:
        request_json_or_text(
            base_url=base_url,
            workspace=workspace,
            token=token,
            path=f"schedules/update/{urllib.parse.quote(spec['path'], safe='')}",
            method="POST",
            payload=schedule_payload(spec),
            expected_statuses=(200,),
            timeout_s=timeout_s,
        )
    except SyncError as exc:
        if is_missing_schedule_target_error(str(exc)):
            raise RetryableSyncError(str(exc)) from exc
        raise


def sync_schedule(
    *,
    base_url: str,
    workspace: str,
    token: str,
    spec: dict,
    max_attempts: int,
    settle_interval_s: float,
    request_timeout_s: float,
) -> dict:
    attempts = 0

    def sync_attempt() -> dict:
        nonlocal attempts
        attempts += 1
        try:
            if not script_exists(
                base_url=base_url,
                workspace=workspace,
                token=token,
                script_path=spec["script_path"],
                timeout_s=request_timeout_s,
            ):
                raise RetryableSyncError(f"script target {spec['script_path']} is not visible yet")
            if schedule_exists(
                base_url=base_url,
                workspace=workspace,
                token=token,
                schedule_path=spec["path"],
                timeout_s=request_timeout_s,
            ):
                update_schedule(
                    base_url=base_url,
                    workspace=workspace,
                    token=token,
                    spec=spec,
                    timeout_s=request_timeout_s,
                )
                return {"path": spec["path"], "attempts": attempts, "status": "updated"}
            create_schedule(
                base_url=base_url,
                workspace=workspace,
                token=token,
                spec=spec,
                timeout_s=request_timeout_s,
            )
            return {"path": spec["path"], "attempts": attempts, "status": "created"}
        except (RetryableSyncError, OSError) as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_schedule_sync_pending",
                retry_class=RetryClass.BACKOFF,
            ) from exc

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
            error_context=f"windmill seed schedule sync for {spec['path']}",
        )
    except Exception as exc:
        raise SyncError(f"failed to sync {spec['path']} after {max_attempts} attempts: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize repo-managed Windmill seed schedules.")
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
                sync_schedule(
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
