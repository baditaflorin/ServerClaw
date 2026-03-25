from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

from platform.ledger._common import REPO_ROOT, load_module_from_repo

from .budgets import WorkflowBudget, load_workflow_policy


WATCHDOG_POLL_INTERVAL_SECONDS = 10
STALE_JOB_SILENCE_THRESHOLD_SECONDS = 90
WATCHDOG_REPEAT_ACTION_THRESHOLD = 3
WATCHDOG_REPEAT_ACTION_WINDOW_SECONDS = 600
WATCHDOG_HEARTBEAT_SUBJECT = "platform.watchdog.heartbeat"
WATCHDOG_REPEATED_ACTION_SUBJECT = "platform.findings.watchdog_repeated_action"
STALE_JOB_ABORTED_SUBJECT = "platform.watchdog.stale_job_aborted"
BUDGET_EXCEEDED_SUBJECT = "scheduler.budget_exceeded"


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _maybe_parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_timestamp(value)
    except ValueError:
        return None


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


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
        self._path = path or self._default_path()

    @staticmethod
    def _default_path() -> Path:
        override = os.environ.get("LV3_SCHEDULER_STATE_PATH", "").strip()
        if override:
            return Path(override).expanduser()
        session_root = os.environ.get("LV3_SESSION_LOCAL_ROOT", "").strip()
        if session_root:
            return Path(session_root).expanduser() / "scheduler" / "active-jobs.json"
        return REPO_ROOT / ".local" / "scheduler" / "active-jobs.json"

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
        _write_json(self._path, payload)


class WatchdogActionStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (REPO_ROOT / ".local" / "scheduler" / "watchdog-actions.json")

    def record(self, action_type: str, *, occurred_at: datetime, retention_seconds: int) -> int:
        payload = self._read()
        actions = []
        cutoff = occurred_at - timedelta(seconds=max(retention_seconds, WATCHDOG_REPEAT_ACTION_WINDOW_SECONDS))
        for entry in payload.get("actions", []):
            if not isinstance(entry, dict):
                continue
            parsed = _maybe_parse_timestamp(entry.get("occurred_at"))
            if parsed is None or parsed < cutoff:
                continue
            actions.append(
                {
                    "action_type": str(entry.get("action_type", "")),
                    "occurred_at": parsed.isoformat(),
                }
            )
        actions.append({"action_type": action_type, "occurred_at": occurred_at.isoformat()})
        self._write({"actions": actions})
        window_cutoff = occurred_at - timedelta(seconds=WATCHDOG_REPEAT_ACTION_WINDOW_SECONDS)
        return sum(
            1
            for entry in actions
            if entry["action_type"] == action_type and _parse_timestamp(entry["occurred_at"]) >= window_cutoff
        )

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"actions": []}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"actions": []}

    def _write(self, payload: dict[str, Any]) -> None:
        _write_json(self._path, payload)


