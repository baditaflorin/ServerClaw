from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from platform.conflict import IntentConflictRegistry
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
    agent_policies: str | None = None,
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
    default_policies = """
- agent_id: operator:lv3-cli
  description: operator
  identity_class: operator-agent
  trust_tier: T3
  read_surfaces:
    - search
    - world_state
  autonomous_actions:
    max_risk_class: MEDIUM
    allowed_workflow_tags:
      - converge
      - diagnostic
      - mutation
      - validation
    disallowed_workflow_ids:
      - destroy-vm
    max_daily_autonomous_executions: 50
  escalation:
    on_risk_above: MEDIUM
    escalation_target: operator
    escalation_event: platform.intent.rejected
""".strip()
    (repo_root / "config" / "agent-policies.yaml").write_text(
        (agent_policies if agent_policies is not None else default_policies) + "\n",
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


class SequencedWindmillClient:
    def __init__(self, *, submit_responses: list[dict[str, Any]], statuses_by_job: dict[str, list[dict[str, Any]]]) -> None:
        self.submit_responses = list(submit_responses)
        self.statuses_by_job = {key: list(value) for key, value in statuses_by_job.items()}
        self.submit_calls: list[tuple[str, dict[str, Any], int | None]] = []

    def submit_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        self.submit_calls.append((workflow_id, arguments, timeout_seconds))
        response = self.submit_responses.pop(0)
        return dict(response)

    def get_job(self, job_id: str) -> dict[str, Any]:
        statuses = self.statuses_by_job[job_id]
        if len(statuses) > 1:
            return statuses.pop(0)
        return statuses[0]

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any]:
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


def test_scheduler_state_store_uses_session_local_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LV3_SESSION_LOCAL_ROOT", str(tmp_path / ".local" / "session-workspaces" / "test-session"))

    store = SchedulerStateStore()

    assert str(store._path).endswith(".local/session-workspaces/test-session/scheduler/active-jobs.json")


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


def test_scheduler_skips_lock_and_commits_speculative_workflow(tmp_path: Path) -> None:
    probe_path = tmp_path / "tests" / "fixtures" / "spec_probe.py"
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    probe_path.write_text(
        "def probe(context):\n    return {'conflict_detected': False, 'metadata': {'checked': True}}\n",
        encoding="utf-8",
    )
    write_scheduler_repo(
        tmp_path,
        workflows={
            "rotate-netbox-db-password": {
                "description": "Rotate NetBox secret",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "resource_claims": [{"resource": "service:netbox", "access": "write"}],
                "speculative": {
                    "eligible": True,
                    "compensating_workflow_id": "restore-netbox-db-password",
                    "conflict_probe": {"path": str(probe_path.relative_to(tmp_path)), "callable": "probe"},
                    "probe_delay_seconds": 0,
                    "rollback_window_seconds": 120,
                },
            },
            "restore-netbox-db-password": {
                "description": "Restore NetBox secret",
                "live_impact": "guest_live",
                "execution_class": "mutation",
            },
            "converge-netbox": {
                "description": "Deploy NetBox",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "resource_claims": [{"resource": "service:netbox", "access": "write"}],
            },
        },
    )
    registry = IntentConflictRegistry(repo_root=tmp_path, state_path=tmp_path / ".local" / "conflicts.json")
    registry.register_intent(
        {"workflow_id": "converge-netbox", "arguments": {}, "target_service_id": "netbox"},
        actor_intent_id="intent-existing",
        actor="agent:test",
        ttl_seconds=120,
    )
    windmill = SequencedWindmillClient(
        submit_responses=[{"job_id": "job-rotate", "running": True}],
        statuses_by_job={
            "job-rotate": [
                {"running": True, "started_at": datetime.now(UTC).isoformat()},
                {"completed": True, "success": True, "result": {"status": "ok"}},
            ]
        },
    )
    ledger = RecordingLedgerWriter()
    lock_manager = FakeLockManager(available=False)
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=lock_manager,
        ledger_writer=ledger,
        conflict_registry=registry,
        sleep_fn=lambda _seconds: None,
    )

    result = scheduler.submit(
        SimpleNamespace(
            id="intent-spec",
            workflow_id="rotate-netbox-db-password",
            execution_mode="speculative",
            arguments={"secret_id": "netbox/db", "execution_mode": "speculative"},
            target_service_id="netbox",
        )
    )

    assert result.status == "completed"
    assert lock_manager.acquired == []
    assert [call[0] for call in windmill.submit_calls] == ["rotate-netbox-db-password"]
    assert "execution.speculative_committed" in [event["event_type"] for event in ledger.events]


