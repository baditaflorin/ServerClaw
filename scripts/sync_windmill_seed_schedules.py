#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class SyncError(RuntimeError):
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
    if status not in expected_statuses:
        raise SyncError(f"{method} {path} returned {status}: {body[:500]}")
    return status, body


def schedule_payload(spec: dict) -> dict:
    return {
        "schedule": spec["schedule"],
        "timezone": spec["timezone"],
        "args": spec.get("args", {}),
        "summary": spec["summary"],
        "description": spec["description"],
        "no_flow_overlap": spec.get("no_flow_overlap", True),
    }


def schedule_exists(*, base_url: str, workspace: str, token: str, schedule_path: str) -> bool:
    _, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"schedules/exists/{urllib.parse.quote(schedule_path, safe='')}",
        method="GET",
        expected_statuses=(200,),
    )
    return body.strip().lower() == "true"


def create_schedule(*, base_url: str, workspace: str, token: str, spec: dict) -> None:
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
    )
    if status == 400 and "already exists" not in body.lower():
        raise SyncError(f"create {spec['path']} returned 400: {body[:500]}")


def update_schedule(*, base_url: str, workspace: str, token: str, spec: dict) -> None:
    request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"schedules/update/{urllib.parse.quote(spec['path'], safe='')}",
        method="POST",
        payload=schedule_payload(spec),
        expected_statuses=(200,),
    )


def sync_schedule(
    *,
    base_url: str,
    workspace: str,
    token: str,
    spec: dict,
    max_attempts: int,
    settle_interval_s: float,
) -> dict:
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            if schedule_exists(base_url=base_url, workspace=workspace, token=token, schedule_path=spec["path"]):
                update_schedule(base_url=base_url, workspace=workspace, token=token, spec=spec)
                return {"path": spec["path"], "attempts": attempt, "status": "updated"}
            create_schedule(base_url=base_url, workspace=workspace, token=token, spec=spec)
            return {"path": spec["path"], "attempts": attempt, "status": "created"}
        except (OSError, SyncError) as exc:
            last_error = str(exc)[:500]
            time.sleep(settle_interval_s)
    raise SyncError(f"failed to sync {spec['path']} after {max_attempts} attempts: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize repo-managed Windmill seed schedules.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=8)
    parser.add_argument("--settle-interval", type=float, default=1.0)
    args = parser.parse_args()

    token = os.environ.get("WINDMILL_TOKEN", "").strip()
    if not token:
        print(json.dumps({"status": "error", "reason": "WINDMILL_TOKEN is required"}), file=os.sys.stderr)
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
            file=os.sys.stderr,
        )
        return 1

    print(json.dumps({"status": "ok", "count": len(results), "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
