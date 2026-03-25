from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from platform.locking import LockType, ResourceLockRegistry


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def test_duplicate_acquire_refreshes_existing_lock(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 3, 25, 12, 0, tzinfo=UTC))
    registry = ResourceLockRegistry(state_path=tmp_path / "locks.json", now_fn=clock.now)

    first = registry.acquire(
        "vm:120/service:netbox",
        LockType.EXCLUSIVE,
        "agent:ctx-a",
        ttl_seconds=60,
        context_id="ctx-a",
        metadata={"phase": "plan"},
    )

    clock.value += timedelta(seconds=10)
    refreshed = registry.acquire(
        "vm:120/service:netbox",
        LockType.EXCLUSIVE,
        "agent:ctx-a",
        ttl_seconds=120,
        context_id="ctx-a-next",
        metadata={"phase": "execute"},
    )

    assert refreshed.lock_id == first.lock_id
    assert refreshed.acquired_at == first.acquired_at
    assert refreshed.context_id == "ctx-a-next"
    assert refreshed.expires_at == "2026-03-25T12:02:10Z"
    assert refreshed.metadata == {"phase": "execute"}


def test_release_all_and_heartbeat_round_trip(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 3, 25, 12, 0, tzinfo=UTC))
    registry = ResourceLockRegistry(state_path=tmp_path / "locks.json", now_fn=clock.now)

    first = registry.acquire("vm:120/service:netbox", LockType.EXCLUSIVE, "agent:ctx-a", ttl_seconds=30)
    registry.acquire("vm:120/service:keycloak", LockType.INTENT, "agent:ctx-a", ttl_seconds=30)

    clock.value += timedelta(seconds=5)
    refreshed = registry.heartbeat(first.lock_id, ttl_seconds=90)

    assert refreshed is not None
    assert refreshed.expires_at == "2026-03-25T12:01:35Z"
    assert registry.release_all("agent:ctx-a") == 2
    assert registry.read_all() == []
