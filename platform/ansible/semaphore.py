from __future__ import annotations

import copy
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


UNFINISHED_TASK_STATUSES = {
    "waiting",
    "starting",
    "waiting_confirmation",
    "confirmed",
    "rejected",
    "running",
    "stopping",
}


class SemaphoreError(RuntimeError):
    """Raised when the Semaphore API returns an unexpected response."""


def _json_dumps(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_value(val) for key, val in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _filtered_payload(payload: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in payload.items()
        if key in allowed_keys and value is not None
    }


def _payload_differs(current: dict[str, Any], desired: dict[str, Any], allowed_keys: set[str]) -> bool:
    return _normalize_value(_filtered_payload(current, allowed_keys)) != _normalize_value(
        _filtered_payload(desired, allowed_keys)
    )


@dataclass
class BootstrapSummary:
    project: dict[str, Any]
    repository: dict[str, Any]
    inventory: dict[str, Any]
    templates: list[dict[str, Any]]
    api_token: str


class SemaphoreClient:
    def __init__(self, base_url: str, *, verify_ssl: bool = True, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._cookie_jar = http.cookiejar.CookieJar()
        cookie_handler = urllib.request.HTTPCookieProcessor(self._cookie_jar)
        self._cookie_opener = urllib.request.build_opener(cookie_handler)
        self._bearer_token: str | None = None
        if not verify_ssl:
            import ssl

            insecure_context = ssl.create_default_context()
            insecure_context.check_hostname = False
            insecure_context.verify_mode = ssl.CERT_NONE
            https_handler = urllib.request.HTTPSHandler(context=insecure_context)
            self._cookie_opener = urllib.request.build_opener(cookie_handler, https_handler)
            self._token_opener = urllib.request.build_opener(https_handler)
        else:
            self._token_opener = urllib.request.build_opener()

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Any | None = None,
        use_bearer: bool = False,
        expected_statuses: set[int] | None = None,
        accept_json: bool = True,
    ) -> tuple[int, Any]:
        data = None if payload is None else _json_dumps(payload)
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        headers: dict[str, str] = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if use_bearer:
            if not self._bearer_token:
                raise SemaphoreError("Bearer token is not configured")
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        opener = self._token_opener if use_bearer else self._cookie_opener
        expected = expected_statuses or {200}
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")
        if status not in expected:
            raise SemaphoreError(f"{method} {path} returned HTTP {status}: {raw}")
        if not raw:
            return status, None
        if accept_json:
            return status, json.loads(raw)
        return status, raw

    def login(self, username: str, password: str) -> None:
        self._request(
            "/api/auth/login",
            method="POST",
            payload={"auth": username, "password": password},
            expected_statuses={204},
            accept_json=False,
        )

    def set_api_token(self, token: str) -> None:
        self._bearer_token = token.strip()

    def verify_api_token(self, token: str | None = None) -> bool:
        previous = self._bearer_token
        if token is not None:
            self._bearer_token = token.strip()
        try:
            self._request("/api/user", use_bearer=True)
        except SemaphoreError:
            if token is not None:
                self._bearer_token = previous
            return False
        return True

    def create_api_token(self) -> str:
        _status, payload = self._request("/api/user/tokens", method="POST", payload={})
        token_id = payload.get("id")
        if not isinstance(token_id, str) or not token_id:
            raise SemaphoreError("Semaphore did not return a usable API token id")
        return token_id

    def get_user(self, *, use_bearer: bool = True) -> dict[str, Any]:
        _status, payload = self._request("/api/user", use_bearer=use_bearer)
        return payload

    def list_projects(self, *, use_bearer: bool = True) -> list[dict[str, Any]]:
        _status, payload = self._request("/api/projects", use_bearer=use_bearer)
        return payload

    def create_project(self, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request("/api/projects", method="POST", payload=payload, use_bearer=use_bearer, expected_statuses={201})
        return response

    def update_project(self, project_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/project/{project_id}",
            method="PUT",
            payload=payload,
            use_bearer=use_bearer,
        )
        return response

    def list_project_keys(self, project_id: int, *, use_bearer: bool = True) -> list[dict[str, Any]]:
        _status, payload = self._request(f"/api/project/{project_id}/keys", use_bearer=use_bearer)
        return payload

    def list_repositories(self, project_id: int, *, use_bearer: bool = True) -> list[dict[str, Any]]:
        _status, payload = self._request(f"/api/project/{project_id}/repositories", use_bearer=use_bearer)
        return payload

    def create_repository(self, project_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/project/{project_id}/repositories",
            method="POST",
            payload=payload,
            use_bearer=use_bearer,
            expected_statuses={201},
        )
        return response

    def update_repository(self, project_id: int, repository_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/project/{project_id}/repositories/{repository_id}",
            method="PUT",
            payload=payload,
            use_bearer=use_bearer,
        )
        return response

    def list_inventories(self, project_id: int, *, use_bearer: bool = True) -> list[dict[str, Any]]:
        _status, payload = self._request(f"/api/project/{project_id}/inventory", use_bearer=use_bearer)
        return payload

    def create_inventory(self, project_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/project/{project_id}/inventory",
            method="POST",
            payload=payload,
            use_bearer=use_bearer,
            expected_statuses={201},
        )
        return response

    def update_inventory(self, project_id: int, inventory_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/project/{project_id}/inventory/{inventory_id}",
            method="PUT",
            payload=payload,
            use_bearer=use_bearer,
        )
        return response

    def list_templates(self, project_id: int, *, use_bearer: bool = True) -> list[dict[str, Any]]:
        _status, payload = self._request(f"/api/project/{project_id}/templates", use_bearer=use_bearer)
        return payload

    def create_template(self, project_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/project/{project_id}/templates",
            method="POST",
            payload=payload,
            use_bearer=use_bearer,
            expected_statuses={201},
        )
        return response

    def update_template(self, project_id: int, template_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/project/{project_id}/templates/{template_id}",
            method="PUT",
            payload=payload,
            use_bearer=use_bearer,
        )
        return response

    def start_task(
        self,
        project_id: int,
        template_id: int,
        *,
        inventory_id: int | None = None,
        params: dict[str, Any] | None = None,
        use_bearer: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": project_id,
            "template_id": template_id,
            "params": params or {},
        }
        if inventory_id is not None:
            payload["inventory_id"] = inventory_id
        _status, response = self._request(
            f"/api/project/{project_id}/tasks",
            method="POST",
            payload=payload,
            use_bearer=use_bearer,
            expected_statuses={201},
        )
        return response

    def get_task(self, project_id: int, task_id: int, *, use_bearer: bool = True) -> dict[str, Any]:
        _status, payload = self._request(f"/api/project/{project_id}/tasks/{task_id}", use_bearer=use_bearer)
        return payload

    def get_task_output(self, project_id: int, task_id: int, *, raw: bool = True, use_bearer: bool = True) -> str:
        path = f"/api/project/{project_id}/tasks/{task_id}/{'raw_output' if raw else 'output'}"
        _status, payload = self._request(path, use_bearer=use_bearer, accept_json=not raw)
        if raw:
            return payload
        return json.dumps(payload, indent=2, sort_keys=True)

    def wait_for_task(
        self,
        project_id: int,
        task_id: int,
        *,
        timeout_seconds: int = 300,
        poll_seconds: int = 5,
        use_bearer: bool = True,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            task = self.get_task(project_id, task_id, use_bearer=use_bearer)
            status = task.get("status")
            if status not in UNFINISHED_TASK_STATUSES:
                return task
            time.sleep(poll_seconds)
        raise SemaphoreError(f"Timed out waiting for task {task_id} to finish")


PROJECT_UPDATE_FIELDS = {"name", "alert", "alert_chat", "max_parallel_tasks", "type"}
REPOSITORY_UPDATE_FIELDS = {"name", "git_url", "git_branch", "ssh_key_id", "project_id"}
INVENTORY_UPDATE_FIELDS = {
    "name",
    "inventory",
    "ssh_key_id",
    "become_key_id",
    "type",
    "template_id",
    "repository_id",
    "runner_tag",
    "project_id",
}
TEMPLATE_UPDATE_FIELDS = {
    "name",
    "playbook",
    "arguments",
    "allow_override_args_in_task",
    "description",
    "type",
    "autorun",
    "git_branch",
    "survey_vars",
    "suppress_success_alerts",
    "app",
    "task_params",
    "allow_override_branch_in_task",
    "allow_parallel_tasks",
    "inventory_id",
    "repository_id",
    "environment_id",
    "project_id",
    "vaults",
}


def ensure_project(client: Any, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
    project_name = payload["name"]
    projects = client.list_projects(use_bearer=use_bearer)
    for project in projects:
        if project.get("name") != project_name:
            continue
        project_id = int(project["id"])
        desired = dict(payload)
        desired["id"] = project_id
        if _payload_differs(project, desired, PROJECT_UPDATE_FIELDS):
            return client.update_project(project_id, desired, use_bearer=use_bearer)
        return project
    return client.create_project(payload, use_bearer=use_bearer)


def find_none_key_id(keys: list[dict[str, Any]]) -> int:
    for key in keys:
        if key.get("type") == "none":
            return int(key["id"])
    raise SemaphoreError("Semaphore project does not expose a usable 'none' access key")


def ensure_repository(client: Any, project_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
    repositories = client.list_repositories(project_id, use_bearer=use_bearer)
    desired = dict(payload)
    desired["project_id"] = project_id
    for repository in repositories:
        if repository.get("name") != desired["name"]:
            continue
        repository_id = int(repository["id"])
        desired["id"] = repository_id
        if _payload_differs(repository, desired, REPOSITORY_UPDATE_FIELDS):
            return client.update_repository(project_id, repository_id, desired, use_bearer=use_bearer)
        return repository
    return client.create_repository(project_id, desired, use_bearer=use_bearer)


def ensure_inventory(client: Any, project_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
    inventories = client.list_inventories(project_id, use_bearer=use_bearer)
    desired = dict(payload)
    desired["project_id"] = project_id
    for inventory in inventories:
        if inventory.get("name") != desired["name"]:
            continue
        inventory_id = int(inventory["id"])
        desired["id"] = inventory_id
        if _payload_differs(inventory, desired, INVENTORY_UPDATE_FIELDS):
            return client.update_inventory(project_id, inventory_id, desired, use_bearer=use_bearer)
        return inventory
    return client.create_inventory(project_id, desired, use_bearer=use_bearer)


def ensure_template(client: Any, project_id: int, payload: dict[str, Any], *, use_bearer: bool = True) -> dict[str, Any]:
    templates = client.list_templates(project_id, use_bearer=use_bearer)
    desired = dict(payload)
    desired["project_id"] = project_id
    for template in templates:
        if template.get("name") != desired["name"]:
            continue
        template_id = int(template["id"])
        desired["id"] = template_id
        if _payload_differs(template, desired, TEMPLATE_UPDATE_FIELDS):
            return client.update_template(project_id, template_id, desired, use_bearer=use_bearer)
        return template
    return client.create_template(project_id, desired, use_bearer=use_bearer)


def apply_bootstrap_spec(
    client: SemaphoreClient,
    spec: dict[str, Any],
    *,
    username: str,
    password: str,
    verify_ssl: bool,
    existing_api_token: str | None = None,
) -> BootstrapSummary:
    client.login(username, password)
    api_token = existing_api_token.strip() if existing_api_token and existing_api_token.strip() else ""
    if not api_token or not client.verify_api_token(api_token):
        api_token = client.create_api_token()
    client.set_api_token(api_token)

    project = ensure_project(client, spec["project"])
    project_id = int(project["id"])
    none_key_id = find_none_key_id(client.list_project_keys(project_id))

    repository_payload = dict(spec["repository"])
    repository_payload.setdefault("ssh_key_id", none_key_id)
    repository = ensure_repository(client, project_id, repository_payload)

    inventory_payload = dict(spec["inventory"])
    inventory_payload.setdefault("ssh_key_id", none_key_id)
    inventory = ensure_inventory(client, project_id, inventory_payload)

    templates: list[dict[str, Any]] = []
    for template_payload in spec.get("templates", []):
        desired = dict(template_payload)
        desired.setdefault("inventory_id", int(inventory["id"]))
        desired.setdefault("repository_id", int(repository["id"]))
        templates.append(ensure_template(client, project_id, desired))

    return BootstrapSummary(
        project=project,
        repository=repository,
        inventory=inventory,
        templates=templates,
        api_token=api_token,
    )
