from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from platform.agent_policy import AgentPolicyEngine, DailyExecutionCounter, PolicyOutcome, normalize_actor_id
from platform.conflict import IntentConflictRegistry
from platform.goal_compiler.schema import RiskClass
from platform.ledger import LedgerReader, LedgerWriter
from platform.retry import policy_for_surface, with_retry

from .budgets import HostTouchEstimate, WorkflowPolicy, estimate_touched_hosts, load_workflow_policy
from .rollback_guard import RollbackGuard
from .speculative import (
    ConflictProbeResult,
    SpeculativeExecutionRecord,
    SpeculativeStateStore,
    build_compensating_arguments,
    run_conflict_probe,
)
from .watchdog import ActiveJobRecord, SchedulerStateStore, Watchdog


REPO_ROOT = Path(__file__).resolve().parents[2]


class WindmillClient(Protocol):
    def submit_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        ...

    def get_job(self, job_id: str) -> dict[str, Any]:
        ...

    def list_jobs(self, *, running: bool | None = None) -> list[dict[str, Any]]:
        ...

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any] | None:
        ...


@dataclass
class LockToken:
    slot_index: int
    release_fn: Any

    def release(self) -> None:
        self.release_fn()


class ConcurrencyLockManager(Protocol):
    def acquire(self, workflow_id: str, *, max_instances: int) -> LockToken | None:
        ...


class FileConcurrencyLockManager:
    def __init__(self, lock_dir: Path | None = None) -> None:
        self._lock_dir = lock_dir or (REPO_ROOT / ".local" / "scheduler" / "locks")

    def acquire(self, workflow_id: str, *, max_instances: int) -> LockToken | None:
        import fcntl

        self._lock_dir.mkdir(parents=True, exist_ok=True)
        slug = workflow_id.replace("/", "_")
        for slot_index in range(max_instances):
            path = self._lock_dir / f"{slug}.{slot_index}.lock"
            handle = path.open("a+", encoding="utf-8")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue

            def release(handle=handle) -> None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()

            return LockToken(slot_index=slot_index, release_fn=release)
        return None


class PostgresAdvisoryLockManager:
    def __init__(self, dsn: str, *, connect: Any | None = None) -> None:
        self._dsn = dsn
        self._connect = connect

    @staticmethod
    def _lock_key(workflow_id: str, slot_index: int) -> int:
        digest = hashlib.blake2b(f"{workflow_id}:{slot_index}".encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=True)

    def _connector(self) -> Any:
        if self._connect is not None:
            return self._connect
        import psycopg2  # type: ignore

        return psycopg2.connect

    def acquire(self, workflow_id: str, *, max_instances: int) -> LockToken | None:
        connect = self._connector()
        for slot_index in range(max_instances):
            connection = connect(self._dsn)
            connection.autocommit = False
            try:
                with connection.cursor() as cursor:
                    cursor.execute("BEGIN")
                    cursor.execute(
                        "SELECT pg_try_advisory_xact_lock(%s)",
                        (self._lock_key(workflow_id, slot_index),),
                    )
                    row = cursor.fetchone()
                if row and bool(row[0]):
                    def release(connection=connection) -> None:
                        try:
                            connection.commit()
                        finally:
                            connection.close()

                    return LockToken(slot_index=slot_index, release_fn=release)
            except Exception:
                connection.rollback()
                connection.close()
                raise
            connection.rollback()
            connection.close()
        return None


