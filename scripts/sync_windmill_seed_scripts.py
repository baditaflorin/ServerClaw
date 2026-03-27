#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from platform.retry import PlatformRetryError, RetryClass, RetryPolicy, with_retry


class SyncError(RuntimeError):
    pass


class RetryableSyncError(SyncError):
    pass


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
) -> tuple[int, str]:
    url = f"{base_url}/api/w/{urllib.parse.quote(workspace, safe='')}/{path}"
    request = build_request(url, token, method, payload)
    try:
        with urllib.request.urlopen(request) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RetryableSyncError(f"{method} {path} transient transport failure: {exc}") from exc
    if status not in expected_statuses:
        error_cls = RetryableSyncError if status >= 500 or status in (408, 429) else SyncError
        raise error_cls(f"{method} {path} returned {status}: {body[:500]}")
    return status, body


def delete_script(*, base_url: str, workspace: str, token: str, script_path: str) -> None:
    status, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"scripts/delete/p/{urllib.parse.quote(script_path, safe='')}",
        method="POST",
        expected_statuses=(200, 400, 404),
    )
    if status == 400 and "no rows returned" not in body.lower():
        raise SyncError(f"delete {script_path} returned 400: {body[:500]}")


def get_script(
    *,
    base_url: str,
    workspace: str,
    token: str,
    script_path: str,
) -> tuple[int, dict | None]:
    status, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"scripts/get/p/{urllib.parse.quote(script_path, safe='')}",
        method="GET",
        expected_statuses=(200, 404),
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
        status, _ = get_script(base_url=base_url, workspace=workspace, token=token, script_path=script_path)
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
        status, payload = get_script(base_url=base_url, workspace=workspace, token=token, script_path=script_path)
        if status == 200 and payload and payload.get("content") == expected_content:
            return
        time.sleep(interval_s)
    raise SyncError(f"timed out waiting for {script_path} to match expected content")


def sync_script(
    *,
    base_url: str,
    workspace: str,
    token: str,
    spec: dict,
    max_attempts: int,
    settle_interval_s: float,
) -> dict:
    content = Path(spec["local_file"]).read_text(encoding="utf-8")
    attempts = 0

    def sync_attempt() -> dict:
        nonlocal attempts
        attempts += 1
        try:
            delete_script(base_url=base_url, workspace=workspace, token=token, script_path=spec["path"])
            time.sleep(settle_interval_s)
            wait_for_absent(
                base_url=base_url,
                workspace=workspace,
                token=token,
                script_path=spec["path"],
                timeout_s=max(3.0, settle_interval_s * 4),
                interval_s=settle_interval_s,
            )
        except RetryableSyncError as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            ) from exc
        except SyncError:
            pass
        try:
            status, body = create_script(base_url=base_url, workspace=workspace, token=token, spec=spec, content=content)
        except RetryableSyncError as exc:
            raise PlatformRetryError(
                str(exc),
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            ) from exc
        if status != 201:
            raise PlatformRetryError(
                f"failed to sync {spec['path']}: {body[:500]}",
                code="platform:windmill_seed_sync_pending",
                retry_class=RetryClass.BACKOFF,
            )
        wait_for_content(
            base_url=base_url,
            workspace=workspace,
            token=token,
            script_path=spec["path"],
            expected_content=content,
            timeout_s=max(3.0, settle_interval_s * 4),
            interval_s=settle_interval_s,
        )
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
        raise SyncError(f"failed to sync {spec['path']} after {max_attempts} attempts: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize repo-managed Windmill seed scripts.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--settle-interval", type=float, default=1.0)
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
