from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import browser_runner_client


class FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


def test_build_headers_supports_api_key_and_bearer_token() -> None:
    headers = browser_runner_client.build_headers(
        api_key="api-key",
        api_key_header="X-Test-Key",
        bearer_token="jwt-token",
    )

    assert headers == {
        "Content-Type": "application/json",
        "X-Test-Key": "api-key",
        "Authorization": "Bearer jwt-token",
    }


def test_read_secret_rejects_blank_file(tmp_path: Path) -> None:
    secret_path = tmp_path / "secret.txt"
    secret_path.write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        browser_runner_client.read_secret(secret_path)


def test_run_session_posts_json_payload() -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=0):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"status": "ok", "run_id": "abc123"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        payload = browser_runner_client.run_session(
            "http://browser-runner.test",
            {"url": "https://example.com"},
            timeout_seconds=33,
            headers={"Authorization": "Bearer test"},
        )

    assert payload == {"status": "ok", "run_id": "abc123"}
    assert captured["url"] == "http://browser-runner.test/sessions"
    assert captured["method"] == "POST"
    assert captured["body"] == {"url": "https://example.com"}
    assert captured["timeout"] == 33
    assert ("Authorization", "Bearer test") in captured["headers"].items()


def test_get_health_requests_healthz_endpoint() -> None:
    with patch("urllib.request.urlopen", return_value=FakeResponse({"status": "ok"})) as mocked:
        payload = browser_runner_client.get_health("http://browser-runner.test")

    assert payload == {"status": "ok"}
    request = mocked.call_args.args[0]
    assert request.full_url == "http://browser-runner.test/healthz"
    assert request.get_method() == "GET"
