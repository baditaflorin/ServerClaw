from __future__ import annotations

import copy
import http.cookiejar
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from platform.retry import MaxRetriesExceeded, RetryPolicy, with_retry


TERMINAL_PIPELINE_STATES = {
    "success",
    "failure",
    "killed",
    "error",
    "declined",
    "skipped",
}


class GiteaError(RuntimeError):
    """Raised when the Gitea API returns an unexpected response."""


class WoodpeckerError(RuntimeError):
    """Raised when the Woodpecker API or login flow returns an unexpected response."""


class _HttpStatusError(RuntimeError):
    def __init__(self, message: str, *, status: int, body: str):
        super().__init__(message)
        self.status = status
        self.body = body


def _json_dumps(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in sorted(value.items())}
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


def _is_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError | socket.timeout):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return isinstance(reason, TimeoutError | socket.timeout)
    return False


def _strip_api_prefix(path: str) -> str:
    if path.startswith("/api/"):
        return path[4:]
    return path


def _api_candidates(path: str) -> list[str]:
    clean = "/" + _strip_api_prefix(path).lstrip("/")
    prefixed = "/api" + clean
    return [clean, prefixed]


def _pipeline_state(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or payload.get("state") or "").strip().lower()


def _hidden_inputs(inputs: dict[str, dict[str, str]]) -> dict[str, str]:
    return {
        name: attributes.get("value", "")
        for name, attributes in inputs.items()
        if attributes.get("type", "text").lower() in {"hidden", "submit"}
    }


def _pick_username_field(inputs: dict[str, dict[str, str]]) -> str:
    for candidate in ("user_name", "username", "login", "email"):
        if candidate in inputs:
            return candidate
    for name, attributes in inputs.items():
        if attributes.get("type", "text").lower() in {"text", "email"}:
            return name
    raise WoodpeckerError("The Gitea login form does not expose a username field")


def _pick_password_field(inputs: dict[str, dict[str, str]]) -> str:
    for candidate in ("password", "passwd"):
        if candidate in inputs:
            return candidate
    for name, attributes in inputs.items():
        if attributes.get("type", "").lower() == "password":
            return name
    raise WoodpeckerError("The Gitea login form does not expose a password field")


class _LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._forms: list[dict[str, Any]] = []
        self._current_form: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "form":
            self._current_form = {
                "action": attributes.get("action", ""),
                "method": attributes.get("method", "get").lower(),
                "inputs": {},
            }
            self._forms.append(self._current_form)
            return
        if tag == "input" and self._current_form is not None:
            name = attributes.get("name", "").strip()
            if not name:
                return
            self._current_form["inputs"][name] = attributes

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._current_form = None

    def pick_form(self) -> dict[str, Any] | None:
        for form in self._forms:
            action = str(form.get("action", "")).lower()
            if "/user/login" in action:
                return form
        return self._forms[0] if self._forms else None