def test_scheduler_rolls_back_speculative_loser(tmp_path: Path) -> None:
    probe_path = tmp_path / "tests" / "fixtures" / "spec_probe_conflict.py"
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    probe_path.write_text(
        (
            "def probe(context):\n"
            "    return {\n"
            "        'conflict_detected': True,\n"
            "        'winning_intent_id': 'intent-existing',\n"
            "        'conflicting_intent_id': 'intent-existing',\n"
            "        'message': 'existing writer wins',\n"
            "    }\n"
        ),
        encoding="utf-8",
    )
    write_scheduler_repo(
        tmp_path,
        workflows={
            "rotate-netbox-db-password": {
                "description": "Rotate NetBox secret",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "resource_claims": [{"resource": "service:netbox", "access": "write"}],
                "speculative": {
                    "eligible": True,
                    "compensating_workflow_id": "restore-netbox-db-password",
                    "conflict_probe": {"path": str(probe_path.relative_to(tmp_path)), "callable": "probe"},
                    "probe_delay_seconds": 0,
                    "rollback_window_seconds": 120,
                },
            },
            "restore-netbox-db-password": {
                "description": "Restore NetBox secret",
                "live_impact": "guest_live",
                "execution_class": "mutation",
            },
            "converge-netbox": {
                "description": "Deploy NetBox",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "resource_claims": [{"resource": "service:netbox", "access": "write"}],
            },
        },
    )
    registry = IntentConflictRegistry(repo_root=tmp_path, state_path=tmp_path / ".local" / "conflicts.json")
    registry.register_intent(
        {"workflow_id": "converge-netbox", "arguments": {}, "target_service_id": "netbox"},
        actor_intent_id="intent-existing",
        actor="agent:test",
        ttl_seconds=120,
    )
    windmill = SequencedWindmillClient(
        submit_responses=[
            {"job_id": "job-rotate", "running": True},
            {"job_id": "job-restore", "running": True},
        ],
        statuses_by_job={
            "job-rotate": [
                {"running": True, "started_at": datetime.now(UTC).isoformat()},
                {"completed": True, "success": True, "result": {"status": "rotated"}},
            ],
            "job-restore": [
                {"running": True, "started_at": datetime.now(UTC).isoformat()},
                {"completed": True, "success": True, "result": {"status": "restored"}},
            ],
        },
    )
    ledger = RecordingLedgerWriter()
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=FakeLockManager(available=False),
        ledger_writer=ledger,
        conflict_registry=registry,
        sleep_fn=lambda _seconds: None,
    )

    result = scheduler.submit(
        SimpleNamespace(
            id="intent-spec",
            workflow_id="rotate-netbox-db-password",
            execution_mode="speculative",
            arguments={"secret_id": "netbox/db", "execution_mode": "speculative"},
            target_service_id="netbox",
        )
    )

    assert result.status == "rolled_back"
    assert [call[0] for call in windmill.submit_calls] == [
        "rotate-netbox-db-password",
        "restore-netbox-db-password",
    ]
    assert "execution.speculative_rolled_back" in [event["event_type"] for event in ledger.events]


def test_load_workflow_policy_rejects_invalid_speculative_config(tmp_path: Path) -> None:
    write_scheduler_repo(
        tmp_path,
        workflows={
            "rotate-netbox-db-password": {
                "description": "Rotate NetBox secret",
                "live_impact": "guest_live",
                "execution_class": "mutation",
                "speculative": {"eligible": True},
            }
        },
    )

    try:
        load_workflow_policy("rotate-netbox-db-password", repo_root=tmp_path)
    except ValueError as exc:
        assert "compensating_workflow_id" in str(exc)
    else:  # pragma: no cover - defensive guard for failing assertion
        raise AssertionError("expected invalid speculative config to raise ValueError")


def test_scheduler_rejects_when_autonomous_daily_cap_is_reached(tmp_path: Path) -> None:
    write_scheduler_repo(
        tmp_path,
        workflows={
            "validate": {
                "description": "Validate repository",
                "live_impact": "repo_only",
                "execution_class": "diagnostic",
                "required_read_surfaces": ["search"],
            }
        },
        agent_policies="""
- agent_id: agent/triage-loop
  description: triage
  identity_class: service-agent
  trust_tier: T2
  read_surfaces:
    - search
  autonomous_actions:
    max_risk_class: LOW
    allowed_workflow_tags:
      - diagnostic
      - validation
    disallowed_workflow_ids: []
    max_daily_autonomous_executions: 1
  escalation:
    on_risk_above: LOW
    escalation_target: mattermost:#platform-incidents
    escalation_event: platform.intent.rejected
""".strip()
        + "\n",
    )
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=FakeWindmillClient(statuses=[{"completed": True, "success": True, "result": {"ok": True}}]),
        repo_root=tmp_path,
        lock_manager=FakeLockManager(),
        sleep_fn=lambda _seconds: None,
    )

    first = scheduler.submit(
        SimpleNamespace(workflow_id="validate", arguments={"mode": "strict"}, final_risk_class="LOW"),
        requested_by="agent/triage-loop",
        autonomous=True,
    )
    second = scheduler.submit(
        SimpleNamespace(workflow_id="validate", arguments={"mode": "strict"}, final_risk_class="LOW"),
        requested_by="agent/triage-loop",
        autonomous=True,
    )

    assert first.status == "completed"
    assert second.status == "autonomy_limit_reached"
