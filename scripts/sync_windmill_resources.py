#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_HTTP_TIMEOUT_S = 10.0


class SyncError(RuntimeError):
    pass


def build_request(url: str, token: str, method: str, payload: dict[str, Any] | None = None) -> urllib.request.Request:
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
    payload: dict[str, Any] | None = None,
    expected_statuses: tuple[int, ...],
    timeout_s: float = DEFAULT_HTTP_TIMEOUT_S,
) -> tuple[int, str]:
    url = f"{base_url.rstrip('/')}/api/w/{urllib.parse.quote(workspace, safe='')}/{path}"
    request = build_request(url, token, method, payload)
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise SyncError(f"{method} {path} transport failure: {exc}") from exc
    if status not in expected_statuses:
        raise SyncError(f"{method} {path} returned {status}: {body[:500]}")
    return status, body


def resource_type_exists(*, base_url: str, workspace: str, token: str, name: str, timeout_s: float) -> bool:
    status, _ = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"resources/type/exists/{urllib.parse.quote(name, safe='')}",
        method="GET",
        expected_statuses=(200,),
        timeout_s=timeout_s,
    )
    return status == 200


def resource_exists(*, base_url: str, workspace: str, token: str, path: str, timeout_s: float) -> bool:
    _, body = request_json_or_text(
        base_url=base_url,
        workspace=workspace,
        token=token,
        path=f"resources/exists/{urllib.parse.quote(path, safe='')}",
        method="GET",
        expected_statuses=(200,),
        timeout_s=timeout_s,
    )
    return body.strip().lower() == "true"


def sync_resource_types(
    *,
    base_url: str,
    workspace: str,
    token: str,
    resource_types: list[dict[str, Any]],
    timeout_s: float,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in resource_types:
        name = item["name"]
        if resource_type_exists(base_url=base_url, workspace=workspace, token=token, name=name, timeout_s=timeout_s):
            request_json_or_text(
                base_url=base_url,
                workspace=workspace,
                token=token,
                path=f"resources/type/update/{urllib.parse.quote(name, safe='')}",
                method="POST",
                payload={
                    "schema": item.get("schema", {}),
                    "description": item.get("description", ""),
                },
                expected_statuses=(200,),
                timeout_s=timeout_s,
            )
            results.append({"kind": "resource_type", "name": name, "status": "updated"})
            continue
        request_json_or_text(
            base_url=base_url,
            workspace=workspace,
            token=token,
            path="resources/type/create",
            method="POST",
            payload={
                "name": name,
                "schema": item.get("schema", {}),
                "description": item.get("description", ""),
            },
            expected_statuses=(200, 201),
            timeout_s=timeout_s,
        )
        results.append({"kind": "resource_type", "name": name, "status": "created"})
    return results


def sync_resources(
    *,
    base_url: str,
    workspace: str,
    token: str,
    resources: list[dict[str, Any]],
    timeout_s: float,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in resources:
        path = item["path"]
        payload = {
            "path": path,
            "value": item["value"],
            "description": item.get("description", ""),
            "resource_type": item["resource_type"],
        }
        if resource_exists(base_url=base_url, workspace=workspace, token=token, path=path, timeout_s=timeout_s):
            request_json_or_text(
                base_url=base_url,
                workspace=workspace,
                token=token,
                path=f"resources/update/{urllib.parse.quote(path, safe='')}",
                method="POST",
                payload=payload,
                expected_statuses=(200,),
                timeout_s=timeout_s,
            )
            results.append({"kind": "resource", "name": path, "status": "updated"})
            continue
        request_json_or_text(
            base_url=base_url,
            workspace=workspace,
            token=token,
            path="resources/create?update_if_exists=true",
            method="POST",
            payload=payload,
            expected_statuses=(200, 201),
            timeout_s=timeout_s,
        )
        results.append({"kind": "resource", "name": path, "status": "created"})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize repo-managed Windmill resource types and resources.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--http-timeout", type=float, default=DEFAULT_HTTP_TIMEOUT_S)
    args = parser.parse_args()

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must contain a JSON object")
        resource_types = manifest.get("resource_types", [])
        resources = manifest.get("resources", [])
        if not isinstance(resource_types, list) or not isinstance(resources, list):
            raise ValueError("Manifest resource_types/resources entries must be lists")
        results = []
        results.extend(
            sync_resource_types(
                base_url=args.base_url,
                workspace=args.workspace,
                token=args.token,
                resource_types=resource_types,
                timeout_s=args.http_timeout,
            )
        )
        results.extend(
            sync_resources(
                base_url=args.base_url,
                workspace=args.workspace,
                token=args.token,
                resources=resources,
                timeout_s=args.http_timeout,
            )
        )
        print(json.dumps({"status": "ok", "results": results}, indent=2))
        return 0
    except (OSError, ValueError, SyncError, json.JSONDecodeError) as exc:
        print(f"Windmill resource sync error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
