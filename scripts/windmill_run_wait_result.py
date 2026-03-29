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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Windmill script via jobs/run_wait_result.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--payload-json", default="{}")
    parser.add_argument("--timeout", type=int, default=120)
    return parser


def login_with_bootstrap_secret(base_url: str, secret: str, timeout: int) -> str:
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
    with urllib.request.urlopen(request, timeout=timeout) as response:
        token = response.read().decode("utf-8").strip()
    if not token:
        raise RuntimeError("Windmill bootstrap login returned an empty session token")
    return token


class WindmillClient:
    def __init__(self, *, base_url: str, token: str, timeout: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._bootstrap_secret = token
        self._token = token

    def _request(self, path: str, *, method: str, payload: dict | None = None):
        data = None
        headers = {"Authorization": f"Bearer {self._token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 401 or self._token != self._bootstrap_secret:
                raise
            self._token = login_with_bootstrap_secret(self.base_url, self._bootstrap_secret, self.timeout)
            return self._request(path, method=method, payload=payload)

    def request_json_or_text(self, path: str, *, method: str, payload: dict | None = None):
        with self._request(path, method=method, payload=payload) as response:
            body = response.read().decode("utf-8")
        if not body.strip():
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body


def resolve_script_hash(client: WindmillClient, *, workspace: str, script_path: str) -> str:
    encoded_workspace = urllib.parse.quote(workspace, safe="")
    encoded_path = urllib.parse.quote(script_path, safe="")
    metadata = client.request_json_or_text(
        f"/api/w/{encoded_workspace}/scripts/get/p/{encoded_path}",
        method="GET",
    )
    if not isinstance(metadata, dict):
        raise RuntimeError(f"Unexpected Windmill script metadata response for {script_path!r}: {metadata!r}")
    script_hash = metadata.get("hash")
    if not isinstance(script_hash, str) or not script_hash.strip():
        raise RuntimeError(f"Windmill script metadata for {script_path!r} did not include a hash")
    return script_hash.strip()


def submit_job_by_hash(
    client: WindmillClient,
    *,
    workspace: str,
    script_hash: str,
    payload: dict,
) -> str:
    encoded_workspace = urllib.parse.quote(workspace, safe="")
    encoded_hash = urllib.parse.quote(script_hash, safe="")
    response = client.request_json_or_text(
        f"/api/w/{encoded_workspace}/jobs/run/h/{encoded_hash}",
        method="POST",
        payload=payload,
    )
    if isinstance(response, str) and response.strip():
        return response.strip()
    if isinstance(response, dict):
        for key in ("job_id", "id"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise RuntimeError(f"Unexpected Windmill job submission response for hash {script_hash!r}: {response!r}")


def wait_for_job_result(client: WindmillClient, *, workspace: str, job_id: str) -> object:
    encoded_workspace = urllib.parse.quote(workspace, safe="")
    encoded_job_id = urllib.parse.quote(job_id, safe="")
    deadline = time.monotonic() + client.timeout
    last_status: dict[str, object] | None = None
    while time.monotonic() < deadline:
        status = client.request_json_or_text(
            f"/api/w/{encoded_workspace}/jobs_u/get/{encoded_job_id}",
            method="GET",
        )
        if not isinstance(status, dict):
            raise RuntimeError(f"Unexpected Windmill job status response for {job_id!r}: {status!r}")
        last_status = status
        if status.get("type") == "CompletedJob" or status.get("success") is not None:
            if status.get("success") is False:
                details = status.get("result") or status.get("logs") or status
                raise RuntimeError(f"Windmill job {job_id} failed: {details!r}")
            return status.get("result")
        time.sleep(2)
    raise TimeoutError(f"Windmill job {job_id} did not complete within {client.timeout} seconds")


def main() -> int:
    args = build_parser().parse_args()
    token = os.environ.get("WINDMILL_TOKEN", "").strip()
    if not token:
        print("WINDMILL_TOKEN is required", file=sys.stderr)
        return 2

    payload = json.loads(args.payload_json)
    client = WindmillClient(base_url=args.base_url, token=token, timeout=args.timeout)
    try:
        script_hash = resolve_script_hash(client, workspace=args.workspace, script_path=args.path)
        job_id = submit_job_by_hash(client, workspace=args.workspace, script_hash=script_hash, payload=payload)
        result = wait_for_job_result(client, workspace=args.workspace, job_id=job_id)
        sys.stdout.write(json.dumps(result))
    except urllib.error.HTTPError as exc:
        sys.stderr.write(exc.read().decode("utf-8"))
        return 1
    except (RuntimeError, TimeoutError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
