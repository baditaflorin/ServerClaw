from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable
from typing import Any

import pytest

from platform.events.publisher import connect_nats as publisher_connect_nats
from platform.retry import RetryClass, classify_error
from scripts.drift_lib import connect_nats as drift_connect_nats


class FakeNatsError(Exception):
    pass


FakeNatsError.__module__ = "nats.errors"


class FakeNatsClient:
    instances: list["FakeNatsClient"] = []

    def __init__(self) -> None:
        self.connect_calls = 0
        self.connected = False
        self.kwargs: dict[str, Any] | None = None
        type(self).instances.append(self)

    async def connect(self, **kwargs: Any) -> None:
        self.connect_calls += 1
        self.kwargs = kwargs
        if len(type(self).instances) == 1 and self.connect_calls == 1:
            raise FakeNatsError("nats: empty response from server when expecting INFO message")
        self.connected = True


@pytest.fixture()
def fake_nats_modules(monkeypatch: pytest.MonkeyPatch) -> type[FakeNatsClient]:
    FakeNatsClient.instances = []

    nats_module = types.ModuleType("nats")
    nats_aio_module = types.ModuleType("nats.aio")
    nats_client_module = types.ModuleType("nats.aio.client")
    nats_client_module.Client = FakeNatsClient
    nats_aio_module.client = nats_client_module
    nats_module.aio = nats_aio_module

    monkeypatch.setitem(sys.modules, "nats", nats_module)
    monkeypatch.setitem(sys.modules, "nats.aio", nats_aio_module)
    monkeypatch.setitem(sys.modules, "nats.aio.client", nats_client_module)

    return FakeNatsClient


def test_classify_error_retries_transient_nats_handshake_failure() -> None:
    classified = classify_error(FakeNatsError("nats: empty response from server when expecting INFO message"))

    assert classified.code == "net:connection_timeout"
    assert classified.retry_class == RetryClass.TRANSIENT


@pytest.mark.parametrize(
    ("connect_fn",),
    [
        (publisher_connect_nats,),
        (drift_connect_nats,),
    ],
)
def test_connect_nats_retries_with_fresh_client_after_handshake_failure(
    fake_nats_modules: type[FakeNatsClient],
    connect_fn: Callable[[str, dict[str, str] | None], Any],
) -> None:
    connected_client = asyncio.run(
        connect_fn(
            "nats://127.0.0.1:4222",
            credentials={"user": "jetstream-admin", "password": "secret"},
        )
    )

    assert len(fake_nats_modules.instances) == 2
    assert connected_client is fake_nats_modules.instances[-1]
    assert fake_nats_modules.instances[0].connect_calls == 1
    assert fake_nats_modules.instances[-1].connected is True
    assert fake_nats_modules.instances[-1].kwargs is not None
    assert fake_nats_modules.instances[-1].kwargs["user"] == "jetstream-admin"
