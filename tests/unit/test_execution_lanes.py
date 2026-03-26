from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from platform.execution_lanes import LaneRegistry, resolve_lanes
from platform.scheduler import BudgetedWorkflowScheduler


def write_lane_repo(repo_root: Path) -> None:
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "agent-policies.yaml").write_text(
        """
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
      - mutation
      - diagnostic
    disallowed_workflow_ids: []
    max_daily_autonomous_executions: 50
  escalation:
    on_risk_above: MEDIUM
    escalation_target: operator
    escalation_event: platform.intent.rejected
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "workflow-defaults.yaml").write_text(
        """
default_budget:
  max_duration_seconds: 600
  max_steps: 200
  max_concurrent_instances: 2
  max_touched_hosts: 10
  max_restarts: 1
  max_rollback_depth: 1
  escalation_action: notify_and_abort
default_resource_reservation:
  cpu_milli: 500
  memory_mb: 256
  disk_iops: 30
  estimated_duration_seconds: 180
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "execution-lanes.yaml").write_text(
        """
schema_version: 1.0.0
lanes:
  lane:docker-runtime:
    hostname: docker-runtime-lv3
    vmid: 120
    services:
      - netbox
      - windmill
    max_concurrent_ops: 1
    serialisation: resource_lock
    admission_policy: soft
    vm_budget:
      total_cpu_milli: 1000
      total_memory_mb: 512
      total_disk_iops: 100
  lane:postgres:
    hostname: postgres-lv3
    vmid: 150
    services:
      - postgres
    max_concurrent_ops: 1
    serialisation: strict
    admission_policy: hard
    vm_budget:
      total_cpu_milli: 1000
      total_memory_mb: 512
      total_disk_iops: 100
  lane:platform:
    hostname: platform
    vmid: null
    services: []
    max_concurrent_ops: 1
    serialisation: strict
    admission_policy: hard
    vm_budget:
      total_cpu_milli: 1000
      total_memory_mb: 512
      total_disk_iops: 100
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "dependency-graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "edges": [
                    {"from": "netbox", "to": "postgres", "type": "hard"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "config" / "workflow-catalog.json").write_text(
        json.dumps(
            {
                "workflows": {
                    "converge-netbox": {"description": "Deploy NetBox"},
                    "converge-windmill": {"description": "Deploy Windmill"},
                    "converge-platform": {"description": "Cross-service update", "required_lanes": ["lane:platform"]},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_resolve_lanes_includes_dependency_lane(tmp_path: Path) -> None:
    write_lane_repo(tmp_path)

    resolution = resolve_lanes(
        {"workflow_id": "converge-netbox", "target_service_id": "netbox", "arguments": {}},
        repo_root=tmp_path,
    )

    assert resolution.primary_lane_id == "lane:docker-runtime"
    assert resolution.required_lanes == ("lane:docker-runtime", "lane:postgres")
    assert resolution.dependency_lanes == ("lane:postgres",)


def test_resolve_lanes_supports_list_based_catalog_schema(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "execution-lanes.yaml").write_text(
        """
schema_version: 1.0.0
lanes:
  - lane_id: lane:docker-runtime
    vm_id: 120
    hostname: docker-runtime-lv3
    services:
      - netbox
    max_concurrent_ops: 1
    serialisation: resource_lock
    admission_policy: soft
    vm_budget:
      total_cpu_milli: 1000
      total_memory_mb: 512
      total_disk_iops: 100
  - lane_id: lane:postgres
    vm_id: 150
    hostname: postgres-lv3
    services:
      - postgres
    max_concurrent_ops: 1
    serialisation: strict
    admission_policy: hard
    vm_budget:
      total_cpu_milli: 1000
      total_memory_mb: 512
      total_disk_iops: 100
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "dependency-graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "edges": [{"from": "netbox", "to": "postgres", "type": "hard"}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "workflow-catalog.json").write_text(
        json.dumps({"workflows": {"converge-netbox": {"description": "Deploy NetBox"}}}, indent=2) + "\n",
        encoding="utf-8",
    )

    resolution = resolve_lanes(
        {"workflow_id": "converge-netbox", "target_service_id": "netbox", "arguments": {}},
        repo_root=tmp_path,
    )

    assert resolution.primary_lane_id == "lane:docker-runtime"
    assert resolution.required_lanes == ("lane:docker-runtime", "lane:postgres")


