from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

import platform.scheduler.windmill_client as windmill_client_module
import runbook_executor as executor_module
from platform.circuit import CircuitBreaker, CircuitOpenError, CircuitPolicy, MemoryCircuitStateBackend, should_count_urllib_exception
from platform.scheduler import HttpWindmillClient


def build_windmill_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        "windmill",
        CircuitPolicy(
            name="windmill",
            service="Windmill workflow engine",
            failure_threshold=1,
            recovery_window_s=300,
            success_threshold=1,
            timeout_s=15,
        ),
        backend=MemoryCircuitStateBackend(),
        exception_classifier=should_count_urllib_exception,
    )


def test_runbook_windmill_runner_stops_retrying_after_circuit_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):
        calls.append(request.full_url)
        raise urllib.error.URLError("windmill unavailable")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    runner = executor_module.WindmillWorkflowRunner(
        base_url="https://windmill.example.test",
        token="test-token",
        circuit_breaker=build_windmill_breaker(),
    )

    with pytest.raises(urllib.error.URLError):
        runner.run_workflow("deploy-and-promote", {"service": "netbox"})
    with pytest.raises(CircuitOpenError):
        runner.run_workflow("deploy-and-promote", {"service": "netbox"})

    assert len(calls) == 1


def test_scheduler_windmill_client_stops_retrying_after_circuit_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):
        calls.append(request.full_url)
        raise urllib.error.URLError("windmill unavailable")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = HttpWindmillClient(
        base_url="https://windmill.example.test",
        token="test-token",
        circuit_breaker=build_windmill_breaker(),
    )

    with pytest.raises(urllib.error.URLError):
        client.submit_workflow("deploy-and-promote", {"service": "netbox"})
    with pytest.raises(CircuitOpenError):
        client.submit_workflow("deploy-and-promote", {"service": "netbox"})

    assert len(calls) == 1


def test_scheduler_windmill_client_retries_401_with_bootstrap_login(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, body: str) -> None:
            self._body = body.encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def close(self) -> None:
            return None

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    calls: list[tuple[str, str | None]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):
        auth_header = request.headers.get("Authorization")
        calls.append((request.full_url, auth_header))
        if request.full_url.endswith("/api/auth/login"):
            assert json.loads(request.data.decode("utf-8")) == {
                "email": "superadmin_secret@windmill.dev",
                "password": "managed-secret",
            }
            return FakeResponse("session-token")
        if auth_header == "Bearer stale-session-token":
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=FakeResponse("Unauthorized"),
            )
        assert auth_header == "Bearer session-token"
        if request.full_url.endswith("/scripts/get/p/f%2Flv3%2Fdeploy-and-promote"):
            return FakeResponse('{"hash":"hash-123"}')
        if request.full_url.endswith("/jobs/run/h/hash-123"):
            return FakeResponse('"job-123"')
        raise AssertionError(request.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client = HttpWindmillClient(
        base_url="https://windmill.example.test",
        token="stale-session-token",
        bootstrap_secret="managed-secret",
    )
    client._internal_api_retry_policy = None

    assert client.submit_workflow("deploy-and-promote", {"service": "netbox"}) == {
        "job_id": "job-123",
        "running": True,
    }
    assert calls == [
        ("https://windmill.example.test/api/w/lv3/scripts/get/p/f%2Flv3%2Fdeploy-and-promote", "Bearer stale-session-token"),
        ("https://windmill.example.test/api/auth/login", None),
        ("https://windmill.example.test/api/w/lv3/scripts/get/p/f%2Flv3%2Fdeploy-and-promote", "Bearer session-token"),
        ("https://windmill.example.test/api/w/lv3/jobs/run/h/hash-123", "Bearer session-token"),
    ]


def test_scheduler_windmill_client_falls_back_to_path_submit_when_hash_submit_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __init__(self, body: str) -> None:
            self._body = body.encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def close(self) -> None:
            return None

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    calls: list[tuple[str, str | None]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):
        auth_header = request.headers.get("Authorization")
        calls.append((request.full_url, auth_header))
        if request.full_url.endswith("/api/w/lv3/scripts/get/p/f%2Flv3%2Fdeploy-and-promote"):
            return FakeResponse('{"path":"f/lv3/deploy-and-promote","hash":"abc123"}')
        if request.full_url.endswith("/api/w/lv3/jobs/run/h/abc123"):
            raise urllib.error.HTTPError(
                request.full_url,
                404,
                "Not Found",
                hdrs=None,
                fp=FakeResponse("hash route unavailable"),
            )
        if request.full_url.endswith("/api/w/lv3/jobs/run/p/f%2Flv3%2Fdeploy-and-promote"):
            return FakeResponse('"job-123"')
        raise AssertionError(request.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client = HttpWindmillClient(
        base_url="https://windmill.example.test",
        token="managed-secret",
    )
    client._internal_api_retry_policy = None

    assert client.submit_workflow("deploy-and-promote", {"service": "netbox"}) == {
        "job_id": "job-123",
        "running": True,
    }
    assert calls == [
        ("https://windmill.example.test/api/w/lv3/scripts/get/p/f%2Flv3%2Fdeploy-and-promote", "Bearer managed-secret"),
        ("https://windmill.example.test/api/w/lv3/jobs/run/h/abc123", "Bearer managed-secret"),
        ("https://windmill.example.test/api/w/lv3/jobs/run/p/f%2Flv3%2Fdeploy-and-promote", "Bearer managed-secret"),
    ]


def test_scheduler_windmill_client_waits_for_job_result(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, body: str) -> None:
            self._body = body.encode("utf-8")

        def read(self) -> bytes:
            return self._body

        def close(self) -> None:
            return None

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    poll_count = {"count": 0}
    sleep_calls: list[float] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):
        if request.full_url.endswith("/api/w/lv3/scripts/get/p/f%2Flv3%2Fdeploy-and-promote"):
            return FakeResponse('{"path":"f/lv3/deploy-and-promote","hash":"abc123"}')
        if request.full_url.endswith("/api/w/lv3/jobs/run/h/abc123"):
            return FakeResponse('"job-123"')
        if request.full_url.endswith("/api/w/lv3/jobs_u/completed/get_result_maybe/job-123?get_started=true"):
            poll_count["count"] += 1
            if poll_count["count"] == 1:
                return FakeResponse('{"completed": false, "started": false, "result": null}')
            return FakeResponse('{"completed": true, "success": true, "result": {"status": "ok"}}')
        raise AssertionError(request.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(windmill_client_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    client = HttpWindmillClient(
        base_url="https://windmill.example.test",
        token="managed-secret",
    )
    client._internal_api_retry_policy = None

    assert client.run_workflow_wait_result(
        "deploy-and-promote",
        {"service": "netbox"},
        timeout_seconds=10,
        poll_interval_seconds=0.25,
    ) == {"status": "ok"}
    assert poll_count["count"] == 2
    assert sleep_calls == [0.25]
