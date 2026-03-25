from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from repo_package_loader import load_repo_package


GOAL_COMPILER_MODULE = load_repo_package(
    "lv3_goal_compiler_batch_test",
    Path(__file__).resolve().parents[2] / "platform" / "goal_compiler",
)
DIFF_ENGINE_MODULE = load_repo_package(
    "lv3_diff_engine_batch_test",
    Path(__file__).resolve().parents[2] / "platform" / "diff_engine",
)
GoalCompiler = GOAL_COMPILER_MODULE.GoalCompiler
IntentBatchPlanner = GOAL_COMPILER_MODULE.IntentBatchPlanner
ChangedObject = DIFF_ENGINE_MODULE.ChangedObject
SemanticDiff = DIFF_ENGINE_MODULE.SemanticDiff


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def batch_repo(tmp_path: Path) -> Path:
    write(
        tmp_path / "config" / "service-capability-catalog.json",
        json.dumps(
            {
                "services": [
                    {"id": "netbox", "name": "NetBox", "vm": "netbox-lv3"},
                    {"id": "grafana", "name": "Grafana", "vm": "monitoring-lv3"},
                ]
            }
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "workflow-catalog.json",
        json.dumps(
            {
                "workflows": {
                    "converge-netbox": {
                        "description": "Converge NetBox",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "required_read_surfaces": ["world_state"],
                    },
                    "converge-grafana": {
                        "description": "Converge Grafana",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "required_read_surfaces": ["world_state"],
                    },
                    "restart-netbox": {
                        "description": "Restart NetBox",
                        "live_impact": "guest_live",
                        "execution_class": "mutation",
                        "required_read_surfaces": ["world_state"],
                    },
                }
            }
        )
        + "\n",
    )
    write(
        tmp_path / "config" / "agent-policies.yaml",
        """
- agent_id: operator:lv3-cli
  description: operator
  identity_class: operator-agent
  trust_tier: T3
  read_surfaces:
    - maintenance_windows
    - search
    - world_state
  autonomous_actions:
    max_risk_class: MEDIUM
    allowed_workflow_tags:
      - diagnostic
      - converge
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
        + "\n",
    )
    write(
        tmp_path / "inventory" / "hosts.yml",
        """
all:
  children:
    lv3_guests:
      hosts:
        netbox-lv3:
          ansible_host: 10.10.10.30
        monitoring-lv3:
          ansible_host: 10.10.10.40
""".strip()
        + "\n",
    )
    return tmp_path


class FakeDiffEngine:
    def __init__(self, *, sleep_seconds: float = 0.0) -> None:
        self.sleep_seconds = sleep_seconds

    def compute(self, payload: dict[str, object]) -> SemanticDiff:
        time.sleep(self.sleep_seconds)
        workflow_id = str(payload["workflow_id"])
        target = str(payload.get("target_service_id") or workflow_id)
        if workflow_id == "restart-netbox":
            changed = (
                ChangedObject(
                    surface="service",
                    object_id="netbox",
                    change_kind="restart",
                    before={"state": "running"},
                    after={"state": "running"},
                    confidence="exact",
                    reversible=True,
                    notes="restart service",
                ),
            )
        else:
            changed = (
                ChangedObject(
                    surface="service",
                    object_id=target,
                    change_kind="update",
                    before={"version": "old"},
                    after={"version": "new"},
                    confidence="exact",
                    reversible=True,
                    notes="update service",
                ),
            )
        return SemanticDiff(
            intent_id=str(payload["intent_id"]),
            computed_at="2026-03-25T12:00:00Z",
            changed_objects=changed,
            total_changes=len(changed),
            irreversible_count=0,
            unknown_count=0,
            adapters_used=("fake",),
            elapsed_ms=int(self.sleep_seconds * 1000),
        )


class FakeLedgerWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def write(self, **payload: object) -> dict[str, object]:
        self.events.append(dict(payload))
        return dict(payload)


def test_planner_fans_out_dry_runs_in_parallel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = batch_repo(tmp_path)
    maintenance_state = repo_root / ".local" / "state" / "maintenance" / "windows.json"
    write(maintenance_state, "{}\n")
    monkeypatch.setenv("LV3_MAINTENANCE_WINDOWS_FILE", str(maintenance_state))
    compiler = GoalCompiler(repo_root)
    batch = compiler.compile_batch(["deploy netbox", "converge-grafana"])
    ledger = FakeLedgerWriter()
    planner = IntentBatchPlanner(
        repo_root=repo_root,
        max_parallelism=2,
        diff_engine=FakeDiffEngine(sleep_seconds=0.2),
        ledger_writer=ledger,
    )

    started = time.monotonic()
    result = planner.plan(batch)
    elapsed = time.monotonic() - started

    assert elapsed < 0.55
    assert len(result.execution_plan.stages) == 1
    assert result.execution_plan.stages[0].parallelism == "full"
    assert ledger.events[0]["event_type"] == "intent.batch_plan"


def test_planner_rejects_conflicting_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = batch_repo(tmp_path)
    maintenance_state = repo_root / ".local" / "state" / "maintenance" / "windows.json"
    write(maintenance_state, "{}\n")
    monkeypatch.setenv("LV3_MAINTENANCE_WINDOWS_FILE", str(maintenance_state))
    compiler = GoalCompiler(repo_root)
    batch = compiler.compile_batch(["deploy netbox", "deploy netbox"])
    planner = IntentBatchPlanner(repo_root=repo_root, diff_engine=FakeDiffEngine())

    result = planner.plan(batch)

    assert len(result.execution_plan.stages) == 1
    assert len(result.execution_plan.stages[0].intent_ids) == 1
    assert len(result.execution_plan.rejected_intents) == 1
    rejected_id = result.execution_plan.rejected_intents[0]
    assert result.execution_plan.rejected_reasons[rejected_id] == "write_write_conflict on service:netbox"


def test_planner_orders_restart_after_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = batch_repo(tmp_path)
    maintenance_state = repo_root / ".local" / "state" / "maintenance" / "windows.json"
    write(maintenance_state, "{}\n")
    monkeypatch.setenv("LV3_MAINTENANCE_WINDOWS_FILE", str(maintenance_state))
    compiler = GoalCompiler(repo_root)
    batch = compiler.compile_batch(["deploy netbox", "restart-netbox"])
    planner = IntentBatchPlanner(repo_root=repo_root, diff_engine=FakeDiffEngine())

    result = planner.plan(batch)

    assert [stage.parallelism for stage in result.execution_plan.stages] == ["sequential", "sequential"]
    first_stage_entry = next(entry for entry in result.dry_runs if entry.intent_id == result.execution_plan.stages[0].intent_ids[0])
    second_stage_entry = next(entry for entry in result.dry_runs if entry.intent_id == result.execution_plan.stages[1].intent_ids[0])
    assert first_stage_entry.instruction == "deploy netbox"
    assert second_stage_entry.instruction == "restart-netbox"
    assert any(item.conflict_type == "restart_during_config" for item in result.execution_plan.conflicts)
