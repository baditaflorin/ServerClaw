from __future__ import annotations

import asyncio
import socket
import urllib.error
from pathlib import Path

import httpx
import pytest

from platform.retry import MaxRetriesExceeded, RetryPolicy, async_with_retry, load_retry_surface_policies, with_retry


def test_with_retry_escalates_transient_failures_to_backoff() -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 4:
            raise urllib.error.URLError(socket.timeout("timed out"))
        return "ok"

    result = with_retry(
        flaky,
        policy=RetryPolicy(max_attempts=5, base_delay_s=1.0, max_delay_s=5.0, multiplier=2.0, jitter=False, transient_max=2),
        error_context="transient escalation test",
        sleep_fn=sleeps.append,
    )

    assert result == "ok"
    assert calls["count"] == 4
    assert sleeps == [1.0]


def test_with_retry_raises_max_retries_with_last_error() -> None:
    def always_timeout() -> str:
        raise urllib.error.URLError(socket.timeout("timed out"))

    with pytest.raises(MaxRetriesExceeded) as exc_info:
        with_retry(
            always_timeout,
            policy=RetryPolicy(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0, multiplier=2.0, jitter=False, transient_max=0),
            error_context="always timeout",
            sleep_fn=lambda _seconds: None,
        )

    assert isinstance(exc_info.value.last_error, urllib.error.URLError)


def test_with_retry_retries_connection_reset_errors() -> None:
    calls = {"count": 0}
    sleeps: list[float] = []

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionResetError(54, "Connection reset by peer")
        return "ok"

    result = with_retry(
        flaky,
        policy=RetryPolicy(max_attempts=3, base_delay_s=0.25, max_delay_s=1.0, multiplier=2.0, jitter=False, transient_max=0),
        error_context="connection reset",
        sleep_fn=sleeps.append,
    )

    assert result == "ok"
    assert calls["count"] == 2
    assert sleeps == [0.25]


def test_async_with_retry_honours_retry_after() -> None:
    sleeps: list[float] = []
    calls = {"count": 0}

    async def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(429, headers={"Retry-After": "3"})
            raise httpx.HTTPStatusError("busy", request=request, response=response)
        return "ok"

    result = asyncio.run(
        async_with_retry(
            flaky,
            policy=RetryPolicy(max_attempts=4, base_delay_s=0.1, max_delay_s=1.0, multiplier=2.0, jitter=False, transient_max=0),
            error_context="retry-after",
            sleep_fn=lambda seconds: _async_record_sleep(seconds, sleeps),
        )
    )

    assert result == "ok"
    assert sleeps == [3.0, 3.0]


async def _async_record_sleep(seconds: float, sleeps: list[float]) -> None:
    sleeps.append(seconds)


def test_load_retry_surface_policies_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "retry-policies.yaml"
    config_path.write_text(
        (
            "schema_version: 1.0.0\n"
            "policies:\n"
            "  - surface: internal_api\n"
            "    max_attempts: 9\n"
            "    base_delay_s: 0.25\n"
            "    max_delay_s: 7.0\n"
            "    multiplier: 3.0\n"
            "    jitter: false\n"
            "    transient_max: 4\n"
        ),
        encoding="utf-8",
    )

    policies = load_retry_surface_policies(config_path)

    assert policies.get("internal_api") == RetryPolicy(
        max_attempts=9,
        base_delay_s=0.25,
        max_delay_s=7.0,
        multiplier=3.0,
        jitter=False,
        transient_max=4,
    )
