from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from platform.coordination import AgentCoordinationMap, AgentSessionEntry
from platform.intent_queue import IntentQueue
from platform.ledger import LedgerWriter
from platform.locking import DeadlockDetector, LockType, ResourceLockRegistry, ResourceLocked


REPO_ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_lock_registry_enforces_hierarchy_and_purges_expired(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 3, 25, 10, 0, tzinfo=UTC))
    registry = ResourceLockRegistry(state_path=tmp_path / "locks.json", now_fn=clock.now)

    registry.acquire("vm:120", LockType.EXCLUSIVE, "agent:ctx-a", ttl_seconds=30)

    with pytest.raises(ResourceLocked):
        registry.acquire("vm:120/service:netbox", LockType.SHARED, "agent:ctx-b")

    clock.value += timedelta(seconds=31)

    assert registry.read_all() == []


def test_deadlock_detector_resolves_lowest_priority_participant(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 3, 25, 10, 0, tzinfo=UTC))
    locks = ResourceLockRegistry(state_path=tmp_path / "locks.json", now_fn=clock.now)
    queue = IntentQueue(state_path=tmp_path / "queue.json", now_fn=clock.now)
    coordination = AgentCoordinationMap(state_path=tmp_path / "coordination.json", now_fn=clock.now)
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = LedgerWriter(file_path=ledger_path, nats_publisher=None)

    locks.acquire("vm:120/service:netbox", LockType.EXCLUSIVE, "agent:ctx-a", ttl_seconds=300)
    locks.acquire("vm:120/service:keycloak", LockType.EXCLUSIVE, "agent:ctx-b", ttl_seconds=300)

    queue.enqueue(
        intent_id="intent-a",
        context_id="ctx-a",
        agent_id="agent/a",
        priority=20,
        required_locks=["vm:120/service:keycloak"],
    )
    queue.enqueue(
        intent_id="intent-b",
        context_id="ctx-b",
        agent_id="agent/b",
        priority=80,
        required_locks=["vm:120/service:netbox"],
    )

    coordination.publish(
        AgentSessionEntry(
            context_id="ctx-a",
            agent_id="agent/a",
            session_label="session-a",
            current_intent_id="intent-a",
            status="blocked",
            blocked_reason="waiting_for:vm:120/service:keycloak",
        )
    )
    coordination.publish(
        AgentSessionEntry(
            context_id="ctx-b",
            agent_id="agent/b",
            session_label="session-b",
            current_intent_id="intent-b",
            status="blocked",
            blocked_reason="waiting_for:vm:120/service:netbox",
        )
    )

    result = DeadlockDetector(
        lock_registry=locks,
        coordination_map=coordination,
        intent_queue=queue,
        ledger_writer=ledger,
    ).run_once()

    assert result["deadlocks_detected"] == 1
    assert result["resolutions"][0]["victim"]["context_id"] == "ctx-b"
    assert queue.get("intent-b").attempts == 2
    assert queue.get("intent-b").status == "waiting"
    assert locks.get_holder("vm:120/service:keycloak") is None

    records = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["event_type"] == "execution.deadlock_aborted"
    assert records[0]["target_id"] == "intent-b"


def test_deadlock_detector_flags_livelock(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 3, 25, 10, 0, tzinfo=UTC))
    queue = IntentQueue(state_path=tmp_path / "queue.json", now_fn=clock.now)
    queue.enqueue(
        intent_id="intent-livelock",
        context_id="ctx-livelock",
        agent_id="agent/livelock",
        priority=50,
        required_locks=["vm:120/service:netbox"],
        attempts=4,
    )
    entry = queue.get("intent-livelock")
    assert entry is not None
    payload = entry.as_dict()
    payload["queued_at"] = (clock.value - timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
    (tmp_path / "queue.json").write_text(
        json.dumps({"schema_version": "1.0.0", "entries": {"intent-livelock": payload}}, indent=2) + "\n",
        encoding="utf-8",
    )

    detector = DeadlockDetector(
        lock_registry=ResourceLockRegistry(state_path=tmp_path / "locks.json", now_fn=clock.now),
        coordination_map=AgentCoordinationMap(state_path=tmp_path / "coordination.json", now_fn=clock.now),
        intent_queue=queue,
    )
    result = detector.run_once()

    assert result["deadlocks_detected"] == 0
    assert result["livelocks_detected"] == 1
    assert result["livelocks"][0]["intent_id"] == "intent-livelock"


def test_deadlock_windmill_wrapper_runs_detector(tmp_path: Path) -> None:
    module = load_module("deadlock_windmill", "config/windmill/scripts/detect-deadlocks.py")
    result = module.main(
        repo_path=str(REPO_ROOT),
        lock_registry_path=str(tmp_path / "locks.json"),
        coordination_map_path=str(tmp_path / "coordination.json"),
        intent_queue_path=str(tmp_path / "queue.json"),
        ledger_file_path=str(tmp_path / "ledger.jsonl"),
    )

    assert result["deadlocks_detected"] == 0
    assert result["livelocks_detected"] == 0
