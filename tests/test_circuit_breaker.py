from __future__ import annotations

import importlib
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from repo_package_loader import load_repo_package


CIRCUIT_MODULE = load_repo_package(
    "lv3_platform_circuit_test",
    Path(__file__).resolve().parents[1] / "platform" / "circuit",
)
BREAKER_MODULE = importlib.import_module("lv3_platform_circuit_test.breaker")

CircuitBreaker = CIRCUIT_MODULE.CircuitBreaker
CircuitOpenError = CIRCUIT_MODULE.CircuitOpenError
CircuitPolicy = CIRCUIT_MODULE.CircuitPolicy
CircuitState = CIRCUIT_MODULE.CircuitState
JsonFileCircuitStateBackend = CIRCUIT_MODULE.JsonFileCircuitStateBackend
MemoryCircuitStateBackend = CIRCUIT_MODULE.MemoryCircuitStateBackend
load_circuit_policies = BREAKER_MODULE.load_circuit_policies
should_count_urllib_exception = CIRCUIT_MODULE.should_count_urllib_exception


def test_circuit_opens_after_threshold_and_rejects_until_recovery_window_passes() -> None:
    backend = MemoryCircuitStateBackend()
    policy = CircuitPolicy(
        name="windmill",
        service="Windmill workflow engine",
        failure_threshold=2,
        recovery_window_s=60,
        success_threshold=1,
        timeout_s=15,
    )
    breaker = CircuitBreaker(
        "windmill",
        policy,
        backend=backend,
        exception_classifier=should_count_urllib_exception,
    )

    def fail() -> None:
        raise urllib.error.URLError("windmill unavailable")

    with pytest.raises(urllib.error.URLError):
        breaker.call(fail)
    assert breaker.state().state == "closed"
    assert breaker.state().failure_count == 1

    with pytest.raises(urllib.error.URLError):
        breaker.call(fail)

    opened_state = breaker.state()
    assert opened_state.state == "open"
    assert opened_state.failure_count == 2
    assert opened_state.opened_at is not None

    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: {"ok": True})


def test_half_open_successes_close_the_circuit() -> None:
    backend = MemoryCircuitStateBackend()
    policy = CircuitPolicy(
        name="keycloak",
        service="Keycloak OIDC / JWKS",
        failure_threshold=1,
        recovery_window_s=30,
        success_threshold=2,
        timeout_s=10,
    )
    breaker = CircuitBreaker("keycloak", policy, backend=backend)
    state = CircuitState.for_policy(policy)
    state.state = "open"
    state.failure_count = 1
    state.opened_at = datetime.now(UTC) - timedelta(seconds=120)
    backend.save_sync(state)

    assert breaker.call(lambda: {"probe": 1}) == {"probe": 1}
    half_open_state = breaker.state()
    assert half_open_state.state == "half_open"
    assert half_open_state.consecutive_successes == 1

    assert breaker.call(lambda: {"probe": 2}) == {"probe": 2}
    closed_state = breaker.state()
    assert closed_state.state == "closed"
    assert closed_state.failure_count == 0
    assert closed_state.opened_at is None


def test_file_backend_shares_open_state_between_breakers(tmp_path: Path) -> None:
    backend = JsonFileCircuitStateBackend(tmp_path / "circuits.json")
    policy = CircuitPolicy(
        name="windmill",
        service="Windmill workflow engine",
        failure_threshold=1,
        recovery_window_s=300,
        success_threshold=1,
        timeout_s=15,
    )
    breaker_one = CircuitBreaker(
        "windmill",
        policy,
        backend=backend,
        exception_classifier=should_count_urllib_exception,
    )
    breaker_two = CircuitBreaker(
        "windmill",
        policy,
        backend=backend,
        exception_classifier=should_count_urllib_exception,
    )

    with pytest.raises(urllib.error.URLError):
        breaker_one.call(lambda: (_ for _ in ()).throw(urllib.error.URLError("windmill down")))

    with pytest.raises(CircuitOpenError):
        breaker_two.call(lambda: {"unexpected": "success"})


def test_load_circuit_policies_reads_repo_managed_contract(tmp_path: Path) -> None:
    policy_path = tmp_path / "config" / "circuit-policies.yaml"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "circuits": [
                    {
                        "name": "windmill",
                        "service": "Windmill workflow engine",
                        "failure_threshold": 5,
                        "recovery_window_s": 60,
                        "success_threshold": 2,
                        "timeout_s": 15,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    policies = load_circuit_policies(policy_path)

    assert set(policies) == {"windmill"}
    assert policies["windmill"].failure_threshold == 5
