from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from platform.conflict import IntentConflictRegistry
from platform.scheduler import BudgetedWorkflowScheduler


def write_conflict_repo(repo_root: Path) -> None:
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "workflow-defaults.yaml").write_text(
        (
            "default_budget:\n"
            "  max_duration_seconds: 600\n"
            "  max_steps: 200\n"
            "  max_concurrent_instances: 2\n"
            "  max_touched_hosts: 10\n"
            "  max_restarts: 1\n"
            "  max_rollback_depth: 1\n"
            "  escalation_action: notify_and_abort\n"
        ),
        encoding="utf-8",
    )
    (repo_root / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "converge-netbox": {
                        "description": "Deploy NetBox",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "resource_claims": [{"resource": "service:netbox", "access": "write"}],
                    },
                    "rotate-netbox-db-password": {
                        "description": "Rotate a NetBox secret",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "resource_claims": [
                            {"resource": "service:netbox", "access": "write"},
                            {"resource": "secret:netbox/db", "access": "write"},
                        ],
                    },
                    "converge-postgres": {
                        "description": "Deploy Postgres",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "resource_claims": [{"resource": "service:postgres", "access": "write"}],
                    },
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "dependency-graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "nodes": [
                    {"id": "netbox", "service": "netbox", "name": "NetBox", "vm": "netbox-lv3", "tier": 1},
                    {"id": "postgres", "service": "postgres", "name": "Postgres", "vm": "postgres-lv3", "tier": 1},
                ],
                "edges": [
                    {"from": "netbox", "to": "postgres", "type": "hard", "description": "NetBox depends on Postgres"}
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


class FakeLockToken:
    def release(self) -> None:
        return None


class FakeLockManager:
    def acquire(self, workflow_id: str, *, max_instances: int) -> FakeLockToken | None:
        return FakeLockToken()


class BlockingWindmillClient:
    def __init__(self) -> None:
        self.submit_calls: list[str] = []
        self.submitted = threading.Event()
        self.release = threading.Event()
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def submit_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        self.submit_calls.append(workflow_id)
        self.submitted.set()
        return {"job_id": f"job-{workflow_id}", "running": True}

    def get_job(self, job_id: str) -> dict[str, Any]:
        if not self.release.is_set():
            time.sleep(0.01)
            return {"running": True, "started_at": self._started_at}
        return {"completed": True, "success": True, "result": {"job_id": job_id}}

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any]:
        return {"job_id": job_id, "canceled": True}


def test_registry_allows_single_winner_under_race(tmp_path: Path) -> None:
    write_conflict_repo(tmp_path)
    registry = IntentConflictRegistry(repo_root=tmp_path, state_path=tmp_path / ".local" / "conflicts.json")
    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker(intent_id: str) -> None:
        barrier.wait()
        result = registry.register_intent(
            {"workflow_id": "converge-netbox", "arguments": {"service": "netbox"}, "target_service_id": "netbox"},
            actor_intent_id=intent_id,
            actor="agent:test",
            ttl_seconds=120,
        )
        results.append(result.status)

    first = threading.Thread(target=worker, args=("intent-a",))
    second = threading.Thread(target=worker, args=("intent-b",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert sorted(results) == ["clear", "conflict"]


def test_scheduler_rejects_overlapping_service_writes(tmp_path: Path) -> None:
    write_conflict_repo(tmp_path)
    windmill = BlockingWindmillClient()
    scheduler_one = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=FakeLockManager(),
        sleep_fn=lambda _seconds: None,
    )
    scheduler_two = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=FakeLockManager(),
        sleep_fn=lambda _seconds: None,
    )
    first_result: dict[str, Any] = {}

    def run_first() -> None:
        first_result["result"] = scheduler_one.submit(
            SimpleNamespace(intent_id="intent-a", workflow_id="converge-netbox", arguments={}, target_service_id="netbox")
        )

    thread = threading.Thread(target=run_first)
    thread.start()
    assert windmill.submitted.wait(timeout=2.0)

    second = scheduler_two.submit(
        SimpleNamespace(
            intent_id="intent-b",
            workflow_id="rotate-netbox-db-password",
            arguments={"secret_id": "netbox/db"},
            target_service_id="netbox",
        )
    )

    assert second.status == "conflict_rejected"
    assert windmill.submit_calls == ["converge-netbox"]

    windmill.release.set()
    thread.join(timeout=2.0)
    assert first_result["result"].status == "completed"


def test_scheduler_returns_duplicate_recent_result(tmp_path: Path) -> None:
    write_conflict_repo(tmp_path)
    windmill = BlockingWindmillClient()
    windmill.release.set()
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=windmill,
        repo_root=tmp_path,
        lock_manager=FakeLockManager(),
        sleep_fn=lambda _seconds: None,
    )

    first = scheduler.submit(
        SimpleNamespace(intent_id="intent-a", workflow_id="converge-netbox", arguments={}, target_service_id="netbox")
    )
    second = scheduler.submit(
        SimpleNamespace(intent_id="intent-b", workflow_id="converge-netbox", arguments={}, target_service_id="netbox")
    )

    assert first.status == "completed"
    assert second.status == "duplicate"
    assert windmill.submit_calls == ["converge-netbox"]
    assert second.output == {"job_id": "job-converge-netbox"}


def test_preview_warns_when_dependency_is_already_mutating(tmp_path: Path) -> None:
    write_conflict_repo(tmp_path)
    registry = IntentConflictRegistry(repo_root=tmp_path, state_path=tmp_path / ".local" / "conflicts.json")
    registry.register_intent(
        {"workflow_id": "converge-postgres", "arguments": {}, "target_service_id": "postgres"},
        actor_intent_id="intent-postgres",
        actor="agent:test",
        ttl_seconds=120,
    )

    preview = registry.preview_intent(
        {"workflow_id": "converge-netbox", "arguments": {}, "target_service_id": "netbox"},
        actor_intent_id="intent-netbox",
        actor="agent:test",
    )

    assert preview.status == "clear"
    assert [warning.conflict_type for warning in preview.warnings] == ["cascade_conflict"]
