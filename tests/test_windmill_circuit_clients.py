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
