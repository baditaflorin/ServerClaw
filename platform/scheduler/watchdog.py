from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

from platform.ledger._common import REPO_ROOT, load_module_from_repo

from .budgets import WorkflowBudget


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _default_escalation_handler(subject: str, payload: dict[str, Any]) -> None:
    import os

    nats_url = os.environ.get("LV3_LEDGER_NATS_URL", "").strip() or os.environ.get("LV3_NATS_URL", "").strip()
    if not nats_url:
        return
    drift_lib = load_module_from_repo(REPO_ROOT / "scripts" / "drift_lib.py", "lv3_scheduler_drift_lib")
    drift_lib.publish_nats_events(
        [{"subject": subject, "payload": payload}],
        nats_url=nats_url,
        credentials=None,
    )


@dataclass(frozen=True)
class ActiveJobRecord:
    job_id: str
    workflow_id: str
    actor_intent_id: str
    requested_by: str
    execution_class: str
    started_at: str
    budget: WorkflowBudget | None = None
    parent_actor_intent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "workflow_id": self.workflow_id,
            "actor_intent_id": self.actor_intent_id,
            "requested_by": self.requested_by,
            "execution_class": self.execution_class,
            "started_at": self.started_at,
            "metadata": self.metadata,
        }
        if self.parent_actor_intent_id:
            payload["parent_actor_intent_id"] = self.parent_actor_intent_id
        if self.budget is not None:
            payload["budget"] = self.budget.as_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActiveJobRecord":
        budget_payload = payload.get("budget")
        budget = WorkflowBudget(**budget_payload) if isinstance(budget_payload, dict) else None
        metadata = payload.get("metadata")
        return cls(
            job_id=str(payload["job_id"]),
            workflow_id=str(payload["workflow_id"]),
            actor_intent_id=str(payload["actor_intent_id"]),
            requested_by=str(payload.get("requested_by", "operator:unknown")),
            execution_class=str(payload.get("execution_class", "mutation")),
            started_at=str(payload["started_at"]),
            budget=budget,
            parent_actor_intent_id=payload.get("parent_actor_intent_id"),
            metadata=metadata if isinstance(metadata, dict) else {},
        )


@dataclass(frozen=True)
class WatchdogViolation:
    reason: str
    observed: int | float
    limit: int | float
    message: str
    advisory_only: bool = False


class SchedulerStateStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (REPO_ROOT / ".local" / "scheduler" / "active-jobs.json")

    def list_active_jobs(self) -> list[ActiveJobRecord]:
        payload = self._read()
        jobs = payload.get("active_jobs", [])
        if not isinstance(jobs, list):
            return []
        return [ActiveJobRecord.from_dict(job) for job in jobs if isinstance(job, dict)]

    def upsert(self, record: ActiveJobRecord) -> None:
        payload = self._read()
        jobs = [
            job
            for job in payload.get("active_jobs", [])
            if isinstance(job, dict) and str(job.get("job_id")) != record.job_id
        ]
        jobs.append(record.as_dict())
        self._write({"active_jobs": sorted(jobs, key=lambda item: str(item.get("job_id", "")))})

    def remove(self, job_id: str) -> None:
        payload = self._read()
        jobs = [
            job
            for job in payload.get("active_jobs", [])
            if isinstance(job, dict) and str(job.get("job_id")) != job_id
        ]
        self._write({"active_jobs": jobs})

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"active_jobs": []}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"active_jobs": []}

    def _write(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, dir=self._path.parent, encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self._path)


