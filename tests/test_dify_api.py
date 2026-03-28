from __future__ import annotations

import base64
import json
from collections import deque

import requests

from scripts.dify_api import DifyClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self) -> dict:
        return self._payload


def test_setup_runs_init_validation_before_bootstrap(monkeypatch) -> None:
    client = DifyClient("https://agents.lv3.org")
    calls: list[tuple[str, str, dict]] = []
    responses = deque(
        [
            FakeResponse(200, {"step": "not_started"}),
            FakeResponse(200, {"status": "not_started"}),
            FakeResponse(201, {"result": "success"}),
            FakeResponse(201, {"result": "success"}),
        ]
    )

    def fake_request(self, method, url, timeout=None, headers=None, **kwargs):  # noqa: ANN001
        calls.append((method, url, kwargs))
        return responses.popleft()

    monkeypatch.setattr(requests.Session, "request", fake_request)

    result = client.setup(
        email="ops@lv3.org",
        name="Ops",
        password="abcd1234abcd1234",
        init_password="init1234abcd1234",
    )

    assert result == {"result": "success"}
    assert [call[1] for call in calls] == [
        "https://agents.lv3.org/console/api/setup",
        "https://agents.lv3.org/console/api/init",
        "https://agents.lv3.org/console/api/init",
        "https://agents.lv3.org/console/api/setup",
    ]


def test_login_request_uses_csrf_token_cookie(monkeypatch) -> None:
    client = DifyClient("https://agents.lv3.org")
    client.session.cookies.set("csrf_token", "csrf-123")
    seen_headers: list[dict[str, str]] = []
    seen_payloads: list[dict] = []

    def fake_request(self, method, url, timeout=None, headers=None, **kwargs):  # noqa: ANN001
        seen_headers.append(headers or {})
        seen_payloads.append(kwargs.get("json") or {})
        return FakeResponse(200, {"result": "success"})

    monkeypatch.setattr(requests.Session, "request", fake_request)

    payload = client.login(email="ops@lv3.org", password="abcd1234abcd1234")

    assert payload["result"] == "success"
    assert seen_headers[0]["X-CSRF-Token"] == "csrf-123"
    assert seen_payloads[0]["password"] == base64.b64encode(b"abcd1234abcd1234").decode("ascii")


def test_http_tunnel_headers_forward_auth_and_cookie_state() -> None:
    client = DifyClient("http://127.0.0.1:18094")
    client.session.cookies.set("__Host-access_token", "access-123")
    client.session.cookies.set("__Host-refresh_token", "refresh-123")
    client.session.cookies.set("__Host-csrf_token", "csrf-123")

    headers = client._headers()

    assert headers["Authorization"] == "Bearer access-123"
    assert headers["X-CSRF-Token"] == "csrf-123"
    assert "__Host-access_token=access-123" in headers["Cookie"]
    assert "__Host-refresh_token=refresh-123" in headers["Cookie"]
    assert "__Host-csrf_token=csrf-123" in headers["Cookie"]