class Watchdog:
    def __init__(
        self,
        *,
        windmill_client: Any,
        state_store: SchedulerStateStore,
        ledger_writer: Any | None = None,
        conflict_registry: Any | None = None,
        lane_registry: Any | None = None,
        lane_budget_store: Any | None = None,
        idempotency_store: Any | None = None,
        escalation_handler: Callable[[str, dict[str, Any]], None] | None = _default_escalation_handler,
        advisory_host_limit: bool = True,
        repo_root: Path | None = None,
        heartbeat_path: Path | None = None,
        action_store: WatchdogActionStore | None = None,
        poll_interval_seconds: int = WATCHDOG_POLL_INTERVAL_SECONDS,
        stale_job_silence_threshold_seconds: int = STALE_JOB_SILENCE_THRESHOLD_SECONDS,
        repeated_action_threshold: int = WATCHDOG_REPEAT_ACTION_THRESHOLD,
        repeated_action_window_seconds: int = WATCHDOG_REPEAT_ACTION_WINDOW_SECONDS,
    ) -> None:
        self._windmill_client = windmill_client
        self._state_store = state_store
        self._ledger_writer = ledger_writer
        self._conflict_registry = conflict_registry
        self._lane_registry = lane_registry
        self._lane_budget_store = lane_budget_store
        self._idempotency_store = idempotency_store
        self._escalation_handler = escalation_handler
        self._advisory_host_limit = advisory_host_limit
        self._repo_root = repo_root or REPO_ROOT
        self._heartbeat_path = heartbeat_path or (self._repo_root / ".local" / "scheduler" / "watchdog-heartbeat.json")
        self._action_store = action_store or WatchdogActionStore(
            self._repo_root / ".local" / "scheduler" / "watchdog-actions.json"
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._stale_job_silence_threshold_seconds = stale_job_silence_threshold_seconds
        self._repeated_action_threshold = repeated_action_threshold
        self._repeated_action_window_seconds = repeated_action_window_seconds

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
        state = str(status.get("status") or status.get("job_status") or status.get("state") or "").lower()
        return state in {"cancelled", "canceled", "completed", "failed", "success"}

    @staticmethod
    def is_running(status: dict[str, Any]) -> bool:
        if status.get("running") is True:
            return True
        state = str(status.get("status") or status.get("job_status") or status.get("state") or "").lower()
        if state in {"queued", "waiting", "pending", "scheduled"}:
            return False
        if state in {"running", "started", "in_progress"}:
            return True
        return not Watchdog.is_terminal(status) and bool(status.get("started_at"))

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

    @staticmethod
    def extract_last_activity_at(status: dict[str, Any], *, fallback_started_at: str | None = None) -> datetime | None:
        candidates: list[datetime] = []
        for key in (
            "last_log_at",
            "last_log_timestamp",
            "last_output_at",
            "updated_at",
            "last_updated_at",
            "last_progress_at",
            "last_ping",
            "started_at",
        ):
            parsed = _maybe_parse_timestamp(status.get(key))
            if parsed is not None:
                candidates.append(parsed)

        flow_status = status.get("flow_status")
        if isinstance(flow_status, dict):
            for key in ("updated_at", "started_at", "last_progress_at"):
                parsed = _maybe_parse_timestamp(flow_status.get(key))
                if parsed is not None:
                    candidates.append(parsed)
            modules = flow_status.get("modules")
            if isinstance(modules, list):
                for module in modules:
                    if not isinstance(module, dict):
                        continue
                    for key in ("updated_at", "started_at", "ended_at"):
                        parsed = _maybe_parse_timestamp(module.get(key))
                        if parsed is not None:
                            candidates.append(parsed)

        if fallback_started_at:
            parsed = _maybe_parse_timestamp(fallback_started_at)
            if parsed is not None:
                candidates.append(parsed)
        return max(candidates) if candidates else None

    def _normalize_workflow_candidates(self, workflow_path: str) -> list[str]:
        candidates = [workflow_path]
        if workflow_path.startswith("f/"):
            trimmed = workflow_path.split("/", 2)[-1]
            candidates.append(trimmed)
            candidates.append(trimmed.replace("_", "-"))
        else:
            candidates.append(workflow_path.replace("_", "-"))
        ordered: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    def _policy_for_workflow_path(self, workflow_path: str) -> tuple[str, WorkflowBudget, str] | None:
        for candidate in self._normalize_workflow_candidates(workflow_path):
            try:
                policy = load_workflow_policy(candidate, repo_root=self._repo_root)
            except KeyError:
                continue
            return candidate, policy.budget, policy.execution_class
        return None

    def _build_discovered_job_record(self, payload: dict[str, Any]) -> ActiveJobRecord | None:
        job_id = payload.get("job_id") or payload.get("id")
        started_at = payload.get("started_at") or payload.get("created_at")
        workflow_path = payload.get("script_path") or payload.get("scriptPath") or payload.get("path")
        if not isinstance(job_id, str) or not job_id.strip():
            return None
        if not isinstance(workflow_path, str) or not workflow_path.strip():
            return None
        if not isinstance(started_at, str) or not started_at.strip():
            return None

        policy = self._policy_for_workflow_path(workflow_path)
        if policy is None:
            return None
        workflow_id, budget, execution_class = policy
        if execution_class != "mutation":
            return None

        arguments = payload.get("args")
        if not isinstance(arguments, dict):
            arguments = payload.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        actor_intent_id = str(arguments.get("actor_intent_id") or payload.get("tag") or f"windmill:{job_id}")
        return ActiveJobRecord(
            job_id=str(job_id),
            workflow_id=workflow_id,
            actor_intent_id=actor_intent_id,
            requested_by=str(payload.get("created_by") or arguments.get("requested_by") or "operator:unknown"),
            execution_class=execution_class,
            started_at=started_at,
            budget=budget,
            parent_actor_intent_id=arguments.get("parent_actor_intent_id"),
            metadata={
                "discovered_by": "windmill.list_jobs",
                "script_path": workflow_path,
            },
        )

    def discover_active_jobs(self) -> list[ActiveJobRecord]:
        list_jobs = getattr(self._windmill_client, "list_jobs", None)
        if not callable(list_jobs):
            return []
        try:
            payload = list_jobs(running=True)
        except Exception:
            return []
        jobs = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            record = self._build_discovered_job_record(item)
            if record is not None:
                jobs.append(record)
        return jobs

    def list_monitored_jobs(self) -> list[ActiveJobRecord]:
        jobs_by_id: dict[str, ActiveJobRecord] = {
            record.job_id: record for record in self.discover_active_jobs()
        }
        for record in self._state_store.list_active_jobs():
            discovered = jobs_by_id.get(record.job_id)
            if discovered is None:
                jobs_by_id[record.job_id] = record
                continue
            merged_metadata = {**discovered.metadata, **record.metadata}
            jobs_by_id[record.job_id] = ActiveJobRecord(
                job_id=record.job_id,
                workflow_id=record.workflow_id or discovered.workflow_id,
                actor_intent_id=record.actor_intent_id or discovered.actor_intent_id,
                requested_by=record.requested_by or discovered.requested_by,
                execution_class=record.execution_class or discovered.execution_class,
                started_at=record.started_at or discovered.started_at,
                budget=record.budget or discovered.budget,
                parent_actor_intent_id=record.parent_actor_intent_id or discovered.parent_actor_intent_id,
                metadata=merged_metadata,
            )
        return sorted(jobs_by_id.values(), key=lambda item: item.job_id)

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

        if self.is_running(status):
            last_activity = self.extract_last_activity_at(status, fallback_started_at=job.started_at)
            if last_activity is not None:
                silence_seconds = max(0.0, (current_time - last_activity).total_seconds())
                if silence_seconds > self._stale_job_silence_threshold_seconds:
                    return WatchdogViolation(
                        reason="stale_job_silence",
                        observed=round(silence_seconds, 2),
                        limit=self._stale_job_silence_threshold_seconds,
                        message=(
                            f"workflow {job.workflow_id} appears stale "
                            f"({silence_seconds:.1f}s since the last observed activity)"
                        ),
                    )
        return None

    def _record_action(self, action_type: str, *, occurred_at: datetime) -> int:
        return self._action_store.record(
            action_type,
            occurred_at=occurred_at,
            retention_seconds=self._repeated_action_window_seconds,
        )

    def _maybe_emit_repeated_action(self, action_type: str, *, count: int, payload: dict[str, Any]) -> None:
        if count < self._repeated_action_threshold or self._escalation_handler is None:
            return
        self._escalation_handler(
            WATCHDOG_REPEATED_ACTION_SUBJECT,
            {
                "action_type": action_type,
                "count_in_window": count,
                "window_seconds": self._repeated_action_window_seconds,
                "threshold": self._repeated_action_threshold,
                "severity": "medium",
                "last_payload": payload,
            },
        )

    def _emit_heartbeat(self, summary: dict[str, Any]) -> None:
        heartbeat = {
            "checked_at": summary["checked_at"],
            "active_jobs": summary["active_jobs"],
            "completed_jobs": summary["completed_jobs"],
            "violation_count": len(summary["violations"]),
            "warning_count": len(summary["warnings"]),
            "poll_interval_seconds": self._poll_interval_seconds,
        }
        _write_json(self._heartbeat_path, heartbeat)
        if self._escalation_handler is not None:
            self._escalation_handler(WATCHDOG_HEARTBEAT_SUBJECT, heartbeat)
        summary["heartbeat_file"] = str(self._heartbeat_path)

    def handle_terminal(self, job: ActiveJobRecord, status: dict[str, Any]) -> dict[str, Any]:
        self._state_store.remove(job.job_id)
        if self._conflict_registry is not None:
            final_status = "completed"
            if status.get("canceled") is True:
                final_status = "aborted"
            elif status.get("success") is False:
                final_status = "failed"
            self._conflict_registry.complete_intent(job.actor_intent_id, status=final_status, output=status.get("result"))
        if self._lane_registry is not None:
            self._lane_registry.release(job.actor_intent_id)
        if self._lane_budget_store is not None:
            self._lane_budget_store.release(job.actor_intent_id)
        if self._idempotency_store is not None:
            record = self._idempotency_store.record_for_intent(job.actor_intent_id)
            if record is not None:
                self._idempotency_store.complete(
                    record.idempotency_key,
                    status=final_status,
                    result=status.get("result"),
                    job_id=job.job_id,
                )
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
        *,
        now: datetime,
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
            "requested_by": job.requested_by,
            "windmill_status": status,
        }
        if violation.advisory_only:
            return payload

        self._windmill_client.cancel_job(job.job_id, reason=violation.message)
        self._state_store.remove(job.job_id)
        if self._conflict_registry is not None:
            self._conflict_registry.complete_intent(job.actor_intent_id, status="budget_exceeded")
        if self._lane_registry is not None:
            self._lane_registry.release(job.actor_intent_id)
        if self._lane_budget_store is not None:
            self._lane_budget_store.release(job.actor_intent_id)
        if self._idempotency_store is not None:
            record = self._idempotency_store.record_for_intent(job.actor_intent_id)
            if record is not None:
                self._idempotency_store.complete(
                    record.idempotency_key,
                    status="budget_exceeded",
                    result=status.get("result"),
                    job_id=job.job_id,
                )
        action_type = "budget_violation_aborted"
        event_type = "execution.budget_exceeded"
        subject = None
        if violation.reason == "stale_job_silence":
            action_type = "stale_job_aborted"
            event_type = "execution.stale_job_detected"
            subject = STALE_JOB_ABORTED_SUBJECT

        recent_count = self._record_action(action_type, occurred_at=now)
        payload["recent_action_count"] = recent_count
        if self._ledger_writer is not None:
            self._ledger_writer.write(
                event_type=event_type,
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

        if self._escalation_handler is not None:
            if subject is not None:
                self._escalation_handler(subject, payload)
            elif job.budget and job.budget.escalation_action != "abort_silently":
                self._escalation_handler(BUDGET_EXCEEDED_SUBJECT, payload)
            self._maybe_emit_repeated_action(action_type, count=recent_count, payload=payload)
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
        for job in self.list_monitored_jobs():
            summary["active_jobs"] += 1
            lane_reservation_ttl = job.metadata.get("lane_reservation_ttl_seconds")
            if self._lane_budget_store is not None and isinstance(lane_reservation_ttl, int) and lane_reservation_ttl > 0:
                self._lane_budget_store.renew(job.actor_intent_id, ttl_seconds=lane_reservation_ttl, now=current_time)
            try:
                status = self._windmill_client.get_job(job.job_id)
            except Exception as exc:
                summary["warnings"].append(
                    {
                        "job_id": job.job_id,
                        "workflow_id": job.workflow_id,
                        "reason": "status_query_failed",
                        "message": f"failed to query Windmill job state: {exc}",
                    }
                )
                continue
            if self.is_terminal(status):
                self.handle_terminal(job, status)
                summary["completed_jobs"] += 1
                continue
            violation = self.evaluate(job, status, now=current_time)
            if violation is None:
                continue
            payload = self.handle_violation(job, status, violation, now=current_time)
            target = "warnings" if violation.advisory_only else "violations"
            summary[target].append(payload)
        self._emit_heartbeat(summary)
        return summary