@dataclass(frozen=True)
class SchedulerResult:
    status: str
    workflow_id: str
    job_id: str | None = None
    actor_intent_id: str | None = None
    output: Any = None
    reason: str | None = None
    budget: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HttpWindmillClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        workspace: str = "lv3",
        request_timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._workspace = workspace
        self._request_timeout_seconds = request_timeout_seconds
        self._internal_api_retry_policy = policy_for_surface("internal_api")

    def _request(
        self,
        path: str,
        *,
        method: str,
        payload: Any | None = None,
        timeout: float | None = None,
        retry: bool = True,
    ) -> Any:
        data = None
        headers = {"Authorization": f"Bearer {self._token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        open_request = lambda: urllib.request.urlopen(
            request,
            timeout=timeout or self._request_timeout_seconds,
        )
        response_cm = (
            with_retry(
                open_request,
                policy=self._internal_api_retry_policy,
                error_context=f"windmill {method} {path}",
            )
            if retry
            else open_request()
        )
        with response_cm as response:
            body = response.read().decode("utf-8")
        if not body.strip():
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    def submit_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        script_path = workflow_id if "/" in workflow_id else f"f/{self._workspace}/{workflow_id}"
        encoded_path = urllib.parse.quote(script_path, safe="")
        try:
            response = self._request(
                f"/api/w/{self._workspace}/jobs/run/p/{encoded_path}",
                method="POST",
                payload=arguments,
                retry=False,
            )
            if isinstance(response, str):
                return {"job_id": response, "running": True}
            if isinstance(response, dict):
                if "job_id" in response or "id" in response:
                    return {"job_id": str(response.get("job_id") or response.get("id")), **response}
                return response
            raise RuntimeError(f"unexpected Windmill submit response: {response!r}")
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 405}:
                raise

        response = self._request(
            f"/api/w/{self._workspace}/jobs/run_wait_result/p/{encoded_path}",
            method="POST",
            payload=arguments,
            timeout=timeout_seconds or self._request_timeout_seconds,
            retry=False,
        )
        return {
            "completed": True,
            "success": True,
            "result": response,
            "mode": "sync_fallback",
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        response = self._request(
            f"/api/w/{self._workspace}/jobs_u/get/{urllib.parse.quote(job_id, safe='')}",
            method="GET",
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"unexpected Windmill job response: {response!r}")
        return response

    def list_jobs(self, *, running: bool | None = None) -> list[dict[str, Any]]:
        query: dict[str, str] = {}
        if running is not None:
            query["running"] = "true" if running else "false"
        path = f"/api/w/{self._workspace}/jobs/list"
        if query:
            path = f"{path}?{urllib.parse.urlencode(query)}"
        response = self._request(path, method="GET")
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        if isinstance(response, dict):
            for key in ("jobs", "items", "results", "data"):
                value = response.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        raise RuntimeError(f"unexpected Windmill jobs response: {response!r}")

    def cancel_job(self, job_id: str, *, reason: str | None = None) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(job_id, safe="")
        payload = {"reason": reason} if reason else None
        for path in (
            f"/api/w/{self._workspace}/jobs_u/cancel/{encoded}",
            f"/api/w/{self._workspace}/jobs_u/queue/cancel/{encoded}",
            f"/api/w/{self._workspace}/jobs_u/force_cancel/{encoded}",
            f"/api/w/{self._workspace}/jobs_u/queue/force_cancel/{encoded}",
        ):
            try:
                response = self._request(path, method="POST", payload=payload)
                return response if isinstance(response, dict) else {"response": response}
            except urllib.error.HTTPError as exc:
                if exc.code in {404, 405}:
                    continue
                raise
        return None


class BudgetedWorkflowScheduler:
    def __init__(
        self,
        *,
        windmill_client: WindmillClient,
        repo_root: Path | None = None,
        lock_manager: ConcurrencyLockManager | None = None,
        ledger_writer: LedgerWriter | None = None,
        ledger_reader: LedgerReader | None = None,
        state_store: SchedulerStateStore | None = None,
        rollback_guard: RollbackGuard | None = None,
        watchdog: Watchdog | None = None,
        daily_execution_counter: DailyExecutionCounter | None = None,
        conflict_registry: IntentConflictRegistry | None = None,
        speculative_state_store: SpeculativeStateStore | None = None,
        poll_interval_seconds: float = 2.0,
        sleep_fn: Any = time.sleep,
    ) -> None:
        self._repo_root = repo_root or REPO_ROOT
        self._windmill_client = windmill_client
        self._state_store = state_store or SchedulerStateStore()
        self._ledger_writer = ledger_writer
        self._ledger_reader = ledger_reader
        self._rollback_guard = rollback_guard or RollbackGuard(ledger_reader)
        self._watchdog = watchdog or Watchdog(
            windmill_client=windmill_client,
            state_store=self._state_store,
            ledger_writer=ledger_writer,
        )
        self._policy_engine = AgentPolicyEngine(self._repo_root)
        self._daily_execution_counter = daily_execution_counter or DailyExecutionCounter(
            self._repo_root / ".local" / "state" / "agent-policy" / "daily-autonomous-executions.json"
        )
        self._conflict_registry = conflict_registry or IntentConflictRegistry(repo_root=self._repo_root)
        self._speculative_state_store = speculative_state_store or SpeculativeStateStore(
            self._repo_root / ".local" / "scheduler" / "speculative-executions.json"
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep_fn
        if lock_manager is not None:
            self._lock_manager = lock_manager
        else:
            dsn = os.environ.get("LV3_LEDGER_DSN", "").strip()
            self._lock_manager = PostgresAdvisoryLockManager(dsn) if dsn else FileConcurrencyLockManager()

    @staticmethod
    def _parent_actor_intent_id(arguments: dict[str, Any]) -> str | None:
        for key in ("parent_actor_intent_id", "rollback_parent_intent_id", "actor_intent_id"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _resolve_actor_intent_id(intent: Any) -> str:
        for key in ("actor_intent_id", "intent_id", "id"):
            value = getattr(intent, key, None)
            if isinstance(value, str) and value.strip():
                return value
        return str(uuid.uuid4())

    def _write_claim_registered_event(
        self,
        *,
        policy: WorkflowPolicy,
        actor_intent_id: str,
        requested_by: str,
        resource_claims: list[dict[str, str]],
        warnings: list[dict[str, Any]],
    ) -> None:
        if self._ledger_writer is None:
            return
        self._ledger_writer.write(
            event_type="intent.claim_registered",
            actor=requested_by,
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            metadata={
                "resource_claims": resource_claims,
                "conflict_warnings": warnings,
            },
        )

    def _write_conflict_rejected_event(
        self,
        *,
        policy: WorkflowPolicy,
        actor_intent_id: str,
        requested_by: str,
        result: Any,
    ) -> None:
        if self._ledger_writer is None:
            return
        self._ledger_writer.write(
            event_type="intent.rejected",
            actor=requested_by,
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            metadata={
                "reason": "conflict_rejected",
                "conflicting_intent_id": result.conflicting_intent_id,
                "conflicting_actor": result.conflicting_actor,
                "conflict_type": result.conflict_type,
                "message": result.message,
                "resource_claims": [claim.as_dict() for claim in result.resource_claims],
                "conflict_warnings": [warning.as_dict() for warning in result.warnings],
            },
        )

    def _write_deduplicated_event(
        self,
        *,
        policy: WorkflowPolicy,
        actor_intent_id: str,
        requested_by: str,
        result: Any,
    ) -> None:
        if self._ledger_writer is None:
            return
        self._ledger_writer.write(
            event_type="intent.deduplicated",
            actor=requested_by,
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            metadata={
                "existing_intent_id": result.conflicting_intent_id,
                "existing_actor": result.conflicting_actor,
                "resource_claims": [claim.as_dict() for claim in result.resource_claims],
            },
            receipt=result.dedup_output,
        )

    @staticmethod
    def _is_rollback(workflow_id: str, arguments: dict[str, Any]) -> bool:
        if "rollback" in workflow_id.lower():
            return True
        for key in ("rollback", "rollback_of", "parent_actor_intent_id", "rollback_parent_intent_id"):
            if key in arguments:
                return True
        return False

    def _write_started_event(
        self,
        *,
        policy: WorkflowPolicy,
        requested_by: str,
        actor_intent_id: str,
        parent_actor_intent_id: str | None,
        job_id: str | None,
        host_touch_estimate: HostTouchEstimate,
        execution_mode: str = "pessimistic",
    ) -> None:
        if self._ledger_writer is None:
            return
        metadata = {
            "requested_by": requested_by,
            "job_id": job_id,
            "budget": policy.budget.as_dict(),
            "execution_class": policy.execution_class,
            "host_touch_estimate": host_touch_estimate.as_dict(),
            "execution_mode": execution_mode,
        }
        if parent_actor_intent_id:
            metadata["parent_actor_intent_id"] = parent_actor_intent_id
        self._ledger_writer.write(
            event_type="execution.started",
            actor="scheduler:budgeted-workflow-scheduler",
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            metadata=metadata,
        )
        if execution_mode == "speculative":
            self._ledger_writer.write(
                event_type="execution.speculative_started",
                actor="scheduler:budgeted-workflow-scheduler",
                actor_intent_id=actor_intent_id,
                target_kind="workflow",
                target_id=policy.workflow_id,
                metadata=metadata,
            )

    def _write_policy_decision_event(
        self,
        *,
        status: str,
        policy: WorkflowPolicy,
        requested_by: str,
        actor_intent_id: str,
        metadata: dict[str, Any],
    ) -> None:
        if self._ledger_writer is None:
            return
        event_type = "execution.escalated" if status == "capability_escalated" else "execution.rejected"
        self._ledger_writer.write(
            event_type=event_type,
            actor="scheduler:budgeted-workflow-scheduler",
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            metadata={"requested_by": requested_by, **metadata},
        )

    @staticmethod
    def _risk_class_for_submission(intent: Any, policy: WorkflowPolicy) -> RiskClass:
        for attr in ("final_risk_class", "risk_class"):
            value = getattr(intent, attr, None)
            if isinstance(value, RiskClass):
                return value
            if isinstance(value, str) and value.strip():
                return RiskClass(value.strip())
        mapping = {
            "repo_only": RiskClass.LOW,
            "guest_live": RiskClass.MEDIUM,
            "external_live": RiskClass.MEDIUM,
            "host_live": RiskClass.HIGH,
            "host_and_guest_live": RiskClass.HIGH,
        }
        return mapping.get(policy.live_impact, RiskClass.MEDIUM)

    @staticmethod
    def _required_read_surfaces(intent: Any) -> list[str]:
        value = getattr(intent, "required_read_surfaces", [])
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]

    @staticmethod
    def _speculative_requested(intent: Any, policy: WorkflowPolicy) -> bool:
        if not policy.speculative.eligible or policy.execution_class != "mutation":
            return False
        execution_mode = getattr(intent, "execution_mode", None)
        if isinstance(execution_mode, str) and execution_mode.strip() == "speculative":
            return True
        arguments = getattr(intent, "arguments", {}) or {}
        if not isinstance(arguments, dict):
            return False
        if arguments.get("execution_mode") == "speculative":
            return True
        return bool(arguments.get("allow_speculative"))

    @staticmethod
    def _terminal_status(payload: dict[str, Any]) -> str:
        if payload.get("canceled") is True:
            return "aborted"
        if payload.get("success") is False:
            return "failed"
        return "completed"

    def _write_execution_terminal_event(
        self,
        *,
        event_type: str,
        actor_intent_id: str,
        workflow_id: str,
        actor: str = "scheduler:budgeted-workflow-scheduler",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._ledger_writer is None:
            return
        self._ledger_writer.write(
            event_type=event_type,
            actor=actor,
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=workflow_id,
            metadata=dict(metadata or {}),
        )

    def _run_probe(
        self,
        *,
        policy: WorkflowPolicy,
        actor_intent_id: str,
        job_id: str | None,
        requested_by: str,
        arguments: dict[str, Any],
        conflict_result: Any,
    ) -> ConflictProbeResult:
        probe_due_at = datetime.now(UTC).isoformat()
        self._speculative_state_store.upsert(
            SpeculativeExecutionRecord(
                actor_intent_id=actor_intent_id,
                workflow_id=policy.workflow_id,
                status="probing",
                probe_due_at=probe_due_at,
                updated_at=probe_due_at,
                job_id=job_id,
                conflict_with=getattr(conflict_result, "conflicting_intent_id", None),
                compensating_workflow_id=policy.speculative.compensating_workflow_id,
                metadata={
                    "requested_by": requested_by,
                    "resource_claims": [
                        claim.as_dict() for claim in getattr(conflict_result, "resource_claims", [])
                    ],
                },
            )
        )
        self._write_execution_terminal_event(
            event_type="execution.speculative_probing",
            actor_intent_id=actor_intent_id,
            workflow_id=policy.workflow_id,
            metadata={"job_id": job_id, "probe_due_at": probe_due_at},
        )
        if policy.speculative.probe_delay_seconds > 0:
            self._sleep(policy.speculative.probe_delay_seconds)
        return run_conflict_probe(
            repo_root=self._repo_root,
            probe_spec=policy.speculative.conflict_probe or {},
            context={
                "workflow_id": policy.workflow_id,
                "actor_intent_id": actor_intent_id,
                "job_id": job_id,
                "arguments": dict(arguments),
                "requested_by": requested_by,
                "resource_claims": [claim.as_dict() for claim in getattr(conflict_result, "resource_claims", [])],
                "conflicting_intent_id": getattr(conflict_result, "conflicting_intent_id", None),
            },
        )

    def _run_compensating_workflow(
        self,
        *,
        original_policy: WorkflowPolicy,
        actor_intent_id: str,
        job_id: str | None,
        arguments: dict[str, Any],
        conflict: ConflictProbeResult,
    ) -> tuple[str, str | None, Any]:
        compensating_workflow_id = original_policy.speculative.compensating_workflow_id
        if not compensating_workflow_id:
            return "failed", None, {"reason": "missing_compensating_workflow"}
        policy = load_workflow_policy(compensating_workflow_id, repo_root=self._repo_root)
        compensating_actor_intent_id = str(uuid.uuid4())
        payload = build_compensating_arguments(
            original_arguments=arguments,
            original_workflow_id=original_policy.workflow_id,
            actor_intent_id=actor_intent_id,
            job_id=job_id,
            conflict=conflict,
        )
        submission = self._windmill_client.submit_workflow(
            compensating_workflow_id,
            payload,
            timeout_seconds=policy.budget.max_duration_seconds,
        )
        compensating_job_id = submission.get("job_id")
        self._write_started_event(
            policy=policy,
            requested_by="agent/speculative-rollback",
            actor_intent_id=compensating_actor_intent_id,
            parent_actor_intent_id=actor_intent_id,
            job_id=str(compensating_job_id) if compensating_job_id else None,
            host_touch_estimate=HostTouchEstimate(count=0, advisory_only=True, source="speculative_rollback"),
        )
        if not compensating_job_id:
            status = "completed" if submission.get("success", True) else "failed"
            self._write_execution_terminal_event(
                event_type="execution.completed" if status == "completed" else "execution.failed",
                actor_intent_id=compensating_actor_intent_id,
                workflow_id=compensating_workflow_id,
                actor="scheduler:speculative-rollback",
                metadata={"windmill_submission": submission},
            )
            return status, None, submission.get("result")
        while True:
            status_payload = self._windmill_client.get_job(str(compensating_job_id))
            if status_payload.get("completed") or status_payload.get("success") is not None or status_payload.get("canceled") is True:
                status = self._terminal_status(status_payload)
                self._write_execution_terminal_event(
                    event_type=(
                        "execution.completed"
                        if status == "completed"
                        else "execution.aborted" if status == "aborted" else "execution.failed"
                    ),
                    actor_intent_id=compensating_actor_intent_id,
                    workflow_id=compensating_workflow_id,
                    actor="scheduler:speculative-rollback",
                    metadata={"windmill_status": status_payload, "parent_actor_intent_id": actor_intent_id},
                )
                return status, str(compensating_job_id), status_payload.get("result")
            self._sleep(self._poll_interval_seconds)

    def submit(
        self,
        intent: Any,
        *,
        requested_by: str = "operator:lv3-cli",
        autonomous: bool = False,
    ) -> SchedulerResult:
        policy = load_workflow_policy(intent.workflow_id, repo_root=self._repo_root)
        requested_by = normalize_actor_id(requested_by)
        actor_intent_id = self._resolve_actor_intent_id(intent)
        parent_actor_intent_id = self._parent_actor_intent_id(getattr(intent, "arguments", {}) or {})
        host_touch_estimate = estimate_touched_hosts(intent, policy)
        risk_class = self._risk_class_for_submission(intent, policy)
        current_daily_executions = self._daily_execution_counter.get(requested_by) if autonomous else None

        try:
            decision = self._policy_engine.evaluate(
                actor_id=requested_by,
                workflow_id=policy.workflow_id,
                risk_class=risk_class,
                required_read_surfaces=self._required_read_surfaces(intent),
                autonomous=autonomous,
                current_daily_executions=current_daily_executions,
            )
        except KeyError as exc:
            metadata = {"reason": "actor_policy_missing", "actor_id": requested_by, "error": str(exc)}
            self._write_policy_decision_event(
                status="capability_denied",
                policy=policy,
                requested_by=requested_by,
                actor_intent_id=actor_intent_id,
                metadata=metadata,
            )
            return SchedulerResult(
                status="capability_denied",
                workflow_id=policy.workflow_id,
                actor_intent_id=actor_intent_id,
                reason="actor_policy_missing",
                budget=policy.budget.as_dict(),
                metadata=metadata,
            )

        if decision.outcome != PolicyOutcome.ALLOW:
            status = "capability_escalated" if decision.outcome == PolicyOutcome.ESCALATE else "capability_denied"
            if decision.reason == "daily_autonomous_limit_reached":
                status = "autonomy_limit_reached"
            metadata = decision.as_dict()
            self._write_policy_decision_event(
                status=status,
                policy=policy,
                requested_by=requested_by,
                actor_intent_id=actor_intent_id,
                metadata=metadata,
            )
            return SchedulerResult(
                status=status,
                workflow_id=policy.workflow_id,
                actor_intent_id=actor_intent_id,
                reason=decision.reason,
                budget=policy.budget.as_dict(),
                metadata=metadata,
            )

        if (
            policy.execution_class == "mutation"
            and host_touch_estimate.count > policy.budget.max_touched_hosts
            and not host_touch_estimate.advisory_only
        ):
            return SchedulerResult(
                status="budget_exceeded",
                workflow_id=policy.workflow_id,
                actor_intent_id=actor_intent_id,
                reason="max_touched_hosts",
                budget=policy.budget.as_dict(),
                metadata={"host_touch_estimate": host_touch_estimate.as_dict()},
            )

        if self._is_rollback(policy.workflow_id, getattr(intent, "arguments", {}) or {}) and parent_actor_intent_id:
            rollback_depth = self._rollback_guard.check_depth(
                parent_actor_intent_id,
                max_depth=policy.budget.max_rollback_depth,
            )
            if rollback_depth.exceeded:
                return SchedulerResult(
                    status="rollback_depth_exceeded",
                    workflow_id=policy.workflow_id,
                    actor_intent_id=actor_intent_id,
                    reason=rollback_depth.reason or "max_rollback_depth",
                    budget=policy.budget.as_dict(),
                    metadata={
                        "rollback_depth": rollback_depth.depth,
                        "rollback_chain": list(rollback_depth.chain),
                    },
                )

        speculative_requested = self._speculative_requested(intent, policy)
        lock_token = None
        registered_claim = False
        claim_closed = False
        if policy.execution_class == "mutation" and not speculative_requested:
            lock_token = self._lock_manager.acquire(
                policy.workflow_id,
                max_instances=policy.budget.max_concurrent_instances,
            )
            if lock_token is None:
                return SchedulerResult(
                    status="concurrency_limit",
                    workflow_id=policy.workflow_id,
                    actor_intent_id=actor_intent_id,
                    reason="workflow busy",
                    budget=policy.budget.as_dict(),
                )

        try:
            if autonomous:
                self._daily_execution_counter.increment(requested_by)
            conflict_result = self._conflict_registry.register_intent(
                intent,
                actor_intent_id=actor_intent_id,
                actor=requested_by,
                ttl_seconds=(
                    policy.budget.max_duration_seconds
                    + (policy.speculative.rollback_window_seconds if speculative_requested else 0)
                    + 60
                ),
                allow_conflicts=speculative_requested,
            )
            if conflict_result.status == "conflict":
                self._write_conflict_rejected_event(
                    policy=policy,
                    actor_intent_id=actor_intent_id,
                    requested_by=requested_by,
                    result=conflict_result,
                )
                return SchedulerResult(
                    status="conflict_rejected",
                    workflow_id=policy.workflow_id,
                    actor_intent_id=actor_intent_id,
                    reason=conflict_result.message,
                    budget=policy.budget.as_dict(),
                    metadata=conflict_result.as_dict(),
                )
            if conflict_result.status == "duplicate":
                self._write_deduplicated_event(
                    policy=policy,
                    actor_intent_id=actor_intent_id,
                    requested_by=requested_by,
                    result=conflict_result,
                )
                return SchedulerResult(
                    status="duplicate",
                    workflow_id=policy.workflow_id,
                    actor_intent_id=actor_intent_id,
                    output=conflict_result.dedup_output,
                    budget=policy.budget.as_dict(),
                    metadata=conflict_result.as_dict(),
                )
            registered_claim = True
            self._write_claim_registered_event(
                policy=policy,
                actor_intent_id=actor_intent_id,
                requested_by=requested_by,
                resource_claims=[claim.as_dict() for claim in conflict_result.resource_claims],
                warnings=[warning.as_dict() for warning in conflict_result.warnings],
            )
            if speculative_requested and conflict_result.status == "speculative":
                self._speculative_state_store.upsert(
                    SpeculativeExecutionRecord(
                        actor_intent_id=actor_intent_id,
                        workflow_id=policy.workflow_id,
                        status="executing",
                        probe_due_at=datetime.now(UTC).isoformat(),
                        updated_at=datetime.now(UTC).isoformat(),
                        conflict_with=conflict_result.conflicting_intent_id,
                        compensating_workflow_id=policy.speculative.compensating_workflow_id,
                        metadata={"requested_by": requested_by},
                    )
                )
            submission = self._windmill_client.submit_workflow(
                policy.workflow_id,
                getattr(intent, "arguments", {}) or {},
                timeout_seconds=policy.budget.max_duration_seconds if policy.execution_class == "mutation" else None,
            )
            job_id = submission.get("job_id")
            self._write_started_event(
                policy=policy,
                requested_by=requested_by,
                actor_intent_id=actor_intent_id,
                parent_actor_intent_id=parent_actor_intent_id,
                job_id=str(job_id) if job_id else None,
                host_touch_estimate=host_touch_estimate,
                execution_mode="speculative" if speculative_requested else "pessimistic",
            )

            if not job_id:
                status = "completed" if submission.get("success", True) else "failed"
                if status != "completed" or not speculative_requested:
                    self._write_execution_terminal_event(
                        event_type="execution.completed" if status == "completed" else "execution.failed",
                        actor_intent_id=actor_intent_id,
                        workflow_id=policy.workflow_id,
                        metadata={"windmill_submission": submission},
                    )
                    if registered_claim:
                        self._conflict_registry.complete_intent(
                            actor_intent_id,
                            status=status,
                            output=submission.get("result"),
                        )
                        claim_closed = True
                else:
                    probe_result = self._run_probe(
                        policy=policy,
                        actor_intent_id=actor_intent_id,
                        job_id=None,
                        requested_by=requested_by,
                        arguments=getattr(intent, "arguments", {}) or {},
                        conflict_result=conflict_result,
                    )
                    if not probe_result.conflict_detected or probe_result.winning_intent_id in {None, actor_intent_id}:
                        self._speculative_state_store.mark_status(
                            actor_intent_id,
                            status="committed",
                            metadata=probe_result.as_dict(),
                        )
                        self._write_execution_terminal_event(
                            event_type="execution.completed",
                            actor_intent_id=actor_intent_id,
                            workflow_id=policy.workflow_id,
                            metadata={
                                "windmill_submission": submission,
                                "execution_mode": "speculative",
                            },
                        )
                        self._write_execution_terminal_event(
                            event_type="execution.speculative_committed",
                            actor_intent_id=actor_intent_id,
                            workflow_id=policy.workflow_id,
                            metadata=probe_result.as_dict(),
                        )
                        if registered_claim:
                            self._conflict_registry.complete_intent(
                                actor_intent_id,
                                status="completed",
                                output=submission.get("result"),
                            )
                            claim_closed = True
                        status = "completed"
                    else:
                        compensating_status, compensating_job_id, compensating_output = self._run_compensating_workflow(
                            original_policy=policy,
                            actor_intent_id=actor_intent_id,
                            job_id=None,
                            arguments=getattr(intent, "arguments", {}) or {},
                            conflict=probe_result,
                        )
                        if compensating_status == "completed":
                            self._speculative_state_store.mark_status(
                                actor_intent_id,
                                status="rolled_back",
                                conflict_with=probe_result.conflicting_intent_id,
                                compensating_workflow_id=policy.speculative.compensating_workflow_id,
                                compensating_job_id=compensating_job_id,
                                metadata=probe_result.as_dict(),
                            )
                            self._write_execution_terminal_event(
                                event_type="execution.speculative_rolled_back",
                                actor_intent_id=actor_intent_id,
                                workflow_id=policy.workflow_id,
                                metadata={
                                    **probe_result.as_dict(),
                                    "compensating_workflow_id": policy.speculative.compensating_workflow_id,
                                    "compensating_job_id": compensating_job_id,
                                },
                            )
                            if registered_claim:
                                self._conflict_registry.complete_intent(actor_intent_id, status="rolled_back")
                                claim_closed = True
                            status = "rolled_back"
                            submission["result"] = compensating_output
                        else:
                            self._speculative_state_store.mark_status(
                                actor_intent_id,
                                status="rollback_failed",
                                conflict_with=probe_result.conflicting_intent_id,
                                compensating_workflow_id=policy.speculative.compensating_workflow_id,
                                compensating_job_id=compensating_job_id,
                                metadata=probe_result.as_dict(),
                            )
                            self._write_execution_terminal_event(
                                event_type="execution.failed",
                                actor_intent_id=actor_intent_id,
                                workflow_id=policy.workflow_id,
                                metadata={
                                    **probe_result.as_dict(),
                                    "reason": "compensating_workflow_failed",
                                    "compensating_workflow_id": policy.speculative.compensating_workflow_id,
                                    "compensating_job_id": compensating_job_id,
                                },
                            )
                            if registered_claim:
                                self._conflict_registry.complete_intent(actor_intent_id, status="failed")
                                claim_closed = True
                            status = "failed"
                return SchedulerResult(
                    status=status,
                    workflow_id=policy.workflow_id,
                    actor_intent_id=actor_intent_id,
                    output=submission.get("result"),
                    budget=policy.budget.as_dict(),
                    metadata={
                        "windmill_submission": submission,
                        "conflict_warnings": [warning.as_dict() for warning in conflict_result.warnings],
                    },
                )

            active_job = ActiveJobRecord(
                job_id=str(job_id),
                workflow_id=policy.workflow_id,
                actor_intent_id=actor_intent_id,
                parent_actor_intent_id=parent_actor_intent_id,
                requested_by=requested_by,
                execution_class=policy.execution_class,
                started_at=datetime.now(UTC).isoformat(),
                budget=policy.budget if policy.execution_class == "mutation" else None,
                metadata={
                    "host_touch_estimate": host_touch_estimate.as_dict(),
                    "execution_mode": "speculative" if speculative_requested else "pessimistic",
                },
            )
            self._state_store.upsert(active_job)

            while True:
                status = self._windmill_client.get_job(str(job_id))
                violation = self._watchdog.evaluate(active_job, status)
                if violation is not None and not violation.advisory_only:
                    payload = self._watchdog.handle_violation(active_job, status, violation)
                    if registered_claim:
                        self._conflict_registry.complete_intent(actor_intent_id, status="budget_exceeded")
                        claim_closed = True
                    return SchedulerResult(
                        status="budget_exceeded",
                        workflow_id=policy.workflow_id,
                        job_id=str(job_id),
                        actor_intent_id=actor_intent_id,
                        reason=violation.reason,
                        budget=policy.budget.as_dict(),
                        metadata=payload,
                    )
                if self._watchdog.is_terminal(status):
                    self._watchdog.handle_terminal(active_job, status)
                    final_status = self._terminal_status(status)
                    if final_status == "completed" and speculative_requested:
                        probe_result = self._run_probe(
                            policy=policy,
                            actor_intent_id=actor_intent_id,
                            job_id=str(job_id),
                            requested_by=requested_by,
                            arguments=getattr(intent, "arguments", {}) or {},
                            conflict_result=conflict_result,
                        )
                        if not probe_result.conflict_detected or probe_result.winning_intent_id in {None, actor_intent_id}:
                            self._speculative_state_store.mark_status(
                                actor_intent_id,
                                status="committed",
                                metadata=probe_result.as_dict(),
                            )
                            self._write_execution_terminal_event(
                                event_type="execution.speculative_committed",
                                actor_intent_id=actor_intent_id,
                                workflow_id=policy.workflow_id,
                                metadata={**probe_result.as_dict(), "job_id": str(job_id)},
                            )
                            if registered_claim:
                                self._conflict_registry.complete_intent(
                                    actor_intent_id,
                                    status="completed",
                                    output=status.get("result"),
                                )
                                claim_closed = True
                        else:
                            compensating_status, compensating_job_id, _compensating_output = self._run_compensating_workflow(
                                original_policy=policy,
                                actor_intent_id=actor_intent_id,
                                job_id=str(job_id),
                                arguments=getattr(intent, "arguments", {}) or {},
                                conflict=probe_result,
                            )
                            if compensating_status == "completed":
                                final_status = "rolled_back"
                                self._speculative_state_store.mark_status(
                                    actor_intent_id,
                                    status="rolled_back",
                                    conflict_with=probe_result.conflicting_intent_id,
                                    compensating_workflow_id=policy.speculative.compensating_workflow_id,
                                    compensating_job_id=compensating_job_id,
                                    metadata=probe_result.as_dict(),
                                )
                                self._write_execution_terminal_event(
                                    event_type="execution.speculative_rolled_back",
                                    actor_intent_id=actor_intent_id,
                                    workflow_id=policy.workflow_id,
                                    metadata={
                                        **probe_result.as_dict(),
                                        "job_id": str(job_id),
                                        "compensating_workflow_id": policy.speculative.compensating_workflow_id,
                                        "compensating_job_id": compensating_job_id,
                                    },
                                )
                                if registered_claim:
                                    self._conflict_registry.complete_intent(actor_intent_id, status="rolled_back")
                                    claim_closed = True
                            else:
                                final_status = "failed"
                                self._speculative_state_store.mark_status(
                                    actor_intent_id,
                                    status="rollback_failed",
                                    conflict_with=probe_result.conflicting_intent_id,
                                    compensating_workflow_id=policy.speculative.compensating_workflow_id,
                                    compensating_job_id=compensating_job_id,
                                    metadata=probe_result.as_dict(),
                                )
                                self._write_execution_terminal_event(
                                    event_type="execution.failed",
                                    actor_intent_id=actor_intent_id,
                                    workflow_id=policy.workflow_id,
                                    metadata={
                                        **probe_result.as_dict(),
                                        "reason": "compensating_workflow_failed",
                                        "compensating_workflow_id": policy.speculative.compensating_workflow_id,
                                        "compensating_job_id": compensating_job_id,
                                    },
                                )
                                if registered_claim:
                                    self._conflict_registry.complete_intent(actor_intent_id, status="failed")
                                    claim_closed = True
                    else:
                        if registered_claim:
                            self._conflict_registry.complete_intent(
                                actor_intent_id,
                                status=final_status,
                                output=status.get("result"),
                            )
                            claim_closed = True
                    return SchedulerResult(
                        status=final_status,
                        workflow_id=policy.workflow_id,
                        job_id=str(job_id),
                        actor_intent_id=actor_intent_id,
                        output=status.get("result"),
                        budget=policy.budget.as_dict(),
                        metadata={
                            "windmill_status": status,
                            "conflict_warnings": [warning.as_dict() for warning in conflict_result.warnings],
                        },
                    )
                self._sleep(self._poll_interval_seconds)
        finally:
            if registered_claim and not claim_closed:
                self._conflict_registry.complete_intent(actor_intent_id, status="aborted")
            if lock_token is not None:
                lock_token.release()


def build_scheduler(
    *,
    base_url: str,
    token: str,
    workspace: str = "lv3",
    repo_root: Path | None = None,
) -> BudgetedWorkflowScheduler:
    dsn = os.environ.get("LV3_LEDGER_DSN", "").strip()
    ledger_writer = LedgerWriter(dsn=dsn) if dsn else None
    ledger_reader = LedgerReader(dsn=dsn) if dsn else None
    client = HttpWindmillClient(base_url=base_url, token=token, workspace=workspace)
    return BudgetedWorkflowScheduler(
        windmill_client=client,
        repo_root=repo_root,
        ledger_writer=ledger_writer,
        ledger_reader=ledger_reader,
    )
