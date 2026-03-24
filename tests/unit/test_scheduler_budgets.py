from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from platform.scheduler import (
    ActiveJobRecord,
    BudgetedWorkflowScheduler,
    SchedulerStateStore,
    Watchdog,
    load_workflow_policy,
)


def write_scheduler_repo(
    repo_root: Path,
    *,
    workflows: dict[str, Any],
    default_budget: dict[str, Any] | None = None,
) -> None:
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "workflow-defaults.yaml").write_text(
        (
            "default_budget:\n"
            f"  max_duration_seconds: {(default_budget or {}).get('max_duration_seconds', 600)}\n"
            f"  max_steps: {(default_budget or {}).get('max_steps', 200)}\n"
            f"  max_concurrent_instances: {(default_budget or {}).get('max_concurrent_instances', 3)}\n"
            f"  max_touched_hosts: {(default_budget or {}).get('max_touched_hosts', 10)}\n"
            f"  max_restarts: {(default_budget or {}).get('max_restarts', 1)}\n"
            f"  max_rollback_depth: {(default_budget or {}).get('max_rollback_depth', 1)}\n"
            f"  escalation_action: {(default_budget or {}).get('escalation_action', 'notify_and_abort')}\n"
        ),
        encoding="utf-8",
    )
    (repo_root / "config" / "workflow-catalog.json").write_text(
        json.dumps({"workflows": workflows}, indent=2) + "\n",
        encoding="utf-8",
    )


class RecordingLedgerWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(self, **payload: Any) -> dict[str, Any]:
        self.events.append(payload)
        return payload


class FakeIntentReader:
    def __init__(self, chain: dict[str, str | None]) -> None:
        self._chain = chain

    def events_by_intent(self, actor_intent_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        parent = self._chain.get(actor_intent_id)
        metadata = {"parent_actor_intent_id": parent} if parent else {}
        return [{"metadata": metadata}]


class FakeLockToken:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeLockManager:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.acquired: list[tuple[str, int]] = []
        self.last_token: FakeLockToken | None = None

    def acquire(self, workflow_id: str, *, max_instances: int) -> FakeLockToken | None:
        self.acquired.append((workflow_id, max_instances))
        if not self.available:
            return None
        self.last_token = FakeLockToken()
        return self.last_token


class FakeWindmillClient:
    def __init__(self, *, statuses: list[dict[str, Any]] | None = None) -> None:
        self.statuses = statuses or []
        self.submit_calls: list[tuple[str, dict[str, Any], int | None]] = []
        self.cancel_calls: list[tuple[str, str | None]] = []

    def submit_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        self.submit_calls.append((workflow_id, arguments, timeout_seconds))
        return {"job_id": "job-1", "running": True}

    def get_job(self, job_id: str) -> dict[str, Any]:
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        if self.statuses:
            return self.statuses[0]
        return {"completed": True, "success": True, "result": {"job_id": job_id}}

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any]:
        self.cancel_calls.append((job_id, reason))
        return {"job_id": job_id, "canceled": True}


def test_budget_loader_merges_defaults_and_explicit_overrides(tmp_path: Path) -> None:
    write_scheduler_repo(
        tmp_path,
        workflows={
            "converge-netbox": {
                "description": "Deploy NetBox",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "budget": {
                    "max_duration_seconds": 900,
                    "max_concurrent_instances": 1,
                    "max_steps": 250,
                    "max_touched_hosts": 2,
                    "max_restarts": 0,
                    "max_rollback_depth": 1,
                    "escalation_action": "notify_and_abort",
                },
            }
        },
    )

    policy = load_workflow_policy("converge-netbox", repo_root=tmp_path)

    assert policy.execution_class == "mutation"
    assert policy.budget.max_duration_seconds == 900
    assert policy.budget.max_concurrent_instances == 1
    assert policy.budget.max_steps == 250


def test_scheduler_rejects_when_concurrency_slots_are_busy(tmp_path: Path) -> None:
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
    windmill = FakeWindmillClient()
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=FakeLockManager(available=False),
        sleep_fn=lambda _seconds: None,
    )

    result = scheduler.submit(SimpleNamespace(workflow_id="converge-netbox", arguments={}, target_vm="netbox"))

    assert result.status == "concurrency_limit"
    assert windmill.submit_calls == []


