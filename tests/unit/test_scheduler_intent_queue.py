from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from platform.intent_queue import SchedulerIntentQueueStore
from platform.scheduler import BudgetedWorkflowScheduler
from tests.unit.test_intent_conflicts import (
    BlockingWindmillClient,
    FakeLockManager as ConflictLockManager,
    write_conflict_repo,
)
from tests.unit.test_scheduler_budgets import FakeLockManager, RecordingLedgerWriter, write_scheduler_repo


def test_scheduler_queue_store_claims_highest_priority_first(tmp_path: Path) -> None:
    write_scheduler_repo(
        tmp_path,
        workflows={
            "converge-netbox": {
                "description": "Deploy NetBox",
                "live_impact": "guest_live",
                "execution_class": "mutation",
            }
        },
    )
    store = SchedulerIntentQueueStore(repo_root=tmp_path, state_path=tmp_path / ".local" / "scheduler-queue.json")
    low = store.enqueue(
        SimpleNamespace(workflow_id="converge-netbox", arguments={}, queue_priority=80),
        requested_by="operator:test",
        autonomous=False,
        expires_in_seconds=600,
        priority=80,
    )
    high = store.enqueue(
        SimpleNamespace(workflow_id="converge-netbox", arguments={}, queue_priority=10),
        requested_by="operator:test",
        autonomous=False,
        expires_in_seconds=600,
        priority=10,
    )

    assert store.position_for(high.queue_id) == 1
    assert store.position_for(low.queue_id) == 2
    claimed = store.claim_ready(limit=1)
    assert [item.queue_id for item in claimed] == [high.queue_id]
    assert store.stats()["depth"] == 1


def test_scheduler_queues_busy_workflow_when_opted_in(tmp_path: Path) -> None:
    write_scheduler_repo(
        tmp_path,
        workflows={
            "converge-netbox": {
                "description": "Deploy NetBox",
                "live_impact": "guest_live",
                "execution_class": "mutation",
            }
        },
    )
    queue_store = SchedulerIntentQueueStore(repo_root=tmp_path, state_path=tmp_path / ".local" / "scheduler-queue.json")
    ledger = RecordingLedgerWriter()
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=BlockingWindmillClient(),
        repo_root=tmp_path,
        lock_manager=FakeLockManager(available=False),
        ledger_writer=ledger,
        intent_queue_store=queue_store,
        sleep_fn=lambda _seconds: None,
    )

    result = scheduler.submit(
        SimpleNamespace(workflow_id="converge-netbox", arguments={}, target_vm="netbox", queue_if_conflicted=True)
    )

    assert result.status == "queued"
    assert queue_store.stats()["depth"] == 1
    assert [event["event_type"] for event in ledger.events] == ["intent.queued"]


def test_drain_queued_intents_requeues_until_conflict_clears(tmp_path: Path) -> None:
    write_conflict_repo(tmp_path)
    queue_store = SchedulerIntentQueueStore(repo_root=tmp_path, state_path=tmp_path / ".local" / "scheduler-queue.json")
    windmill = BlockingWindmillClient()
    scheduler_one = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=ConflictLockManager(),
        intent_queue_store=queue_store,
        sleep_fn=lambda _seconds: None,
    )
    scheduler_two = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=ConflictLockManager(),
        intent_queue_store=queue_store,
        sleep_fn=lambda _seconds: None,
    )

    first: dict[str, object] = {}

    def run_first() -> None:
        first["result"] = scheduler_one.submit(
            SimpleNamespace(
                intent_id="intent-a", workflow_id="converge-netbox", arguments={}, target_service_id="netbox"
            )
        )

    thread = threading.Thread(target=run_first)
    thread.start()
    assert windmill.submitted.wait(timeout=2.0)

    queued = scheduler_two.submit(
        SimpleNamespace(
            intent_id="intent-b",
            workflow_id="rotate-netbox-db-password",
            arguments={"secret_id": "netbox/db"},
            target_service_id="netbox",
            queue_if_conflicted=True,
        )
    )
    assert queued.status == "queued"

    blocked = scheduler_two.drain_queued_intents(resource_hints=["service:netbox"], max_items=2)
    assert blocked["results"][0]["status"] == "requeued"
    assert queue_store.stats()["depth"] == 1

    windmill.release.set()
    thread.join(timeout=2.0)
    assert getattr(first["result"], "status", None) == "completed"

    drained = scheduler_two.drain_queued_intents(resource_hints=["service:netbox"], max_items=2)
    assert drained["results"][0]["status"] == "dispatched"
    assert drained["results"][0]["scheduler_status"] == "completed"
    assert queue_store.stats()["depth"] == 0
    assert windmill.submit_calls == ["converge-netbox", "rotate-netbox-db-password"]
