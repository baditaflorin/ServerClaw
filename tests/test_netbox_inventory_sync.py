from __future__ import annotations

import json
import socket
import sys
import urllib.error
from pathlib import Path

from platform.retry import RetryPolicy


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import netbox_inventory_sync  # noqa: E402


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_netbox_client_retries_transient_url_errors(monkeypatch) -> None:
    attempts = {"count": 0}
    observed_timeouts: list[float | None] = []

    def flaky_urlopen(_request, timeout: float | None = None):
        attempts["count"] += 1
        observed_timeouts.append(timeout)
        if attempts["count"] < 3:
            raise urllib.error.URLError(socket.timeout("timed out"))
        return FakeResponse({"status": "ok"})

    monkeypatch.setattr(netbox_inventory_sync.urllib.request, "urlopen", flaky_urlopen)

    client = netbox_inventory_sync.NetBoxClient("https://netbox.example.test", "token")
    client.retry_policy = RetryPolicy(
        max_attempts=4,
        base_delay_s=0.0,
        max_delay_s=0.0,
        multiplier=2.0,
        jitter=False,
        transient_max=2,
    )

    assert client.request("GET", "/api/status/") == {"status": "ok"}
    assert attempts["count"] == 3
    assert all(timeout is not None for timeout in observed_timeouts)
