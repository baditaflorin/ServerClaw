from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from platform.retry import MaxRetriesExceeded, RetryPolicy, with_retry


class VikunjaError(RuntimeError):
    """Raised when Vikunja bootstrap or API actions fail."""


def _json_dumps(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError | socket.timeout):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, TimeoutError | socket.timeout)
    return False


class VikunjaClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        verify_ssl: bool = True,
        timeout: int = 20,
        max_rate_limit_retries: int = 6,
        rate_limit_backoff_seconds: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token.strip()
        self.timeout = timeout
        self.max_rate_limit_retries = max_rate_limit_retries
        self.rate_limit_backoff_seconds = rate_limit_backoff_seconds
        self._retry_policy = RetryPolicy(
            max_attempts=self.max_rate_limit_retries + 1,
            base_delay_s=self.rate_limit_backoff_seconds,
            max_delay_s=max(
                self.rate_limit_backoff_seconds * (2 ** max(self.max_rate_limit_retries - 1, 0)),
                self.rate_limit_backoff_seconds,
            ),
            multiplier=2.0,
            jitter=False,
            transient_max=0,
        )
        if not self.api_token:
            raise VikunjaError("Vikunja API token is empty")
        if not verify_ssl:
            import ssl

            insecure_context = ssl.create_default_context()
            insecure_context.check_hostname = False
            insecure_context.verify_mode = ssl.CERT_NONE
            https_handler = urllib.request.HTTPSHandler(context=insecure_context)
            self._opener = urllib.request.build_opener(https_handler)
        else:
            self._opener = urllib.request.build_opener()

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Any | None = None,
        expected_statuses: set[int] | None = None,
        accept_json: bool = True,
    ) -> tuple[int, Any]:
        data = None if payload is None else _json_dumps(payload)
        url = urllib.parse.urljoin(f"{self.base_url}/", f"api/v1/{path.lstrip('/')}")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_token}",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        expected = expected_statuses or {200}

        def execute() -> tuple[int, str]:
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    return response.status, response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8")
                if exc.code in expected:
                    return exc.code, raw
                if exc.code in {408, 429, 500, 502, 503, 504}:
                    setattr(exc, "_lv3_raw_body", raw)
                    raise
                return exc.code, raw
            except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
                if _is_timeout_error(exc):
                    raise
                raise VikunjaError(f"{method} {path} failed: {exc}") from exc

        try:
            status, raw = with_retry(
                execute,
                policy=self._retry_policy,
                error_context=f"vikunja {method} {path}",
                sleep_fn=time.sleep,
            )
        except MaxRetriesExceeded as exc:
            last_error = exc.last_error
            if isinstance(last_error, urllib.error.HTTPError):
                raw = getattr(last_error, "_lv3_raw_body", "")
                raise VikunjaError(f"{method} {path} returned HTTP {last_error.code}: {raw}") from exc
            if last_error is not None and _is_timeout_error(last_error):
                raise VikunjaError(f"{method} {path} timed out: {last_error}") from exc
            raise

        if status in expected:
            if not raw:
                return status, None
            if accept_json:
                return status, json.loads(raw)
            return status, raw
        raise VikunjaError(f"{method} {path} returned HTTP {status}: {raw}")

    def verify_api_token(self) -> bool:
        try:
            self._request("/user")
        except VikunjaError:
            return False
        return True

    def whoami(self) -> dict[str, Any]:
        _status, payload = self._request("/user")
        return payload

    def info(self) -> dict[str, Any]:
        _status, payload = self._request("/info")
        return payload

    def list_projects(self, *, search: str = "") -> list[dict[str, Any]]:
        query = ""
        if search:
            query = "?" + urllib.parse.urlencode({"s": search})
        _status, payload = self._request(f"/projects{query}")
        if not isinstance(payload, list):
            raise VikunjaError("projects response did not return a list")
        return payload

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request("/projects", method="PUT", payload=payload, expected_statuses={201})
        return response

    def update_project(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(f"/projects/{project_id}", method="POST", payload=payload)
        return response

    def list_labels(self, *, search: str = "") -> list[dict[str, Any]]:
        query = ""
        if search:
            query = "?" + urllib.parse.urlencode({"s": search})
        _status, payload = self._request(f"/labels{query}")
        if not isinstance(payload, list):
            raise VikunjaError("labels response did not return a list")
        return payload

    def create_label(self, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request("/labels", method="PUT", payload=payload, expected_statuses={201})
        return response

    def list_tasks(self, *, search: str = "", project_id: int | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if search:
            query["s"] = search
        if project_id is not None:
            query["filter"] = f"project_id = {project_id}"
        suffix = "?" + urllib.parse.urlencode(query) if query else ""
        _status, payload = self._request(f"/tasks{suffix}")
        if not isinstance(payload, list):
            raise VikunjaError("tasks response did not return a list")
        return payload

    def get_task(self, task_id: int) -> dict[str, Any]:
        _status, payload = self._request(f"/tasks/{task_id}")
        return payload

    def create_task(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(f"/projects/{project_id}/tasks", method="PUT", payload=payload, expected_statuses={201})
        return response

    def update_task(self, task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(f"/tasks/{task_id}", method="POST", payload=payload)
        return response

    def add_comment(self, task_id: int, comment: str) -> dict[str, Any]:
        _status, response = self._request(
            f"/tasks/{task_id}/comments",
            method="PUT",
            payload={"comment": comment},
            expected_statuses={201},
        )
        return response

    def replace_task_labels(self, task_id: int, label_ids: list[int]) -> dict[str, Any]:
        labels = [{"id": label_id} for label_id in label_ids]
        _status, response = self._request(
            f"/tasks/{task_id}/labels/bulk",
            method="POST",
            payload={"labels": labels},
            expected_statuses={201},
        )
        return response

    def replace_task_assignees(self, task_id: int, user_ids: list[int]) -> dict[str, Any]:
        assignees = [{"id": user_id} for user_id in user_ids]
        _status, response = self._request(
            f"/tasks/{task_id}/assignees/bulk",
            method="POST",
            payload={"assignees": assignees},
            expected_statuses={201},
        )
        return response

    def search_users(self, query: str) -> list[dict[str, Any]]:
        suffix = "?" + urllib.parse.urlencode({"s": query})
        _status, payload = self._request(f"/users{suffix}")
        if not isinstance(payload, list):
            raise VikunjaError("users response did not return a list")
        return payload

    def list_project_users(self, project_id: int) -> list[dict[str, Any]]:
        _status, payload = self._request(f"/projects/{project_id}/users")
        if not isinstance(payload, list):
            raise VikunjaError("project users response did not return a list")
        return payload

    def add_project_user(self, project_id: int, username: str, permission: int) -> dict[str, Any]:
        _status, response = self._request(
            f"/projects/{project_id}/users",
            method="PUT",
            payload={"username": username, "permission": permission},
            expected_statuses={201},
        )
        return response

    def update_project_user(self, project_id: int, user_id: int, username: str, permission: int) -> dict[str, Any]:
        _status, response = self._request(
            f"/projects/{project_id}/users/{user_id}",
            method="POST",
            payload={"username": username, "permission": permission},
        )
        return response

    def list_webhooks(self, project_id: int) -> list[dict[str, Any]]:
        _status, payload = self._request(f"/projects/{project_id}/webhooks")
        if not isinstance(payload, list):
            raise VikunjaError("webhooks response did not return a list")
        return payload

    def create_webhook(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(
            f"/projects/{project_id}/webhooks",
            method="PUT",
            payload=payload,
            expected_statuses={200},
        )
        return response

    def delete_webhook(self, project_id: int, webhook_id: int) -> None:
        self._request(f"/projects/{project_id}/webhooks/{webhook_id}", method="DELETE")


def login(base_url: str, username: str, password: str, *, verify_ssl: bool = True, timeout: int = 20) -> str:
    data = _json_dumps({"username": username, "password": password, "long_token": True})
    url = urllib.parse.urljoin(f"{base_url.rstrip('/')}/", "api/v1/login")
    if not verify_ssl:
        import ssl

        insecure_context = ssl.create_default_context()
        insecure_context.check_hostname = False
        insecure_context.verify_mode = ssl.CERT_NONE
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=insecure_context))
    else:
        opener = urllib.request.build_opener()
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        raise VikunjaError(f"login failed with HTTP {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise VikunjaError(f"login failed: {exc.reason}") from exc
    token = str(payload.get("token", "")).strip()
    if not token:
        raise VikunjaError("login returned an empty token")
    return token


def create_api_token(
    base_url: str,
    session_token: str,
    *,
    title: str,
    expires_at: str,
    verify_ssl: bool = True,
    timeout: int = 20,
) -> dict[str, Any]:
    client = VikunjaClient(base_url, session_token, verify_ssl=verify_ssl, timeout=timeout)
    _status, payload = client._request(
        "/tokens",
        method="PUT",
        payload={"title": title, "expires_at": expires_at},
        expected_statuses={200},
    )
    return payload


def load_auth(path: str | Path) -> dict[str, Any]:
    auth_path = Path(path).expanduser()
    return json.loads(auth_path.read_text(encoding="utf-8"))


def write_auth(path: str | Path, payload: dict[str, Any]) -> None:
    auth_path = Path(path).expanduser()
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    auth_path.chmod(0o600)


def find_project_by_identifier(projects: list[dict[str, Any]], identifier: str) -> dict[str, Any] | None:
    for project in projects:
        if project.get("identifier") == identifier or project.get("title") == identifier:
            return project
    return None


def find_label_by_title(labels: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    for label in labels:
        if label.get("title") == title:
            return label
    return None