def _parse_login_form(html_text: str, base_url: str) -> tuple[str, dict[str, dict[str, str]], dict[str, str]]:
    parser = _LoginFormParser()
    parser.feed(html_text)
    form = parser.pick_form()
    if form is None:
        raise WoodpeckerError("The Gitea login page did not expose a usable login form")
    inputs = form["inputs"]
    action = urllib.parse.urljoin(base_url, str(form.get("action") or "/user/login"))
    payload = _hidden_inputs(inputs)
    return action, inputs, payload


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GiteaClient:
    def __init__(self, base_url: str, api_token: str, *, verify_ssl: bool = True, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token.strip()
        self.timeout = timeout
        if not self.api_token:
            raise GiteaError("Gitea API token is empty")
        if not verify_ssl:
            import ssl

            insecure_context = ssl.create_default_context()
            insecure_context.check_hostname = False
            insecure_context.verify_mode = ssl.CERT_NONE
            self._opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=insecure_context))
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
            "Authorization": f"token {self.api_token}",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        expected = expected_statuses or {200}
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")
        if status not in expected:
            raise GiteaError(f"{method} {path} returned HTTP {status}: {raw}")
        if not raw:
            return status, None
        if accept_json:
            return status, json.loads(raw)
        return status, raw

    def list_oauth_applications(self) -> list[dict[str, Any]]:
        _status, payload = self._request("/api/v1/user/applications/oauth2")
        return payload

    def create_oauth_application(self, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(
            "/api/v1/user/applications/oauth2",
            method="POST",
            payload=payload,
            expected_statuses={201},
        )
        return response

    def update_oauth_application(self, application_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request(
            f"/api/v1/user/applications/oauth2/{application_id}",
            method="PATCH",
            payload=payload,
            expected_statuses={200},
        )
        return response

    def delete_oauth_application(self, application_id: int) -> None:
        self._request(
            f"/api/v1/user/applications/oauth2/{application_id}",
            method="DELETE",
            expected_statuses={204},
            accept_json=False,
        )

    def get_repository(self, full_name: str) -> dict[str, Any]:
        owner, name = split_repository_full_name(full_name)
        _status, payload = self._request(f"/api/v1/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}")
        return payload


class WoodpeckerClient:
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
        if not self.api_token:
            raise WoodpeckerError("Woodpecker API token is empty")
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
        if not verify_ssl:
            import ssl

            insecure_context = ssl.create_default_context()
            insecure_context.check_hostname = False
            insecure_context.verify_mode = ssl.CERT_NONE
            self._opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=insecure_context))
        else:
            self._opener = urllib.request.build_opener()

    def _request_once(
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
                if exc.code in {429, 500, 502, 503, 504}:
                    setattr(exc, "_lv3_raw_body", raw)
                    raise
                raise _HttpStatusError(
                    f"{method} {path} returned HTTP {exc.code}: {raw}",
                    status=exc.code,
                    body=raw,
                ) from exc
            except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
                if _is_timeout_error(exc):
                    raise
                raise WoodpeckerError(f"{method} {path} timed out: {exc}") from exc

        try:
            status, raw = with_retry(
                execute,
                policy=self._retry_policy,
                error_context=f"woodpecker {method} {path}",
                sleep_fn=time.sleep,
            )
        except MaxRetriesExceeded as exc:
            last_error = exc.last_error
            if isinstance(last_error, urllib.error.HTTPError):
                raw = getattr(last_error, "_lv3_raw_body", "")
                raise WoodpeckerError(f"{method} {path} returned HTTP {last_error.code}: {raw}") from exc
            if last_error is not None and _is_timeout_error(last_error):
                raise WoodpeckerError(f"{method} {path} timed out: {last_error}") from exc
            raise

        if not raw:
            return status, None
        if accept_json:
            return status, json.loads(raw)
        return status, raw

    def _request_candidates(
        self,
        paths: list[str],
        *,
        method: str = "GET",
        payload: Any | None = None,
        expected_statuses: set[int] | None = None,
        accept_json: bool = True,
    ) -> tuple[int, Any]:
        last_error: BaseException | None = None
        for path in paths:
            try:
                return self._request_once(
                    path,
                    method=method,
                    payload=payload,
                    expected_statuses=expected_statuses,
                    accept_json=accept_json,
                )
            except _HttpStatusError as exc:
                last_error = exc
                if exc.status == 404:
                    continue
                raise WoodpeckerError(str(exc)) from exc
        if last_error is not None:
            raise WoodpeckerError(str(last_error)) from last_error
        raise WoodpeckerError("Woodpecker request did not have any candidate paths to try")

    def verify_api_token(self) -> bool:
        try:
            self.get_user()
        except WoodpeckerError:
            return False
        return True

    def get_user(self) -> dict[str, Any]:
        _status, payload = self._request_candidates(_api_candidates("/user"))
        return payload

    def list_user_repositories(self, *, include_inactive: bool = False, name: str | None = None) -> list[dict[str, Any]]:
        query = {}
        if include_inactive:
            query["all"] = "true"
        if name:
            query["name"] = name
        suffix = "?" + urllib.parse.urlencode(query) if query else ""
        _status, payload = self._request_candidates(_api_candidates("/user/repos" + suffix))
        return payload

    def lookup_repository(self, full_name: str) -> dict[str, Any] | None:
        candidates = []
        clean = full_name.strip().strip("/")
        if not clean:
            raise WoodpeckerError("Repository full name is empty")
        candidates.extend(_api_candidates(f"/repos/lookup/{urllib.parse.quote(clean, safe='')}"))
        candidates.extend(_api_candidates(f"/repos/lookup/{clean}"))
        try:
            _status, payload = self._request_candidates(candidates)
        except WoodpeckerError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        return payload

    def activate_repository(self, forge_remote_id: int | str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"forge_remote_id": str(forge_remote_id)})
        _status, payload = self._request_candidates(
            _api_candidates(f"/repos?{query}"),
            method="POST",
            payload={},
        )
        return payload

    def list_repository_secrets(self, repo_id: int) -> list[dict[str, Any]]:
        _status, payload = self._request_candidates(_api_candidates(f"/repos/{repo_id}/secrets"))
        return payload

    def create_repository_secret(self, repo_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _status, response = self._request_candidates(
            _api_candidates(f"/repos/{repo_id}/secrets"),
            method="POST",
            payload=payload,
            expected_statuses={200, 201},
        )
        return response

    def update_repository_secret(self, repo_id: int, secret_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib.parse.quote(secret_name, safe="")
        _status, response = self._request_candidates(
            _api_candidates(f"/repos/{repo_id}/secrets/{encoded}"),
            method="PATCH",
            payload=payload,
            expected_statuses={200},
        )
        return response

    def ensure_repository_secret(
        self,
        repo_id: int,
        *,
        name: str,
        value: str,
        events: list[str] | None = None,
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        desired = {
            "name": name,
            "value": value,
            "events": list(events or ["push", "pull_request", "manual"]),
            "images": list(images or []),
        }
        for secret in self.list_repository_secrets(repo_id):
            if secret.get("name") != name:
                continue
            current_events = list(secret.get("events") or [])
            current_images = list(secret.get("images") or [])
            if current_events == desired["events"] and current_images == desired["images"]:
                return self.update_repository_secret(repo_id, name, desired)
            return self.update_repository_secret(repo_id, name, desired)
        return self.create_repository_secret(repo_id, desired)

    def list_pipelines(self, repo_id: int, *, branch: str | None = None) -> list[dict[str, Any]]:
        query = {}
        if branch:
            query["branch"] = branch
        suffix = "?" + urllib.parse.urlencode(query) if query else ""
        _status, payload = self._request_candidates(_api_candidates(f"/repos/{repo_id}/pipelines{suffix}"))
        return payload

    def trigger_pipeline(
        self,
        repo_id: int,
        *,
        branch: str,
        variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = {"branch": branch, "variables": variables or {}}
        _status, response = self._request_candidates(
            _api_candidates(f"/repos/{repo_id}/pipelines"),
            method="POST",
            payload=payload,
            expected_statuses={200},
        )
        return response

    def get_pipeline(self, repo_id: int, number: int | str) -> dict[str, Any]:
        _status, payload = self._request_candidates(_api_candidates(f"/repos/{repo_id}/pipelines/{number}"))
        return payload

    def wait_for_pipeline(
        self,
        repo_id: int,
        number: int,
        *,
        timeout_seconds: int = 600,
        poll_seconds: int = 5,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        latest = self.get_pipeline(repo_id, number)
        while time.monotonic() < deadline:
            state = _pipeline_state(latest)
            if state in TERMINAL_PIPELINE_STATES:
                return latest
            time.sleep(poll_seconds)
            latest = self.get_pipeline(repo_id, number)
        raise WoodpeckerError(
            f"Timed out waiting for Woodpecker pipeline {number} on repo {repo_id}; last state={_pipeline_state(latest)!r}"
        )


class WoodpeckerSessionClient:
    def __init__(self, base_url: str, *, verify_ssl: bool = True, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
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

    def _request(
        self,
        url_or_path: str,
        *,
        method: str = "GET",
        payload: Any | None = None,
        form: dict[str, Any] | None = None,
        expected_statuses: set[int] | None = None,
        accept_json: bool = True,
        follow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any, dict[str, str], str]:
        if payload is not None and form is not None:
            raise WoodpeckerError("Use either payload or form data, not both")
        data = None
        request_headers = {
            "Accept": "application/json" if accept_json else "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        request_headers.update(headers or {})
        if payload is not None:
            data = _json_dumps(payload)
            request_headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        url = urllib.parse.urljoin(f"{self.base_url}/", url_or_path.lstrip("/"))
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            url = url_or_path
        request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
        opener = self._opener if follow_redirects else self._no_redirect_opener
        expected = expected_statuses or {200}
        response_headers: dict[str, str] = {}
        final_url = url
        try:
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                status = response.status
                response_headers = dict(response.headers.items())
                final_url = response.geturl()
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")
            response_headers = dict(exc.headers.items())
            final_url = exc.geturl()
        if status not in expected:
            raise WoodpeckerError(f"{method} {url} returned HTTP {status}: {raw}")
        if not raw:
            return status, None, response_headers, final_url
        if accept_json:
            return status, json.loads(raw), response_headers, final_url
        return status, raw, response_headers, final_url

    def login_via_gitea(self, username: str, password: str) -> dict[str, Any]:
        _status, html, _headers, final_url = self._request(
            "/authorize",
            expected_statuses={200},
            accept_json=False,
            follow_redirects=True,
        )
        action_url, inputs, payload = _parse_login_form(str(html), final_url)
        payload[_pick_username_field(inputs)] = username
        payload[_pick_password_field(inputs)] = password
        self._request(
            action_url,
            method="POST",
            form=payload,
            expected_statuses={200},
            accept_json=False,
            follow_redirects=True,
            headers={"Referer": final_url},
        )
        return self.get_user()

    def _request_candidates(
        self,
        paths: list[str],
        *,
        method: str = "GET",
        payload: Any | None = None,
        form: dict[str, Any] | None = None,
        expected_statuses: set[int] | None = None,
        accept_json: bool = True,
        follow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any, dict[str, str], str]:
        last_error: BaseException | None = None
        for path in paths:
            try:
                return self._request(
                    path,
                    method=method,
                    payload=payload,
                    form=form,
                    expected_statuses=expected_statuses,
                    accept_json=accept_json,
                    follow_redirects=follow_redirects,
                    headers=headers,
                )
            except WoodpeckerError as exc:
                last_error = exc
                if "HTTP 404" in str(exc):
                    continue
                raise
        if last_error is not None:
            raise WoodpeckerError(str(last_error)) from last_error
        raise WoodpeckerError("Woodpecker session request did not have any candidate paths to try")

    def get_user(self) -> dict[str, Any]:
        _status, payload, _headers, _final_url = self._request_candidates(_api_candidates("/user"))
        return payload

    def create_user_token(self) -> str:
        _status, payload, _headers, _final_url = self._request_candidates(
            _api_candidates("/user/token"),
            method="POST",
            expected_statuses={200},
            accept_json=False,
        )
        token = str(payload or "").strip().strip('"')
        if not token:
            raise WoodpeckerError("Woodpecker did not return a usable user token")
        return token


def split_repository_full_name(full_name: str) -> tuple[str, str]:
    clean = full_name.strip().strip("/")
    if "/" not in clean:
        raise ValueError(f"Repository name must be in owner/name form, got {full_name!r}")
    owner, name = clean.split("/", 1)
    if not owner or not name:
        raise ValueError(f"Repository name must be in owner/name form, got {full_name!r}")
    return owner, name


def ensure_gitea_oauth_application(
    client: GiteaClient,
    *,
    name: str,
    redirect_uri: str,
    existing_client_id: str | None = None,
    existing_client_secret: str | None = None,
) -> dict[str, Any]:
    desired = {
        "name": name,
        "redirect_uris": [redirect_uri],
        "confidential_client": True,
        "skip_secondary_authorization": True,
    }
    existing = next((item for item in client.list_oauth_applications() if item.get("name") == name), None)
    if existing is None:
        created = client.create_oauth_application(desired)
        client_id = str(created.get("client_id") or created.get("clientId") or "").strip()
        client_secret = str(created.get("client_secret") or created.get("clientSecret") or "").strip()
        if not client_id or not client_secret:
            raise GiteaError("Gitea did not return a usable OAuth client id and secret")
        return {
            "id": int(created["id"]),
            "client_id": client_id,
            "client_secret": client_secret,
            "recreated": False,
        }

    existing_id = int(existing["id"])
    if _payload_differs(existing, desired, {"name", "redirect_uris", "confidential_client", "skip_secondary_authorization"}):
        client.update_oauth_application(existing_id, desired)

    client_id = str(existing_client_id or existing.get("client_id") or existing.get("clientId") or "").strip()
    client_secret = str(existing_client_secret or "").strip()
    recreated = False
    if not client_id or not client_secret:
        client.delete_oauth_application(existing_id)
        created = client.create_oauth_application(desired)
        client_id = str(created.get("client_id") or created.get("clientId") or "").strip()
        client_secret = str(created.get("client_secret") or created.get("clientSecret") or "").strip()
        recreated = True
    if not client_id or not client_secret:
        raise GiteaError("Gitea did not return a usable OAuth client id and secret")
    return {
        "id": existing_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "recreated": recreated,
    }


@dataclass
class BootstrapSummary:
    whoami: dict[str, Any]
    repo: dict[str, Any]
    api_token: str
    repo_secret: dict[str, Any] | None = None


def bootstrap_woodpecker(
    *,
    controller_base_url: str,
    login_base_url: str,
    gitea_api_url: str,
    gitea_api_token: str,
    gitea_username: str,
    gitea_password: str,
    repo_full_name: str,
    secret_name: str | None = None,
    secret_value: str | None = None,
    secret_events: list[str] | None = None,
    verify_ssl: bool = True,
    login_verify_ssl: bool = True,
    existing_api_token: str | None = None,
) -> BootstrapSummary:
    api_token = (existing_api_token or "").strip()
    client = None
    if api_token:
        try:
            client = WoodpeckerClient(controller_base_url, api_token, verify_ssl=verify_ssl)
            if not client.verify_api_token():
                client = None
                api_token = ""
        except WoodpeckerError:
            client = None
            api_token = ""

    if client is None:
        session = WoodpeckerSessionClient(login_base_url, verify_ssl=login_verify_ssl)
        session.login_via_gitea(gitea_username, gitea_password)
        api_token = session.create_user_token()
        client = WoodpeckerClient(controller_base_url, api_token, verify_ssl=verify_ssl)
        if not client.verify_api_token():
            client = WoodpeckerClient(login_base_url, api_token, verify_ssl=login_verify_ssl)
            if not client.verify_api_token():
                raise WoodpeckerError("The newly created Woodpecker API token is not valid on the configured endpoints")

    gitea_client = GiteaClient(gitea_api_url, gitea_api_token, verify_ssl=login_verify_ssl)
    gitea_repo = gitea_client.get_repository(repo_full_name)
    repo = client.lookup_repository(repo_full_name)
    if repo is None:
        repo = client.activate_repository(gitea_repo["id"])
        repo = client.lookup_repository(repo_full_name) or repo
    repo_secret = None
    if secret_name and secret_value is not None:
        repo_secret = client.ensure_repository_secret(
            int(repo["id"]),
            name=secret_name,
            value=secret_value,
            events=list(secret_events or ["push", "pull_request", "manual"]),
        )
    return BootstrapSummary(
        whoami=client.get_user(),
        repo=repo,
        api_token=api_token,
        repo_secret=repo_secret,
    )
