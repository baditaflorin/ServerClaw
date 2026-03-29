from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol

from platform.agent_policy import AgentPolicyEngine, DailyExecutionCounter, PolicyOutcome, normalize_actor_id
from platform.circuit import CircuitRegistry, should_count_urllib_exception
from platform.conflict import IntentConflictRegistry
from platform.goal_compiler.schema import RiskClass
from platform.idempotency import IdempotencyStore, compute_idempotency_key
from platform.intent_queue import SchedulerIntentQueueStore
from platform.ledger import LedgerReader, LedgerWriter
from platform.retry import policy_for_surface, with_retry
from platform.timeouts import default_timeout, resolve_timeout_seconds

from platform.execution_lanes import LaneLease, LaneRegistry, resolve_lanes

from .budgets import HostTouchEstimate, WorkflowPolicy, estimate_touched_hosts, load_workflow_policy
from .lanes import FileLaneReservationStore, resolve_execution_lane
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
        request_timeout_seconds: float = default_timeout("http_request"),
        circuit_breaker: Any | None = None,
        circuit_registry: CircuitRegistry | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._workspace = workspace
        self._internal_api_retry_policy = policy_for_surface("internal_api")
        self._request_timeout_seconds = resolve_timeout_seconds("http_request", request_timeout_seconds)
        self._circuit_breaker = circuit_breaker
        self._session_token: str | None = None
        if self._circuit_breaker is None:
            registry = circuit_registry or CircuitRegistry(REPO_ROOT)
            if registry.has_policy("windmill"):
                self._circuit_breaker = registry.sync_breaker(
                    "windmill",
                    exception_classifier=should_count_urllib_exception,
                )

    def _login_with_bootstrap_secret(self) -> str:
        payload = json.dumps(
            {
                "email": "superadmin_secret@windmill.dev",
                "password": self._token,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/api/auth/login",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=resolve_timeout_seconds("http_request", self._request_timeout_seconds),
        ) as response:
            token = response.read().decode("utf-8").strip()
        if not token:
            raise RuntimeError("Windmill bootstrap login returned an empty session token")
        self._session_token = token
        return token

    def _request(
        self,
        path: str,
        *,
        method: str,
        payload: Any | None = None,
        timeout: float | None = None,
        retry: bool = True,
        allow_login_retry: bool = True,
    ) -> Any:
        data = None
        auth_token = self._session_token or self._token
        headers = {"Authorization": f"Bearer {auth_token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        def execute() -> str:
            open_request = lambda: urllib.request.urlopen(
                request,
                timeout=resolve_timeout_seconds("http_request", timeout or self._request_timeout_seconds),
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
                return response.read().decode("utf-8")

        if self._circuit_breaker is not None:
            try:
                body = self._circuit_breaker.call(execute)
            except urllib.error.HTTPError as exc:
                if exc.code != 401 or not allow_login_retry or self._session_token is not None:
                    raise
                self._login_with_bootstrap_secret()
                return self._request(
                    path,
                    method=method,
                    payload=payload,
                    timeout=timeout,
                    retry=retry,
                    allow_login_retry=False,
                )
        else:
            try:
                body = execute()
            except urllib.error.HTTPError as exc:
                if exc.code != 401 or not allow_login_retry or self._session_token is not None:
                    raise
                self._login_with_bootstrap_secret()
                return self._request(
                    path,
                    method=method,
                    payload=payload,
                    timeout=timeout,
                    retry=retry,
                    allow_login_retry=False,
                )
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
        script_hash = self._resolve_script_hash(script_path)
        encoded_hash = urllib.parse.quote(script_hash, safe="")
        try:
            response = self._request(
                f"/api/w/{self._workspace}/jobs/run/h/{encoded_hash}",
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
            timeout=resolve_timeout_seconds("http_request", timeout_seconds or self._request_timeout_seconds),
            retry=False,
        )
        return {
            "completed": True,
            "success": True,
            "result": response,
            "mode": "sync_fallback",
        }

    def _resolve_script_hash(self, script_path: str) -> str:
        encoded_path = urllib.parse.quote(script_path, safe="")
        response = self._request(
            f"/api/w/{self._workspace}/scripts/get/p/{encoded_path}",
            method="GET",
            retry=False,
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"unexpected Windmill script metadata response: {response!r}")
        script_hash = response.get("hash")
        if not isinstance(script_hash, str) or not script_hash.strip():
            raise RuntimeError(f"Windmill script metadata for {script_path!r} did not include a hash")
        return script_hash.strip()

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
        lane_registry: LaneRegistry | None = None,
        speculative_state_store: SpeculativeStateStore | None = None,
        lane_budget_store: FileLaneReservationStore | None = None,
        idempotency_store: IdempotencyStore | None = None,
        intent_queue_store: SchedulerIntentQueueStore | None = None,
        poll_interval_seconds: float = 2.0,
        sleep_fn: Any = time.sleep,
    ) -> None:
        self._repo_root = repo_root or REPO_ROOT
        self._windmill_client = windmill_client
        self._state_store = state_store or SchedulerStateStore()
        self._ledger_writer = ledger_writer
        self._ledger_reader = ledger_reader
        self._rollback_guard = rollback_guard or RollbackGuard(ledger_reader)
        self._policy_engine = AgentPolicyEngine(self._repo_root)
        self._daily_execution_counter = daily_execution_counter or DailyExecutionCounter(
            self._repo_root / ".local" / "state" / "agent-policy" / "daily-autonomous-executions.json"
        )
        self._conflict_registry = conflict_registry or IntentConflictRegistry(repo_root=self._repo_root)
        self._lane_registry = lane_registry or LaneRegistry(repo_root=self._repo_root)
        self._speculative_state_store = speculative_state_store or SpeculativeStateStore(
            self._repo_root / ".local" / "scheduler" / "speculative-executions.json"
        )
        self._lane_budget_store = lane_budget_store or FileLaneReservationStore(
            self._repo_root / ".local" / "scheduler" / "lane-reservations.json"
        )
        self._idempotency_store = idempotency_store or IdempotencyStore(repo_root=self._repo_root)
        self._intent_queue_store = intent_queue_store or SchedulerIntentQueueStore(repo_root=self._repo_root)
        self._watchdog = watchdog or Watchdog(
            windmill_client=windmill_client,
            state_store=self._state_store,
            ledger_writer=ledger_writer,
            conflict_registry=self._conflict_registry,
            lane_registry=self._lane_registry,
            lane_budget_store=self._lane_budget_store,
            idempotency_store=self._idempotency_store,
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
        required_lanes: list[str],
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
                "required_lanes": required_lanes,
            },
        )

    def _write_queued_event(
        self,
        *,
        policy: WorkflowPolicy,
        actor_intent_id: str,
        requested_by: str,
        queue_id: str,
        primary_lane_id: str | None = None,
        required_lanes: list[str] | None = None,
        position: int | None = None,
        reason: str | None = None,
        queued_at: str | None = None,
        expires_at: str | None = None,
        priority: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._ledger_writer is None:
            return
        payload: dict[str, Any] = {"queue_id": queue_id}
        if primary_lane_id is not None:
            payload["primary_lane_id"] = primary_lane_id
        if required_lanes is not None:
            payload["required_lanes"] = required_lanes
        if position is not None:
            payload["queue_position"] = position
        if reason is not None:
            payload["reason"] = reason
        if queued_at is not None:
            payload["queued_at"] = queued_at
        if expires_at is not None:
            payload["expires_at"] = expires_at
        if priority is not None:
            payload["priority"] = priority
        if metadata:
            payload.update(metadata)
        self._ledger_writer.write(
            event_type="intent.queued",
            actor=requested_by,
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            metadata=payload,
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
        lane_reservation: dict[str, Any] | None = None,
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
        if lane_reservation:
            metadata["lane_reservation"] = lane_reservation
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

    def _write_budget_exceeded_event(
        self,
        *,
        policy: WorkflowPolicy,
        requested_by: str,
        actor_intent_id: str,
        metadata: dict[str, Any],
    ) -> None:
        if self._ledger_writer is None:
            return
        self._ledger_writer.write(
            event_type="execution.budget_exceeded",
            actor="scheduler:budgeted-workflow-scheduler",
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            metadata={"requested_by": requested_by, **metadata},
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

    def _write_idempotent_hit_event(
        self,
        *,
        policy: WorkflowPolicy,
        actor_intent_id: str,
        requested_by: str,
        record: Any,
    ) -> None:
        if self._ledger_writer is None:
            return
        self._ledger_writer.write(
            event_type="execution.idempotent_hit",
            actor="scheduler:budgeted-workflow-scheduler",
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=policy.workflow_id,
            receipt=record.result,
            metadata={
                "requested_by": requested_by,
                "idempotency_key": record.idempotency_key,
                "original_actor_intent_id": record.actor_intent_id,
                "original_job_id": record.windmill_job_id,
                "completed_at": record.completed_at,
            },
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
    def _queue_requested(intent: Any) -> bool:
        return bool(getattr(intent, "queue_if_conflicted", False))

    @staticmethod
    def _queue_priority(intent: Any) -> int | None:
        value = getattr(intent, "queue_priority", None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
        return None

    @staticmethod
    def _queue_notify_channel(intent: Any) -> str | None:
        value = getattr(intent, "queue_notify_channel", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _queue_expiry_seconds(intent: Any, policy: WorkflowPolicy) -> int:
        for field in ("queue_expires_in_seconds", "queue_ttl_seconds"):
            value = getattr(intent, field, None)
            if isinstance(value, int) and value > 0:
                return value
            if isinstance(value, str) and value.strip().isdigit():
                return max(int(value.strip()), 1)
        return max(policy.budget.max_duration_seconds * 3, 900)

    @staticmethod
    def _released_resource_hints(resource_claims: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        hints: list[str] = []
        for claim in resource_claims:
            if not isinstance(claim, dict):
                continue
            resource = str(claim.get("resource", "")).strip()
            if not resource or resource in seen:
                continue
            seen.add(resource)
            hints.append(resource)
        return hints

    def _required_lanes(self, intent: Any) -> list[str]:
        value = getattr(intent, "required_lanes", None)
        if isinstance(value, list):
            normalized = [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]
            if normalized:
                return normalized
        resolution = resolve_lanes(intent, repo_root=self._repo_root)
        return list(resolution.required_lanes)

    def dispatch_queued(self, *, max_dispatches: int = 10) -> dict[str, Any]:
        queued_entries = self._lane_registry.lease_dispatchable(max_items=max_dispatches)
        dispatched: list[dict[str, Any]] = []
        for entry in queued_entries:
            payload = dict(entry.intent_payload)
            payload["id"] = payload.get("id") or entry.actor_intent_id
            payload["intent_id"] = payload.get("intent_id") or entry.actor_intent_id
            payload["required_lanes"] = list(entry.required_lanes)
            intent = SimpleNamespace(**payload)
            lane_lease = LaneLease(
                actor_intent_id=entry.actor_intent_id,
                primary_lane_id=entry.primary_lane_id,
                required_lanes=entry.required_lanes,
                leased_at=entry.queued_at,
                expires_at=entry.expires_at,
            )
            try:
                result = self.submit(
                    intent,
                    requested_by=entry.requested_by,
                    autonomous=entry.autonomous,
                    wait_for_completion=False,
                    queue_if_lane_unavailable=False,
                    lane_lease=lane_lease,
                )
            except Exception as exc:
                self._lane_registry.release(entry.actor_intent_id)
                dispatched.append(
                    {
                        "actor_intent_id": entry.actor_intent_id,
                        "primary_lane_id": entry.primary_lane_id,
                        "status": "dispatch_failed",
                        "error": str(exc),
                    }
                )
                continue
            dispatched.append(
                {
                    "actor_intent_id": entry.actor_intent_id,
                    "primary_lane_id": entry.primary_lane_id,
                    "status": result.status,
                    "job_id": result.job_id,
                }
            )
        return {
            "queued_examined": len(queued_entries),
            "dispatched": dispatched,
            "lane_state": self._lane_registry.snapshot(),
        }

    def _write_queue_terminal_event(
        self,
        *,
        event_type: str,
        actor_intent_id: str,
        workflow_id: str,
        requested_by: str,
        queue_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._ledger_writer is None:
            return
        payload = {"queue_id": queue_id}
        if metadata:
            payload.update(metadata)
        self._ledger_writer.write(
            event_type=event_type,
            actor=requested_by,
            actor_intent_id=actor_intent_id,
            target_kind="workflow",
            target_id=workflow_id,
            metadata=payload,
        )

    def _enqueue_intent(
        self,
        *,
        intent: Any,
        policy: WorkflowPolicy,
        actor_intent_id: str,
        requested_by: str,
        autonomous: bool,
        reason: str,
        last_conflict: str | None = None,
    ) -> SchedulerResult:
        queue_intent = SimpleNamespace(
            actor_intent_id=actor_intent_id,
            id=actor_intent_id,
            intent_id=actor_intent_id,
            workflow_id=getattr(intent, "workflow_id", policy.workflow_id),
            arguments=getattr(intent, "arguments", {}) or {},
            target_service_id=getattr(intent, "target_service_id", None),
            target_vm=getattr(intent, "target_vm", None),
            resource_claims=getattr(intent, "resource_claims", None),
            required_read_surfaces=getattr(intent, "required_read_surfaces", []),
            risk_class=getattr(intent, "risk_class", None),
            final_risk_class=getattr(intent, "final_risk_class", None),
            queue_if_conflicted=True,
            queue_priority=getattr(intent, "queue_priority", None),
            queue_expires_in_seconds=getattr(intent, "queue_expires_in_seconds", None),
            queue_notify_channel=getattr(intent, "queue_notify_channel", None),
        )
        queued = self._intent_queue_store.enqueue(
            queue_intent,
            requested_by=requested_by,
            autonomous=autonomous,
            expires_in_seconds=self._queue_expiry_seconds(queue_intent, policy),
            priority=self._queue_priority(queue_intent),
            last_conflict=last_conflict or reason,
            notify_channel=self._queue_notify_channel(queue_intent),
        )
        position = self._intent_queue_store.position_for(queued.queue_id)
        stats = self._intent_queue_store.stats()
        self._write_queued_event(
            policy=policy,
            actor_intent_id=actor_intent_id,
            requested_by=requested_by,
            queue_id=queued.queue_id,
            position=position,
            reason=reason,
            queued_at=queued.queued_at,
            expires_at=queued.expires_at,
            priority=queued.priority,
            metadata={"queue_depth": stats.get("depth")},
        )
        return SchedulerResult(
            status="queued",
            workflow_id=policy.workflow_id,
            actor_intent_id=actor_intent_id,
            reason=reason,
            budget=policy.budget.as_dict(),
            metadata={
                "queue_id": queued.queue_id,
                "queue_position": position,
                "queue_depth": stats.get("depth"),
                "priority": queued.priority,
                "queued_at": queued.queued_at,
                "expires_at": queued.expires_at,
            },
        )

    def _spawn_queue_dispatcher(
        self,
        *,
        resource_hints: list[str],
        workflow_hints: list[str],
        max_items: int = 5,
    ) -> None:
        script_path = self._repo_root / "scripts" / "intent_queue_dispatcher.py"
        if not script_path.exists():
            return
        command = [sys.executable, str(script_path), "--repo-root", str(self._repo_root), "--max-items", str(max_items)]
        for hint in resource_hints:
            if hint:
                command.extend(["--resource-hint", hint])
        for hint in workflow_hints:
            if hint:
                command.extend(["--workflow-hint", hint])
        try:
            subprocess.Popen(
                command,
                cwd=self._repo_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            return

    def drain_queued_intents(
        self,
        *,
        resource_hints: list[str] | None = None,
        workflow_hints: list[str] | None = None,
        max_items: int = 5,
    ) -> dict[str, Any]:
        expired = self._intent_queue_store.expire_waiting()
        for item in expired:
            self._write_queue_terminal_event(
                event_type="intent.expired",
                actor_intent_id=item.actor_intent_id,
                workflow_id=item.workflow_id,
                requested_by=item.requested_by,
                queue_id=item.queue_id,
                metadata={
                    "expires_at": item.expires_at,
                    "queued_at": item.queued_at,
                    "reason": item.last_conflict or "queue TTL exceeded",
                },
            )

        claimed = self._intent_queue_store.claim_ready(
            resource_hints=resource_hints,
            workflow_hints=workflow_hints,
            limit=max(max_items, 1),
        )
        dispatched: list[dict[str, Any]] = []
        for item in claimed:
            try:
                result = self.submit(
                    item.as_scheduler_intent(),
                    requested_by=item.requested_by,
                    autonomous=item.autonomous,
                    from_queue=True,
                )
            except Exception as exc:
                self._intent_queue_store.requeue(item.queue_id, reason=str(exc))
                dispatched.append(
                    {
                        "queue_id": item.queue_id,
                        "workflow_id": item.workflow_id,
                        "status": "requeued",
                        "reason": str(exc),
                    }
                )
                continue

            if result.status in {"concurrency_limit", "conflict_rejected"}:
                self._intent_queue_store.requeue(item.queue_id, reason=result.reason or result.status)
                dispatched.append(
                    {
                        "queue_id": item.queue_id,
                        "workflow_id": item.workflow_id,
                        "status": "requeued",
                        "scheduler_status": result.status,
                        "reason": result.reason,
                    }
                )
                continue

            terminal_metadata = {
                "scheduler_status": result.status,
                "reason": result.reason,
                "job_id": result.job_id,
            }
            if result.metadata:
                terminal_metadata["scheduler_metadata"] = result.metadata
            self._intent_queue_store.mark_dispatched(
                item.queue_id,
                completion_status=result.status,
                metadata=terminal_metadata,
            )
            self._write_queue_terminal_event(
                event_type="intent.dispatched",
                actor_intent_id=item.actor_intent_id,
                workflow_id=item.workflow_id,
                requested_by=item.requested_by,
                queue_id=item.queue_id,
                metadata=terminal_metadata,
            )
            dispatched.append(
                {
                    "queue_id": item.queue_id,
                    "workflow_id": item.workflow_id,
                    "status": "dispatched",
                    "scheduler_status": result.status,
                    "job_id": result.job_id,
                }
            )

        return {
            "status": "ok",
            "expired_count": len(expired),
            "claimed_count": len(claimed),
            "results": dispatched,
            "queue": self._intent_queue_store.stats(),
        }

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

    @staticmethod
    def _idempotency_scope(intent: Any, arguments: dict[str, Any]) -> str | None:
        for attr in ("idempotency_scope", "trigger_ref", "nats_message_id"):
            value = getattr(intent, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("idempotency_scope", "trigger_ref", "nats_message_id"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _idempotency_target(intent: Any, arguments: dict[str, Any], policy: WorkflowPolicy) -> str:
        for attr in ("target_service_id", "target_vm"):
            value = getattr(intent, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("service_id", "service", "target_service", "target", "target_vm"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return policy.workflow_id

    def submit(
        self,
        intent: Any,
        *,
        requested_by: str = "operator:lv3-cli",
        autonomous: bool = False,
        wait_for_completion: bool = True,
        queue_if_lane_unavailable: bool = True,
        lane_lease: LaneLease | None = None,
        from_queue: bool = False,
    ) -> SchedulerResult:
        policy = load_workflow_policy(intent.workflow_id, repo_root=self._repo_root)
        requested_by = normalize_actor_id(requested_by)
        actor_intent_id = self._resolve_actor_intent_id(intent)
        arguments = getattr(intent, "arguments", {}) or {}
        parent_actor_intent_id = self._parent_actor_intent_id(arguments)
        host_touch_estimate = estimate_touched_hosts(intent, policy)
        risk_class = self._risk_class_for_submission(intent, policy)
        required_lanes = self._required_lanes(intent)
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
        idempotency_key = compute_idempotency_key(
            policy.workflow_id,
            self._idempotency_target(intent, arguments, policy),
            arguments,
            requested_by,
            exact_scope=self._idempotency_scope(intent, arguments),
        )
        idempotency_claim = self._idempotency_store.claim(
            idempotency_key=idempotency_key,
            workflow_id=policy.workflow_id,
            actor_id=requested_by,
            actor_intent_id=actor_intent_id,
            target_service_id=self._idempotency_target(intent, arguments, policy),
            metadata={"requested_by": requested_by},
        )
        if idempotency_claim.action == "completed":
            self._write_idempotent_hit_event(
                policy=policy,
                actor_intent_id=actor_intent_id,
                requested_by=requested_by,
                record=idempotency_claim.record,
            )
            return SchedulerResult(
                status="idempotent_hit",
                workflow_id=policy.workflow_id,
                job_id=idempotency_claim.record.windmill_job_id,
                actor_intent_id=actor_intent_id,
                output=idempotency_claim.record.result,
                budget=policy.budget.as_dict(),
                metadata={
                    "idempotency_key": idempotency_key,
                    "original_actor_intent_id": idempotency_claim.record.actor_intent_id,
                    "original_job_id": idempotency_claim.record.windmill_job_id,
                    "completed_at": idempotency_claim.record.completed_at,
                },
            )
        if idempotency_claim.action == "in_flight" and idempotency_claim.record.actor_intent_id != actor_intent_id:
            return SchedulerResult(
                status="in_flight",
                workflow_id=policy.workflow_id,
                job_id=idempotency_claim.record.windmill_job_id,
                actor_intent_id=actor_intent_id,
                budget=policy.budget.as_dict(),
                metadata={
                    "idempotency_key": idempotency_key,
                    "original_actor_intent_id": idempotency_claim.record.actor_intent_id,
                    "original_job_id": idempotency_claim.record.windmill_job_id,
                    "submitted_at": idempotency_claim.record.submitted_at,
                },
            )
        effective_wait_for_completion = wait_for_completion or speculative_requested
        intent_ttl_seconds = (
            policy.budget.max_duration_seconds
            + (policy.speculative.rollback_window_seconds if speculative_requested else 0)
            + 60
        )
        lock_token = None
        lane_decision = None
        lane_reservation_ttl = None
        registered_claim = False
        claim_closed = False
        release_lane_on_exit = False
        release_budget_on_exit = False
        released_resource_hints: list[str] = []
        released_workflow_hints: list[str] = []
        conflict_result: Any | None = None

        try:
            if policy.execution_class == "mutation":
                if lane_lease is not None:
                    release_lane_on_exit = True
                else:
                    lane_result = self._lane_registry.reserve(
                        intent,
                        actor_intent_id=actor_intent_id,
                        ttl_seconds=intent_ttl_seconds,
                    )
                    if lane_result.status == "busy":
                        if not queue_if_lane_unavailable:
                            self._idempotency_store.delete(idempotency_key)
                            return SchedulerResult(
                                status="lane_busy",
                                workflow_id=policy.workflow_id,
                                actor_intent_id=actor_intent_id,
                                reason=f"{lane_result.resolution.primary_lane_id} is at capacity",
                                budget=policy.budget.as_dict(),
                                metadata=lane_result.as_dict(),
                            )
                        queue_entry = self._lane_registry.enqueue(
                            intent,
                            actor_intent_id=actor_intent_id,
                            requested_by=requested_by,
                            ttl_seconds=intent_ttl_seconds,
                            autonomous=autonomous,
                        )
                        if queue_entry is None:
                            self._idempotency_store.delete(idempotency_key)
                            return SchedulerResult(
                                status="lane_busy",
                                workflow_id=policy.workflow_id,
                                actor_intent_id=actor_intent_id,
                                reason=f"{lane_result.resolution.primary_lane_id} is at capacity",
                                budget=policy.budget.as_dict(),
                                metadata=lane_result.as_dict(),
                            )
                        self._write_queued_event(
                            policy=policy,
                            actor_intent_id=actor_intent_id,
                            requested_by=requested_by,
                            queue_id=queue_entry.queue_id,
                            primary_lane_id=queue_entry.primary_lane_id,
                            required_lanes=list(queue_entry.required_lanes),
                        )
                        return SchedulerResult(
                            status="queued",
                            workflow_id=policy.workflow_id,
                            actor_intent_id=actor_intent_id,
                            reason=f"{queue_entry.primary_lane_id} is busy",
                            budget=policy.budget.as_dict(),
                            metadata={
                                "queue_id": queue_entry.queue_id,
                                "primary_lane_id": queue_entry.primary_lane_id,
                                "required_lanes": list(queue_entry.required_lanes),
                            },
                        )
                    release_lane_on_exit = lane_result.status == "acquired"

                if not speculative_requested:
                    lock_token = self._lock_manager.acquire(
                        policy.workflow_id,
                        max_instances=policy.budget.max_concurrent_instances,
                    )
                    if lock_token is None:
                        if self._queue_requested(intent) and not from_queue:
                            self._idempotency_store.delete(idempotency_key)
                            return self._enqueue_intent(
                                intent=intent,
                                policy=policy,
                                actor_intent_id=actor_intent_id,
                                requested_by=requested_by,
                                autonomous=autonomous,
                                reason="workflow busy",
                                last_conflict="concurrency_limit",
                            )
                        self._idempotency_store.delete(idempotency_key)
                        return SchedulerResult(
                            status="concurrency_limit",
                            workflow_id=policy.workflow_id,
                            actor_intent_id=actor_intent_id,
                            reason="workflow busy",
                            budget=policy.budget.as_dict(),
                        )

                lane = resolve_execution_lane(
                    intent,
                    workflow=policy.workflow,
                    repo_root=self._repo_root,
                )
                if lane is not None and policy.resource_reservation is not None:
                    lane_reservation_ttl = max(1, policy.resource_reservation.estimated_duration_seconds * 2)
                    lane_decision = self._lane_budget_store.reserve(
                        lane=lane,
                        reservation=policy.resource_reservation,
                        actor_intent_id=actor_intent_id,
                        workflow_id=policy.workflow_id,
                        requested_by=requested_by,
                        ttl_seconds=lane_reservation_ttl,
                    )
                    if not lane_decision.allowed:
                        metadata = lane_decision.as_dict()
                        self._write_budget_exceeded_event(
                            policy=policy,
                            requested_by=requested_by,
                            actor_intent_id=actor_intent_id,
                            metadata={"reason": "lane_budget_exceeded", **metadata},
                        )
                        self._idempotency_store.delete(idempotency_key)
                        return SchedulerResult(
                            status="budget_exceeded",
                            workflow_id=policy.workflow_id,
                            actor_intent_id=actor_intent_id,
                            reason="lane_budget_exceeded",
                            budget=policy.budget.as_dict(),
                            metadata=metadata,
                        )
                    release_budget_on_exit = True

            conflict_result = self._conflict_registry.register_intent(
                intent,
                actor_intent_id=actor_intent_id,
                actor=requested_by,
                ttl_seconds=intent_ttl_seconds,
                allow_conflicts=speculative_requested,
            )
            if conflict_result.status == "conflict":
                if self._queue_requested(intent) and not speculative_requested and not from_queue:
                    self._idempotency_store.delete(idempotency_key)
                    return self._enqueue_intent(
                        intent=intent,
                        policy=policy,
                        actor_intent_id=actor_intent_id,
                        requested_by=requested_by,
                        autonomous=autonomous,
                        reason=conflict_result.message,
                        last_conflict="conflict_rejected",
                    )
                self._idempotency_store.delete(idempotency_key)
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
                self._idempotency_store.delete(idempotency_key)
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
            released_resource_hints = self._released_resource_hints(
                [claim.as_dict() for claim in conflict_result.resource_claims]
            )
            released_workflow_hints = [policy.workflow_id]
            if autonomous:
                self._daily_execution_counter.increment(requested_by)
            self._write_claim_registered_event(
                policy=policy,
                actor_intent_id=actor_intent_id,
                requested_by=requested_by,
                resource_claims=[claim.as_dict() for claim in conflict_result.resource_claims],
                warnings=[warning.as_dict() for warning in conflict_result.warnings],
                required_lanes=required_lanes,
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
                arguments,
                timeout_seconds=policy.budget.max_duration_seconds if policy.execution_class == "mutation" else None,
            )
            job_id = submission.get("job_id")
            if job_id:
                self._idempotency_store.attach_job_id(idempotency_key, str(job_id))
            self._write_started_event(
                policy=policy,
                requested_by=requested_by,
                actor_intent_id=actor_intent_id,
                parent_actor_intent_id=parent_actor_intent_id,
                job_id=str(job_id) if job_id else None,
                host_touch_estimate=host_touch_estimate,
                execution_mode="speculative" if speculative_requested else "pessimistic",
                lane_reservation=lane_decision.as_dict() if lane_decision is not None else None,
            )

            if not job_id:
                status = "completed" if submission.get("success", True) else "failed"
                self._idempotency_store.complete(
                    idempotency_key,
                    status=status,
                    result=submission.get("result"),
                )
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
                        "required_lanes": required_lanes,
                        "lane_budget": lane_decision.as_dict() if lane_decision is not None else None,
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
                    "required_lanes": required_lanes,
                    "lane_reservation_ttl_seconds": lane_reservation_ttl,
                },
            )
            self._state_store.upsert(active_job)
            if not effective_wait_for_completion:
                registered_claim = False
                release_lane_on_exit = False
                release_budget_on_exit = False
                return SchedulerResult(
                    status="submitted",
                    workflow_id=policy.workflow_id,
                    job_id=str(job_id),
                    actor_intent_id=actor_intent_id,
                    budget=policy.budget.as_dict(),
                    metadata={
                        "required_lanes": required_lanes,
                        "conflict_warnings": [warning.as_dict() for warning in conflict_result.warnings],
                        "lane_budget": lane_decision.as_dict() if lane_decision is not None else None,
                    },
                )

            while True:
                if lane_decision is not None and lane_reservation_ttl is not None:
                    self._lane_budget_store.renew(actor_intent_id, ttl_seconds=lane_reservation_ttl)
                status = self._windmill_client.get_job(str(job_id))
                violation = self._watchdog.evaluate(active_job, status)
                if violation is not None and not violation.advisory_only:
                    payload = self._watchdog.handle_violation(active_job, status, violation, now=datetime.now(UTC))
                    self._idempotency_store.complete(
                        idempotency_key,
                        status="budget_exceeded",
                        result=status.get("result"),
                        job_id=str(job_id),
                    )
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
                    self._idempotency_store.complete(
                        idempotency_key,
                        status=final_status,
                        result=status.get("result"),
                        job_id=str(job_id),
                    )
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
                            "required_lanes": required_lanes,
                            "lane_budget": lane_decision.as_dict() if lane_decision is not None else None,
                        },
                    )
                self._sleep(self._poll_interval_seconds)
        finally:
            if registered_claim and not claim_closed:
                self._conflict_registry.complete_intent(actor_intent_id, status="aborted")
            if release_budget_on_exit and lane_decision is not None:
                self._lane_budget_store.release(actor_intent_id)
            if release_lane_on_exit:
                self._lane_registry.release(actor_intent_id)
            if lock_token is not None:
                lock_token.release()
                if policy.workflow_id not in released_workflow_hints:
                    released_workflow_hints.append(policy.workflow_id)
            if released_resource_hints or released_workflow_hints:
                self._spawn_queue_dispatcher(
                    resource_hints=released_resource_hints,
                    workflow_hints=released_workflow_hints,
                )


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