class Watchdog:
    def __init__(
        self,
        *,
        windmill_client: Any,
        state_store: SchedulerStateStore,
        ledger_writer: Any | None = None,
        escalation_handler: Callable[[str, dict[str, Any]], None] | None = _default_escalation_handler,
        advisory_host_limit: bool = True,
    ) -> None:
        self._windmill_client = windmill_client
        self._state_store = state_store
        self._ledger_writer = ledger_writer
        self._escalation_handler = escalation_handler
        self._advisory_host_limit = advisory_host_limit

    @staticmethod
    def is_terminal(status: dict[str, Any]) -> bool:
        if status.get("completed") is True:
            return True
        if status.get("success") is not None:
            return True
        if status.get("canceled") is True:
            return True
        if status.get("running") is False and status.get("started_at"):
            return True
        return False

    @staticmethod
    def extract_completed_steps(status: dict[str, Any]) -> int | None:
        for key in ("completed_steps", "step_count", "steps_completed"):
            value = status.get(key)
            if isinstance(value, int):
                return value

        flow_status = status.get("flow_status")
        if isinstance(flow_status, dict):
            modules = flow_status.get("modules")
            if isinstance(modules, list):
                return sum(
                    1
                    for module in modules
                    if isinstance(module, dict)
                    and (
                        module.get("success") is True
                        or str(module.get("status", "")).lower() in {"success", "completed"}
                    )
                )
        return None

    @staticmethod
    def extract_touched_hosts(status: dict[str, Any]) -> int | None:
        for key in ("touched_hosts_count", "host_count"):
            value = status.get(key)
            if isinstance(value, int):
                return value
        for key in ("touched_hosts", "contacted_hosts", "hosts_touched"):
            value = status.get(key)
            if isinstance(value, list):
                return len({str(item) for item in value if str(item).strip()})
        return None

    def evaluate(
        self,
        job: ActiveJobRecord,
        status: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> WatchdogViolation | None:
        if job.execution_class != "mutation" or job.budget is None:
            return None

        current_time = now or datetime.now(UTC)
        started_at = _parse_timestamp(job.started_at)
        elapsed = max(0.0, (current_time - started_at).total_seconds())
        if elapsed > job.budget.max_duration_seconds:
            return WatchdogViolation(
                reason="max_duration_seconds",
                observed=round(elapsed, 2),
                limit=job.budget.max_duration_seconds,
                message=(
                    f"workflow {job.workflow_id} exceeded duration budget "
                    f"({elapsed:.1f}s > {job.budget.max_duration_seconds}s)"
                ),
            )

        completed_steps = self.extract_completed_steps(status)
        if completed_steps is not None and completed_steps > job.budget.max_steps:
            return WatchdogViolation(
                reason="max_steps",
                observed=completed_steps,
                limit=job.budget.max_steps,
                message=(
                    f"workflow {job.workflow_id} exceeded step budget "
                    f"({completed_steps} > {job.budget.max_steps})"
                ),
            )

        touched_hosts = self.extract_touched_hosts(status)
        if touched_hosts is not None and touched_hosts > job.budget.max_touched_hosts:
            return WatchdogViolation(
                reason="max_touched_hosts",
                observed=touched_hosts,
                limit=job.budget.max_touched_hosts,
                advisory_only=self._advisory_host_limit,
                message=(
                    f"workflow {job.workflow_id} touched more hosts than budgeted "
                    f"({touched_hosts} > {job.budget.max_touched_hosts})"
                ),
            )
        return None

    def handle_terminal(self, job: ActiveJobRecord, status: dict[str, Any]) -> dict[str, Any]:
        self._state_store.remove(job.job_id)
        metadata = {
            "job_id": job.job_id,
            "requested_by": job.requested_by,
            "parent_actor_intent_id": job.parent_actor_intent_id,
            "windmill_status": status,
        }
        if self._ledger_writer is not None:
            event_type = "execution.completed"
            if status.get("canceled") is True:
                event_type = "execution.aborted"
            elif status.get("success") is False:
                event_type = "execution.failed"
            self._ledger_writer.write(
                event_type=event_type,
                actor="scheduler:watchdog",
                actor_intent_id=job.actor_intent_id,
                target_kind="workflow",
                target_id=job.workflow_id,
                metadata=metadata,
            )
        return {
            "status": "completed" if status.get("success", True) and not status.get("canceled") else "aborted",
            "job_id": job.job_id,
            "workflow_id": job.workflow_id,
            "output": status.get("result"),
        }

    def handle_violation(
        self,
        job: ActiveJobRecord,
        status: dict[str, Any],
        violation: WatchdogViolation,
    ) -> dict[str, Any]:
        payload = {
            "job_id": job.job_id,
            "workflow_id": job.workflow_id,
            "actor_intent_id": job.actor_intent_id,
            "parent_actor_intent_id": job.parent_actor_intent_id,
            "reason": violation.reason,
            "observed": violation.observed,
            "limit": violation.limit,
            "message": violation.message,
            "escalation_action": job.budget.escalation_action if job.budget else None,
        }
        if not violation.advisory_only:
            self._windmill_client.cancel_job(job.job_id, reason=violation.message)
            self._state_store.remove(job.job_id)
            if self._ledger_writer is not None:
                self._ledger_writer.write(
                    event_type="execution.budget_exceeded",
                    actor="scheduler:watchdog",
                    actor_intent_id=job.actor_intent_id,
                    target_kind="workflow",
                    target_id=job.workflow_id,
                    metadata=payload,
                )
                self._ledger_writer.write(
                    event_type="execution.aborted",
                    actor="scheduler:watchdog",
                    actor_intent_id=job.actor_intent_id,
                    target_kind="workflow",
                    target_id=job.workflow_id,
                    metadata=payload,
                )
            if self._escalation_handler is not None and job.budget and job.budget.escalation_action != "abort_silently":
                self._escalation_handler("scheduler.budget_exceeded", payload)
        return payload

    def monitor_once(self, *, now: datetime | None = None) -> dict[str, Any]:
        current_time = now or datetime.now(UTC)
        summary = {
            "checked_at": current_time.isoformat(),
            "active_jobs": 0,
            "completed_jobs": 0,
            "violations": [],
            "warnings": [],
        }
        for job in self._state_store.list_active_jobs():
            summary["active_jobs"] += 1
            status = self._windmill_client.get_job(job.job_id)
            if self.is_terminal(status):
                self.handle_terminal(job, status)
                summary["completed_jobs"] += 1
                continue
            violation = self.evaluate(job, status, now=current_time)
            if violation is None:
                continue
            payload = self.handle_violation(job, status, violation)
            target = "warnings" if violation.advisory_only else "violations"
            summary[target].append(payload)
        return summary