def test_scheduler_blocks_rollback_chain_beyond_budget(tmp_path: Path) -> None:
    write_scheduler_repo(
        tmp_path,
        workflows={
            "rollback-netbox": {
                "description": "Rollback NetBox",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "budget": {
                    "max_duration_seconds": 600,
                    "max_steps": 200,
                    "max_concurrent_instances": 1,
                    "max_touched_hosts": 2,
                    "max_restarts": 0,
                    "max_rollback_depth": 1,
                    "escalation_action": "notify_and_abort",
                },
            }
        },
    )
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=FakeWindmillClient(),
        repo_root=tmp_path,
        lock_manager=FakeLockManager(),
        ledger_reader=FakeIntentReader(
            {
                "intent-a": "intent-b",
                "intent-b": None,
            }
        ),
        sleep_fn=lambda _seconds: None,
    )

    result = scheduler.submit(
        SimpleNamespace(
            workflow_id="rollback-netbox",
            arguments={"parent_actor_intent_id": "intent-a"},
            target_vm="netbox",
        )
    )

    assert result.status == "rollback_depth_exceeded"
    assert result.metadata["rollback_depth"] == 2


def test_watchdog_cancels_duration_budget_violations(tmp_path: Path) -> None:
    store = SchedulerStateStore(tmp_path / ".local" / "scheduler" / "active-jobs.json")
    write_scheduler_repo(tmp_path, workflows={"converge-netbox": {"description": "Deploy", "live_impact": "guest_live"}})
    policy = load_workflow_policy("converge-netbox", repo_root=tmp_path)
    started_at = (datetime.now(UTC) - timedelta(seconds=45)).isoformat()
    store.upsert(
        ActiveJobRecord(
            job_id="job-1",
            workflow_id="converge-netbox",
            actor_intent_id="intent-1",
            requested_by="operator:test",
            execution_class="mutation",
            started_at=started_at,
            budget=policy.budget,
        )
    )
    windmill = FakeWindmillClient(statuses=[{"running": True, "started_at": started_at}])
    ledger = RecordingLedgerWriter()
    watchdog = Watchdog(windmill_client=windmill, state_store=store, ledger_writer=ledger)

    summary = watchdog.monitor_once(now=datetime.now(UTC) + timedelta(seconds=601))

    assert len(summary["violations"]) == 1
    assert windmill.cancel_calls[0][0] == "job-1"
    assert [event["event_type"] for event in ledger.events] == [
        "execution.budget_exceeded",
        "execution.aborted",
    ]
    assert store.list_active_jobs() == []


def test_scheduler_submits_waits_and_records_completion(tmp_path: Path) -> None:
    write_scheduler_repo(
        tmp_path,
        workflows={
            "converge-netbox": {
                "description": "Deploy NetBox",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "budget": {
                    "max_duration_seconds": 900,
                    "max_steps": 250,
                    "max_concurrent_instances": 1,
                    "max_touched_hosts": 2,
                    "max_restarts": 0,
                    "max_rollback_depth": 1,
                    "escalation_action": "notify_and_abort",
                },
            }
        },
    )
    store = SchedulerStateStore(tmp_path / ".local" / "scheduler" / "active-jobs.json")
    ledger = RecordingLedgerWriter()
    lock_manager = FakeLockManager()
    windmill = FakeWindmillClient(
        statuses=[
            {"running": True, "started_at": datetime.now(UTC).isoformat()},
            {"completed": True, "success": True, "result": {"status": "ok"}},
        ]
    )
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=lock_manager,
        ledger_writer=ledger,
        state_store=store,
        sleep_fn=lambda _seconds: None,
    )

    result = scheduler.submit(
        SimpleNamespace(workflow_id="converge-netbox", arguments={"service": "netbox"}, target_vm="netbox")
    )

    assert result.status == "completed"
    assert result.output == {"status": "ok"}
    assert [event["event_type"] for event in ledger.events] == [
        "intent.claim_registered",
        "execution.started",
        "execution.completed",
    ]
    assert lock_manager.last_token is not None
    assert lock_manager.last_token.released is True
    assert store.list_active_jobs() == []
