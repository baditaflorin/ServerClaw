from __future__ import annotations

import html
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PlaneError(RuntimeError):
    """Raised when Plane bootstrap or API actions fail."""


def _json_dumps(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _parse_query_error(location: str | None) -> str | None:
    if not location:
        return None
    parsed = urllib.parse.urlparse(location)
    params = urllib.parse.parse_qs(parsed.query)
    messages = params.get("error_message")
    if messages:
        return messages[0]
    values = params.get("error_code")
    if values:
        return values[0]
    return None


def _paged_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return results
    raise PlaneError(f"Unexpected paginated payload shape: {type(payload)!r}")


def _first_cookie(cookie_jar: http.cookiejar.CookieJar, name: str) -> str | None:
    for cookie in cookie_jar:
        if cookie.name == name:
            return cookie.value
    return None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PlaneClient:
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
        if not self.api_token:
            raise PlaneError("Plane API token is empty")
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
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        headers = {
            "Accept": "application/json",
            "X-Api-Key": self.api_token,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        expected = expected_statuses or {200}
        attempt = 0
        while True:
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    status = response.status
            except urllib.error.HTTPError as exc:
                status = exc.code
                raw = exc.read().decode("utf-8")
            if status in expected:
                if not raw:
                    return status, None
                if accept_json:
                    return status, json.loads(raw)
                return status, raw
            if status == 429 and attempt < self.max_rate_limit_retries:
                time.sleep(self.rate_limit_backoff_seconds * (2**attempt))
                attempt += 1
                continue
            raise PlaneError(f"{method} {path} returned HTTP {status}: {raw}")

    def verify_api_key(self) -> bool:
        try:
            self._request("/api/v1/users/me/")
        except PlaneError:
            return False
        return True

    def whoami(self) -> dict[str, Any]:
        _status, payload = self._request("/api/v1/users/me/")
        return payload

    def _collect(self, path: str) -> list[dict[str, Any]]:
        cursor: str | None = None
        results: list[dict[str, Any]] = []
        while True:
            query = "per_page=1000"
            if cursor:
                query += "&cursor=" + urllib.parse.quote(cursor, safe="")
            _status, payload = self._request(f"{path}?{query}")
            page = _paged_results(payload)
            results.extend(page)
            if not isinstance(payload, dict) or not payload.get("next_page_results"):
                return results
            cursor = payload.get("next_cursor")
            if not cursor:
                return results

    def list_workspaces(self) -> list[dict[str, Any]]:
        raise PlaneError("Plane API-key auth does not expose a workspace listing route; use session auth instead")

    def list_projects(self, workspace_slug: str) -> list[dict[str, Any]]:
        return self._collect(f"/api/v1/workspaces/{workspace_slug}/projects/")

    def create_project(self, workspace_slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/v1/workspaces/{workspace_slug}/projects/",
            method="POST",
            payload=payload,
            expected_statuses={201},
        )
        return response

    def list_states(self, workspace_slug: str, project_id: str) -> list[dict[str, Any]]:
        return self._collect(f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/states/")

    def list_issues(self, workspace_slug: str, project_id: str) -> list[dict[str, Any]]:
        return self._collect(f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/issues/")

    def create_issue(self, workspace_slug: str, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/issues/",
            method="POST",
            payload=payload,
            expected_statuses={201},
        )
        return response

    def update_issue(self, workspace_slug: str, project_id: str, issue_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/issues/{issue_id}/",
            method="PATCH",
            payload=payload,
            expected_statuses={200},
        )
        return response


class PlaneSessionClient:
    def __init__(self, base_url: str, *, verify_ssl: bool = True, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._csrf_token: str | None = None
        self._cookie_jar = http.cookiejar.CookieJar()
        cookie_handler = urllib.request.HTTPCookieProcessor(self._cookie_jar)
        if not verify_ssl:
            import ssl

            insecure_context = ssl.create_default_context()
            insecure_context.check_hostname = False
            insecure_context.verify_mode = ssl.CERT_NONE
            https_handler = urllib.request.HTTPSHandler(context=insecure_context)
            self._opener = urllib.request.build_opener(cookie_handler, https_handler)
            self._no_redirect_opener = urllib.request.build_opener(cookie_handler, https_handler, _NoRedirectHandler())
        else:
            self._opener = urllib.request.build_opener(cookie_handler)
            self._no_redirect_opener = urllib.request.build_opener(cookie_handler, _NoRedirectHandler())

    def _csrf_headers(self) -> dict[str, str]:
        token = self._csrf_token
        return {"X-CSRFToken": token} if token else {}

    def _cookie_headers(self) -> dict[str, str]:
        pairs = [f"{cookie.name}={cookie.value}" for cookie in self._cookie_jar]
        if not pairs:
            return {}
        return {"Cookie": "; ".join(pairs)}

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Any | None = None,
        form: dict[str, Any] | None = None,
        expected_statuses: set[int] | None = None,
        accept_json: bool = True,
        follow_redirects: bool = True,
    ) -> tuple[int, Any, dict[str, str]]:
        if payload is not None and form is not None:
            raise PlaneError("Use either payload or form, not both")
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = _json_dumps(payload)
            headers["Content-Type"] = "application/json"
            headers.update(self._csrf_headers())
        elif form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers.update(self._csrf_headers())
        headers.update(self._cookie_headers())
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        opener = self._opener if follow_redirects else self._no_redirect_opener
        expected = expected_statuses or {200}
        response_headers: dict[str, str] = {}
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                status = response.status
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")
            response_headers = dict(exc.headers.items())
        if status not in expected:
            raise PlaneError(f"{method} {path} returned HTTP {status}: {raw}")
        if not raw:
            return status, None, response_headers
        if accept_json:
            return status, json.loads(raw), response_headers
        return status, raw, response_headers

    def prime(self) -> None:
        _status, payload, _headers = self._request("/auth/get-csrf-token/", expected_statuses={200})
        token = str((payload or {}).get("csrf_token", "")).strip()
        if not token:
            raise PlaneError("Plane did not return a usable CSRF token")
        self._csrf_token = token

    def sign_in_admin(self, email: str, password: str) -> str | None:
        self.prime()
        _status, _body, headers = self._request(
            "/api/instances/admins/sign-in/",
            method="POST",
            form={"email": email, "password": password},
            expected_statuses={302},
            accept_json=False,
            follow_redirects=False,
        )
        return _parse_query_error(headers.get("Location"))

    def sign_up_admin(
        self,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        company_name: str,
        is_telemetry_enabled: bool,
    ) -> str | None:
        self.prime()
        _status, _body, headers = self._request(
            "/api/instances/admins/sign-up/",
            method="POST",
            form={
                "email": email,
                "password": password,
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company_name,
                "is_telemetry_enabled": "1" if is_telemetry_enabled else "0",
            },
            expected_statuses={302},
            accept_json=False,
            follow_redirects=False,
        )
        return _parse_query_error(headers.get("Location"))

    def list_workspaces(self) -> list[dict[str, Any]]:
        try:
            _status, payload, _headers = self._request("/api/users/me/workspaces/?per_page=1000")
        except PlaneError as exc:
            if "HTTP 401" not in str(exc):
                raise
            _status, payload, _headers = self._request("/api/instances/workspaces/?per_page=10")
        return _paged_results(payload)

    def create_workspace(self, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response, _headers = self._request(
            "/api/instances/workspaces/",
            method="POST",
            payload=payload,
            expected_statuses={201},
        )
        return response

    def sign_in_user(self, email: str, password: str) -> str | None:
        self.prime()
        _status, _body, headers = self._request(
            "/auth/sign-in/",
            method="POST",
            form={"email": email, "password": password},
            expected_statuses={302},
            accept_json=False,
            follow_redirects=False,
        )
        return _parse_query_error(headers.get("Location"))

    def list_projects(self, workspace_slug: str) -> list[dict[str, Any]]:
        _status, payload, _headers = self._request(f"/api/workspaces/{workspace_slug}/projects/?per_page=1000")
        return _paged_results(payload)

    def create_project(self, workspace_slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response, _headers = self._request(
            f"/api/workspaces/{workspace_slug}/projects/",
            method="POST",
            payload=payload,
            expected_statuses={201},
        )
        return response

    def create_api_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response, _headers = self._request(
            "/api/users/api-tokens/",
            method="POST",
            payload=payload,
            expected_statuses={201},
        )
        return response


def ensure_workspace(session: PlaneSessionClient, name: str, slug: str) -> dict[str, Any]:
    for workspace in session.list_workspaces():
        if workspace.get("slug") == slug:
            return workspace
    return session.create_workspace({"name": name, "slug": slug})


def ensure_project(session: PlaneSessionClient, workspace_slug: str, name: str, identifier: str) -> dict[str, Any]:
    for project in session.list_projects(workspace_slug):
        if project.get("identifier") == identifier or project.get("name") == name:
            return project
    return session.create_project(workspace_slug, {"name": name, "identifier": identifier})


def bootstrap_plane(
    *,
    base_url: str,
    admin_email: str,
    admin_password: str,
    spec: dict[str, Any],
    verify_ssl: bool = True,
    existing_api_token: str | None = None,
) -> dict[str, Any]:
    session = PlaneSessionClient(base_url, verify_ssl=verify_ssl)
    sign_in_error = session.sign_in_admin(admin_email, admin_password)
    if sign_in_error == "ADMIN_USER_DOES_NOT_EXIST":
        admin = spec["admin"]
        sign_up_error = session.sign_up_admin(
            email=admin_email,
            password=admin_password,
            first_name=admin["first_name"],
            last_name=admin.get("last_name", ""),
            company_name=admin.get("company_name", ""),
            is_telemetry_enabled=bool(admin.get("is_telemetry_enabled", False)),
        )
        if sign_up_error:
            raise PlaneError(f"Plane admin sign-up failed with error_code={sign_up_error}")
    elif sign_in_error:
        raise PlaneError(f"Plane admin sign-in failed with error_code={sign_in_error}")

    workspace = ensure_workspace(
        session,
        spec["workspace"]["name"],
        spec["workspace"]["slug"],
    )
    user_sign_in_error = session.sign_in_user(admin_email, admin_password)
    if user_sign_in_error:
        raise PlaneError(f"Plane user sign-in failed with error_code={user_sign_in_error}")
    project = ensure_project(
        session,
        spec["workspace"]["slug"],
        spec["project"]["name"],
        spec["project"]["identifier"],
    )

    api_token_value = (existing_api_token or "").strip()
    if api_token_value:
        token_client = PlaneClient(base_url, api_token_value, verify_ssl=verify_ssl)
        if not token_client.verify_api_key():
            api_token_value = ""

    if not api_token_value:
        token_payload = session.create_api_token(spec.get("api_token", {}))
        api_token_value = str(token_payload.get("token", "")).strip()
        if not api_token_value:
            raise PlaneError("Plane did not return a usable API token")

    token_client = PlaneClient(base_url, api_token_value, verify_ssl=verify_ssl)
    return {
        "workspace": workspace,
        "project": project,
        "api_token": api_token_value,
        "whoami": token_client.whoami(),
    }


ADR_HEADING_RE = re.compile(r"^#\s+ADR\s+(\d+):\s+(.+)$")


@dataclass
class AdrRecord:
    adr_id: str
    title: str
    status: str
    implementation_status: str
    path: Path
    summary: str

    @property
    def external_id(self) -> str:
        return f"adr-{self.adr_id}"


def parse_adr(path: Path) -> AdrRecord:
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = next((line for line in lines if line.startswith("# ADR ")), "")
    match = ADR_HEADING_RE.match(heading.strip())
    if match is None:
        raise PlaneError(f"ADR file {path} is missing a '# ADR XXXX: Title' heading")
    metadata: dict[str, str] = {}
    for line in lines[1:16]:
        if line.startswith("- ") and ":" in line:
            key, value = line[2:].split(":", 1)
            metadata[key.strip()] = value.strip()
    paragraphs: list[str] = []
    current: list[str] = []
    in_context = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Context":
            in_context = True
            current = []
            continue
        if in_context and stripped.startswith("## "):
            break
        if not in_context:
            continue
        if stripped:
            current.append(stripped)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    summary = paragraphs[0] if paragraphs else "No context summary recorded."
    return AdrRecord(
        adr_id=match.group(1),
        title=match.group(2).strip(),
        status=metadata.get("Status", "Unknown"),
        implementation_status=metadata.get("Implementation Status", metadata.get("Status", "Unknown")),
        path=path,
        summary=summary,
    )


def state_name_for_adr(record: AdrRecord) -> str:
    implementation = record.implementation_status.lower()
    status = record.status.lower()
    if any(term in implementation for term in ("not implemented", "not yet", "planned")):
        if "progress" in implementation:
            return "In Progress"
        if any(term in status for term in ("accepted", "approved", "planned")):
            return "Todo"
        return "Backlog"
    if any(term in implementation for term in ("implemented", "live-applied", "live applied")):
        return "Done"
    if "progress" in implementation:
        return "In Progress"
    if any(term in status for term in ("superseded", "rejected", "deprecated", "withdrawn")):
        return "Cancelled"
    if any(term in status for term in ("accepted", "approved", "planned")):
        return "Todo"
    return "Backlog"


def render_adr_description(record: AdrRecord) -> str:
    repo_path = record.path.as_posix()
    marker = "docs/adr/"
    repo_rel = repo_path.split(marker, 1)[1] if marker in repo_path else record.path.name
    return (
        f"<p><strong>ADR {html.escape(record.adr_id)}</strong> is tracked from "
        f"<code>docs/adr/{html.escape(repo_rel)}</code>.</p>"
        f"<p><strong>Status:</strong> {html.escape(record.status)}<br>"
        f"<strong>Implementation Status:</strong> {html.escape(record.implementation_status)}</p>"
        f"<p>{html.escape(record.summary)}</p>"
    )


def ensure_issue_for_adr(
    client: PlaneClient,
    *,
    workspace_slug: str,
    project_id: str,
    states_by_name: dict[str, str],
    record: AdrRecord,
    existing_issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    wanted_state_name = state_name_for_adr(record)
    wanted_state_id = states_by_name.get(wanted_state_name)
    if wanted_state_id is None:
        raise PlaneError(f"Plane project does not define state '{wanted_state_name}'")
    payload = {
        "name": f"ADR {record.adr_id}: {record.title}",
        "description_html": render_adr_description(record),
        "external_source": "repo_adr",
        "external_id": record.external_id,
        "state_id": wanted_state_id,
    }
    issue = existing_issue
    if issue is None:
        for candidate in client.list_issues(workspace_slug, project_id):
            if candidate.get("external_source") == "repo_adr" and candidate.get("external_id") == record.external_id:
                issue = candidate
                break
    if issue is not None:
        issue_id = issue.get("id")
        if not issue_id:
            raise PlaneError(f"Plane returned an issue without an id for {record.external_id}")
        return client.update_issue(workspace_slug, project_id, issue_id, payload)
    return client.create_issue(workspace_slug, project_id, payload)
