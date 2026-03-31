from __future__ import annotations

import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

import one_api_bootstrap


def test_http_json_retries_transient_transport_failures(monkeypatch) -> None:
    attempts = {"count": 0}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    def fake_urlopen(request, timeout=None):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return FakeResponse()

    monkeypatch.setattr(one_api_bootstrap.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(one_api_bootstrap.time, "sleep", lambda *_args, **_kwargs: None)

    status, payload = one_api_bootstrap.http_json("GET", "http://example.invalid/api/status")

    assert attempts["count"] == 3
    assert status == 200
    assert payload == {"status": "ok"}


def test_http_json_wraps_permanent_http_failures_without_retry(monkeypatch) -> None:
    attempts = {"count": 0}

    class FakeHttpError(urllib.error.HTTPError):
        def __init__(self) -> None:
            super().__init__(
                url="http://example.invalid/api/status",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=None,
            )

        def read(self) -> bytes:
            return b'{"message":"unauthorized"}'

    def fake_urlopen(request, timeout=None):
        attempts["count"] += 1
        raise FakeHttpError()

    monkeypatch.setattr(one_api_bootstrap.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(one_api_bootstrap.time, "sleep", lambda *_args, **_kwargs: None)

    with pytest.raises(one_api_bootstrap.BootstrapError, match="failed with status 401"):
        one_api_bootstrap.http_json("GET", "http://example.invalid/api/status")

    assert attempts["count"] == 1


def test_script_entrypoint_imports_repo_retry_module() -> None:
    result = subprocess.run(
        [sys.executable, str(Path(one_api_bootstrap.__file__).resolve()), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
