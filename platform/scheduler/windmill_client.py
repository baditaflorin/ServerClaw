from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]

try:
    from platform.circuit import CircuitRegistry as _CircuitRegistry
    from platform.circuit import should_count_urllib_exception as _should_count_urllib_exception
except ModuleNotFoundError:
    _CircuitRegistry = None
    _should_count_urllib_exception = None

try:
    from platform.retry import policy_for_surface as _policy_for_surface
    from platform.retry import with_retry as _with_retry
except ModuleNotFoundError:
    _policy_for_surface = None
    _with_retry = None

try:
    from platform.timeouts import default_timeout as _default_timeout
    from platform.timeouts import resolve_timeout_seconds as _resolve_timeout_seconds
except ModuleNotFoundError:
    def _default_timeout(_surface: str) -> float:
        return 30.0

    def _resolve_timeout_seconds(_surface: str, value: float | None) -> float:
        return float(30.0 if value is None else value)


def _fallback_request_timeout_seconds(value: float | None) -> float:
    return float(30.0 if value is None else value)


def _compute_request_timeout_seconds(value: float | None) -> float:
    try:
        return _resolve_timeout_seconds("http_request", value)
    except Exception:
        return _fallback_request_timeout_seconds(value)


def _load_internal_api_retry_policy() -> Any | None:
    if _policy_for_surface is None:
        return None
    try:
        return _policy_for_surface("internal_api")
    except Exception:
        return None


class WindmillClient(Protocol):
    def submit_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        ...

    def get_job(self, job_id: str) -> dict[str, Any]:
        ...

    def list_jobs(self, *, running: bool | None = None) -> list[dict[str, Any]]:
        ...

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any] | None:
        ...


class HttpWindmillClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        workspace: str = "lv3",
        request_timeout_seconds: float | None = None,
        circuit_breaker: Any | None = None,
        circuit_registry: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._workspace = workspace
        self._internal_api_retry_policy = _load_internal_api_retry_policy()
        self._request_timeout_seconds = _compute_request_timeout_seconds(request_timeout_seconds)
        self._circuit_breaker = circuit_breaker
        self._session_token: str | None = None
        if self._circuit_breaker is None and _CircuitRegistry is not None and _should_count_urllib_exception is not None:
            try:
                registry = circuit_registry or _CircuitRegistry(REPO_ROOT)
                if registry.has_policy("windmill"):
                    self._circuit_breaker = registry.sync_breaker(
                        "windmill",
                        exception_classifier=_should_count_urllib_exception,
                    )
            except Exception:
                self._circuit_breaker = None

    def _login_with_bootstrap_secret(self) -> str:
        payload = json.dumps(
            {
                "email": "superadmin_secret@windmill.dev",
                "password": self._token,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/api/auth/login",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=_compute_request_timeout_seconds(self._request_timeout_seconds),
        ) as response:
            token = response.read().decode("utf-8").strip()
        if not token:
            raise RuntimeError("Windmill bootstrap login returned an empty session token")
        self._session_token = token
        return token

    def _request(
        self,
        path: str,
        *,
        method: str,
        payload: Any | None = None,
        timeout: float | None = None,
        retry: bool = True,
        allow_login_retry: bool = True,
    ) -> Any:
        data = None
        auth_token = self._session_token or self._token
        headers = {"Authorization": f"Bearer {auth_token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        def execute() -> str:
            open_request = lambda: urllib.request.urlopen(
                request,
                timeout=_compute_request_timeout_seconds(timeout or self._request_timeout_seconds),
            )
            response_cm = open_request()
            if retry and self._internal_api_retry_policy is not None and _with_retry is not None:
                response_cm = _with_retry(
                    open_request,
                    policy=self._internal_api_retry_policy,
                    error_context=f"windmill {method} {path}",
                )
            with response_cm as response:
                return response.read().decode("utf-8")

        if self._circuit_breaker is not None:
            try:
                body = self._circuit_breaker.call(execute)
            except urllib.error.HTTPError as exc:
                if exc.code != 401 or not allow_login_retry or self._session_token is not None:
                    raise
                self._login_with_bootstrap_secret()
                return self._request(
                    path,
                    method=method,
                    payload=payload,
                    timeout=timeout,
                    retry=retry,
                    allow_login_retry=False,
                )
        else:
            try:
                body = execute()
            except urllib.error.HTTPError as exc:
                if exc.code != 401 or not allow_login_retry or self._session_token is not None:
                    raise
                self._login_with_bootstrap_secret()
                return self._request(
                    path,
                    method=method,
                    payload=payload,
                    timeout=timeout,
                    retry=retry,
                    allow_login_retry=False,
                )
        if not body.strip():
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    def _workflow_script_path(self, workflow_id: str) -> str:
        return workflow_id if "/" in workflow_id else f"f/{self._workspace}/{workflow_id}"

    @staticmethod
    def _normalize_submission_response(response: Any) -> dict[str, Any]:
        if isinstance(response, str):
            return {"job_id": response, "running": True}
        if isinstance(response, dict):
            if "job_id" in response or "id" in response:
                return {"job_id": str(response.get("job_id") or response.get("id")), **response}
            return response
        raise RuntimeError(f"unexpected Windmill submit response: {response!r}")

    @staticmethod
    def is_terminal_job(payload: dict[str, Any]) -> bool:
        if payload.get("completed") is True:
            return True
        if payload.get("success") is not None:
            return True
        if payload.get("canceled") is True:
            return True
        if payload.get("running") is False and payload.get("started_at"):
            return True
        state = str(payload.get("status") or payload.get("job_status") or payload.get("state") or "").lower()
        return state in {"cancelled", "canceled", "completed", "failed", "success"}

    def get_script(self, script_path: str) -> dict[str, Any]:
        encoded_path = urllib.parse.quote(script_path, safe="")
        response = self._request(
            f"/api/w/{self._workspace}/scripts/get/p/{encoded_path}",
            method="GET",
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"unexpected Windmill script response: {response!r}")
        return response

    def resolve_script_hash(self, script_path: str) -> str:
        payload = self.get_script(script_path)
        script_hash = payload.get("hash")
        if script_hash in (None, ""):
            raise RuntimeError(f"Windmill script {script_path!r} did not expose a hash")
        return str(script_hash)

    def submit_workflow_by_hash(
        self,
        script_hash: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        encoded_hash = urllib.parse.quote(script_hash, safe="")
        response = self._request(
            f"/api/w/{self._workspace}/jobs/run/h/{encoded_hash}",
            method="POST",
            payload=arguments,
            retry=False,
        )
        return self._normalize_submission_response(response)

    def submit_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        script_path = self._workflow_script_path(workflow_id)
        encoded_path = urllib.parse.quote(script_path, safe="")
        try:
            response = self._request(
                f"/api/w/{self._workspace}/jobs/run/p/{encoded_path}",
                method="POST",
                payload=arguments,
                retry=False,
            )
            return self._normalize_submission_response(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 405}:
                raise

        submission = self.submit_workflow_by_hash(self.resolve_script_hash(script_path), arguments)
        submission.setdefault("mode", "hash_fallback")
        return submission

    def get_job(self, job_id: str) -> dict[str, Any]:
        response = self._request(
            f"/api/w/{self._workspace}/jobs_u/get/{urllib.parse.quote(job_id, safe='')}",
            method="GET",
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"unexpected Windmill job response: {response!r}")
        return response

    def wait_for_job(
        self,
        job_id: str,
        *,
        timeout_seconds: int | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> dict[str, Any]:
        wait_timeout = timeout_seconds or self._request_timeout_seconds
        deadline = time.monotonic() + max(wait_timeout, 1)
        while True:
            response = self.get_job(job_id)
            if self.is_terminal_job(response):
                return response
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for Windmill job {job_id}")
            time.sleep(min(max(poll_interval_seconds, 0.1), remaining))

    def run_workflow_wait_result(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> Any:
        submission = self.submit_workflow(workflow_id, arguments, timeout_seconds=timeout_seconds)
        job_id = submission.get("job_id")
        if job_id is None:
            if submission.get("canceled") is True:
                raise RuntimeError(f"Windmill workflow {workflow_id} was canceled before returning a result")
            if submission.get("success") is False:
                raise RuntimeError(
                    f"Windmill workflow {workflow_id} failed before returning a result: {json.dumps(submission, sort_keys=True)}"
                )
            return submission.get("result")

        status = self.wait_for_job(
            str(job_id),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        if status.get("canceled") is True:
            raise RuntimeError(f"Windmill job {job_id} for {workflow_id} was canceled")
        if status.get("success") is False:
            raise RuntimeError(f"Windmill job {job_id} for {workflow_id} failed: {json.dumps(status, sort_keys=True)}")
        return status.get("result")

    def list_jobs(self, *, running: bool | None = None) -> list[dict[str, Any]]:
        query: dict[str, str] = {}
        if running is not None:
            query["running"] = "true" if running else "false"
        path = f"/api/w/{self._workspace}/jobs/list"
        if query:
            path = f"{path}?{urllib.parse.urlencode(query)}"
        response = self._request(path, method="GET")
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        if isinstance(response, dict):
            for key in ("jobs", "items", "results", "data"):
                value = response.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise RuntimeError(f"unexpected Windmill jobs response: {response!r}")

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(job_id, safe="")
        payload = {"reason": reason} if reason else None
        for path in (
            f"/api/w/{self._workspace}/jobs_u/cancel/{encoded}",
            f"/api/w/{self._workspace}/jobs_u/queue/cancel/{encoded}",
            f"/api/w/{self._workspace}/jobs_u/force_cancel/{encoded}",
            f"/api/w/{self._workspace}/jobs_u/queue/force_cancel/{encoded}",
        ):
            try:
                response = self._request(path, method="POST", payload=payload)
                return response if isinstance(response, dict) else {"response": response}
            except urllib.error.HTTPError as exc:
                if exc.code in {404, 405}:
                    continue
                raise
        return None