def test_lane_registry_queues_when_capacity_is_exhausted(tmp_path: Path) -> None:
    write_lane_repo(tmp_path)
    registry = LaneRegistry(repo_root=tmp_path, state_path=tmp_path / ".local" / "lanes.json")

    first = registry.reserve(
        {"workflow_id": "converge-netbox", "target_service_id": "netbox", "arguments": {}},
        actor_intent_id="intent-a",
        ttl_seconds=120,
    )
    second = registry.reserve(
        {"workflow_id": "converge-windmill", "target_service_id": "windmill", "arguments": {}},
        actor_intent_id="intent-b",
        ttl_seconds=120,
    )
    queued = registry.enqueue(
        {"workflow_id": "converge-windmill", "target_service_id": "windmill", "arguments": {}},
        actor_intent_id="intent-b",
        requested_by="operator:test",
        ttl_seconds=120,
        autonomous=False,
    )

    assert first.status == "acquired"
    assert second.status == "busy"
    assert queued is not None
    assert queued.primary_lane_id == "lane:docker-runtime"


def test_lane_registry_dispatches_after_release(tmp_path: Path) -> None:
    write_lane_repo(tmp_path)
    registry = LaneRegistry(repo_root=tmp_path, state_path=tmp_path / ".local" / "lanes.json")
    registry.reserve(
        {"workflow_id": "converge-netbox", "target_service_id": "netbox", "arguments": {}},
        actor_intent_id="intent-a",
        ttl_seconds=120,
    )
    registry.enqueue(
        {"workflow_id": "converge-windmill", "target_service_id": "windmill", "arguments": {}, "id": "intent-b"},
        actor_intent_id="intent-b",
        requested_by="operator:test",
        ttl_seconds=120,
        autonomous=False,
    )

    registry.release("intent-a")
    dispatchable = registry.lease_dispatchable(max_items=1)

    assert len(dispatchable) == 1
    assert dispatchable[0].actor_intent_id == "intent-b"


class FakeLockToken:
    def release(self) -> None:
        return None


class FakeLockManager:
    def acquire(self, workflow_id: str, *, max_instances: int) -> FakeLockToken | None:
        return FakeLockToken()


class BusyLockManager:
    def acquire(self, workflow_id: str, *, max_instances: int) -> FakeLockToken | None:
        return None


class FakeWindmillClient:
    def submit_workflow(self, workflow_id: str, arguments: dict[str, str], *, timeout_seconds: int | None = None) -> dict[str, str]:
        return {"job_id": f"job-{workflow_id}", "running": True}

    def get_job(self, job_id: str) -> dict[str, str]:
        return {"running": True}

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, str]:
        return {"job_id": job_id, "canceled": True}


def test_scheduler_returns_queued_when_lane_is_busy(tmp_path: Path) -> None:
    write_lane_repo(tmp_path)
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=FakeWindmillClient(),
        repo_root=tmp_path,
        lock_manager=FakeLockManager(),
        sleep_fn=lambda _seconds: None,
    )

    first = scheduler.submit(
        SimpleNamespace(intent_id="intent-a", workflow_id="converge-netbox", arguments={}, target_service_id="netbox"),
        wait_for_completion=False,
    )
    second = scheduler.submit(
        SimpleNamespace(intent_id="intent-b", workflow_id="converge-windmill", arguments={}, target_service_id="windmill"),
    )

    assert first.status == "submitted"
    assert second.status == "queued"
    assert second.metadata["primary_lane_id"] == "lane:docker-runtime"


def test_scheduler_releases_lane_when_workflow_lock_is_busy(tmp_path: Path) -> None:
    write_lane_repo(tmp_path)
    scheduler = BudgetedWorkflowScheduler(
        windmill_client=FakeWindmillClient(),
        repo_root=tmp_path,
        lock_manager=BusyLockManager(),
        sleep_fn=lambda _seconds: None,
    )

    result = scheduler.submit(
        SimpleNamespace(intent_id="intent-a", workflow_id="converge-netbox", arguments={}, target_service_id="netbox"),
        wait_for_completion=False,
    )

    registry = LaneRegistry(repo_root=tmp_path, state_path=tmp_path / ".local" / "state" / "execution-lanes" / "registry.json")
    snapshot = registry.snapshot()

    assert result.status == "concurrency_limit"
    assert all(not leases for leases in snapshot["active"].values())
    assert snapshot["queue"] == []
