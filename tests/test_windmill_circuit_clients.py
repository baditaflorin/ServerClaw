from __future__ import annotations

import urllib.error
import urllib.request

import pytest

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
            return FakeResponse("session-token")
        if auth_header == "Bearer managed-secret":
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
        token="managed-secret",
    )

    assert client.submit_workflow("deploy-and-promote", {"service": "netbox"}) == {
        "job_id": "job-123",
        "running": True,
    }
    assert calls == [
        ("https://windmill.example.test/api/w/lv3/scripts/get/p/f%2Flv3%2Fdeploy-and-promote", "Bearer managed-secret"),
        ("https://windmill.example.test/api/auth/login", None),
        ("https://windmill.example.test/api/w/lv3/scripts/get/p/f%2Flv3%2Fdeploy-and-promote", "Bearer session-token"),
        ("https://windmill.example.test/api/w/lv3/jobs/run/h/hash-123", "Bearer session-token"),
    ]
